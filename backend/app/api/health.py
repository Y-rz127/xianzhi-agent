"""readiness 检查：PG / Redis / RAG / 报告队列，不调用 LLM。

liveness 只看进程存活；readiness 失败返回 503，供网关/编排系统摘流量。
所有探测带 1.5s 超时，避免健康检查本身被故障依赖拖死。
"""
from __future__ import annotations

import asyncio
import time

from app.core.config import settings
from app.core.redis_client import get_redis
from app.db.pool import get_pool
from app.rag.vector_store import get_knowledge_base

_PING_TIMEOUT = 1.5


def _pg_ping() -> None:
    with get_pool().connection() as conn:
        conn.execute("SELECT 1")


async def _check_pg() -> dict:
    start = time.monotonic()
    try:
        await asyncio.wait_for(asyncio.to_thread(_pg_ping), timeout=_PING_TIMEOUT)
        return {"ok": True, "latency_ms": round((time.monotonic() - start) * 1000, 2)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:80]}"}


async def _check_redis() -> dict:
    if not settings.redis_url:
        return {"ok": True, "detail": "not_configured"}
    start = time.monotonic()
    try:
        r = await asyncio.wait_for(get_redis(), timeout=_PING_TIMEOUT)
        if r is None:
            return {"ok": False, "error": "unavailable"}
        await asyncio.wait_for(r.ping(), timeout=_PING_TIMEOUT)
        return {"ok": True, "latency_ms": round((time.monotonic() - start) * 1000, 2)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:80]}"}


async def _queue_depth() -> int | None:
    r = await get_redis()
    if r is None:
        return None
    try:
        return int(await asyncio.wait_for(r.llen("xianzhi:report:queue"), timeout=1.0))
    except Exception:
        return None


async def _check_memory() -> dict:
    """记忆层（对话历史）可用性：PG 模式要求建表成功。

    为什么不能复用 `_check_pg`：那条只做裸 psycopg 的 `SELECT 1`，而对话历史走的是
    `langchain_postgres`（底层 SQLAlchemy）。实测过一种"绿着但废了"的组合 ——
    PG 探测正常、记忆层却因原生扩展被系统策略拦截（Windows 智能应用控制拦
    `sqlalchemy/sql/_util_cy.pyd`）而完全不可用：此时 /health/ready 仍报 ok，
    但用户问一句就丢一句。所以这里单独探一次，宁可 503 也别假绿。
    """
    kind = (settings.memory_store_type or "").strip().lower()
    if kind != "postgres":
        return {"ok": True, "detail": kind or "file"}
    try:
        from app.memory import postgres_memory as pg_memory

        status = pg_memory.memory_schema_status()
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:80]}"}
    fatal = status.get("fatal") or ""
    if fatal:
        return {"ok": False, "error": fatal[:120]}
    if not status.get("ready"):
        return {"ok": False, "error": "schema 未就绪"}
    return {"ok": True}


async def readiness() -> dict:
    """返回 readiness 快照；ok=False 时调用方应返回 503。"""
    pg, redis, memory = await asyncio.gather(_check_pg(), _check_redis(), _check_memory())
    rag_ready = get_knowledge_base().ready
    queue_depth = await _queue_depth() if redis.get("ok") else None
    ok = bool(pg.get("ok") and redis.get("ok") and memory.get("ok") and rag_ready)
    return {
        "status": "ok" if ok else "degraded",
        "ok": ok,
        "version": settings.app_version,
        "checks": {
            "postgres": pg,
            "memory": memory,
            "redis": redis,
            "rag": {"ok": rag_ready},
            "report_queue": {"ok": queue_depth is not None, "depth": queue_depth},
        },
    }
