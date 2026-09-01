"""塔罗占卜相关接口。"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.common import client_error, is_message_too_long, message_too_long_text
from app.api.context import get_app_context
from app.core.logger import log
from app.sub_app.tarot.tarot_app import SPREADS

router = APIRouter(prefix="/tarot", tags=["Tarot"])


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
            {"key": k, "name": v["name"], "desc": v["desc"], "count": v["count"]}
            for k, v in SPREADS.items()
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
                        if not await _safe_ws_send(websocket, {"type": "message", "data": chunk}):
                            client_alive = False
                            log.info("客户端已断开，停止 LLM 解读")
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