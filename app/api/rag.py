"""RAG 知识库管理接口。

知识问答已并入先知对话流（app/agent/xianzhi_workflow.py 的 theory worker），
本模块只负责知识库文档的增删查与向量索引重建。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.common import api_guard
from app.logger import log
from app.rag.vector_store import KNOWLEDGE_DIR, knowledge_base

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
    with api_guard("上传知识库文档失败"):
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        path.write_bytes(content)
        log.info("上传知识库文档: {}", path.name)
        return {"filename": path.name, "size": path.stat().st_size}


@mgmt_router.delete("/docs/{filename}")
async def delete_rag_doc(filename: str):
    """删除知识库中的指定 markdown 文档。"""
    path = _resolve_doc_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    with api_guard("删除知识库文档失败"):
        path.unlink()
        log.info("删除知识库文档: {}", path.name)
        return {"status": "ok", "filename": path.name}


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
