"""先知对话接口：SSE / WebSocket / 同步 三种通道。

路由挂在 /xianzhi 前缀下（由 app.api.xianzhi 聚合），本模块自持 router。
命盘上下文挂载、线程安全通知桥、保活循环等共享辅助见 app.api._xianzhi_common。
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

from app.agent.context import AppContext, get_app_context
from app.api import data_access as repo
from app.api._xianzhi_common import (
    WS_PING_SECONDS,
    _mount_chart_context,
    _safe_ws_send,
    make_chart_notifier,
    make_progress_notifier,
    ws_keepalive_loop,
)
from app.api.deps import app_context_dependency
from app.core.http.errors import (
    check_message_length,
    client_error,
    is_message_too_long,
    message_too_long_text,
)
from app.core.logger import log

router = APIRouter(tags=["Xianzhi"])


@router.get("/chat")
async def chat_with_xianzhi(
    message: str,
    conversation_id: str = "default",
    birth_time: str | None = None,
    gender: str | None = None,
    sect: int = 2,
    yun_sect: int = 1,
    verbose: bool = False,
    birth_place: str = "",
    token: str = Query(None),
    app_ctx: AppContext = Depends(app_context_dependency),
):
    """先知 SSE 流式对话接口（支持挂载出生信息，流式返回 + 可选 chart_context 事件）。"""
    check_message_length(message)
    uid = ""
    if token:
        u = await repo.get_by_token(token)
        if u:
            uid = u["id"]
    try:
        agent, lock = app_ctx.get_xianzhi(conversation_id)
    except RuntimeError:
        return {"error": "Xianzhi not initialized"}

    async def event_stream():
        # 会话实例级锁：同一会话串行，不同会话并行；
        # sect 设置与命盘挂载均在锁内完成，避免并发污染
        async with lock:
            agent._sect = sect
            agent._yun_sect = yun_sect
            loop = asyncio.get_running_loop()
            events: asyncio.Queue = asyncio.Queue()
            _END = object()  # 生产者结束哨兵

            # 挂盘即通知（同 WS 路径）：通知与回答共用一条队列，但通知来自挂盘那一刻，
            # 不再等整轮回答流完，客户端断开也照样先收到。
            agent.set_chart_notifier(
                make_chart_notifier(
                    loop,
                    lambda p: events.put_nowait(("chart_context", json.dumps(p, ensure_ascii=False))),
                )
            )
            # 阶段进度同样入队（长静默期给前端反馈，避免用户以为卡死）
            agent.set_progress_notifier(
                make_progress_notifier(loop, lambda t: events.put_nowait(("progress", t)))
            )
            _mount_chart_context(agent, birth_time, gender, sect, yun_sect, uid, birth_place)

            async def _produce():
                try:
                    async for chunk in agent.arun_stream(message, verbose=verbose):
                        await events.put(("message", chunk))
                except Exception as e:
                    log.exception("SSE stream error")
                    await events.put(("error", client_error(e)))
                finally:
                    await events.put((_END, None))

            task = asyncio.create_task(_produce())
            try:
                while True:
                    kind, data = await events.get()
                    if kind is _END:
                        break
                    yield {"event": kind, "data": data}
                yield {"event": "message", "data": "[DONE]"}
            finally:
                agent.set_chart_notifier(None)
                agent.set_progress_notifier(None)
                # 客户端断开（EventSourceResponse 取消本生成器）：**不取消**在跑的生产任务，
                # 让它照常跑完并落库——用户回头能在会话记录里看到答案；取消 = 白等一场。
                if not task.done():
                    log.info("[sse] 客户端已断开，本轮继续在后台生成并落库")

    # ping：长静默期（检索/生成/审核可长达 2 分钟）保持连接，兼防网关读超时
    return EventSourceResponse(event_stream(), ping=int(WS_PING_SECONDS))


@router.websocket("/ws")
async def ws_chat_with_xianzhi(websocket: WebSocket):
    """先知 WebSocket 流式对话接口（小程序无 SSE，用 WS 替代）。"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            # 客户端可能发非对象 JSON（如数组），校验避免 .get 抛 AttributeError 断连
            if not isinstance(data, dict):
                if not await _safe_ws_send(
                    websocket, {"type": "error", "data": "消息格式错误：应为 JSON 对象"}
                ):
                    break
                continue
            message = data.get("message", "")
            conversation_id = data.get("conversation_id", "default")
            birth_time = data.get("birth_time")
            gender = data.get("gender")
            sect = data.get("sect", 2)
            yun_sect = data.get("yun_sect", 1)
            verbose = bool(data.get("verbose", False))
            birth_place = data.get("birth_place") or ""
            token = data.get("token") or ""
            uid = ""
            if token:
                u = await repo.get_by_token(token)
                if u:
                    uid = u["id"]
            if is_message_too_long(message):
                if not await _safe_ws_send(
                    websocket, {"type": "error", "data": message_too_long_text(message)}
                ):
                    break
                continue
            try:
                agent, lock = get_app_context().get_xianzhi(conversation_id)
            except RuntimeError:
                if not await _safe_ws_send(websocket, {"type": "error", "data": "Xianzhi not initialized"}):
                    break
                continue
            async with lock:
                agent._sect = sect
                agent._yun_sect = yun_sect
                # 挂盘即通知：把「命盘已挂载」提前到挂载那一刻发，不再等整轮回答流完。
                # 旧做法排在回答之后且带 client_alive 门槛，回答一发送失败就静默丢通知
                # （2026-09-15 实测：生成 29s 后 socket 已断 → chart_context 没发出去）。
                loop = asyncio.get_running_loop()

                async def _send_chart_context(payload: dict) -> None:
                    # 这个任务由通知回调 ensure_future 派生，异常没人接 → 内部全兜住
                    try:
                        ok = await _safe_ws_send(
                            websocket, {"type": "chart_context", "data": payload}
                        )
                    except Exception as e:
                        log.warning("[ws] chart_context 发送异常: {}", e)
                        return
                    if not ok:
                        log.warning("[ws] chart_context 发送失败（客户端已断开）: {}", payload)

                agent.set_chart_notifier(
                    make_chart_notifier(loop, lambda p: asyncio.ensure_future(_send_chart_context(p)))
                )
                agent.set_progress_notifier(
                    make_progress_notifier(
                        loop,
                        lambda t: asyncio.ensure_future(
                            _safe_ws_send(websocket, {"type": "progress", "data": t})
                        ),
                    )
                )
                _mount_chart_context(agent, birth_time, gender, sect, yun_sect, uid, birth_place)
                client_alive = True
                # 保活：每 WS_PING_SECONDS 秒一个 ping；发不出去就认定客户端已走并取消本轮
                keepalive = asyncio.create_task(ws_keepalive_loop(websocket, agent))
                try:
                    async for chunk in agent.arun_stream(message, verbose=verbose):
                        # 调试：确认发送给前端的 chunk 内容（排查"AI 回复为空"）
                        log.info("[ws] 发送 chunk {}字 :: {}", len(chunk or ""), (chunk or "")[:40])
                        if not await _safe_ws_send(websocket, {"type": "message", "data": chunk}):
                            client_alive = False
                            log.info("客户端已断开，停止流式发送")
                            # 请求取消：让 agent 执行循环在当前步骤后停止，
                            # 不再继续剩余的 LLM 调用（省 token + 省时延）
                            agent.request_cancel()
                            break
                except Exception as e:
                    log.exception("WebSocket stream error")
                    if client_alive:
                        await _safe_ws_send(websocket, {"type": "error", "data": client_error(e)})
                    client_alive = False
                finally:
                    agent.set_chart_notifier(None)
                    agent.set_progress_notifier(None)
                    keepalive.cancel()
                # 命盘通知已在挂盘那一刻发出（见上面的 set_chart_notifier），
                # 这里不再补发：旧逻辑排在回答之后且以 client_alive 为条件，
                # 回答发送失败时通知必然一起丢，正是"八字信息丢失"的根因。
                if client_alive:
                    await _safe_ws_send(websocket, {"type": "done"})
    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
    except RuntimeError as e:
        if "not connected" in str(e):
            log.info("WebSocket connection lost (client disconnected)")
        else:
            log.exception("WebSocket runtime error")
            await _safe_ws_send(websocket, {"type": "error", "data": client_error(e)})
    except Exception as e:
        log.exception("WebSocket error")
        await _safe_ws_send(websocket, {"type": "error", "data": client_error(e)})


@router.get("/chat/sync")
async def chat_with_xianzhi_sync(
    message: str,
    conversation_id: str = "default",
    birth_time: str | None = None,
    gender: str | None = None,
    sect: int = 2,
    yun_sect: int = 1,
    birth_place: str = "",
    token: str = Query(None),
    app_ctx: AppContext = Depends(app_context_dependency),
):
    """先知同步对话接口（run 在线程池执行，避免阻塞事件循环）。"""
    check_message_length(message)
    uid = ""
    if token:
        u = await repo.get_by_token(token)
        if u:
            uid = u["id"]
    try:
        agent, lock = app_ctx.get_xianzhi(conversation_id)
    except RuntimeError:
        return {"error": "Xianzhi not initialized"}
    async with lock:
        agent._sect = sect
        agent._yun_sect = yun_sect
        _mount_chart_context(agent, birth_time, gender, sect, yun_sect, uid, birth_place)
        try:
            # run 是同步阻塞调用，放到线程池避免卡住事件循环
            return {"result": await asyncio.to_thread(agent.run, message)}
        except Exception as e:
            log.exception("Sync chat error")
            return {"error": client_error(e)}
