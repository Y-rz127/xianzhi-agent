"""长静默期保活 + 阶段进度 回归测试（不联网、不需要真实 WS）。

背景（2026-09-15）：一轮生成实测 116 秒，服务端在这段时间**一个字节都不发**。
后果有两层：
1. 客户端只能显示"推演中…"，用户以为卡死 → 切页面 → 小程序 onHide 关掉 socket；
2. 静默期超过网关/系统的空闲阈值（nginx 默认 proxy_read_timeout=60s）连接被掐。
于是回答生成完却送不出去（"消息都没发出来怎么就断开啦"）。

修法：
- 保活：每 WS_PING_SECONDS 秒发 `{"type":"ping"}`，让连接有事发生；
- 进度：检索/生成/审核/修复各阶段推 `{"type":"progress"}`，前端把"推演中…"换成阶段文案。
- 保活 ping 失败**只停止保活、不中止生成**：答案要落库供前端断线后取回，
  这里取消等于让用户白等两分钟什么都拿不到。

验证点：
① 保活循环按间隔发 ping，失败即退出且不调用 request_cancel；
② 进度回调链路 agent → workflow，且异常被吞掉不影响生成；
③ 进度通知器的线程安全转投。
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock, patch

from app.api.xianzhi import WS_PING_SECONDS, make_progress_notifier, ws_keepalive_loop
from app.agent.xianzhi import Xianzhi


class _FakeWS:
    """记录 send_json 调用的假 WebSocket；fail_after 次后开始抛错。"""

    def __init__(self, fail_after: int | None = None):
        self.sent: list[dict] = []
        self._fail_after = fail_after

    async def send_json(self, data: dict) -> None:
        if self._fail_after is not None and len(self.sent) >= self._fail_after:
            raise RuntimeError("Cannot call send once a close message has been sent")
        self.sent.append(data)


def test_keepalive_interval_is_below_gateway_timeout():
    """间隔必须明显小于常见网关默认 60s 读超时，否则保活没有意义。"""
    assert 0 < WS_PING_SECONDS < 60


def test_keepalive_sends_pings_until_failure():
    ws = _FakeWS(fail_after=2)
    agent = MagicMock()

    async def run():
        task = asyncio.create_task(ws_keepalive_loop(ws, agent, interval=0.01))
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(run())
    assert [m["type"] for m in ws.sent] == ["ping", "ping"]
    # 断线不中止生成：答案要落库给前端取回
    agent.request_cancel.assert_not_called()


def test_keepalive_stops_promptly_when_client_gone():
    ws = _FakeWS(fail_after=0)
    agent = MagicMock()

    async def run():
        task = asyncio.create_task(ws_keepalive_loop(ws, agent, interval=0.01))
        await asyncio.wait_for(task, timeout=2)  # 第一次 ping 失败即返回

    asyncio.run(run())
    assert ws.sent == []
    agent.request_cancel.assert_not_called()


# ---------------- 进度回调链路 ----------------
def _agent() -> Xianzhi:
    with patch("app.agent.xianzhi.create_chat_memory") as m:
        m.return_value = MagicMock()
        return Xianzhi(chat_model=MagicMock(), local_tools=[])


def test_workflow_progress_reaches_notifier():
    agent = _agent()
    seen: list[str] = []
    agent.set_progress_notifier(seen.append)

    # workflow 发出的阶段进度应一路冒泡到前端通知器
    agent._workflow._emit_progress("正在检索命理知识…")
    agent._workflow._emit_progress("正在推演生成…")

    assert seen == ["正在检索命理知识…", "正在推演生成…"]


def test_progress_wired_at_construction():
    agent = _agent()
    assert agent._workflow.on_progress == agent._fire_progress


def test_progress_notifier_error_is_swallowed():
    agent = _agent()

    def boom(_text):
        raise RuntimeError("client gone")

    agent.set_progress_notifier(boom)
    agent._workflow._emit_progress("正在复核断语…")  # 不得抛出


def test_progress_noop_without_notifier_or_text():
    agent = _agent()
    agent._workflow._emit_progress("正在推演生成…")  # 未注册通知器：静默
    agent.set_progress_notifier(lambda t: None)
    agent._workflow._emit_progress("")  # 空文案：不回调


def test_progress_notifier_bridges_from_worker_thread():
    seen: list[tuple] = []

    async def main():
        loop = asyncio.get_running_loop()
        notify = make_progress_notifier(
            loop, lambda t: seen.append((threading.current_thread().name, t))
        )

        def worker():
            notify("正在推演生成…")

        t = threading.Thread(target=worker, name="agent-worker")
        t.start()
        t.join()
        await asyncio.sleep(0.05)

    asyncio.run(main())
    assert seen and seen[0][0] != "agent-worker" and seen[0][1] == "正在推演生成…"


def test_progress_notifier_ignores_empty():
    pushed: list[str] = []
    loop = asyncio.new_event_loop()
    try:
        notify = make_progress_notifier(loop, pushed.append)
        notify("")
        loop.run_until_complete(asyncio.sleep(0.01))
    finally:
        loop.close()
    assert pushed == []
