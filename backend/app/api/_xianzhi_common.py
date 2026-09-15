"""先知接口共享辅助：命盘上下文挂载 / 线程安全通知桥 / 保活循环。

这些函数被 chat/ws/sync 路由共用，且与路由解耦（不依赖 APIRouter），
故独立成模块，避免 app.api.xianzhi 与子路由之间产生循环导入。
"""

from __future__ import annotations

import asyncio

from app.core.logger import log

# 保活 ping 间隔（秒）：小于常见网关默认的 60s 读超时，也小于小程序侧的静默回收窗口
WS_PING_SECONDS = 15.0


def _mount_chart_context(
    agent,
    birth_time: str | None,
    gender: str | None,
    sect: int = 2,
    yun_sect: int = 1,
    user_id: str = "",
    birth_place: str = "",
):
    if birth_time and gender:
        try:
            agent.set_chart_context(birth_time, gender, sect, yun_sect, user_id, birth_place=birth_place)
        except Exception as e:
            log.warning("通过 API 挂载命盘上下文失败: {}", e)


def _payload_from_birth_info(info: dict) -> dict:
    """出生信息 → 前端 chart_context payload（字段名与前端约定一致）。"""
    payload = {"birth_time": info.get("time"), "gender": info.get("gender")}
    if info.get("place"):
        payload["birth_place"] = info["place"]
    return payload


def _chart_context_payload(agent) -> dict:
    """从 Agent 提取出生信息 payload（SSE 需 JSON 序列化，WS 直接传 dict）。"""
    return _payload_from_birth_info(agent._last_birth_info or {})


def _thread_bridge(loop, push):
    """把工作线程里的回调转投到事件循环：push(x) 会在循环线程上执行。"""

    def _send(value) -> None:
        try:
            loop.call_soon_threadsafe(push, value)
        except RuntimeError:
            # 事件循环已关闭（进程退出/测试收尾）：丢弃即可
            pass

    return _send


def make_chart_notifier(loop, push):
    """构造「命盘已挂载」通知器：把工作线程里的事件安全转投到事件循环。

    挂盘发生在 asyncio.to_thread 中（arun_stream → mount_chart_context），
    不能直接 await 发送，必须用 call_soon_threadsafe 回到循环上再发。
    push(payload) 在事件循环上被调用（内部自行 ensure_future/put_nowait）。
    """

    def _notify(info: dict) -> None:
        payload = _payload_from_birth_info(info or {})
        if not payload.get("birth_time") or not payload.get("gender"):
            return
        _thread_bridge(loop, push)(payload)

    return _notify


def make_progress_notifier(loop, push):
    """构造阶段进度通知器（"正在检索…/正在推演生成…"），线程安全转投同 chart_context。"""

    def _notify(text: str) -> None:
        if text:
            _thread_bridge(loop, push)(str(text))

    return _notify


async def ws_keepalive_loop(websocket, agent, *, interval: float = WS_PING_SECONDS) -> None:
    """长静默期保活 + 断线探测。

    为什么需要：本轮生成实测 116 秒，服务端一个字节都不发。这段静默期内
    （1）前面的代理/网关（nginx 默认 proxy_read_timeout=60s）会掐连接；
    （2）小程序侧长时间无数据也容易被系统回收。
    更关键的是：服务端只有"发送时"才知道对端已经走了；不过这里**不中止生成**——
    答案会落库、客户端断线后会去会话记录里取回（前端 onDisconnect → 取回函数）；
    若 request_cancel，用户等了两分钟反而什么都拿不到，比浪费些 token 更糟。
    """
    while True:
        await asyncio.sleep(interval)
        if not await _safe_ws_send(websocket, {"type": "ping"}):
            log.info("[ws] 保活 ping 失败，客户端已断开（本轮继续生成并落库，供前端取回）")
            return


async def _safe_ws_send(websocket: object, data: dict) -> bool:
    """安全发送 WS 消息，客户端已断开时返回 False 而非抛异常。"""
    try:
        await websocket.send_json(data)
        return True
    except Exception:
        return False
