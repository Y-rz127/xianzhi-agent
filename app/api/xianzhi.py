"""先知（Xianzhi）相关接口。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

from app.api.common import check_message_length, client_error, is_message_too_long, message_too_long_text
from app.api.context import AppContext, app_context_dependency, get_app_context
from app.api.deps import require_admin
from app.core.logger import log
from app.db import repository as repo

router = APIRouter(prefix="/xianzhi", tags=["Xianzhi"])


def _mount_chart_context(agent, birth_time: str | None, gender: str | None, sect: int = 2, yun_sect: int = 1, user_id: str = "", birth_place: str = ""):
    """如果提供了出生信息，直接挂载到该会话 Agent 上下文。"""
    if birth_time and gender:
        try:
            agent.set_chart_context(birth_time, gender, sect, yun_sect, user_id, birth_place=birth_place)
        except Exception as e:
            log.warning("通过 API 挂载命盘上下文失败: {}", e)


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
                    bi = agent._last_birth_info
                    import json as _json
                    payload = {"birth_time": bi.get("time"), "gender": bi.get("gender")}
                    if bi.get("place"):
                        payload["birth_place"] = bi["place"]
                    yield {
                        "event": "chart_context",
                        "data": _json.dumps(payload),
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
    try:
        # 排盘为同步重计算，放到线程池避免阻塞事件循环
        return await asyncio.to_thread(_compute_chart_payload, birth_time, gender, sect, yun_sect, longitude)
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


def _build_pdf_report(birth_time: str, gender: str) -> bytes:
    """同步生成基础 PDF 报告（排盘工具 invoke + PDF 渲染）。"""
    from app.tools.bazi import bazi_analysis, bazi_chart, bazi_dayun, bazi_liunian
    from app.tools.pdf_report import generate_bazi_report

    chart_text = bazi_chart.invoke({"birth_time": birth_time, "gender": gender})
    analysis_text = bazi_analysis.invoke({"birth_time": birth_time, "gender": gender, "question": "整体命盘"})
    dayun_text = bazi_dayun.invoke({"birth_time": birth_time, "gender": gender, "count": 8})
    liunian_text = bazi_liunian.invoke({"birth_time": birth_time, "gender": gender, "years": 10})
    return generate_bazi_report(
        birth_time=birth_time,
        gender=gender,
        chart_text=chart_text,
        analysis_text=analysis_text,
        dayun_text=dayun_text,
        liunian_text=liunian_text,
    )


@router.get("/report")
async def generate_report(birth_time: str, gender: str):
    from fastapi import Response

    try:
        pdf_bytes = await asyncio.to_thread(_build_pdf_report, birth_time, gender)
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="xianzhi_bazi_report.pdf"'})
    except Exception as e:
        log.exception("PDF 报告生成失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/full_report")
async def full_report(birth_time: str, gender: str, sections: str = "",
                      app_ctx: AppContext = Depends(app_context_dependency)):
    """生成 LLM 分节命理报告（Markdown）。"""
    chat_model = app_ctx.chat_model
    if chat_model is None:
        return {"error": "Xianzhi not initialized"}
    from app.tools.report_generator import DEFAULT_SECTIONS, generate_full_report

    selected = sections.split(",") if sections else DEFAULT_SECTIONS
    try:
        content = await asyncio.to_thread(generate_full_report, chat_model, birth_time, gender, selected)
        return {"content": content}
    except Exception as e:
        log.exception("生成命理报告失败")
        raise HTTPException(status_code=500, detail=client_error(e))


def _build_full_report_pdf(chat_model, birth_time: str, gender: str, selected: list) -> bytes:
    """同步生成 LLM 分节报告 PDF（多次 LLM 调用 + 排盘工具 invoke + PDF 渲染）。"""
    from app.tools.bazi import bazi_analysis, bazi_chart, bazi_dayun, bazi_liunian
    from app.tools.pdf_report import generate_bazi_report
    from app.tools.report_generator import generate_full_report

    ai_commentary = generate_full_report(chat_model, birth_time, gender, selected)
    chart_text = bazi_chart.invoke({"birth_time": birth_time, "gender": gender})
    analysis_text = bazi_analysis.invoke({"birth_time": birth_time, "gender": gender, "question": "整体命盘"})
    dayun_text = bazi_dayun.invoke({"birth_time": birth_time, "gender": gender, "count": 8})
    liunian_text = bazi_liunian.invoke({"birth_time": birth_time, "gender": gender, "years": 10})
    return generate_bazi_report(
        birth_time=birth_time,
        gender=gender,
        chart_text=chart_text,
        analysis_text=analysis_text,
        dayun_text=dayun_text,
        liunian_text=liunian_text,
        ai_commentary=ai_commentary,
    )


@router.get("/full_report_pdf")
async def full_report_pdf(birth_time: str, gender: str, sections: str = "",
                          app_ctx: AppContext = Depends(app_context_dependency)):
    """生成 LLM 分节命理报告 PDF。"""
    chat_model = app_ctx.chat_model
    if chat_model is None:
        return {"error": "Xianzhi not initialized"}
    from fastapi import Response

    from app.tools.report_generator import DEFAULT_SECTIONS

    selected = sections.split(",") if sections else DEFAULT_SECTIONS
    try:
        pdf_bytes = await asyncio.to_thread(_build_full_report_pdf, chat_model, birth_time, gender, selected)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="xianzhi_full_report.pdf"'},
        )
    except Exception as e:
        log.exception("生成 PDF 报告失败")
        raise HTTPException(status_code=500, detail=client_error(e))
