"""可观测性与健康检查接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.context import AppContext, app_context_dependency
from app.core.observability import get_metrics, get_status
from app.rag.vector_store import get_knowledge_base

router = APIRouter(tags=["Observability"])


@router.get("/health")
async def health(app_ctx: AppContext = Depends(app_context_dependency)):
    """健康检查：返回知识库就绪状态、工作流后端与 Agent 池统计。"""
    return {
        "status": "ok",
        "rag_ready": get_knowledge_base().ready,
        "workflow_backend": app_ctx.workflow_backend(),
        "agent_pool": app_ctx.agent_pool_stats(),
    }


@router.get("/observability/status")
async def observability_status():
    """返回系统可观测性状态。"""
    return get_status()


@router.get("/metrics")
async def metrics():
    """返回 API 请求指标快照。"""
    return get_metrics()
