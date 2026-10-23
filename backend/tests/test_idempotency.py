"""聊天轮次防重放与报告任务并发去重测试（不依赖真实 Redis/PG）。"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sse_starlette.sse import EventSourceResponse

import app.core.turn_idempotency as ti
from app.api import xianzhi_chat as chat_mod, xianzhi_report
from app.core.http.errors import validate_client_msg_id
from app.core.turn_idempotency import (
    STATUS_DONE,
    STATUS_NEW,
    STATUS_RUNNING,
    TurnState,
)
from app.db import report_tasks as rt

VALID_CID = "web-xianzhi-550e8400-e29b-41d4-a716-446655440000"
MID = "client-msg-0001"


@pytest.fixture(autouse=True)
def _clear_local_turns():
    ti._local.clear()
    yield
    ti._local.clear()


def test_validate_client_msg_id_optional_and_bounded() -> None:
    assert validate_client_msg_id(None) == ""
    assert validate_client_msg_id(MID) == MID
    for bad in ("short", "bad id with spaces", "x" * 65):
        with pytest.raises(HTTPException) as exc:
            validate_client_msg_id(bad)
        assert exc.value.status_code == 400


class _FakeRedis:
    """只实现防重放用到的 set/get/eval。"""

    def __init__(self):
        self.data: dict[str, str] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def get(self, key):
        return self.data.get(key)

    async def eval(self, script, numkeys, key):
        if self.data.get(key) == STATUS_RUNNING:
            self.data.pop(key, None)
        return 0


def _patch_redis(monkeypatch, redis):
    async def _get():
        return redis

    monkeypatch.setattr(ti, "get_redis", _get)


def test_turn_lifecycle_new_running_done_replay(monkeypatch) -> None:
    fake = _FakeRedis()
    _patch_redis(monkeypatch, fake)

    assert asyncio.run(ti.begin_turn(VALID_CID, MID, "u1")).status == STATUS_NEW
    # 第二个并发请求：正在处理
    assert asyncio.run(ti.begin_turn(VALID_CID, MID, "u1")).status == STATUS_RUNNING

    asyncio.run(ti.complete_turn(VALID_CID, MID, "u1", "缓存答案"))
    state = asyncio.run(ti.begin_turn(VALID_CID, MID, "u1"))
    assert state.status == STATUS_DONE
    assert state.answer == "缓存答案"


def test_turn_release_only_removes_running(monkeypatch) -> None:
    fake = _FakeRedis()
    _patch_redis(monkeypatch, fake)

    asyncio.run(ti.begin_turn(VALID_CID, MID, "u1"))
    asyncio.run(ti.release_turn(VALID_CID, MID, "u1"))
    assert asyncio.run(ti.begin_turn(VALID_CID, MID, "u1")).status == STATUS_NEW

    asyncio.run(ti.complete_turn(VALID_CID, MID, "u1", "答案"))
    asyncio.run(ti.release_turn(VALID_CID, MID, "u1"))
    assert asyncio.run(ti.begin_turn(VALID_CID, MID, "u1")).status == STATUS_DONE


def test_turn_id_scoped_by_conversation_and_user(monkeypatch) -> None:
    _patch_redis(monkeypatch, _FakeRedis())

    asyncio.run(ti.begin_turn(VALID_CID, MID, "u1"))
    assert asyncio.run(ti.begin_turn(VALID_CID, MID, "u2")).status == STATUS_NEW
    assert asyncio.run(ti.begin_turn(VALID_CID + "x", MID, "u1")).status == STATUS_NEW


def test_turn_falls_back_to_local_when_redis_absent(monkeypatch) -> None:
    async def _none():
        return None

    monkeypatch.setattr(ti, "get_redis", _none)

    assert asyncio.run(ti.begin_turn(VALID_CID, MID, "u1")).status == STATUS_NEW
    assert asyncio.run(ti.begin_turn(VALID_CID, MID, "u1")).status == STATUS_RUNNING
    asyncio.run(ti.complete_turn(VALID_CID, MID, "u1", "本地答案"))
    state = asyncio.run(ti.begin_turn(VALID_CID, MID, "u1"))
    assert state.status == STATUS_DONE
    assert state.answer == "本地答案"


def _patch_chat_repo(monkeypatch) -> None:
    async def _get_by_token(token):
        return {"id": token} if token else None

    async def _ensure(cid, uid):
        return True

    monkeypatch.setattr(chat_mod.repo, "get_by_token", _get_by_token)
    monkeypatch.setattr(chat_mod.repo, "ensure_session_owner", _ensure)


class _Ctx:
    def get_xianzhi(self, cid):
        return object(), asyncio.Lock()


class _FakeAgent:
    """只实现 SSE 路径会用到的属性/方法。"""

    def __init__(self):
        self._sect = 2
        self._yun_sect = 1
        self._user_id = ""

    async def arun_stream(self, message, verbose=False):
        yield "新回答"

    def set_turn_id(self, turn_id):
        self._turn_id = turn_id

    def set_chart_notifier(self, fn):
        pass

    def set_progress_notifier(self, fn):
        pass


class _CtxWithAgent(_Ctx):
    def get_xianzhi(self, cid):
        return _FakeAgent(), asyncio.Lock()


def test_sse_hung_running_key_re_executes(monkeypatch) -> None:
    """锁内拿到 running 只可能是进程崩溃留下的悬挂键：按新轮次执行，不能永久卡住用户。"""
    _patch_chat_repo(monkeypatch)

    async def _running(*a, **k):
        return TurnState(STATUS_RUNNING)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(chat_mod, "begin_turn", _running)
    monkeypatch.setattr(chat_mod, "complete_turn", _noop)
    monkeypatch.setattr(chat_mod, "release_turn", _noop)
    monkeypatch.setattr(chat_mod, "_mount_chart_context", lambda *a, **k: None)

    resp = asyncio.run(
        chat_mod.chat_with_xianzhi(
            message="hi",
            conversation_id=VALID_CID,
            token="user-a",
            client_msg_id=MID,
            app_ctx=_CtxWithAgent(),
        )
    )

    async def _collect():
        return [item async for item in resp.body_iterator]

    events = asyncio.run(_collect())
    assert {"event": "message", "data": "新回答"} in events
    assert events[-1] == {"event": "message", "data": "[DONE]"}


def test_sse_duplicate_done_replays_answer(monkeypatch) -> None:
    _patch_chat_repo(monkeypatch)

    async def _done(*a, **k):
        return TurnState(STATUS_DONE, "已生成的回答")

    monkeypatch.setattr(chat_mod, "begin_turn", _done)
    resp = asyncio.run(
        chat_mod.chat_with_xianzhi(
            message="hi",
            conversation_id=VALID_CID,
            token="user-a",
            client_msg_id=MID,
            app_ctx=_Ctx(),
        )
    )
    assert isinstance(resp, EventSourceResponse)

    async def _collect():
        return [item async for item in resp.body_iterator]

    events = asyncio.run(_collect())
    assert events == [
        {"event": "message", "data": "已生成的回答"},
        {"event": "message", "data": "[DONE]"},
    ]


# ---------------- 报告任务：并发查重 ----------------
class _Tx:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Conn:
    def __init__(self, rows):
        self._rows = list(rows)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def transaction(self):
        return _Tx()

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def connection(self):
        return self._conn


def test_get_or_create_task_uses_transactional_advisory_lock(monkeypatch) -> None:
    conn = _Conn([None, ("task-new", "pending")])
    monkeypatch.setattr(rt, "get_pool", lambda: _Pool(conn))

    task_id, status, created = rt.get_or_create_task("basic_report", {"gender": "男", "birth_time": "x"}, "u1")

    assert (task_id, status, created) == ("task-new", "pending", True)
    assert "pg_advisory_xact_lock" in conn.calls[0][0]
    assert any("INSERT INTO report_tasks" in sql for sql, _p in conn.calls)


def test_get_or_create_task_reuses_existing_without_insert(monkeypatch) -> None:
    conn = _Conn([("task-old", "running")])
    monkeypatch.setattr(rt, "get_pool", lambda: _Pool(conn))

    task_id, status, created = rt.get_or_create_task("basic_report", {"birth_time": "x", "gender": "男"}, "u1")

    assert (task_id, status, created) == ("task-old", "running", False)
    assert not any("INSERT INTO report_tasks" in sql for sql, _p in conn.calls)


def test_submit_report_task_does_not_enqueue_race_loser(monkeypatch) -> None:
    import app.core.redis_client as redis_mod
    import app.tasks.worker as worker

    async def _quota(*a, **k):
        return True

    async def _allow(*a, **k):
        return True

    async def _enqueue(task_id):
        raise AssertionError(f"竞态失败方不应入队: {task_id}")

    monkeypatch.setattr(xianzhi_report, "enforce_quota", _quota)
    monkeypatch.setattr(xianzhi_report, "client_ip_from_request", lambda r: "1.2.3.4")
    monkeypatch.setattr(redis_mod, "rate_limit_allow", _allow)
    monkeypatch.setattr(rt, "find_same_task", lambda *a, **k: None)
    monkeypatch.setattr(rt, "delete_old", lambda *a, **k: None)
    monkeypatch.setattr(rt, "get_or_create_task", lambda *a, **k: ("task-old", "running", False))
    monkeypatch.setattr(worker, "enqueue", _enqueue)

    out = asyncio.run(
        xianzhi_report.submit_report_task(
            {"kind": "basic_report", "birth_time": "1990-05-20 14:30", "gender": "男"},
            request=object(),
            principal={"id": "u1"},
        )
    )

    assert out == {"task_id": "task-old", "status": "running"}


def _patch_submit_common(monkeypatch, create_result):
    import app.core.redis_client as redis_mod

    async def _allow(*a, **k):
        return True

    monkeypatch.setattr(xianzhi_report, "client_ip_from_request", lambda r: "1.2.3.4")
    monkeypatch.setattr(redis_mod, "rate_limit_allow", _allow)
    monkeypatch.setattr(rt, "find_same_task", lambda *a, **k: None)
    monkeypatch.setattr(rt, "delete_old", lambda *a, **k: None)
    monkeypatch.setattr(rt, "get_or_create_task", lambda *a, **k: create_result)


def test_submit_report_task_enqueues_only_created_task(monkeypatch) -> None:
    import app.tasks.worker as worker

    _patch_submit_common(monkeypatch, ("task-new", "pending", True))

    async def _quota(*a, **k):
        return True

    enqueued = []

    async def _enqueue(task_id):
        enqueued.append(task_id)

    monkeypatch.setattr(xianzhi_report, "enforce_quota", _quota)
    monkeypatch.setattr(worker, "enqueue", _enqueue)

    out = asyncio.run(
        xianzhi_report.submit_report_task(
            {"kind": "basic_report", "birth_time": "1990-05-20 14:30", "gender": "男"},
            request=object(),
            principal={"id": "u1"},
        )
    )

    assert out == {"task_id": "task-new", "status": "pending"}
    assert enqueued == ["task-new"]


def test_submit_report_task_quota_failure_rolls_back(monkeypatch) -> None:
    _patch_submit_common(monkeypatch, ("task-new", "pending", True))

    async def _quota(*a, **k):
        raise HTTPException(status_code=429, detail="配额已用完")

    deleted = []
    monkeypatch.setattr(xianzhi_report, "enforce_quota", _quota)
    monkeypatch.setattr(rt, "delete_task", lambda task_id: deleted.append(task_id))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            xianzhi_report.submit_report_task(
                {"kind": "basic_report", "birth_time": "1990-05-20 14:30", "gender": "男"},
                request=object(),
                principal={"id": "u1"},
            )
        )

    assert exc.value.status_code == 429
    assert deleted == ["task-new"], "配额拒绝必须回滚刚建的 pending 任务"
