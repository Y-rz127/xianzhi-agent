"""先知（Xianzhi）相关接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

from app.api import state
from app.api.common import check_message_length, client_error, is_message_too_long, message_too_long_text
from app.config import settings
from app.logger import log

router = APIRouter(prefix="/xianzhi", tags=["Xianzhi"])


def _mount_chart_context(agent, birth_time: str | None, gender: str | None, sect: int = 2, yun_sect: int = 1):
    """如果提供了出生信息，直接挂载到该会话 Agent 上下文。"""
    if birth_time and gender:
        try:
            agent.set_chart_context(birth_time, gender, sect, yun_sect)
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
):
    """先知 SSE 流式对话接口（支持挂载出生信息，流式返回 + 可选 chart_context 事件）。"""
    check_message_length(message)
    try:
        agent, lock = state.get_xianzhi(conversation_id)
    except RuntimeError:
        return {"error": "Xianzhi not initialized"}

    async def event_stream():
        # 会话实例级锁：同一会话串行，不同会话并行；
        # sect 设置与命盘挂载均在锁内完成，避免并发污染
        async with lock:
            agent._sect = sect
            agent._yun_sect = yun_sect
            _mount_chart_context(agent, birth_time, gender, sect, yun_sect)
            try:
                async for chunk in agent.arun_stream(message, verbose=verbose):
                    yield {"event": "message", "data": chunk}
                # 流结束后，如果后端从工具调用中提取到出生信息，通知前端（覆盖自然语言输入场景）
                if agent._last_birth_info:
                    bi = agent._last_birth_info
                    import json as _json
                    yield {
                        "event": "chart_context",
                        "data": _json.dumps({"birth_time": bi.get("time"), "gender": bi.get("gender")}),
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
    except (WebSocketDisconnect, RuntimeError, Exception):
        return False


@router.websocket("/ws")
async def ws_chat_with_xianzhi(websocket: WebSocket):
    """先知 WebSocket 流式对话接口（小程序无 SSE，用 WS 替代）。"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            conversation_id = data.get("conversation_id", "default")
            birth_time = data.get("birth_time")
            gender = data.get("gender")
            sect = data.get("sect", 2)
            yun_sect = data.get("yun_sect", 1)
            verbose = bool(data.get("verbose", False))
            if is_message_too_long(message):
                if not await _safe_ws_send(websocket, {"type": "error", "data": message_too_long_text(message)}):
                    break
                continue
            try:
                agent, lock = state.get_xianzhi(conversation_id)
            except RuntimeError:
                if not await _safe_ws_send(websocket, {"type": "error", "data": "Xianzhi not initialized"}):
                    break
                continue
            async with lock:
                agent._sect = sect
                agent._yun_sect = yun_sect
                _mount_chart_context(agent, birth_time, gender, sect, yun_sect)
                client_alive = True
                try:
                    async for chunk in agent.arun_stream(message, verbose=verbose):
                        if not await _safe_ws_send(websocket, {"type": "message", "data": chunk}):
                            client_alive = False
                            log.info("客户端已断开，停止流式发送")
                            break
                except Exception as e:
                    log.exception("WebSocket stream error")
                    if client_alive:
                        await _safe_ws_send(websocket, {"type": "error", "data": client_error(e)})
                    client_alive = False
                # 流结束后，如果后端从工具调用中提取到出生信息，通知前端（覆盖自然语言输入场景）
                if client_alive and agent._last_birth_info:
                    bi = agent._last_birth_info
                    await _safe_ws_send(websocket, {
                        "type": "chart_context",
                        "data": {"birth_time": bi.get("time"), "gender": bi.get("gender")},
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
):
    """先知同步对话接口（run 在线程池执行，避免阻塞事件循环）。"""
    check_message_length(message)
    try:
        agent, lock = state.get_xianzhi(conversation_id)
    except RuntimeError:
        return {"error": "Xianzhi not initialized"}
    async with lock:
        agent._sect = sect
        agent._yun_sect = yun_sect
        _mount_chart_context(agent, birth_time, gender, sect, yun_sect)
        try:
            # run 是同步阻塞调用，放到线程池避免卡住事件循环
            import asyncio
            return {"result": await asyncio.to_thread(agent.run, message)}
        except Exception as e:
            log.exception("Sync chat error")
            return {"error": client_error(e)}


@router.get("/sessions")
async def list_xianzhi_sessions(prefix: str = "web-xianzhi"):
    """获取先知会话列表。
    prefix 可选值：web-xianzhi（默认，PC 端）/ mp-xianzhi（小程序端）。
    """
    from app.memory.postgres_memory import get_session_info
    return get_session_info(prefix)


@router.get("/sessions/mine")
async def list_my_sessions(token: str = Query(None)):
    """我的对话：按登录用户隔离的先知会话列表（小程序「我的」页用）。"""
    from app.db import users as user_store
    user = user_store.get_by_token(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    from app.memory.postgres_memory import get_session_info
    return get_session_info(prefix="mp-xianzhi", user_id=user["id"])


@router.delete("/sessions/{session_id}")
async def delete_xianzhi_session(session_id: str):
    """删除先知会话（含消息记录）。"""
    from app.memory.postgres_memory import delete_session
    delete_session(session_id)
    return {"status": "ok"}


@router.post("/sessions/{session_id}/clear")
async def clear_xianzhi_session(session_id: str):
    """清空当前会话的消息记录，但保留会话本身（不新建会话）。"""
    from app.memory.postgres_memory import clear_session
    clear_session(session_id)
    return {"status": "ok"}


@router.get("/sessions/{session_id}/messages")
async def get_xianzhi_session_messages(session_id: str):
    """获取会话的完整消息记录。"""
    from app.memory.postgres_memory import get_messages
    return get_messages(session_id)


@router.get("/sessions/{session_id}/birth-info")
async def get_xianzhi_session_birth_info(session_id: str):
    """从会话历史中的排盘工具调用提取出生信息，供前端恢复命盘上下文。"""
    from app.memory.postgres_memory import get_birth_info_from_session
    info = get_birth_info_from_session(session_id)
    return info or {"time": None, "gender": None}


@router.get("/cache_stats")
async def cache_stats():
    """获取排盘缓存统计。"""
    from app.tools.cache import bazi_cache
    return bazi_cache.stats()


@router.get("/chart")
async def get_chart(birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1):
    """直接排盘，返回四柱/五行/大运/流年等结构化数据。"""
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
    from app.tools.bazi import _normalize_birth_time
    try:
        # 标准化出生时间（支持公历+时辰、农历、节日等格式，与 bazi_chart 工具入口一致）
        birth_time = _normalize_birth_time(birth_time)
        parse_birth(birth_time)
        parse_gender(gender)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    chart = build_bazi_chart(birth_time, gender, sect=sect, yun_sect=yun_sect, dayun_count=8, liunian_years=5)
    payload = chart_to_api_dict(chart)
    payload.update({
        "chartText": format_chart_text(chart),
        "analysisText": format_analysis_text(chart, "整体命盘"),
        "dayunText": format_dayun_text(chart),
        "liunianText": format_liunian_text(chart),
    })
    return payload


@router.get("/report")
async def generate_report(birth_time: str, gender: str):
    from fastapi import Response
    from app.tools.bazi import bazi_chart, bazi_analysis, bazi_dayun, bazi_liunian
    from app.tools.pdf_report import generate_bazi_report

    chart_text = bazi_chart.invoke({"birth_time": birth_time, "gender": gender})
    analysis_text = bazi_analysis.invoke({"birth_time": birth_time, "gender": gender, "question": "整体命盘"})
    dayun_text = bazi_dayun.invoke({"birth_time": birth_time, "gender": gender, "count": 8})
    liunian_text = bazi_liunian.invoke({"birth_time": birth_time, "gender": gender, "years": 10})

    try:
        pdf_bytes = generate_bazi_report(
            birth_time=birth_time,
            gender=gender,
            chart_text=chart_text,
            analysis_text=analysis_text,
            dayun_text=dayun_text,
            liunian_text=liunian_text,
        )
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="xianzhi_bazi_report.pdf"'})
    except Exception as e:
        log.exception("PDF 报告生成失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/full_report")
async def full_report(birth_time: str, gender: str, sections: str = ""):
    """生成 LLM 分节命理报告（Markdown）。"""
    chat_model = state.get_chat_model()
    if chat_model is None:
        return {"error": "Xianzhi not initialized"}
    from app.tools.report_generator import generate_full_report, DEFAULT_SECTIONS

    selected = sections.split(",") if sections else DEFAULT_SECTIONS
    try:
        content = generate_full_report(chat_model, birth_time, gender, selected)
        return {"content": content}
    except Exception as e:
        log.exception("生成命理报告失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/full_report_pdf")
async def full_report_pdf(birth_time: str, gender: str, sections: str = ""):
    """生成 LLM 分节命理报告 PDF。"""
    chat_model = state.get_chat_model()
    if chat_model is None:
        return {"error": "Xianzhi not initialized"}
    from fastapi import Response
    from app.tools.report_generator import generate_full_report, DEFAULT_SECTIONS
    from app.tools.pdf_report import generate_bazi_report
    from app.tools.bazi import bazi_chart, bazi_analysis, bazi_dayun, bazi_liunian

    selected = sections.split(",") if sections else DEFAULT_SECTIONS
    try:
        ai_commentary = generate_full_report(chat_model, birth_time, gender, selected)
        chart_text = bazi_chart.invoke({"birth_time": birth_time, "gender": gender})
        analysis_text = bazi_analysis.invoke({"birth_time": birth_time, "gender": gender, "question": "整体命盘"})
        dayun_text = bazi_dayun.invoke({"birth_time": birth_time, "gender": gender, "count": 8})
        liunian_text = bazi_liunian.invoke({"birth_time": birth_time, "gender": gender, "years": 10})
        pdf_bytes = generate_bazi_report(
            birth_time=birth_time,
            gender=gender,
            chart_text=chart_text,
            analysis_text=analysis_text,
            dayun_text=dayun_text,
            liunian_text=liunian_text,
            ai_commentary=ai_commentary,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="xianzhi_full_report.pdf"'},
        )
    except Exception as e:
        log.exception("生成 PDF 报告失败")
        raise HTTPException(status_code=500, detail=client_error(e))
