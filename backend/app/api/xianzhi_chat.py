"""先知对话接口：SSE / WebSocket / 同步 三种通道。

路由挂在 /xianzhi 前缀下（由 app.api.xianzhi 聚合），本模块自持 router。
命盘上下文挂载、线程安全通知桥、保活循环等共享辅助见 app.api._xianzhi_common。

WS 通道是**多路复用**的：小程序里同一页面只有一条 socket（全局 wx.onSocketMessage，
真机上 SocketTask 的方法全是空的，见 frontend/uniapp/src/api/chat.ts 文件头），
所以"多个会话同时生成"只能让一条连接并发跑多轮 —— 每轮带一个 request_id，
推送的每一帧原样带回，前端据此路由到对应会话。详见 _WsConnection。
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
from app.core.config import settings
from app.core.http.errors import (
    check_message_length,
    client_error,
    is_message_too_long,
    message_too_long_text,
    validate_client_msg_id,
    validate_conversation_id,
)
from app.core.logger import log
from app.core.privacy import safe_text
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
    longitude: float | None = None,
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
            _mount_chart_context(agent, birth_time, gender, sect, yun_sect, uid, birth_place, longitude)

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
    websocket: Any,
    agent: Any,
    message: str,
    verbose: bool,
    on_chunk: Any = None,
) -> bool:
    """把 agent 的流式输出转发给 websocket，返回客户端是否还活着。

    `websocket` 只要具备 `async send_json(dict)` 即可：WS 多路复用时传的是
    `_TurnSender`（帧自动带 request_id），单连接传 `_WsConnection`。

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


# ---------------- WebSocket：单连接多路复用 ----------------
#
# 背景：小程序里同一页面只可能有一条 socket，且全局 wx.onSocketMessage 分不出来源，
# 所以"多个会话同时生成"不能靠多开连接（也吃 5 条 socket 上限）。改法是一条连接跑多轮：
#   - 客户端每轮带 request_id，服务端推送的每一帧原样带回，前端据此路由到会话；
#   - 每轮一个独立 task，各自拿自己会话的 SessionLock（同会话仍串行，跨会话并行）；
#   - 并发上限 WS_MAX_PARALLEL_SESSIONS（默认 3），超了直接回错误而不是排队 ——
#     在这条连接上排队只会变成"用户以为发出去了，其实还在等"。

# 后台轮次的强引用：handler 因客户端断开而返回后，本轮还要继续跑完并落库，
# 期间不能被 GC 掉（asyncio 只持弱引用）。
_BACKGROUND_TURNS: set[asyncio.Task] = set()


def _max_parallel_sessions() -> int:
    """单连接并发会话上限（0/负数按 1 处理：至少得能跑一轮）。"""
    try:
        value = int(settings.ws_max_parallel_sessions)
    except (TypeError, ValueError):
        return 1
    return max(1, value)


def _parallel_limit_text(limit: int) -> str:
    return f"最多同时 {limit} 个会话在生成，请等其中一个完成再发"


class _TurnSender:
    """某一轮的发送句柄：帧自动带 request_id，与 WebSocket 同形（只有 send_json）。

    保持同形是为了让 _relay_chunks / _safe_ws_send / 通知器原样复用，
    不必为多路复用改写转发逻辑。
    """

    __slots__ = ("_conn", "request_id")

    def __init__(self, conn: "_WsConnection", request_id: str) -> None:
        self._conn = conn
        self.request_id = request_id

    async def send_json(self, data: dict) -> None:
        await self._conn.send_json({**data, "request_id": self.request_id})

    async def send(self, data: dict) -> bool:
        return await _safe_ws_send(self, data)


class _WsConnection:
    """一条 WS 连接上的并发轮次管理：发送串行化 + 并发上限 + 任务强引用。"""

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        # 多轮并发推流时帧绝不能交错（asyncio 的 send_json 并发调用会互相插入字节）
        self._send_lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task] = {}
        self._anon = 0

    async def send_json(self, data: dict) -> None:
        async with self._send_lock:
            await self._ws.send_json(data)

    async def send(self, data: dict) -> bool:
        return await _safe_ws_send(self, data)

    def sender(self, request_id: str) -> _TurnSender:
        return _TurnSender(self, request_id)

    @property
    def running(self) -> int:
        return len(self._tasks)

    def is_running(self, request_id: str) -> bool:
        return request_id in self._tasks

    def anon_key(self) -> str:
        """未带 request_id 的老客户端：给个内部唯一键，仅用于任务登记。"""
        self._anon += 1
        return f"#anon-{self._anon}"

    def spawn(self, key: str, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks[key] = task
        _BACKGROUND_TURNS.add(task)

        def _done(t: asyncio.Task) -> None:
            _BACKGROUND_TURNS.discard(t)
            if self._tasks.get(key) is t:
                self._tasks.pop(key, None)

        task.add_done_callback(_done)
        return task


async def _run_ws_turn(
    conn: _WsConnection,
    sender: _TurnSender,
    *,
    message: str,
    conversation_id: str,
    mid: str,
    token: str,
    birth_time: str | None,
    gender: str | None,
    sect: int,
    yun_sect: int,
    birth_place: str,
    longitude: float | None,
    verbose: bool,
) -> None:
    """跑一轮对话，把帧推回这条连接（帧带 request_id，前端据此路由）。"""
    uid = ""
    if token:
        u = await repo.get_by_token(token)
        if u:
            uid = u["id"]
    try:
        allowed = await repo.ensure_session_owner(conversation_id, uid)
    except Exception:
        log.exception("[ws] 会话归属校验失败 cid={} uid={}", conversation_id, uid)
        await sender.send({"type": "error", "data": "会话服务暂不可用"})
        return
    if not allowed:
        await sender.send({"type": "error", "data": "无权访问该会话"})
        return
    try:
        agent, lock = get_app_context().get_xianzhi(conversation_id)
    except RuntimeError:
        await sender.send({"type": "error", "data": "Xianzhi not initialized"})
        return
    # 上一轮的客户端虽然走了，生成还在后台跑；同会话串行，这里可能要排队
    # （判定必须在抢锁之前，进锁后 locked() 恒为真）
    if lock.locked():
        log.info("[ws] 上一轮仍在后台生成，本轮排队等待（同会话串行）")
    try:
        await lock.acquire()
    except SessionBusyError:
        await sender.send({"type": "error", "data": _SESSION_BUSY_TEXT})
        return
    try:
        # 防重放判定在锁内：重复请求排队到上一轮结束后必为 done 或 new
        if mid:
            state = await begin_turn(conversation_id, mid, uid)
            if state.status == STATUS_DONE:
                if state.answer:
                    await sender.send({"type": "message", "data": state.answer})
                await sender.send({"type": "done"})
                return
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

        async def _push(payload: dict) -> None:
            # 这个任务由通知回调 ensure_future 派生，异常没人接 → 内部全兜住
            try:
                await sender.send(payload)
            except Exception as e:
                log.warning("[ws] 通知发送异常: {}", e)

        agent.set_chart_notifier(
            make_chart_notifier(
                loop, lambda p: asyncio.ensure_future(_push({"type": "chart_context", "data": p}))
            )
        )
        agent.set_progress_notifier(
            make_progress_notifier(
                loop, lambda t: asyncio.ensure_future(_push({"type": "progress", "data": t}))
            )
        )
        _mount_chart_context(agent, birth_time, gender, sect, yun_sect, uid, birth_place, longitude)
        parts: list[str] = []
        try:
            client_alive = await _relay_chunks(
                sender, agent, message, verbose, on_chunk=parts.append
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
            await sender.send({"type": "error", "data": client_error(e)})
            client_alive = False
        finally:
            agent.set_chart_notifier(None)
            agent.set_progress_notifier(None)
        # 命盘通知已在挂盘那一刻发出（见上面的 set_chart_notifier），
        # 这里不再补发：旧逻辑排在回答之后且以 client_alive 为条件，
        # 回答发送失败时通知必然一起丢，正是"八字信息丢失"的根因。
        if client_alive:
            await sender.send({"type": "done"})
    finally:
        await lock.release()


@router.websocket("/ws")
async def ws_chat_with_xianzhi(websocket: WebSocket):
    """先知 WebSocket 流式对话接口（多路复用：一条连接并发跑多个会话）。

    断线策略与 SSE 一致：**客户端断开只停止推送，不中止本轮生成** —— 跑完照常
    落库，前端回前台（onShow）或断线时去会话记录里取回完整答案。理由见
    ws_keepalive_loop 的注释：等了两分钟却什么都没拿到，比多烧些 token 更糟。
    """
    await websocket.accept()
    conn = _WsConnection(websocket)
    max_parallel = _max_parallel_sessions()
    # 保活按**连接**起一个（不是按轮次）：多轮并发时不能各发各的 ping
    keepalive = asyncio.create_task(ws_keepalive_loop(conn, interval=WS_PING_SECONDS))
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                # 非 JSON 帧（纯文本/二进制/坏 JSON）：如实报错但不要断连
                if not await conn.send({"type": "error", "data": "消息格式错误：应为 JSON 对象"}):
                    break
                continue
            # 客户端可能发非对象 JSON（如数组），校验避免 .get 抛 AttributeError 断连
            if not isinstance(data, dict):
                if not await conn.send({"type": "error", "data": "消息格式错误：应为 JSON 对象"}):
                    break
                continue

            request_id = str(data.get("request_id") or "")[:64]
            sender = conn.sender(request_id)
            if request_id and conn.is_running(request_id):
                await sender.send({"type": "error", "data": "同一请求标识已在生成中"})
                continue
            message = data.get("message", "")
            if is_message_too_long(message):
                await sender.send({"type": "error", "data": message_too_long_text(message)})
                continue
            try:
                conversation_id = validate_conversation_id(data.get("conversation_id", ""))
                mid = validate_client_msg_id(data.get("client_msg_id") or "")
            except HTTPException as e:
                await sender.send({"type": "error", "data": str(e.detail)})
                continue
            # 并发上限：超了明确报错，不排队（排队 = 用户以为发出去了其实在等）
            if conn.running >= max_parallel:
                log.info(
                    "[ws] 并发会话已达上限 {}，拒绝新轮次 cid={}", max_parallel, conversation_id
                )
                await sender.send({"type": "error", "data": _parallel_limit_text(max_parallel)})
                continue
            longitude = data.get("longitude")
            try:
                longitude = float(longitude) if longitude else None
            except (TypeError, ValueError):
                longitude = None
            conn.spawn(
                request_id or conn.anon_key(),
                _run_ws_turn(
                    conn,
                    sender,
                    message=message,
                    conversation_id=conversation_id,
                    mid=mid,
                    token=data.get("token") or "",
                    birth_time=data.get("birth_time"),
                    gender=data.get("gender"),
                    sect=data.get("sect", 2),
                    yun_sect=data.get("yun_sect", 1),
                    birth_place=data.get("birth_place") or "",
                    longitude=longitude,
                    verbose=bool(data.get("verbose", False)),
                ),
            )
    except WebSocketDisconnect:
        log.info("[ws] 客户端断开（在跑的 {} 个会话继续生成并落库）", conn.running)
    except RuntimeError as e:
        if "not connected" in str(e):
            log.info("[ws] 连接已丢失（客户端断开）")
        else:
            log.exception("WebSocket runtime error")
            await conn.send({"type": "error", "data": client_error(e)})
    except Exception as e:
        log.exception("WebSocket error")
        await conn.send({"type": "error", "data": client_error(e)})
    finally:
        keepalive.cancel()
        if _BACKGROUND_TURNS:
            log.info("[ws] 后台仍有 {} 个轮次在生成（连接已断，跑完落库）", len(_BACKGROUND_TURNS))


@router.get("/chat/sync")
async def chat_with_xianzhi_sync(
    message: str,
    conversation_id: str = Query(..., min_length=16, max_length=128),
    birth_time: str | None = None,
    gender: str | None = None,
    sect: int = 2,
    yun_sect: int = 1,
    birth_place: str = "",
    longitude: float | None = None,
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
        _mount_chart_context(agent, birth_time, gender, sect, yun_sect, uid, birth_place, longitude)
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
