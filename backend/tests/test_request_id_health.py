"""P1-09 request_id、readiness 与 metrics 鉴权回归测试。"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.health as health
from app.core.config import settings
from app.core.observability import get_metrics, record_request
from app.core.request_context import (
    RequestIdMiddleware,
    get_request_id,
    normalize_request_id,
)
from app.core.security import _is_auth_exempt, _is_rate_exempt

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


class _KB:
    ready = True


def _patch_health_checks(monkeypatch, pg_ok: bool, redis_ok: bool, queue_depth: int | None = 0):
    async def _pg():
        return {"ok": pg_ok} if pg_ok else {"ok": False, "error": "pg down"}

    async def _redis():
        return {"ok": redis_ok} if redis_ok else {"ok": False, "error": "redis down"}

    async def _queue():
        return queue_depth

    monkeypatch.setattr(health, "_check_pg", _pg)
    monkeypatch.setattr(health, "_check_redis", _redis)
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
