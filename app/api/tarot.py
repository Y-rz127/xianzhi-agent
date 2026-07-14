"""塔罗占卜相关接口。"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api import state
from app.logger import log
from app.tarot_app import SPREADS, SpreadKey

router = APIRouter(prefix="/tarot", tags=["Tarot"])


async def _safe_ws_send(websocket: WebSocket, data: dict) -> bool:
    """安全发送 WS 消息，客户端已断开时返回 False 而非抛异常。"""
    try:
        await websocket.send_json(data)
        return True
    except (WebSocketDisconnect, RuntimeError, Exception):
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
      发送 {"action": "draw", "spread": "daily|three_card|relationship"}
        → 推送 {"type": "cards", "data": [...]} + {"type": "done"}

      发送 {"action": "interpret", "spread": "...", "question": "...", "cards": [...]}
        → 流式推送 {"type": "message", "data": "..."}（多次）
        → 推送 {"type": "done"}

      异常时推送 {"type": "error", "data": "..."}
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action", "draw")
            spread = data.get("spread", "daily")
            if spread not in SPREADS:
                spread = "daily"

            if state._tarot_app is None:
                if not await _safe_ws_send(
                    websocket, {"type": "error", "data": "TarotApp not initialized"}
                ):
                    break
                continue

            # ===== 阶段一：抽牌 =====
            if action == "draw":
                try:
                    cards = state._tarot_app.draw_cards(spread)
                except Exception as e:
                    log.exception("塔罗抽牌失败")
                    if not await _safe_ws_send(
                        websocket, {"type": "error", "data": f"抽牌失败: {e}"}
                    ):
                        break
                    continue
                if not await _safe_ws_send(websocket, {"type": "cards", "data": cards}):
                    log.info("客户端已断开（draw 阶段）")
                    break
                await _safe_ws_send(websocket, {"type": "done"})
                continue

            # ===== 阶段二：LLM 解读 =====
            if action == "interpret":
                question = (data.get("question") or "").strip()
                cards = data.get("cards") or []
                if not cards:
                    if not await _safe_ws_send(
                        websocket, {"type": "error", "data": "解读需要 cards 字段"}
                    ):
                        break
                    continue

                client_alive = True
                try:
                    async for chunk in state._tarot_app.divine_stream(question, spread, cards):
                        if not await _safe_ws_send(websocket, {"type": "message", "data": chunk}):
                            client_alive = False
                            log.info("客户端已断开，停止 LLM 解读")
                            break
                except Exception as e:
                    log.exception("塔罗 LLM 解读异常")
                    if client_alive:
                        await _safe_ws_send(websocket, {"type": "error", "data": str(e)})
                    client_alive = False

                if client_alive:
                    await _safe_ws_send(websocket, {"type": "done"})
                continue

            # 未知 action
            if not await _safe_ws_send(
                websocket, {"type": "error", "data": f"未知 action: {action}"}
            ):
                break
    except WebSocketDisconnect:
        log.info("塔罗 WebSocket disconnected")
    except Exception as e:
        log.exception("塔罗 WebSocket error")
        await _safe_ws_send(websocket, {"type": "error", "data": str(e)})
