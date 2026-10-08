"""命盘上下文「挂载即通知 + 会话级落库」回归测试（不联网、不依赖真实 PG）。

背景（2026-09-15）：小程序端"八字信息经常丢失"。根因两条——
1. 通知（chart_context）排在整轮回答**之后**且以 client_alive 为条件：
   生成 29s 后 socket 已断 → 回答发送失败 → 通知被静默跳过（日志实证）；
   客户端顶栏因此一直是"点击设置出生信息"。
2. 出生信息只活在 agent 实例内存里，PG 侧恢复只从 message_store 的 tool_calls 里翻，
   而正则直接挂的盘不产生 tool_calls → 重启/换会话就查不回来。

本模块钉死修好后的行为：
① 挂盘那一刻就回调（不等回答），同一轮同盘去重、跨轮重新通知；
② 回调抛异常不得影响挂盘本身；
③ 线程安全桥 make_chart_notifier 把工作线程事件转投到事件循环；
④ 出生信息按会话落库，同一张盘只写一次，写库失败不影响回答。
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock, patch

from app.agent.xianzhi import Xianzhi
from app.api.xianzhi import make_chart_notifier

MALE = "男"


def _agent(monkeypatch) -> Xianzhi:
    """构造不触达 PG 的 agent（记忆层用 MagicMock）。"""
    with patch("app.agent.xianzhi.create_chat_memory") as m:
        m.return_value = MagicMock()
        agent = Xianzhi(chat_model=MagicMock(), local_tools=[])
    agent.set_conversation_id("test-notify")
    return agent


# ---------------- ① 挂载即通知 ----------------
def test_notifier_fires_on_mount(monkeypatch):
    agent = _agent(monkeypatch)
    seen: list[dict] = []
    agent.set_chart_notifier(seen.append)

    agent.set_chart_context("2004-06-22 08:00", MALE, birth_place="")

    assert len(seen) == 1
    assert seen[0]["time"] == "2004-06-22 08:00"
    assert seen[0]["gender"] == MALE


def test_notifier_dedupes_same_chart_within_turn(monkeypatch):
    """同一轮里 payload 挂载 + 正文挂载是同一张盘 → 只通知一次。"""
    agent = _agent(monkeypatch)
    seen: list[dict] = []
    agent.set_chart_notifier(seen.append)

    agent.set_chart_context("2005-09-28 18:00", MALE)
    agent.set_chart_context("2005-09-28 18:00", MALE)

    assert len(seen) == 1


def test_notifier_rearms_after_reset(monkeypatch):
    """新一轮（reset）之后同一张盘要再通知一次：客户端可能刚重建页面。"""
    agent = _agent(monkeypatch)
    seen: list[dict] = []
    agent.set_chart_notifier(seen.append)

    agent.set_chart_context("2005-09-28 18:00", MALE)
    agent.reset()
    agent.set_chart_context("2005-09-28 18:00", MALE)

    assert len(seen) == 2


def test_notifier_error_does_not_break_mount(monkeypatch):
    agent = _agent(monkeypatch)

    def boom(_info):
        raise RuntimeError("client gone")

    agent.set_chart_notifier(boom)
    agent.set_chart_context("2004-06-22 08:00", MALE)  # 不得抛出

    assert agent._last_birth_info["time"] == "2004-06-22 08:00"
    assert agent.chart_context  # 命盘上下文照常挂上


def test_no_notifier_is_fine(monkeypatch):
    agent = _agent(monkeypatch)
    agent.set_chart_context("2004-06-22 08:00", MALE)
    assert agent._last_birth_info["gender"] == MALE


# ---------------- ③ 线程安全桥 ----------------
def test_make_chart_notifier_bridges_from_worker_thread():
    """挂盘发生在 asyncio.to_thread 里：回调必须仍在事件循环线程上被执行。"""
    results: list[tuple] = []

    async def main():
        loop = asyncio.get_running_loop()
        notify = make_chart_notifier(
            loop, lambda p: results.append((threading.current_thread().name, p))
        )

        def worker():
            notify({"time": "2004-06-22 08:00", "gender": MALE, "place": "成都"})

        t = threading.Thread(target=worker, name="agent-worker")
        t.start()
        t.join()
        await asyncio.sleep(0.05)  # 等 call_soon_threadsafe 落地

    asyncio.run(main())

    assert results, "工作线程发出的通知必须被转投到事件循环"
    thread_name, payload = results[0]
    assert thread_name != "agent-worker", "push 必须在事件循环线程执行，不能原地发送"
    assert payload == {"birth_time": "2004-06-22 08:00", "gender": MALE, "birth_place": "成都"}


def test_make_chart_notifier_skips_incomplete_payload():
    pushed: list[dict] = []
    loop = asyncio.new_event_loop()
    try:
        notify = make_chart_notifier(loop, pushed.append)
        notify({})  # 缺 time/gender
        notify({"time": "2004-06-22 08:00"})  # 缺 gender
        loop.run_until_complete(asyncio.sleep(0.01))
    finally:
        loop.close()
    assert pushed == []


# ---------------- ④ 出生信息落库 ----------------
def test_persist_birth_info_writes_once_per_chart(monkeypatch):
    agent = _agent(monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(
        "app.memory.postgres_memory.upsert_session_birth_info",
        lambda *a, **k: calls.append(a),
    )
    agent.set_chart_context("2005-09-28 18:00", MALE, birth_place="成都")

    agent._persist_birth_info()
    agent._persist_birth_info()  # 同一张盘不重复写

    assert len(calls) == 1
    assert calls[0][0] == "test-notify" and calls[0][1] == "2005-09-28 18:00" and calls[0][2] == MALE


def test_persist_birth_info_noop_without_chart(monkeypatch):
    agent = _agent(monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(
        "app.memory.postgres_memory.upsert_session_birth_info",
        lambda *a, **k: calls.append(a),
    )
    agent._persist_birth_info()
    assert calls == []


def test_persist_birth_info_swallows_db_error(monkeypatch):
    """写库失败只告警，不能把 cleanup（进而整轮回答落盘）带崩。"""
    agent = _agent(monkeypatch)
    agent.set_chart_context("2004-06-22 08:00", MALE)

    def boom(*a, **k):
        raise RuntimeError("pg down")

    monkeypatch.setattr("app.memory.postgres_memory.upsert_session_birth_info", boom)
    agent._persist_birth_info()  # 不得抛出

    # 失败不置位 → 下一轮仍会重试落库
    assert agent._birth_persisted_key is None


def test_persist_birth_info_carries_user_id(monkeypatch):
    """落库要带会话归属用户：payload 挂载传 uid，正则挂载不传也不能把它抹掉。"""
    agent = _agent(monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(
        "app.memory.postgres_memory.upsert_session_birth_info",
        lambda *a, **k: calls.append(a),
    )
    # 第一轮：API 层 payload 挂载带 uid
    agent.set_chart_context("2005-09-28 18:00", MALE, user_id="u-123")
    agent._persist_birth_info()
    # 第二轮：mount_chart_context（正文正则）不带 uid，覆盖同一张盘 → 同一张盘不重复写库
    agent.reset()
    agent.mount_chart_context("我是2005年9月28日18:00出生的男命")
    agent._persist_birth_info()

    assert [c[5] for c in calls] == ["u-123"], "同一张盘不重复写库"
    assert agent._last_birth_info["user_id"] == "u-123", "uid 必须粘住，不能被空值覆盖"
    # 归属变了（游客→登录）→ 视为新信息，重写一次
    agent.set_chart_context("2005-09-28 18:00", MALE, user_id="u-999")
    agent._persist_birth_info()
    assert [c[5] for c in calls] == ["u-123", "u-999"]


def test_cleanup_persists_birth_info(monkeypatch):
    """cleanup 是每轮收尾钩子：出生信息落库挂在这里，WS 断了也照样执行。"""
    agent = _agent(monkeypatch)
    agent.set_chart_context("2004-06-22 08:00", MALE)
    monkeypatch.setattr(agent, "_persist_history", lambda: None)
    calls: list[tuple] = []
    monkeypatch.setattr(
        "app.memory.postgres_memory.upsert_session_birth_info",
        lambda *a, **k: calls.append(a),
    )

    agent.cleanup()

    assert len(calls) == 1
