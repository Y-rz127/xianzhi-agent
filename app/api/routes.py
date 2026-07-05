"""REST 接口（对应 Java AiController）。"""
from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse
from app.logger import log
from app.api.chart_cases import router as chart_cases_router

router = APIRouter(prefix="/ai", tags=["AI"])
router.include_router(chart_cases_router, prefix="/xianzhi")
_xianzhi = None
_love_app = None
_rag_chain = None


def set_instances(xianzhi, love_app, rag_chain=None):
    global _xianzhi, _love_app, _rag_chain
    _xianzhi = xianzhi
    _love_app = love_app
    _rag_chain = rag_chain


def _mount_chart_context(birth_time: str | None, gender: str | None, sect: int = 2, yun_sect: int = 1):
    """如果提供了出生信息，直接挂载到当前 Agent 上下文。"""
    if _xianzhi is None:
        return
    if birth_time and gender:
        try:
            _xianzhi.set_chart_context(birth_time, gender, sect, yun_sect)
        except Exception as e:
            log.warning("通过 API 挂载命盘上下文失败: {}", e)


@router.get("/xianzhi/chat")
async def chat_with_xianzhi(
    message: str,
    conversation_id: str = "default",
    birth_time: str | None = None,
    gender: str | None = None,
    sect: int = 2,
    yun_sect: int = 1,
    verbose: bool = False,
):
    if _xianzhi is None:
        return {"error": "Xianzhi not initialized"}
    _xianzhi.set_conversation_id(conversation_id)
    _mount_chart_context(birth_time, gender, sect, yun_sect)

    async def event_stream():
        # 单例 Agent 并发保护：串行化执行避免状态互相覆盖
        async with _xianzhi._lock:
            _xianzhi._sect = sect
            _xianzhi._yun_sect = yun_sect
            try:
                async for chunk in _xianzhi.arun_stream(message, verbose=verbose):
                    yield {"event": "message", "data": chunk}
                yield {"event": "message", "data": "[DONE]"}
            except Exception as e:
                log.exception("SSE stream error")
                yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_stream())


@router.websocket("/xianzhi/ws")
async def ws_chat_with_xianzhi(websocket: WebSocket):
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
            if _xianzhi is None:
                await websocket.send_json({"type": "error", "data": "Xianzhi not initialized"})
                continue
            _xianzhi.set_conversation_id(conversation_id)
            _mount_chart_context(birth_time, gender, sect, yun_sect)
            async with _xianzhi._lock:
                _xianzhi._sect = sect
                _xianzhi._yun_sect = yun_sect
                try:
                    async for chunk in _xianzhi.arun_stream(message, verbose=verbose):
                        await websocket.send_json({"type": "message", "data": chunk})
                except Exception as e:
                    log.exception("WebSocket stream error")
                    await websocket.send_json({"type": "error", "data": str(e)})
                    continue
            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
    except Exception as e:
        log.exception("WebSocket error")
        await websocket.send_json({"type": "error", "data": str(e)})


@router.websocket("/love_app/ws")
async def ws_chat_with_love_app(websocket: WebSocket):
    """恋爱大师 WebSocket 流式接口（小程序无 EventSource，用 WS 替代 SSE）。"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            chat_id = data.get("chat_id", data.get("conversation_id", "default"))
            if _love_app is None:
                await websocket.send_json({"type": "error", "data": "LoveApp not initialized"})
                continue
            try:
                async for chunk in _love_app.chat_stream(message, chat_id):
                    await websocket.send_json({"type": "message", "data": chunk})
            except Exception as e:
                log.exception("LoveApp WebSocket stream error")
                await websocket.send_json({"type": "error", "data": str(e)})
                continue
            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        log.info("LoveApp WebSocket disconnected")
    except Exception as e:
        log.exception("LoveApp WebSocket error")
        await websocket.send_json({"type": "error", "data": str(e)})


@router.websocket("/xianzhi/rag/ws")
async def ws_chat_with_rag(websocket: WebSocket):
    """RAG 知识库 WebSocket 流式接口（小程序无 EventSource，用 WS 替代 SSE）。"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            session_id = data.get("session_id", data.get("conversation_id", "default"))
            if _rag_chain is None:
                await websocket.send_json({"type": "error", "data": "RAG chain not initialized"})
                continue
            try:
                async for chunk in _rag_chain.chat_stream(message, session_id):
                    await websocket.send_json({"type": "message", "data": chunk})
            except Exception as e:
                log.exception("RAG WebSocket stream error")
                await websocket.send_json({"type": "error", "data": str(e)})
                continue
            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        log.info("RAG WebSocket disconnected")
    except Exception as e:
        log.exception("RAG WebSocket error")
        await websocket.send_json({"type": "error", "data": str(e)})


@router.get("/xianzhi/chat/sync")
async def chat_with_xianzhi_sync(
    message: str,
    conversation_id: str = "default",
    birth_time: str | None = None,
    gender: str | None = None,
    sect: int = 2,
    yun_sect: int = 1,
):
    if _xianzhi is None:
        return {"error": "Xianzhi not initialized"}
    _xianzhi.set_conversation_id(conversation_id)
    _mount_chart_context(birth_time, gender, sect, yun_sect)
    async with _xianzhi._lock:
        _xianzhi._sect = sect
        _xianzhi._yun_sect = yun_sect
        try:
            return {"result": _xianzhi.run(message)}
        except Exception as e:
            log.exception("Sync chat error")
            return {"error": str(e)}


@router.get("/xianzhi/rag")
async def chat_with_rag(message: str, session_id: str = "default"):
    if _rag_chain is None:
        return {"error": "RAG chain not initialized"}

    async def event_stream():
        try:
            async for chunk in _rag_chain.chat_stream(message, session_id):
                yield {"event": "message", "data": chunk}
            yield {"event": "message", "data": "[DONE]"}
        except Exception as e:
            log.exception("RAG SSE stream error")
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_stream())


@router.get("/xianzhi/rag/sync")
async def chat_with_rag_sync(message: str, session_id: str = "default"):
    if _rag_chain is None:
        return {"error": "RAG chain not initialized"}
    return {"result": _rag_chain.chat(message, session_id)}


@router.get("/xianzhi/sessions")
async def list_xianzhi_sessions():
    from app.memory.postgres_memory import get_session_info
    return get_session_info("xianzhi")


@router.delete("/xianzhi/sessions/{session_id}")
async def delete_xianzhi_session(session_id: str):
    from app.memory.postgres_memory import delete_session
    delete_session(session_id)
    return {"status": "ok"}


@router.get("/xianzhi/sessions/{session_id}/messages")
async def get_xianzhi_session_messages(session_id: str):
    from app.memory.postgres_memory import get_messages
    return get_messages(session_id)


@router.get("/love_app/chat/sse")
async def chat_with_love_app(message: str, chat_id: str = "default"):
    if _love_app is None:
        return {"error": "LoveApp not initialized"}

    async def event_stream():
        async for chunk in _love_app.chat_stream(message, chat_id):
            yield {"event": "message", "data": chunk}
        yield {"event": "message", "data": "[DONE]"}

    return EventSourceResponse(event_stream())


@router.get("/love_app/sessions")
async def list_love_sessions():
    from app.memory.postgres_memory import get_session_info
    return get_session_info("love")


@router.delete("/love_app/sessions/{session_id}")
async def delete_love_session(session_id: str):
    from app.memory.postgres_memory import delete_session
    delete_session(session_id)
    return {"status": "ok"}


@router.get("/love_app/sessions/{session_id}/messages")
async def get_love_session_messages(session_id: str):
    from app.memory.postgres_memory import get_messages
    return get_messages(session_id)


@router.get("/xianzhi/hehun")
async def hehun(birth_time_a: str, gender_a: str, birth_time_b: str, gender_b: str):
    """合婚分析。直接调用合婚工具，无需 Xianzhi 实例。"""
    from fastapi import HTTPException
    from app.tools.bazi import bazi_hehun
    try:
        result = bazi_hehun.invoke({
            "birth_time_a": birth_time_a, "gender_a": gender_a,
            "birth_time_b": birth_time_b, "gender_b": gender_b,
        })
        if result and result.startswith("合婚失败"):
            raise HTTPException(status_code=400, detail=result)
        return {"result": result}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("合婚分析失败")
        raise HTTPException(status_code=500, detail="合婚分析失败: {}".format(e))

@router.get("/xianzhi/huangli")
async def huangli(year: int = None, month: int = None, day: int = None):
    """获取指定日期的黄历信息。"""
    from fastapi import HTTPException
    from lunar_python import Solar
    import datetime
    if year is None:
        today = datetime.date.today()
        year, month, day = today.year, today.month, today.day
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise HTTPException(status_code=400, detail="month 必须在 1-12，day 必须在 1-31")
    try:
        solar = Solar.fromYmd(year, month, day)
        lunar = solar.getLunar()
        times = lunar.getTimes()
        ji_shi = []
        xiong_shi = []
        for t in times:
            is_ji = t.getTianShenLuck() == "吉"
            item = {
                "ganzhi": t.getGanZhi(),
                "time": f"{t.getMinHm()}-{t.getMaxHm()}",
                "isJi": is_ji,
                "tianShen": t.getTianShen(),
                "tianShenType": t.getTianShenType(),
                "sha": t.getSha() or "",
            }
            if is_ji:
                ji_shi.append(item)
            else:
                xiong_shi.append(item)
        return {
            "solar": f"{year}-{month:02d}-{day:02d}",
            "lunar": f"{lunar.getYearInChinese()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
            "yearGanZhi": lunar.getYearInGanZhi(),
            "monthGanZhi": lunar.getMonthInGanZhi(),
            "dayGanZhi": lunar.getDayInGanZhi(),
            "shengXiao": lunar.getYearShengXiao(),
            "yi": lunar.getDayYi()[:10],
            "ji": lunar.getDayJi()[:10],
            "chong": lunar.getDayChongDesc() or "",
            "sha": lunar.getDaySha() or "",
            "jieQi": lunar.getJieQi() or "",
            "naYin": lunar.getDayNaYin() or "",
            "xiu": lunar.getXiu() or "",
            "xiuLuck": lunar.getXiuLuck() or "",
            "xiuSong": (lunar.getXiuSong() or "")[:60],
            "jiShen": lunar.getDayJiShen()[:8] if lunar.getDayJiShen() else [],
            "xiongSha": lunar.getDayXiongSha()[:8] if lunar.getDayXiongSha() else [],
            "jiShi": ji_shi,
            "xiongShi": xiong_shi,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("黄历查询失败")
        raise HTTPException(status_code=400, detail="黄历查询失败: {}".format(e))

@router.get("/xianzhi/cache_stats")
async def cache_stats():
    """获取排盘缓存统计。"""
    from app.tools.cache import bazi_cache
    return bazi_cache.stats()

@router.get("/xianzhi/chart")
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
    try:
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


@router.get("/health")
async def health():
    return {"status": "ok", "rag_ready": _rag_chain is not None}


@router.get("/xianzhi/report")
async def generate_report(birth_time: str, gender: str):
    from fastapi import Response
    from app.tools.bazi import bazi_chart, bazi_analysis, bazi_dayun
    from app.tools.pdf_report import generate_bazi_report

    chart_text = bazi_chart.invoke({"birth_time": birth_time, "gender": gender})
    analysis_text = bazi_analysis.invoke({"birth_time": birth_time, "gender": gender, "question": "整体命盘"})
    dayun_text = bazi_dayun.invoke({"birth_time": birth_time, "gender": gender, "count": 8})

    try:
        pdf_bytes = generate_bazi_report(
            birth_time=birth_time,
            gender=gender,
            chart_text=chart_text,
            analysis_text=analysis_text,
            dayun_text=dayun_text,
        )
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="xianzhi_bazi_report.pdf"'})
    except Exception as e:
        log.exception("PDF 报告生成失败")
        raise HTTPException(status_code=500, detail="PDF 生成失败: {}".format(e))


@router.get("/xianzhi/full_report")
async def full_report(birth_time: str, gender: str, sections: str = ""):
    """生成 LLM 分节命理报告（Markdown）。"""
    if _xianzhi is None:
        return {"error": "Xianzhi not initialized"}
    from app.tools.report_generator import generate_full_report, DEFAULT_SECTIONS

    selected = sections.split(",") if sections else DEFAULT_SECTIONS
    try:
        content = generate_full_report(_xianzhi.chat_model, birth_time, gender, selected)
        return {"content": content}
    except Exception as e:
        log.exception("生成命理报告失败")
        raise HTTPException(status_code=500, detail="报告生成失败: {}".format(e))


@router.get("/xianzhi/full_report_pdf")
async def full_report_pdf(birth_time: str, gender: str, sections: str = ""):
    """生成 LLM 分节命理报告 PDF。"""
    if _xianzhi is None:
        return {"error": "Xianzhi not initialized"}
    from fastapi import Response
    from app.tools.report_generator import generate_full_report, DEFAULT_SECTIONS
    from app.tools.pdf_report import generate_bazi_report
    from app.tools.bazi import bazi_chart, bazi_analysis, bazi_dayun

    selected = sections.split(",") if sections else DEFAULT_SECTIONS
    try:
        ai_commentary = generate_full_report(_xianzhi.chat_model, birth_time, gender, selected)
        chart_text = bazi_chart.invoke({"birth_time": birth_time, "gender": gender})
        analysis_text = bazi_analysis.invoke({"birth_time": birth_time, "gender": gender, "question": "整体命盘"})
        dayun_text = bazi_dayun.invoke({"birth_time": birth_time, "gender": gender, "count": 8})
        pdf_bytes = generate_bazi_report(
            birth_time=birth_time,
            gender=gender,
            chart_text=chart_text,
            analysis_text=analysis_text,
            dayun_text=dayun_text,
            ai_commentary=ai_commentary,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="xianzhi_full_report.pdf"'},
        )
    except Exception as e:
        log.exception("生成 PDF 报告失败")
        raise HTTPException(status_code=500, detail="PDF 生成失败: {}".format(e))


@router.get("/observability/status")
async def observability_status():
    from app.observability import get_status
    return get_status()
