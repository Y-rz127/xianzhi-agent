"""WS 单连接多路复用（多会话并行生成）回归测试。

背景：小程序里同一页面只有一条 socket（全局 wx.onSocketMessage，真机上 SocketTask
的方法全是空的），所以"两个会话同时问"曾被写成"发新消息先掐掉旧连接" ——
用户在上一个会话等生成时新建会话提问，旧连接被关，页面还崩过一次
（WS 回调落在清空后的 messages 数组上，写出 undefined 空洞）。

改法：一条连接并发跑多轮，每轮带 request_id，推送的每一帧原样带回，
前端据此路由到会话；并发上限 WS_MAX_PARALLEL_SESSIONS（默认 3）。

验证点：
① 每轮帧都带自己的 request_id（多轮并发不会串台）；
② 同一连接上的发送被串行化（帧不会被两个协程写坏/交错）；
③ 跨会话并行、同会话串行（锁忙时回 _SESSION_BUSY_TEXT）；
④ 并发上限超了直接回错误而不是排队；
⑤ 客户端断开后本轮继续跑完（不取消），只是不再推送。
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import xianzhi_chat
from app.api.xianzhi_chat import (
    _max_parallel_sessions,
    _parallel_limit_text,
    _run_ws_turn,
    _WsConnection,
)
from app.core.config import settings


class _FakeWS:
    """记录 send_json 的假 WebSocket；fail_after 次之后开始抛错（模拟客户端断开）。"""

    def __init__(self, fail_after: int | None = None) -> None:
        self.sent: list[dict] = []
        self.fail_after = fail_after
        self.in_flight = 0
        self.max_in_flight = 0

    async def send_json(self, data: dict) -> None:
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise RuntimeError("Cannot call send once a close message has been sent")
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        # 让出控制权：若发送没有串行化，两个协程会在这里交错进来
        await asyncio.sleep(0)
        self.sent.append(data)
        self.in_flight -= 1


class _FakeLock:
    def __init__(self, busy: bool = False) -> None:
        self._locked = busy
        self.releases = 0

    def locked(self) -> bool:
        return self._locked

    async def acquire(self) -> None:
        self._locked = True

    async def release(self) -> None:
        self._locked = False
        self.releases += 1


class _FakeAgent:
    """arun_stream 产出固定 chunk；记录是否被完整消费、是否被取消。"""

    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.consumed = False
        self.cancelled = False
        self._last_birth_info: dict = {}

    def set_turn_id(self, mid: str) -> None:
        pass

    def set_chart_notifier(self, notifier) -> None:
        pass

    def set_progress_notifier(self, notifier) -> None:
        pass

    def set_chart_context(self, *args, **kwargs) -> None:
        pass

    def request_cancel(self) -> None:
        self.cancelled = True

    async def arun_stream(self, message: str, verbose: bool = False):
        for c in self.chunks:
            await asyncio.sleep(0)
            yield c
        self.consumed = True


class _FakeContext:
    def __init__(self, agents: dict[str, tuple[_FakeAgent, _FakeLock]]) -> None:
        self._agents = agents

    def get_xianzhi(self, conversation_id: str):
        return self._agents[conversation_id]


async def _no_owner_check(conversation_id: str, uid: str) -> bool:
    return True


def _patch_repo(monkeypatch) -> None:
    monkeypatch.setattr(xianzhi_chat.repo, "ensure_session_owner", _no_owner_check)


async def _run(agent: _FakeAgent, lock: _FakeLock, chunks_ws: _FakeWS, cid: str, rid: str):
    conn = _WsConnection(chunks_ws)
    await _run_ws_turn(
        conn,
        conn.sender(rid),
        message="问题",
        conversation_id=cid,
        mid="",
        token="",
        birth_time=None,
        gender=None,
        sect=2,
        yun_sect=1,
        birth_place="",
        longitude=None,
        verbose=False,
    )
    return agent


# ---------------- ① request_id 路由 ----------------
def test_each_turn_frames_carry_its_own_request_id(monkeypatch):
    """两轮并发时，每帧必须带自己的 request_id —— 前端全靠它路由到会话。"""
    _patch_repo(monkeypatch)
    ws = _FakeWS()
    agent_a, lock_a = _FakeAgent(["甲一", "甲二"]), _FakeLock()
    agent_b, lock_b = _FakeAgent(["乙一"]), _FakeLock()
    ctx = _FakeContext({"conv-aaaaaaaaaaaaaa": (agent_a, lock_a), "conv-bbbbbbbbbbbbbb": (agent_b, lock_b)})
    monkeypatch.setattr(xianzhi_chat, "get_app_context", lambda: ctx)

    async def main():
        await asyncio.gather(
            _run(agent_a, lock_a, ws, "conv-aaaaaaaaaaaaaa", "rid-a"),
            _run(agent_b, lock_b, ws, "conv-bbbbbbbbbbbbbb", "rid-b"),
        )

    asyncio.run(main())
    by_rid = {rid: [f for f in ws.sent if f.get("request_id") == rid] for rid in ("rid-a", "rid-b")}
    assert [f["data"] for f in by_rid["rid-a"] if f["type"] == "message"] == ["甲一", "甲二"]
    assert [f["data"] for f in by_rid["rid-b"] if f["type"] == "message"] == ["乙一"]
    assert by_rid["rid-a"][-1]["type"] == "done"
    assert by_rid["rid-b"][-1]["type"] == "done"
    # 每一帧都必须带 rid：漏一帧就等于把别轮的内容推到当前会话里
    assert all(f.get("request_id") in ("rid-a", "rid-b") for f in ws.sent)


# ---------------- ② 发送串行化 ----------------
def test_sends_are_serialized_across_turns(monkeypatch):
    """多轮并发时帧不能交错（并发 send_json 会互相插入字节）。"""
    _patch_repo(monkeypatch)
    ws = _FakeWS()
    agent_a, lock_a = _FakeAgent(["一", "二", "三"]), _FakeLock()
    agent_b, lock_b = _FakeAgent(["壹", "贰", "叁"]), _FakeLock()
    ctx = _FakeContext({"conv-aaaaaaaaaaaaaa": (agent_a, lock_a), "conv-bbbbbbbbbbbbbb": (agent_b, lock_b)})
    monkeypatch.setattr(xianzhi_chat, "get_app_context", lambda: ctx)

    async def main():
        conn = _WsConnection(ws)
        await asyncio.gather(
            _run_ws_turn(conn, conn.sender("rid-a"), message="问", conversation_id="conv-aaaaaaaaaaaaaa", mid="", token="", birth_time=None, gender=None, sect=2, yun_sect=1, birth_place="", longitude=None, verbose=False),
            _run_ws_turn(conn, conn.sender("rid-b"), message="问", conversation_id="conv-bbbbbbbbbbbbbb", mid="", token="", birth_time=None, gender=None, sect=2, yun_sect=1, birth_place="", longitude=None, verbose=False),
        )

    asyncio.run(main())
    assert ws.max_in_flight == 1
    assert len(ws.sent) == 8  # 每轮 3 个 chunk + done


# ---------------- ③ 同会话串行 ----------------
def test_busy_session_reports_error_with_request_id(monkeypatch):
    """同会话上一轮还没跑完：回忙提示（带 rid），不要让前端一直等。"""
    _patch_repo(monkeypatch)
    ws = _FakeWS()
    agent, lock = _FakeAgent(["一"]), _FakeLock(busy=True)
    ctx = _FakeContext({"conv-aaaaaaaaaaaaaa": (agent, lock)})
    monkeypatch.setattr(xianzhi_chat, "get_app_context", lambda: ctx)

    async def fake_acquire():
        from app.agent.context import SessionBusyError

        raise SessionBusyError("会话正在执行上一轮请求")

    monkeypatch.setattr(lock, "acquire", fake_acquire)
    asyncio.run(_run(agent, lock, ws, "conv-aaaaaaaaaaaaaa", "rid-busy"))

    assert len(ws.sent) == 1
    assert ws.sent[0]["type"] == "error"
    assert ws.sent[0]["request_id"] == "rid-busy"
    assert ws.sent[0]["data"] == xianzhi_chat._SESSION_BUSY_TEXT
    assert agent.consumed is False


# ---------------- ④ 并发上限 ----------------
def test_parallel_limit_reads_settings(monkeypatch):
    assert _max_parallel_sessions() == 3  # 默认 3 个会话同时跑
    monkeypatch.setattr(settings, "ws_max_parallel_sessions", 5)
    assert _max_parallel_sessions() == 5
    monkeypatch.setattr(settings, "ws_max_parallel_sessions", 0)
    assert _max_parallel_sessions() == 1  # 至少能跑一轮
    assert "3" in _parallel_limit_text(3)


def test_endpoint_rejects_turn_over_parallel_limit(monkeypatch):
    """超过上限必须明确报错（而不是悄悄排队）。"""
    app = FastAPI()
    app.include_router(xianzhi_chat.router)
    monkeypatch.setattr(xianzhi_chat, "_max_parallel_sessions", lambda: 1)

    started = asyncio.Event()

    async def running_forever(*args, **kwargs):
        started.set()
        await asyncio.sleep(30)

    monkeypatch.setattr(xianzhi_chat, "_run_ws_turn", running_forever)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "message": "第一个问题",
                    "conversation_id": "conv-aaaaaaaaaaaaaa",
                    "request_id": "rid-1",
                    "client_msg_id": "mid-aaaaaaaa",
                }
            )
            ws.send_json(
                {
                    "message": "第二个问题",
                    "conversation_id": "conv-bbbbbbbbbbbbbb",
                    "request_id": "rid-2",
                    "client_msg_id": "mid-bbbbbbbb",
                }
            )
            frame = ws.receive_json()

    assert frame["type"] == "error"
    assert frame["request_id"] == "rid-2"
    assert "最多同时 1 个会话" in frame["data"]


def test_endpoint_rejects_duplicate_request_id(monkeypatch):
    """同一个 request_id 重复发（客户端重发）：明确拒绝，避免前端路由错乱。"""
    app = FastAPI()
    app.include_router(xianzhi_chat.router)
    monkeypatch.setattr(xianzhi_chat, "_max_parallel_sessions", lambda: 3)

    async def running_forever(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(xianzhi_chat, "_run_ws_turn", running_forever)

    payload = {
        "message": "问题",
        "conversation_id": "conv-aaaaaaaaaaaaaa",
        "request_id": "rid-dup",
        "client_msg_id": "mid-aaaaaaaa",
    }
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json(payload)
            ws.send_json(payload)
            frame = ws.receive_json()

    assert frame["type"] == "error"
    assert frame["request_id"] == "rid-dup"
    assert "同一请求标识" in frame["data"]


# ---------------- ⑤ 断线后台续跑 ----------------
def test_disconnect_keeps_turn_running_without_cancel(monkeypatch):
    """客户端断开只停止推送：本轮继续跑完落库，不 request_cancel。"""
    _patch_repo(monkeypatch)
    ws = _FakeWS(fail_after=1)  # 第一个 chunk 发得出去，第二个开始失败
    agent, lock = _FakeAgent(["一", "二", "三"]), _FakeLock()
    ctx = _FakeContext({"conv-aaaaaaaaaaaaaa": (agent, lock)})
    monkeypatch.setattr(xianzhi_chat, "get_app_context", lambda: ctx)

    asyncio.run(_run(agent, lock, ws, "conv-aaaaaaaaaaaaaa", "rid-x"))

    assert [f["data"] for f in ws.sent] == ["一"]
    assert agent.consumed is True  # 流被消费完 → agent 跑完并落库
    assert agent.cancelled is False
    assert lock.releases == 1


# ---------------- 任务登记 ----------------
def test_connection_tracks_and_cleans_running_turns():
    conn = _WsConnection(_FakeWS())

    async def main():
        async def quick():
            await asyncio.sleep(0)

        task = conn.spawn("rid-1", quick())
        assert conn.running == 1
        assert conn.is_running("rid-1") is True
        await task
        await asyncio.sleep(0)  # done_callback 在下一轮事件循环才跑
        assert conn.running == 0
        assert conn.is_running("rid-1") is False

    asyncio.run(main())


def test_anonymous_turn_keys_are_unique():
    conn = _WsConnection(_FakeWS())
    assert conn.anon_key() != conn.anon_key()
