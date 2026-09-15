"""六爻占卜相关接口。"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.context import get_app_context
from app.agent.prompts import LIUYAO_SYSTEM_PROMPT
from app.core.llm_throttle import llm_tag
from app.core.logger import log
from app.core.text_extract import normalize_ws_payload_text
from app.sub_app.liuyao.liuyao_app import cast, interpret_stream as liuyao_interpret_stream

router = APIRouter(prefix="/liuyao", tags=["LiuYao"])



@router.websocket("/ws")
async def ws_liuyao_interpret(websocket: WebSocket):
    """六爻 AI 解读 WebSocket 流式接口。"""
    await websocket.accept()
    try:
        data = await websocket.receive_text()
        body = json.loads(data)

        question = str(body.get("question") or "").strip()
        result = body.get("result")
        if not question or not isinstance(result, dict):
            await websocket.send_json({"type": "error", "detail": "请填写问题并先完成起卦"})
            await websocket.close()
            return

        await websocket.send_json({"type": "status", "message": "开始解读..."})

        async for text in liuyao_interpret_stream(question, result):
            payload_text = normalize_ws_payload_text(text)
            if payload_text:
                await websocket.send_json({"type": "message", "data": payload_text})

        await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        log.info("六爻 WebSocket disconnected")
    except Exception as e:
        log.exception("六爻 WebSocket 异常")
        try:
            await websocket.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.post("/cast")
async def cast_liuyao(body: dict):
    # 起卦方法和数字（可选）
    method = body.get("method", "coins")
    if method not in {"coins", "numbers", "time"}:
        raise HTTPException(status_code=400, detail="不支持的起卦方式")
    numbers = body.get("numbers")
    if method == "numbers" and (
        not isinstance(numbers, list) or len(numbers) < 2 or not all(isinstance(n, int) for n in numbers[:2])
    ):
        raise HTTPException(status_code=400, detail="数字起卦需要输入两个整数")
    return cast(method, numbers)


def _hexagram_text(hexagram: dict | None) -> str:
    name = (hexagram or {}).get("name", "")
    if not name:
        return "无"
    upper = (hexagram.get("upper") or {}).get("name", "")
    lower = (hexagram.get("lower") or {}).get("name", "")
    return f"{name}（上卦{upper}，下卦{lower}）" if upper and lower else name


@router.post("/interpret")
async def interpret_liuyao(body: dict):
    """解读六爻结果"""
    question = str(body.get("question") or "").strip()
    result = body.get("result")
    if not question or not isinstance(result, dict):
        raise HTTPException(status_code=400, detail="请填写问题并先完成起卦")
    lines = {line.get("index"): line for line in result.get("lines") or []}
    moving = result.get("movingLines") or []
    if not moving:
        moving_text = "无（静卦）"
    else:
        moving_text = "；".join(
            f"第{i}爻（老阳，阳动变阴）"
            if (lines.get(i) or {}).get("value") == 9
            else f"第{i}爻（老阴，阴动变阳）"
            if (lines.get(i) or {}).get("value") == 6
            else f"第{i}爻"
            for i in moving
        )
    prompt = (
        f"请为以下六爻占卜做深度解读：\n\n"
        f"占问者的问题：{question}\n\n"
        f"本卦：{_hexagram_text(result.get('original'))}\n"
        f"变卦：{_hexagram_text(result.get('changed'))}\n"
        f"动爻：{moving_text}\n\n"
        f"请按照系统提示中的结构解读：卦象主题 → 动爻解读 → 本变卦演变 → 具体建议。\n"
        f"解读要落到占问者的具体问题上。"
    )
    try:
        with llm_tag("liuyao"):
            response = await get_app_context().chat_model.ainvoke(
                [SystemMessage(content=LIUYAO_SYSTEM_PROMPT), HumanMessage(content=prompt)]
            )
        return {"interpretation": str(response.content)}
    except Exception:
        raise HTTPException(status_code=502, detail="AI 解读暂不可用，请稍后再试")
