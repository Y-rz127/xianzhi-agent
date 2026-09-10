"""合婚接口（URL 与历史一致：/ai/xianzhi/hehun）。"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.api.common import client_error
from app.api.context import get_app_context
from app.core.logger import log
from app.sub_app.hehun.hehun_app import analyze, analyze_stream as hehun_analyze_stream

router = APIRouter(prefix="/xianzhi", tags=["Tools"])


def _normalize_ws_payload_text(data) -> str:
    """归一化 WebSocket 消息中的文本字段（兼容多种格式）。"""
    if data is None:
        return ""
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        for key in ("text", "content", "delta", "result"):
            val = data.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        if "choices" in data and isinstance(data["choices"], list):
            choice = data["choices"][0] if data["choices"] else {}
            delta = choice.get("delta", {})
            if isinstance(delta, dict) and delta.get("content"):
                return str(delta["content"]).strip()
        for val in data.values():
            if (
                isinstance(val, str)
                and len(val) > 20
                and not val.startswith("<")
                and "object at 0x" not in val
            ):
                return val.strip()
        return ""
    text = str(data)
    if len(text) > 200 or "<__" in text or "object at 0x" in text:
        return ""
    return text.strip()


@router.websocket("/hehun/ws")
async def ws_hehun_analyze(websocket: WebSocket):
    """合婚分析 WebSocket 流式接口。"""
    await websocket.accept()
    try:
        data = await websocket.receive_text()
        body = json.loads(data)

        birth_time_a = str(body.get("birthTimeA") or "").strip()
        gender_a = str(body.get("genderA") or "").strip()
        birth_time_b = str(body.get("birthTimeB") or "").strip()
        gender_b = str(body.get("genderB") or "").strip()
        sect = int(body.get("sect", 2))
        longitude_a = body.get("longitudeA")
        longitude_b = body.get("longitudeB")

        if not birth_time_a or not gender_a or not birth_time_b or not gender_b:
            await websocket.send_json({"type": "error", "detail": "需提供双方完整的出生信息"})
            await websocket.close()
            return

        await websocket.send_json({"type": "status", "message": "开始合婚分析..."})

        async for text in hehun_analyze_stream(
            birth_time_a=birth_time_a,
            gender_a=gender_a,
            birth_time_b=birth_time_b,
            gender_b=gender_b,
            sect=sect,
            longitude_a=longitude_a,
            longitude_b=longitude_b,
        ):
            payload_text = _normalize_ws_payload_text(text)
            if payload_text:
                await websocket.send_json({"type": "message", "data": payload_text})

        await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        log.info("合婚 WebSocket disconnected")
    except Exception as e:
        log.exception("合婚 WebSocket 异常")
        try:
            await websocket.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/hehun")
async def hehun(
    birth_time_a: str,
    gender_a: str,
    birth_time_b: str,
    gender_b: str,
    sect: int = 2,
    longitude_a: float | None = None,
    longitude_b: float | None = None,
):
    """合婚分析：先调规则工具拿基础数据，再调 LLM 做综合解读。"""
    try:
        # 排盘与 LLM 调用均为同步阻塞计算，放线程池避免卡住事件循环
        try:
            llm = get_app_context().chat_model
        except RuntimeError:
            llm = None
        result = await asyncio.to_thread(
            analyze,
            birth_time_a,
            gender_a,
            birth_time_b,
            gender_b,
            sect=sect,
            longitude_a=longitude_a,
            longitude_b=longitude_b,
            chat_model=llm,
        )
        if result.startswith("合婚失败"):
            raise HTTPException(status_code=400, detail=result)
        return {"result": result}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("合婚分析失败")
        raise HTTPException(status_code=500, detail=client_error(e))
