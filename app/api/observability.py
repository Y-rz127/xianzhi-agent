"""可观测性与健康检查接口。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api import state
from app.observability import get_metrics, get_status

router = APIRouter(tags=["Observability"])


@router.get("/health")
async def health():
    """健康检查：返回 RAG 就绪状态、工作流后端与 Agent 池统计。"""
    return {
        "status": "ok",
        "rag_ready": state._rag_chain is not None,
        "workflow_backend": state.workflow_backend(),
        "agent_pool": state.agent_pool_stats(),
    }


@router.get("/observability/status")
async def observability_status():
    """返回系统可观测性状态。"""
    return get_status()


@router.get("/metrics")
async def metrics():
    """返回 API 请求指标快照。"""
    return get_metrics()
