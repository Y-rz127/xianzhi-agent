"""WebSocket 公共工具：先知对话与塔罗占卜共用的安全发送。"""
from __future__ import annotations

from fastapi import WebSocket


async def safe_ws_send(websocket: WebSocket, data: dict) -> bool:
    """安全发送 WS 消息，客户端已断开时返回 False 而非抛异常。"""
    try:
        await websocket.send_json(data)
        return True
    except Exception:
        return False
