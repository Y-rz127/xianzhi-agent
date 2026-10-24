"""可观测性与健康检查接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.agent.context import AppContext
from app.api.deps import app_context_dependency, require_admin
from app.core.observability import get_metrics, get_status, prometheus_text
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
async def observability_status(_admin: dict | None = Depends(require_admin)):
    """返回系统可观测性状态（管理员）。"""
    return get_status()


@router.get("/metrics")
async def metrics(_admin: dict | None = Depends(require_admin)):
    """返回 API 请求指标快照（管理员，含成本与错误信息）。"""
    return get_metrics()


@router.get("/metrics/prometheus", response_class=PlainTextResponse)
async def metrics_prometheus(_admin: dict | None = Depends(require_admin)):
    """Prometheus 抓取端点（X-API-Key）：每副本各暴露一份，跨副本聚合由 Prometheus 完成。"""
    return PlainTextResponse(
        prometheus_text(), media_type="text/plain; version=0.0.4; charset=utf-8"
    )
