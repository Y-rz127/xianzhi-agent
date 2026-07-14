"""恋爱大师（Love App）相关接口。"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

from app.api import state
from app.logger import log

router = APIRouter(prefix="/love_app", tags=["Love App"])


@router.get("/chat/sse")
async def chat_with_love_app(message: str, chat_id: str = "default"):
    if state._love_app is None:
        return {"error": "LoveApp not initialized"}

    async def event_stream():
        async for chunk in state._love_app.chat_stream(message, chat_id):
            yield {"event": "message", "data": chunk}
        yield {"event": "message", "data": "[DONE]"}

    return EventSourceResponse(event_stream())


async def _safe_ws_send(websocket: WebSocket, data: dict) -> bool:
    """安全发送 WS 消息，客户端已断开时返回 False 而非抛异常。"""
    try:
        await websocket.send_json(data)
        return True
    except (WebSocketDisconnect, RuntimeError, Exception):
        return False


@router.websocket("/ws")
async def ws_chat_with_love_app(websocket: WebSocket):
    """恋爱大师 WebSocket 流式接口（小程序无 EventSource，用 WS 替代 SSE）。"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            chat_id = data.get("chat_id", data.get("conversation_id", "default"))
            if state._love_app is None:
                if not await _safe_ws_send(websocket, {"type": "error", "data": "LoveApp not initialized"}):
                    break
                continue
            client_alive = True
            try:
                async for chunk in state._love_app.chat_stream(message, chat_id):
                    if not await _safe_ws_send(websocket, {"type": "message", "data": chunk}):
                        client_alive = False
                        log.info("客户端已断开，停止流式发送")
                        break
            except Exception as e:
                log.exception("LoveApp WebSocket stream error")
                if client_alive:
                    await _safe_ws_send(websocket, {"type": "error", "data": str(e)})
                client_alive = False
            if client_alive:
                await _safe_ws_send(websocket, {"type": "done"})
    except WebSocketDisconnect:
        log.info("LoveApp WebSocket disconnected")
    except Exception as e:
        log.exception("LoveApp WebSocket error")
        await _safe_ws_send(websocket, {"type": "error", "data": str(e)})


@router.get("/sessions")
async def list_love_sessions(prefix: str = "web-love"):
    """获取恋爱大师会话列表。
    prefix 可选值：web-love（默认，PC 端）/ mp-love（小程序端）。
    """
    from app.memory.postgres_memory import get_session_info
    return get_session_info(prefix)


@router.delete("/sessions/{session_id}")
async def delete_love_session(session_id: str):
    from app.memory.postgres_memory import delete_session
    delete_session(session_id)
    return {"status": "ok"}


@router.post("/sessions/{session_id}/clear")
async def clear_love_session(session_id: str):
    """清空当前会话的消息记录，但保留会话本身（不新建会话）。"""
    from app.memory.postgres_memory import clear_session
    clear_session(session_id)
    return {"status": "ok"}


@router.get("/sessions/{session_id}/messages")
async def get_love_session_messages(session_id: str):
    from app.memory.postgres_memory import get_messages
    return get_messages(session_id)
