"""RAG 知识库问答与管理接口。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

from app.api import state
from app.api.common import check_message_length, client_error, is_message_too_long, message_too_long_text
from app.logger import log
from app.rag.vector_store import KNOWLEDGE_DIR, knowledge_base

# 问答相关接口（保持与前端已有调用兼容）
chat_router = APIRouter(prefix="/xianzhi", tags=["RAG"])
# 知识库管理接口
mgmt_router = APIRouter(prefix="/rag", tags=["RAG"])


def _resolve_doc_path(filename: str) -> Path:
    """安全解析知识库文件路径，禁止目录遍历。"""
    name = Path(filename).name
    if not name or name != filename or ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = KNOWLEDGE_DIR / name
    try:
        path.relative_to(KNOWLEDGE_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="非法文件路径") from exc
    return path


def _list_markdown_files() -> list[dict]:
    """列出 knowledge_docs 目录下所有 markdown 文件。"""
    if not KNOWLEDGE_DIR.exists():
        return []
    files = []
    for md in sorted(KNOWLEDGE_DIR.glob("*.md")):
        stat = md.stat()
        files.append({
            "filename": md.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return files


# ---------- 问答接口 ----------

@chat_router.get("/rag")
async def chat_with_rag(message: str, session_id: str = "default"):
    """RAG 知识库 SSE 流式问答接口。"""
    check_message_length(message)
    if state._rag_chain is None:
        return {"error": "RAG chain not initialized"}

    async def event_stream():
        try:
            async for chunk in state._rag_chain.chat_stream(message, session_id):
                yield {"event": "message", "data": chunk}
            yield {"event": "message", "data": "[DONE]"}
        except Exception as e:
            log.exception("RAG SSE stream error")
            yield {"event": "error", "data": client_error(e)}

    return EventSourceResponse(event_stream())


async def _safe_ws_send(websocket: WebSocket, data: dict) -> bool:
    """安全发送 WS 消息，客户端已断开时返回 False 而非抛异常。"""
    try:
        await websocket.send_json(data)
        return True
    except (WebSocketDisconnect, RuntimeError, Exception):
        return False


@chat_router.websocket("/rag/ws")
async def ws_chat_with_rag(websocket: WebSocket):
    """RAG 知识库 WebSocket 流式接口（小程序无 EventSource，用 WS 替代 SSE）。"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            session_id = data.get("session_id", data.get("conversation_id", "default"))
            if is_message_too_long(message):
                if not await _safe_ws_send(websocket, {"type": "error", "data": message_too_long_text(message)}):
                    break
                continue
            if state._rag_chain is None:
                if not await _safe_ws_send(websocket, {"type": "error", "data": "RAG chain not initialized"}):
                    break
                continue
            client_alive = True
            try:
                async for chunk in state._rag_chain.chat_stream(message, session_id):
                    if not await _safe_ws_send(websocket, {"type": "message", "data": chunk}):
                        client_alive = False
                        log.info("客户端已断开，停止流式发送")
                        break
            except Exception as e:
                log.exception("RAG WebSocket stream error")
                if client_alive:
                    await _safe_ws_send(websocket, {"type": "error", "data": client_error(e)})
                client_alive = False
            if client_alive:
                await _safe_ws_send(websocket, {"type": "done"})
    except WebSocketDisconnect:
        log.info("RAG WebSocket disconnected")
    except Exception as e:
        log.exception("RAG WebSocket error")
        await _safe_ws_send(websocket, {"type": "error", "data": client_error(e)})


@chat_router.get("/rag/sync")
async def chat_with_rag_sync(message: str, session_id: str = "default"):
    """RAG 知识库同步问答接口（一次性返回完整结果）。"""
    if state._rag_chain is None:
        return {"error": "RAG chain not initialized"}
    return {"result": state._rag_chain.chat(message, session_id)}



@chat_router.post("/rag/sessions/{session_id}/clear")
async def clear_rag_session(session_id: str):
    """清空 RAG 问答会话的消息记录，保留会话 ID。"""
    import uuid
    from app.config import settings
    from app.memory.postgres_memory import _get_pool
    try:
        session_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, session_id))
        with _get_pool().connection() as conn:
            conn.execute("DELETE FROM rag_message_store WHERE session_id = %s", (session_uuid,))
        return {"status": "ok"}
    except Exception as e:
        log.exception("清空 RAG 会话消息失败: {}", session_id)
        return {"status": "error", "detail": str(e)}

# ---------- 知识库管理接口 ----------

@mgmt_router.get("/docs")
async def list_rag_docs():
    """列出所有知识库 markdown 文档。"""
    return {"files": _list_markdown_files()}


@mgmt_router.post("/docs/upload")
async def upload_rag_doc(file: UploadFile = File(...)):
    """上传新的 markdown 文档到知识库目录。"""
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="仅支持上传 .md 文件")

    path = _resolve_doc_path(filename)
    try:
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        path.write_bytes(content)
        log.info("上传知识库文档: {}", path.name)
        return {"filename": path.name, "size": path.stat().st_size}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("上传知识库文档失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@mgmt_router.delete("/docs/{filename}")
async def delete_rag_doc(filename: str):
    """删除知识库中的指定 markdown 文档。"""
    path = _resolve_doc_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        path.unlink()
        log.info("删除知识库文档: {}", path.name)
        return {"status": "ok", "filename": path.name}
    except Exception as e:
        log.exception("删除知识库文档失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@mgmt_router.post("/docs/rebuild")
async def rebuild_rag_index(force: bool = False):
    """重新初始化 RAG 向量知识库。

    默认按文档指纹判断：文档未变更时直接复用已有索引（零 embedding 调用）；
    force=true 时无视指纹强制全量重建。
    """
    try:
        ready = knowledge_base.init(force=force)
        return {"ready": ready, "embedding": knowledge_base.embedding_id}
    except Exception as e:
        log.exception("重建 RAG 向量库失败")
        raise HTTPException(status_code=500, detail="重建失败，请查看服务日志")


@mgmt_router.get("/status")
async def rag_status():
    """获取 RAG 知识库状态。"""
    return {
        "ready": knowledge_base.ready,
        "count": len(_list_markdown_files()),
    }
