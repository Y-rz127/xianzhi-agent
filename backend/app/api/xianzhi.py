"""先知（Xianzhi）相关接口。"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

from app.api.common import check_message_length, client_error, is_message_too_long, message_too_long_text
from app.api.context import AppContext, app_context_dependency, get_app_context
from app.api.deps import require_admin
from app.core.logger import log
from app.db import repository as repo

router = APIRouter(prefix="/xianzhi", tags=["Xianzhi"])


def _mount_chart_context(agent, birth_time: str | None, gender: str | None, sect: int = 2, yun_sect: int = 1, user_id: str = "", birth_place: str = ""):
    if birth_time and gender:
        try:
            agent.set_chart_context(birth_time, gender, sect, yun_sect, user_id, birth_place=birth_place)
        except Exception as e:
            log.warning("通过 API 挂载命盘上下文失败: {}", e)


def _chart_context_payload(agent) -> dict:
    """从 Agent 提取出生信息 payload（SSE 需 JSON 序列化，WS 直接传 dict）。"""
    bi = agent._last_birth_info or {}
    payload = {"birth_time": bi.get("time"), "gender": bi.get("gender")}
    if bi.get("place"):
        payload["birth_place"] = bi["place"]
    return payload


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
            _mount_chart_context(agent, birth_time, gender, sect, yun_sect, uid, birth_place)
            try:
                async for chunk in agent.arun_stream(message, verbose=verbose):
                    yield {"event": "message", "data": chunk}
                # 流结束后，如果后端从工具调用中提取到出生信息，通知前端（覆盖自然语言输入场景）
                if agent._last_birth_info:
                    yield {
                        "event": "chart_context",
                        "data": json.dumps(_chart_context_payload(agent)),
                    }
                yield {"event": "message", "data": "[DONE]"}
            except Exception as e:
                log.exception("SSE stream error")
                yield {"event": "error", "data": client_error(e)}

    return EventSourceResponse(event_stream())


async def _safe_ws_send(websocket: WebSocket, data: dict) -> bool:
    """安全发送 WS 消息，客户端已断开时返回 False 而非抛异常。"""
    try:
        await websocket.send_json(data)
        return True
    except Exception:
        return False


@router.websocket("/ws")
async def ws_chat_with_xianzhi(websocket: WebSocket):
    """先知 WebSocket 流式对话接口（小程序无 SSE，用 WS 替代）。"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            # 客户端可能发非对象 JSON（如数组），校验避免 .get 抛 AttributeError 断连
            if not isinstance(data, dict):
                if not await _safe_ws_send(websocket, {"type": "error", "data": "消息格式错误：应为 JSON 对象"}):
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
                if not await _safe_ws_send(websocket, {"type": "error", "data": message_too_long_text(message)}):
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
                _mount_chart_context(agent, birth_time, gender, sect, yun_sect, uid, birth_place)
                client_alive = True
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
                # 流结束后，如果后端从工具调用中提取到出生信息，通知前端（覆盖自然语言输入场景）
                if client_alive and agent._last_birth_info:
                    bi = agent._last_birth_info
                    ws_payload = {"birth_time": bi.get("time"), "gender": bi.get("gender")}
                    if bi.get("place"):
                        ws_payload["birth_place"] = bi["place"]
                    await _safe_ws_send(websocket, {
                        "type": "chart_context",
                        "data": ws_payload,
                    })
                if client_alive:
                    await _safe_ws_send(websocket, {"type": "done"})
    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
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


@router.get("/sessions", dependencies=[Depends(require_admin)])
async def list_xianzhi_sessions(prefix: str = "web-xianzhi"):
    """获取先知会话列表。
    prefix 可选值：web-xianzhi（默认，PC 端）/ mp-xianzhi（小程序端）。
    """
    return await repo.get_session_info(prefix)


@router.get("/sessions/mine")
async def list_my_sessions(token: str = Query(None)):
    """我的对话：按登录用户隔离的先知会话列表（小程序「我的」页用）。"""
    user = await repo.get_by_token(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return await repo.get_session_info(prefix="mp-xianzhi", user_id=user["id"])


async def _check_session_access(session_id: str, token: str | None):
    """会话归属校验：user_id 非空的会话仅限本人 token 访问（防越权枚举）。

    - 游客会话（session_metadata.user_id 为空，如 PC web 无登录场景）放行；
    - 有归属会话：token 无效或与归属用户不一致 → 403。
      （小程序端 get/del 请求自动携带 token query，正常用户不受影响）
    """
    owner = await repo.get_session_owner(session_id)
    if not owner:
        return
    user = await repo.get_by_token(token) if token else None
    if not user or user["id"] != owner:
        raise HTTPException(status_code=403, detail="无权访问该会话")


@router.delete("/sessions/{session_id}")
async def delete_xianzhi_session(session_id: str, token: str = Query(None)):
    """删除先知会话（含消息记录）。有归属的会话需本人 token。"""
    await _check_session_access(session_id, token)
    await repo.delete_session(session_id)
    return {"status": "ok"}


@router.get("/sessions/{session_id}/messages")
async def get_xianzhi_session_messages(session_id: str, token: str = Query(None)):
    """获取会话的完整消息记录。有归属的会话需本人 token。"""
    await _check_session_access(session_id, token)
    return await repo.get_messages(session_id)


@router.get("/sessions/{session_id}/birth-info")
async def get_xianzhi_session_birth_info(session_id: str, token: str = Query(None)):
    """从会话历史中的排盘工具调用提取出生信息，供前端恢复命盘上下文。

    出生信息属敏感个人数据，有归属的会话需本人 token。
    """
    await _check_session_access(session_id, token)
    info = await repo.get_birth_info_from_session(session_id)
    return info or {"time": None, "gender": None}


@router.get("/cache_stats")
async def cache_stats():
    """获取排盘缓存统计。"""
    from app.tools.cache import bazi_cache
    return bazi_cache.stats()


def _compute_chart_payload(birth_time: str, gender: str, sect: int, yun_sect: int, longitude: float | None) -> dict:
    """同步排盘流水线（标准化 → 校验 → 排盘 → 格式化），输入非法抛 ValueError。"""
    from app.domain.bazi_engine import (
        build_bazi_chart,
        chart_to_api_dict,
        format_analysis_text,
        format_chart_text,
        format_dayun_text,
        format_liunian_text,
        parse_birth,
        parse_gender,
    )
    from app.domain.time_parse import _normalize_birth_time
    # 标准化出生时间（支持公历+时辰、农历、节日等格式，与 bazi_chart 工具入口一致）
    birth_time = _normalize_birth_time(birth_time)
    parse_birth(birth_time)
    parse_gender(gender)
    chart = build_bazi_chart(birth_time, gender, sect=sect, yun_sect=yun_sect, dayun_count=8, liunian_years=5, longitude=longitude)
    payload = chart_to_api_dict(chart)
    payload.update({
        "chartText": format_chart_text(chart),
        "analysisText": format_analysis_text(chart, "整体命盘"),
        "dayunText": format_dayun_text(chart),
        "liunianText": format_liunian_text(chart),
    })
    return payload


@router.get("/chart")
async def get_chart(birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1, longitude: float | None = None):
    """直接排盘，返回四柱/五行/大运/流年等结构化数据。

    Args:
        longitude: 出生地经度（用于真太阳时校正，可选）
    """
    from app.tools.cache import bazi_cache

    # 复用与聊天工具同一套 LRU：/chart 是全量重算的 CPU 密集路径，高频请求会抢 GIL 拖垮事件循环
    # key 追加经度（真太阳时校正会改变四柱）；None 与 0 是不同 key，语义正确
    cache_tool = f"chart_api:{longitude}"
    payload = bazi_cache.get(birth_time, gender, sect, yun_sect, cache_tool)
    if payload is not None:
        return payload
    try:
        # 排盘为同步重计算，放到线程池避免阻塞事件循环
        payload = await asyncio.to_thread(_compute_chart_payload, birth_time, gender, sect, yun_sect, longitude)
        bazi_cache.set(birth_time, gender, payload, sect, yun_sect, cache_tool)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


_GAN = "甲乙丙丁戊己庚辛壬癸"
_ZHI = "子丑寅卯辰巳午未申酉戌亥"


@router.post("/bazi/infer-dates")
async def infer_bazi_dates(payload: dict):
    """根据八字反推候选出生日期：用户只知八字、不知精确时间时调用。

    请求体: {"pillars": "甲申庚午壬申甲辰", "gender": "男", "top_n": 3}
    返回: {"pillars": "...", "candidates": [{"birth_time", "ganzhi", "shi_chen"}, ...]}
    """
    from app.domain.bazi_engine import find_birth_dates_from_pillars
    pillars = (payload.get("pillars") or "").strip()
    gender = (payload.get("gender") or "男").strip() or "男"
    top_n = int(payload.get("top_n") or 3)
    seq = [c for c in pillars if c in _GAN or c in _ZHI]
    if len(seq) < 8:
        raise HTTPException(status_code=400, detail="八字应为 4 个干支共 8 字，如 甲申庚午壬申甲辰")
    try:
        candidates = await asyncio.to_thread(find_birth_dates_from_pillars, pillars, gender, top_n=top_n)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"pillars": pillars, "gender": gender, "candidates": candidates}


# ---------------- 报告任务（后台异步队列） ----------------

# 提交节流：每 kind 每 IP 10 分钟内最多 3 次（报告是重资产动作：CPU/LLM 配额）
_REPORT_TASK_SUBMIT_LIMIT = 3
_REPORT_TASK_SUBMIT_WINDOW = 600


@router.post("/report/tasks")
async def submit_report_task(payload: dict, request: Request):
    """提交报告生成任务，返回 task_id；生成在后台队列执行，轮询 GET /report/tasks/{id} 取状态。

    kind: basic_report(排盘 PDF) | full_report(LLM Markdown) | full_report_pdf(LLM PDF)
    """
    from app.core.redis_client import rate_limit_allow
    from app.db import report_tasks
    from app.tasks.worker import enqueue
    from app.tools.report_tasks import KINDS

    kind = (payload.get("kind") or "").strip()
    birth_time = (payload.get("birth_time") or "").strip()
    gender = (payload.get("gender") or "").strip()
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"kind 必须是 {'/'.join(KINDS)}")
    if not birth_time or not gender:
        raise HTTPException(status_code=400, detail="birth_time 和 gender 必填")

    ip = request.client.host if request.client else "unknown"
    verdict = await rate_limit_allow(f"task-submit:{kind}:{ip}", _REPORT_TASK_SUBMIT_LIMIT, _REPORT_TASK_SUBMIT_WINDOW)
    if verdict is False:
        raise HTTPException(status_code=429, detail="提交过于频繁，请稍后再试")

    params = {"birth_time": birth_time, "gender": gender, "sections": (payload.get("sections") or "").strip()}
    # 幂等复用：同参数任务未过期直接返回旧 task_id（防止重复烧 LLM/CPU）
    existing = await asyncio.to_thread(report_tasks.find_same_task, kind, params)
    if existing:
        return {"task_id": existing, "status": "pending"}
    try:
        await asyncio.to_thread(report_tasks.delete_old)
    except Exception:
        pass
    task_id = await asyncio.to_thread(report_tasks.create_task, kind, params)
    try:
        await enqueue(task_id)
    except Exception:
        await asyncio.to_thread(report_tasks.fail, task_id, "任务队列不可用，请稍后重试")
        raise HTTPException(status_code=503, detail="任务队列不可用，请稍后再试")
    return {"task_id": task_id, "status": "pending"}


@router.get("/report/tasks/{task_id}")
async def get_report_task(task_id: str):
    """查询任务状态；full_report 完成后 content 字段直接携带 Markdown 文本。"""
    from app.db import report_tasks

    row = await asyncio.to_thread(report_tasks.get_task, task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    result = {
        "task_id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "error": row["error"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }
    if row["kind"] == "full_report" and row["status"] == "done" and row["payload"]:
        result["content"] = bytes(row["payload"]).decode("utf-8", errors="replace")
    return result


@router.get("/report/tasks/{task_id}/result")
async def get_report_task_result(task_id: str):
    """下载任务产物（PDF / Markdown 文件）。"""
    from fastapi import Response

    from app.db import report_tasks
    from app.tools.report_tasks import KINDS

    row = await asyncio.to_thread(report_tasks.get_task, task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if row["status"] in ("pending", "running"):
        raise HTTPException(status_code=409, detail="任务尚未完成")
    if row["status"] != "done" or row["payload"] is None:
        raise HTTPException(status_code=410, detail=f"任务生成失败：{row['error'] or '未知错误'}")
    prefix, media = KINDS[row["kind"]]
    ext = "md" if row["kind"] == "full_report" else "pdf"
    return Response(
        content=bytes(row["payload"]),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{prefix}.{ext}"'},
    )
