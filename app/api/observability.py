"""可观测性与健康检查接口。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api import state
from app.observability import get_metrics, get_status

router = APIRouter(tags=["Observability"])


@router.get("/health")
async def health():
    return {"status": "ok", "rag_ready": state._rag_chain is not None}


@router.get("/observability/status")
async def observability_status():
    return get_status()


@router.get("/metrics")
async def metrics():
    """返回 API 请求指标快照。"""
    return get_metrics()
