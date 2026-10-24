"""先知对话接口：SSE / WebSocket / 同步 三种通道。

路由挂在 /xianzhi 前缀下（由 app.api.xianzhi 聚合），本模块自持 router。
命盘上下文挂载、线程安全通知桥、保活循环等共享辅助见 app.api._xianzhi_common。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

from app.agent.context import AppContext, SessionBusyError, get_app_context
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
    validate_client_msg_id,
    validate_conversation_id,
)
from app.core.logger import log
from app.core.privacy import safe_birth_time, safe_text
from app.core.turn_idempotency import (
    STATUS_DONE,
    STATUS_RUNNING,
    begin_turn,
    complete_turn,
    release_turn,
)

router = APIRouter(tags=["Xianzhi"])

_SESSION_BUSY_TEXT = "上一轮回答仍在生成，请稍后重试"


async def _guard_session(conversation_id: str, uid: str) -> str:
    """校验会话 ID 格式与归属；已绑定他人的会话返回 403。"""
    cid = validate_conversation_id(conversation_id)
    try:
        allowed = await repo.ensure_session_owner(cid, uid)
    except Exception:
        log.exception("会话归属校验失败 cid={} uid={}", conversation_id, uid)
        raise HTTPException(status_code=503, detail="会话服务暂不可用")
    if not allowed:
        raise HTTPException(status_code=403, detail="无权访问该会话")
    return cid


@router.get("/chat")
async def chat_with_xianzhi(
    message: str,
    conversation_id: str = Query(..., min_length=16, max_length=128),
    birth_time: str | None = None,
    gender: str | None = None,
    sect: int = 2,
    yun_sect: int = 1,
    verbose: bool = False,
    birth_place: str = "",
    token: str = Query(None),
    client_msg_id: str | None = Query(None, max_length=64),
    app_ctx: AppContext = Depends(app_context_dependency),
):
    """先知 SSE 流式对话接口（支持挂载出生信息，流式返回 + 可选 chart_context 事件）。"""
    check_message_length(message)
    uid = ""
    if token:
        u = await repo.get_by_token(token)
        if u:
            uid = u["id"]
    conversation_id = await _guard_session(conversation_id, uid)
    try:
        agent, lock = app_ctx.get_xianzhi(conversation_id)
    except RuntimeError:
        return {"error": "Xianzhi not initialized"}
    mid = validate_client_msg_id(client_msg_id)

    async def event_stream():
        # 会话实例级锁：同一会话串行，不同会话并行；
        # sect 设置与命盘挂载均在锁内完成，避免并发污染。
        # 排队超过上限就明确报忙，不让 EventSource 连接无限挂着。
        try:
            await lock.acquire()
        except SessionBusyError:
            yield {"event": "error", "data": _SESSION_BUSY_TEXT}
            return
        try:
            # 防重放判定放在锁内：重复请求会排队到上一轮结束后再判定，
            # 此时必为 done（直接回放）或 new；running 只可能是进程崩溃留下的悬挂键
            if mid:
                state = await begin_turn(conversation_id, mid, uid)
                if state.status == STATUS_DONE:
                    if state.answer:
                        yield {"event": "message", "data": state.answer}
                    yield {"event": "message", "data": "[DONE]"}
                    return
                if state.status == STATUS_RUNNING:
                    log.warning("[sse] client_msg_id={} 为悬挂 running，按新轮次执行", mid)
            agent.set_turn_id(mid)
            agent._sect = sect
            agent._yun_sect = yun_sect
            if uid:
                agent._user_id = uid
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

            parts: list[str] = []
            finished = False

            async def _produce():
                nonlocal finished
                try:
                    async for chunk in agent.arun_stream(message, verbose=verbose):
                        parts.append(chunk)
                        await events.put(("message", chunk))
                    finished = True
                    if mid:
                        try:
                            await complete_turn(conversation_id, mid, uid, "".join(parts))
                        except Exception as e:
                            log.warning("[sse] 轮次结果缓存失败: {}", e)
                except Exception as e:
                    log.exception("SSE stream error")
                    await events.put(("error", client_error(e)))
                finally:
                    if mid and not finished:
                        try:
                            await release_turn(conversation_id, mid, uid)
                        except Exception:
                            pass
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
        finally:
            await lock.release()

    # ping：长静默期（检索/生成/审核可长达 2 分钟）保持连接，兼防网关读超时
    return EventSourceResponse(event_stream(), ping=int(WS_PING_SECONDS))


async def _relay_chunks(
    websocket: WebSocket,
    agent: Any,
    message: str,
    verbose: bool,
    on_chunk: Any = None,
) -> bool:
    """把 agent 的流式输出转发给 websocket，返回客户端是否还活着。

    客户端断开后**继续消费流**（只收不发），让 agent 跑完整轮并落库：
    - 不能 break：跳出 async for 会关闭生成器，把本轮 LLM 链掐死在半途；
    - 不能 request_cancel：用户切走两分钟回来会发现什么都没拿到。
    本轮答案由 agent 自身 cleanup → _persist_history 落库，前端回前台
    （onShow → resumePendingTurn）或断线时（onDisconnect）去会话记录里取回。
    这条不变量由 tests/test_progress_and_keepalive.py 守着。
    """
    client_alive = True
    async for chunk in agent.arun_stream(message, verbose=verbose):
        # 客户端断开也要继续收集完整答案，供轮次防重放复用
        if on_chunk is not None:
            on_chunk(chunk)
        if not client_alive:
            continue
        # 调试：确认发送给前端的 chunk 长度（默认不落用户可见正文）
        log.info("[ws] 发送 chunk {}字 :: {}", len(chunk or ""), safe_text(chunk, 40))
        if not await _safe_ws_send(websocket, {"type": "message", "data": chunk}):
            client_alive = False
            log.info("[ws] 客户端已断开，本轮转入后台生成：跑完落库供前端取回")
    return client_alive


@router.websocket("/ws")
async def ws_chat_with_xianzhi(websocket: WebSocket):
    """先知 WebSocket 流式对话接口（小程序无 SSE，用 WS 替代）。

    断线策略与 SSE 一致：**客户端断开只停止推送，不中止本轮生成** —— 跑完照常
    落库，前端回前台（onShow）或断线时去会话记录里取回完整答案。理由见
    ws_keepalive_loop 的注释：等了两分钟却什么都没拿到，比多烧些 token 更糟。
    """
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
            conversation_id = data.get("conversation_id", "")
            birth_time = data.get("birth_time")
            gender = data.get("gender")
            sect = data.get("sect", 2)
            yun_sect = data.get("yun_sect", 1)
            verbose = bool(data.get("verbose", False))
            birth_place = data.get("birth_place") or ""
            token = data.get("token") or ""
            client_msg_id = data.get("client_msg_id") or ""
            uid = ""
            mid = ""
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
                conversation_id = validate_conversation_id(conversation_id)
                mid = validate_client_msg_id(client_msg_id)
                allowed = await repo.ensure_session_owner(conversation_id, uid)
            except HTTPException as e:
                if not await _safe_ws_send(websocket, {"type": "error", "data": str(e.detail)}):
                    break
                continue
            except Exception:
                log.exception("[ws] 会话归属校验失败 cid={} uid={}", conversation_id, uid)
                if not await _safe_ws_send(websocket, {"type": "error", "data": "会话服务暂不可用"}):
                    break
                continue
            if not allowed:
                if not await _safe_ws_send(websocket, {"type": "error", "data": "无权访问该会话"}):
                    break
                continue
            try:
                agent, lock = get_app_context().get_xianzhi(conversation_id)
            except RuntimeError:
                if not await _safe_ws_send(websocket, {"type": "error", "data": "Xianzhi not initialized"}):
                    break
                continue
            # 上一轮的客户端虽然走了，生成还在后台跑；同会话串行，这里可能要排队
            # （判定必须在抢锁之前，进锁后 locked() 恒为真）
            if lock.locked():
                log.info("[ws] 上一轮仍在后台生成，本轮排队等待（同会话串行）")
            try:
                await lock.acquire()
            except SessionBusyError:
                if not await _safe_ws_send(
                    websocket, {"type": "error", "data": _SESSION_BUSY_TEXT}
                ):
                    break
                continue
            try:
                # 防重放判定在锁内：重复请求排队到上一轮结束后必为 done 或 new
                if mid:
                    state = await begin_turn(conversation_id, mid, uid)
                    if state.status == STATUS_DONE:
                        if state.answer:
                            await _safe_ws_send(websocket, {"type": "message", "data": state.answer})
                        await _safe_ws_send(websocket, {"type": "done"})
                        continue
                    if state.status == STATUS_RUNNING:
                        log.warning("[ws] client_msg_id={} 为悬挂 running，按新轮次执行", mid)
                agent.set_turn_id(mid)
                agent._sect = sect
                agent._yun_sect = yun_sect
                if uid:
                    agent._user_id = uid
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
                        log.warning(
                            "[ws] chart_context 发送失败（客户端已断开） birth={}",
                            safe_birth_time(payload.get("birth_time", "")),
                        )

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
                # 保活：每 WS_PING_SECONDS 秒一个 ping；发不出去就认定客户端已走（不中止生成）
                keepalive = asyncio.create_task(ws_keepalive_loop(websocket, agent))
                parts: list[str] = []
                try:
                    client_alive = await _relay_chunks(
                        websocket, agent, message, verbose, on_chunk=parts.append
                    )
                    if mid:
                        try:
                            await complete_turn(conversation_id, mid, uid, "".join(parts))
                        except Exception as e:
                            log.warning("[ws] 轮次结果缓存失败: {}", e)
                except Exception as e:
                    log.exception("WebSocket stream error")
                    # 本轮失败释放执行权，允许用户用同一 client_msg_id 立即重试
                    if mid:
                        await release_turn(conversation_id, mid, uid)
                    # _safe_ws_send 自带断线保护（连接已死时静默返回 False），无需再判存活
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
            finally:
                await lock.release()
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
    conversation_id: str = Query(..., min_length=16, max_length=128),
    birth_time: str | None = None,
    gender: str | None = None,
    sect: int = 2,
    yun_sect: int = 1,
    birth_place: str = "",
    token: str = Query(None),
    client_msg_id: str | None = Query(None, max_length=64),
    app_ctx: AppContext = Depends(app_context_dependency),
):
    """先知同步对话接口（run 在线程池执行，避免阻塞事件循环）。"""
    check_message_length(message)
    uid = ""
    if token:
        u = await repo.get_by_token(token)
        if u:
            uid = u["id"]
    conversation_id = await _guard_session(conversation_id, uid)
    try:
        agent, lock = app_ctx.get_xianzhi(conversation_id)
    except RuntimeError:
        return {"error": "Xianzhi not initialized"}
    mid = validate_client_msg_id(client_msg_id)
    try:
        await lock.acquire()
    except SessionBusyError:
        raise HTTPException(status_code=409, detail=_SESSION_BUSY_TEXT)
    try:
        # 防重放判定在锁内：重复请求排队到上一轮结束后直接复用它
        if mid:
            state = await begin_turn(conversation_id, mid, uid)
            if state.status == STATUS_DONE:
                return {"result": state.answer}
            if state.status == STATUS_RUNNING:
                log.warning("[sync] client_msg_id={} 为悬挂 running，按新轮次执行", mid)
        agent.set_turn_id(mid)
        agent._sect = sect
        agent._yun_sect = yun_sect
        if uid:
            agent._user_id = uid
        _mount_chart_context(agent, birth_time, gender, sect, yun_sect, uid, birth_place)
        try:
            # run 是同步阻塞调用，放到线程池避免卡住事件循环
            answer = await asyncio.to_thread(agent.run, message)
        except Exception as e:
            if mid:
                await release_turn(conversation_id, mid, uid)
            log.exception("Sync chat error")
            return {"error": client_error(e)}
        if mid:
            try:
                await complete_turn(conversation_id, mid, uid, answer)
            except Exception as e:
                log.warning("[sync] 轮次结果缓存失败: {}", e)
        return {"result": answer}
    finally:
        await lock.release()
