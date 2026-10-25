"""P1-09 request_id、readiness 与 metrics 鉴权回归测试。"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.health as health
from app.core.config import settings
from app.core.observability import (
    get_metrics,
    prometheus_text,
    record_llm_call,
    record_request,
)
from app.core.request_context import (
    RequestIdMiddleware,
    get_request_id,
    normalize_request_id,
)
from app.core.security import _is_admin_path, _is_auth_exempt, _is_rate_exempt

pytestmark = pytest.mark.security


def test_normalize_request_id_accepts_valid_and_generates_invalid():
    assert normalize_request_id("client-rid-123") == "client-rid-123"
    generated = normalize_request_id("bad id with spaces")
    assert len(generated) == 16
    assert generated.isalnum()


def test_request_id_middleware_generates_and_echoes_header():
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/x")
    def x():
        return {"rid": get_request_id()}

    client = TestClient(app)
    first = client.get("/x")
    assert first.status_code == 200
    assert first.headers["x-request-id"] == first.json()["rid"]
    assert len(first.headers["x-request-id"]) == 16

    second = client.get("/x", headers={"X-Request-ID": "client-rid-123"})
    assert second.headers["x-request-id"] == "client-rid-123"
    assert second.json()["rid"] == "client-rid-123"


def test_record_request_keeps_request_id_in_recent_errors():
    record_request("GET", "/unit-test/rid", 500, 0.01, request_id="rid-unit-test")
    errors = get_metrics()["recent_errors"]
    assert any(e.get("request_id") == "rid-unit-test" for e in errors)


def test_metrics_requires_admin_but_stays_rate_limit_exempt():
    assert _is_auth_exempt("/api/ai/metrics") is False
    assert _is_rate_exempt("/api/ai/metrics") is True
    assert _is_auth_exempt("/api/ai/observability/status") is False
    assert _is_rate_exempt("/api/ai/observability/status") is True
    assert _is_auth_exempt("/api/health/ready") is True


def test_prometheus_endpoint_stays_admin_only():
    assert _is_auth_exempt("/api/ai/metrics/prometheus") is False
    assert _is_admin_path("/api/ai/metrics/prometheus") is True


def _prom_value(text: str, metric_line_prefix: str) -> float:
    for line in text.splitlines():
        if line.startswith(metric_line_prefix):
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"未找到指标行: {metric_line_prefix}")


def test_prometheus_text_exports_histogram_and_llm_counters():
    record_request("GET", "/unit-test/prom", 200, 0.2)
    record_llm_call("unit-model", "unit-tag", 10, 5, 100.0)

    text = prometheus_text()
    labels = 'method="GET",path="/unit-test/prom"'
    count = _prom_value(text, f"xianzhi_http_request_duration_seconds_count{{{labels}}}")
    inf = _prom_value(text, f'xianzhi_http_request_duration_seconds_bucket{{{labels},le="+Inf"}}')
    within_300ms = _prom_value(
        text, f'xianzhi_http_request_duration_seconds_bucket{{{labels},le="0.3"}}'
    )

    assert count >= 1
    assert inf == count  # Prometheus 累计桶：+Inf 等于总次数
    assert 0 < within_300ms <= count
    assert 'xianzhi_http_requests_total{method="GET",path="/unit-test/prom"}' in text
    assert 'xianzhi_llm_calls_total{model="unit-model",tag="unit-tag"}' in text
    assert 'xianzhi_llm_tokens_total{model="unit-model",tag="unit-tag",kind="prompt"}' in text
    assert "xianzhi_llm_estimated_cost_yuan_total" in text


def test_prometheus_text_escapes_label_values():
    record_request("GET", '/unit-test/escape"x', 404, 0.01)

    text = prometheus_text()

    assert 'path="/unit-test/escape\\"x"' in text


class _KB:
    ready = True


def _patch_health_checks(
    monkeypatch,
    pg_ok: bool,
    redis_ok: bool,
    queue_depth: int | None = 0,
    memory_ok: bool = True,
):
    async def _pg():
        return {"ok": pg_ok} if pg_ok else {"ok": False, "error": "pg down"}

    async def _redis():
        return {"ok": redis_ok} if redis_ok else {"ok": False, "error": "redis down"}

    async def _queue():
        return queue_depth

    async def _memory():
        return {"ok": memory_ok} if memory_ok else {"ok": False, "error": "memory down"}

    monkeypatch.setattr(health, "_check_pg", _pg)
    monkeypatch.setattr(health, "_check_redis", _redis)
    monkeypatch.setattr(health, "_check_memory", _memory)
    monkeypatch.setattr(health, "_queue_depth", _queue)
    monkeypatch.setattr(health, "get_knowledge_base", lambda: _KB())


def test_readiness_ok_when_all_dependencies_up(monkeypatch):
    _patch_health_checks(monkeypatch, pg_ok=True, redis_ok=True, queue_depth=3)

    result = asyncio.run(health.readiness())

    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["checks"]["report_queue"]["depth"] == 3


def test_readiness_reports_release_version(monkeypatch):
    """灰度/回滚需要从健康检查直接确认实例版本。"""
    _patch_health_checks(monkeypatch, pg_ok=True, redis_ok=True)
    monkeypatch.setattr(settings, "app_version", "release-2026-10-24")

    result = asyncio.run(health.readiness())

    assert result["version"] == "release-2026-10-24"


def test_readiness_degraded_when_pg_down(monkeypatch):
    _patch_health_checks(monkeypatch, pg_ok=False, redis_ok=True)

    result = asyncio.run(health.readiness())

    assert result["ok"] is False
    assert result["status"] == "degraded"
    assert result["checks"]["postgres"]["ok"] is False


def test_readiness_degraded_when_rag_not_ready(monkeypatch):
    class _NotReady:
        ready = False

    _patch_health_checks(monkeypatch, pg_ok=True, redis_ok=True)
    monkeypatch.setattr(health, "get_knowledge_base", lambda: _NotReady())

    result = asyncio.run(health.readiness())

    assert result["ok"] is False
    assert result["checks"]["rag"]["ok"] is False


def test_readiness_degraded_when_memory_store_unavailable(monkeypatch):
    """PG 通了但记忆层不可用（原生扩展被策略拦）时必须报 not ready。

    这就是"绿着但废了"的场景：`SELECT 1` 走裸 psycopg 是通的，可对话历史走
    langchain_postgres（SQLAlchemy），它一挂用户问一句丢一句。
    """
    _patch_health_checks(monkeypatch, pg_ok=True, redis_ok=True, memory_ok=False)

    result = asyncio.run(health.readiness())

    assert result["ok"] is False
    assert result["status"] == "degraded"
    assert result["checks"]["postgres"]["ok"] is True  # PG 本身没问题
    assert result["checks"]["memory"]["ok"] is False  # 但记忆层不可用


class _MemStatus:
    def __init__(self, ready: bool, fatal: str = ""):
        self._status = {"ready": ready, "fatal": fatal}

    def __call__(self):
        return self._status


def test_check_memory_skips_probe_on_file_backend(monkeypatch):
    """文件记忆后端不依赖 PG：直接 ok，带 detail 说明。"""
    monkeypatch.setattr(settings, "memory_store_type", "file")

    assert asyncio.run(health._check_memory()) == {"ok": True, "detail": "file"}


def test_check_memory_reports_fatal_import_failure(monkeypatch):
    """依赖被拦（ImportError）→ not ready，并把原因带出来方便排查。"""
    from app.memory import postgres_memory as pg_memory

    monkeypatch.setattr(settings, "memory_store_type", "postgres")
    monkeypatch.setattr(
        pg_memory,
        "memory_schema_status",
        _MemStatus(False, "ImportError: DLL load failed while importing _util_cy"),
    )

    result = asyncio.run(health._check_memory())

    assert result["ok"] is False
    assert "_util_cy" in result["error"]


def test_check_memory_ok_when_schema_ready(monkeypatch):
    from app.memory import postgres_memory as pg_memory

    monkeypatch.setattr(settings, "memory_store_type", "postgres")
    monkeypatch.setattr(pg_memory, "memory_schema_status", _MemStatus(True))

    assert asyncio.run(health._check_memory())["ok"] is True


def test_check_memory_not_ready_before_schema_init(monkeypatch):
    """还没建过表（启动早期/尚未初始化）→ not ready，而不是乐观放行。"""
    from app.memory import postgres_memory as pg_memory

    monkeypatch.setattr(settings, "memory_store_type", "postgres")
    monkeypatch.setattr(pg_memory, "memory_schema_status", _MemStatus(False))

    result = asyncio.run(health._check_memory())

    assert result["ok"] is False
    assert "schema" in result["error"]
