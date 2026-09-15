"""紫微斗数相关接口（排盘只读；解读走既有 LLM；鉴权/限流由全局中间件处理）。"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.context import get_app_context
from app.agent.prompts import ZIWEI_SYSTEM_PROMPT
from app.core.http.errors import client_error
from app.core.llm_throttle import llm_tag
from app.core.logger import log
from app.core.text_extract import normalize_ws_payload_text
from app.sub_app.ziwei import ziwei_app

router = APIRouter(prefix="/ziwei", tags=["ZiWei"])



@router.websocket("/ws")
async def ws_ziwei_interpret(websocket: WebSocket):
    """紫微斗数 AI 简批 WebSocket 流式接口。"""
    await websocket.accept()
    try:
        data = await websocket.receive_text()
        body = json.loads(data)

        date = str(body.get("date") or "").strip()
        gender = str(body.get("gender") or "").strip()
        calendar = str(body.get("calendar") or "solar").strip()
        try:
            time_index = int(body.get("time_index"))
        except (TypeError, ValueError):
            await websocket.send_json({"type": "error", "detail": "需提供合法的时辰序号 time_index(0~12)"})
            await websocket.close()
            return
        leap = bool(body.get("leap", False))
        focus = str(body.get("focus") or "").strip()

        if not date or not gender:
            await websocket.send_json({"type": "error", "detail": "需提供出生日期与性别"})
            await websocket.close()
            return

        await websocket.send_json({"type": "status", "message": "开始解读..."})

        async for text in ziwei_app.interpret_stream(
            date=date,
            time_index=time_index,
            gender=gender,
            calendar=calendar,
            leap=leap,
            focus=focus,
        ):
            payload_text = normalize_ws_payload_text(text)
            if payload_text:
                await websocket.send_json({"type": "message", "data": payload_text})

        await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        log.info("紫微 WebSocket disconnected")
    except Exception as e:
        log.exception("紫微 WebSocket 异常")
        try:
            await websocket.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def _cast_or_400(date: str, time_index: int, gender: str, calendar: str, leap: bool) -> dict:
    try:
        if calendar == "lunar":
            return ziwei_app.cast_chart_dict(
                lunar_date=date, leap=leap, time_index=time_index, gender=gender, calendar="lunar"
            )
        return ziwei_app.cast_chart_dict(
            solar_date=date, time_index=time_index, gender=gender, calendar="solar"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("紫微排盘失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/chart")
async def ziwei_chart(date: str, time_index: int, gender: str, calendar: str = "solar", leap: bool = False):
    """完整命盘（snake_case）。date 依 calendar 取阳历 YYYY-MM-DD 或农历 YYYY-M-D。"""
    return _cast_or_400(date, time_index, gender, calendar, leap)


@router.post("/interpret")
async def ziwei_interpret(body: dict):
    """AI 简批：后端按参数重排盘（不信任前端传盘），拼结构化命盘摘要入 prompt。"""
    date = str(body.get("date") or "").strip()
    gender = str(body.get("gender") or "").strip()
    calendar = str(body.get("calendar") or "solar").strip()
    try:
        time_index = int(body.get("time_index"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="需提供合法的时辰序号 time_index(0~12)")
    leap = bool(body.get("leap", False))
    focus = str(body.get("focus") or "").strip()
    if not date or not gender:
        raise HTTPException(status_code=400, detail="需提供出生日期与性别")

    chart = _cast_or_400(date, time_index, gender, calendar, leap)
    summary = ziwei_app.build_chart_summary(chart, focus)
    prompt = (
        "请为以下紫微斗数命盘做整体简批，并重点讲命宫、财帛、官禄三宫：\n\n"
        f"{summary}\n\n"
        "请严格按系统提示的结构：格局基调 → 命/财/官三宫逐宫 → 三方四正综合 → 一条建议。"
    )
    try:
        with llm_tag("ziwei"):
            response = await get_app_context().chat_model.ainvoke(
                [SystemMessage(content=ZIWEI_SYSTEM_PROMPT), HumanMessage(content=prompt)]
            )
        return {"text": str(response.content)}
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="AI 解读暂不可用，请稍后再试")
