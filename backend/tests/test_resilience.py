"""故障注入：Redis / LLM / 报告队列不可用时的降级行为。"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import app.core.redis_client as redis_client
import app.tasks.worker as worker
from app.agent.xianzhi import Xianzhi
from app.core.config import settings
from app.core.llm_failover import ModelUnavailableError
from app.core.security import RateLimitMiddleware

pytestmark = pytest.mark.chaos


class _FakeApp:
    def __init__(self):
        self.calls = 0

    async def __call__(self, scope, receive, send):
        self.calls += 1
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def test_rate_limit_falls_back_to_local_when_redis_unavailable(monkeypatch):
    async def _redis_none(*args, **kwargs):
        return None

    monkeypatch.setattr(redis_client, "rate_limit_allow", _redis_none)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    app = _FakeApp()
    middleware = RateLimitMiddleware(app)
    scope = {"type": "http", "path": "/unit-test", "headers": [], "client": ("127.0.0.1", 1234)}
    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request"}

    async def main():
        for _ in range(3):
            await middleware(scope, receive, send)

    asyncio.run(main())

    assert app.calls == 2, "前两次应在 Redis 不可用时走本地窗口放行"
    assert any(m.get("status") == 429 for m in sent), "第三次应被本地滑动窗口拦截"


def test_report_enqueue_fails_closed_without_redis(monkeypatch):
    async def _no_redis():
        return None

    monkeypatch.setattr(worker, "get_redis", _no_redis)
    with pytest.raises(RuntimeError):
        asyncio.run(worker.enqueue("task-unit-test"))


def test_requeue_pending_skips_without_redis(monkeypatch):
    async def _no_redis():
        return None

    listed: list[int] = []

    def _list_pending(limit=500):
        listed.append(limit)
        return ["task-1"]

    monkeypatch.setattr(worker, "get_redis", _no_redis)
    monkeypatch.setattr(worker.report_tasks, "list_pending", _list_pending)

    assert asyncio.run(worker.requeue_pending()) == 0
    assert listed == [], "Redis 不可用时不查库、也不假装入队"


class _FakeRedisQueue:
    def __init__(self, queued: list[str] | None = None):
        self.queue = list(queued or [])
        self.ops: list[tuple[str, str]] = []

    async def lrem(self, key, count, value):
        self.ops.append(("lrem", value))
        self.queue = [x for x in self.queue if x != value]
        return 1

    async def lpush(self, key, value):
        self.ops.append(("lpush", value))
        self.queue.insert(0, value)


def test_requeue_pending_dedupes_then_pushes(monkeypatch):
    fake = _FakeRedisQueue(["task-1"])  # task-1 已在队列中（未被消费）

    async def _redis():
        return fake

    monkeypatch.setattr(worker, "get_redis", _redis)
    monkeypatch.setattr(worker.report_tasks, "list_pending", lambda limit=500: ["task-1", "task-2"])

    assert asyncio.run(worker.requeue_pending()) == 2
    assert fake.ops == [
        ("lrem", "task-1"),
        ("lpush", "task-1"),
        ("lrem", "task-2"),
        ("lpush", "task-2"),
    ]
    assert sorted(fake.queue) == ["task-1", "task-2"]
    assert fake.queue.count("task-1") == 1, "重复消息必须先被 LREM 去重"


def test_reconcile_after_restart_only_fails_running(monkeypatch):
    """pending 不再被判失败：启动时改为重新入队，避免取号后崩溃的任务永久卡住。"""
    import contextlib

    import app.db.report_tasks as report_tasks

    class _Conn:
        def __init__(self):
            self.sqls: list[str] = []

        def execute(self, sql, params=None):
            self.sqls.append(sql)
            return self

    class _Pool:
        def __init__(self, conn):
            self.conn = conn

        def connection(self):
            return contextlib.nullcontext(self.conn)

    conn = _Conn()
    monkeypatch.setattr(report_tasks, "get_pool", lambda: _Pool(conn))

    report_tasks.reconcile_after_restart()

    joined = "\n".join(conn.sqls)
    assert "status = 'running'" in joined
    assert "任务超时未执行" not in joined


def test_workflow_all_models_down_returns_friendly_error():
    with patch("app.agent.xianzhi.create_chat_memory") as m:
        m.return_value = MagicMock()
        agent = Xianzhi(chat_model=MagicMock(), local_tools=[])

    def _boom(*args, **kwargs):
        raise ModelUnavailableError("降级链全部模型均不可用")

    agent._execute_workflow = _boom
    agent._get_session_summary = lambda: ""
    agent._persist_history = lambda: None

    chunks = list(agent._workflow_stream("问题"))

    assert chunks[-1] == "分析过程遇到错误，请稍后重试。"
