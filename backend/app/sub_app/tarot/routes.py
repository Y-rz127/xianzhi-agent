"""塔罗占卜相关接口。"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent.context import get_app_context
from app.core.http.errors import client_error, is_message_too_long, message_too_long_text
from app.core.logger import log
from app.sub_app.tarot.tarot_app import SPREADS

router = APIRouter(prefix="/tarot", tags=["Tarot"])


def _normalize_ws_payload_text(payload: object) -> str:
    """把 WebSocket message payload 统一成纯字符串。

    旧路径有时会把模型块对象、list/dict 结构或对象的 repr 直接塞进
    message 的 data 字段；这会导致前端 `onMessage` 收到非字符串，
    结果在页面上只留下标题而不是真正的解读正文。

    支持的输入格式：
      - str: 直接返回
      - list[str|dict]: 递归提取并拼接
      - dict: 提取 text/content 字段
      - 对象: 尝试 .text/.content 属性或 str()
    """
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        parts = []
        for item in payload:
            text = _normalize_ws_payload_text(item)
            if text:
                parts.append(text)
        return "".join(parts)
    if isinstance(payload, dict):
        # OpenAI/消息块常见形态：{"type":"text","text":"..."}
        # 或 LangChain AIMessageChunk content 字段
        for key in ("text", "content", "delta"):
            val = payload.get(key)
            if isinstance(val, str) and val:
                return val
            if isinstance(val, (list, dict)):
                nested = _normalize_ws_payload_text(val)
                if nested:
                    return nested
        # 兜底：检查所有字符串值
        for val in payload.values():
            if isinstance(val, str) and len(val) > 10:
                return val
        return ""
    # 处理 LangChain MessageChunk 对象或其他对象
    if hasattr(payload, "content"):
        return _normalize_ws_payload_text(getattr(payload, "content"))
    if hasattr(payload, "text"):
        return _normalize_ws_payload_text(getattr(payload, "text"))
    # 最后兜底：转成字符串，但如果太长或包含对象信息则丢弃
    s = str(payload).strip()
    if s and not s.startswith("<") and len(s) < 10000:
        return s
    return ""


async def _safe_ws_send(websocket: WebSocket, data: dict) -> bool:
    """安全发送 WS 消息，客户端已断开时返回 False 而非抛异常。"""
    try:
        await websocket.send_json(data)
        return True
    except Exception:
        return False


@router.get("/spreads")
async def list_spreads():
    """返回支持的牌阵列表。"""
    return {
        "spreads": [
            {"key": k, "name": v["name"], "desc": v["desc"], "count": v["count"]} for k, v in SPREADS.items()
        ]
    }


@router.websocket("/ws")
async def ws_tarot_divine(websocket: WebSocket):
    """塔罗占卜 WebSocket 流式接口。

    协议（通过 action 字段区分两阶段）:
      {"action": "draw", "spread": "..."} → 推送 {"type": "cards"} + {"type": "done"}
      {"action": "interpret", "spread": "...", "question": "...", "cards": [...]}
        → 流式推送 {"type": "message"}（多次）→ 推送 {"type": "done"}
      异常时推送 {"type": "error", "data": "..."}
    """

    async def _ws_error(msg: str) -> bool:
        return await _safe_ws_send(websocket, {"type": "error", "data": msg})

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action", "draw")
            spread = data.get("spread", "daily")
            if spread not in SPREADS:
                spread = "daily"

            tarot_app = get_app_context().tarot_app
            if tarot_app is None:
                if not await _ws_error("TarotApp not initialized"):
                    break
                continue

            if action == "draw":
                try:
                    cards = tarot_app.draw_cards(spread)
                except Exception as e:
                    log.exception("塔罗抽牌失败")
                    if not await _ws_error(client_error(e)):
                        break
                    continue
                if not await _safe_ws_send(websocket, {"type": "cards", "data": cards}):
                    log.info("客户端已断开（draw 阶段）")
                    break
                await _safe_ws_send(websocket, {"type": "done"})
                continue

            if action == "interpret":
                question = (data.get("question") or "").strip()
                cards = data.get("cards") or []
                if is_message_too_long(question):
                    if not await _ws_error(message_too_long_text(question)):
                        break
                    continue
                if not cards:
                    if not await _ws_error("解读需要 cards 字段"):
                        break
                    continue
                client_alive = True
                try:
                    async for chunk in tarot_app.divine_stream(question, spread, cards):
                        text = _normalize_ws_payload_text(chunk)
                        if not await _safe_ws_send(websocket, {"type": "message", "data": text}):
                            client_alive = False
                            log.info("塔罗解读：客户端已断开")
                            break
                except Exception as e:
                    log.exception("塔罗 LLM 解读异常")
                    if client_alive:
                        await _safe_ws_send(websocket, {"type": "error", "data": client_error(e)})
                    client_alive = False
                if client_alive:
                    await _safe_ws_send(websocket, {"type": "done"})
                continue

            if not await _ws_error(f"未知 action: {action}"):
                break
    except WebSocketDisconnect:
        log.info("塔罗 WebSocket disconnected")
    except Exception as e:
        log.exception("塔罗 WebSocket error")
        await _safe_ws_send(websocket, {"type": "error", "data": client_error(e)})
