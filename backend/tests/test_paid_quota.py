"""付费接口主体解析、日配额与报告任务归属测试（不依赖真实 Redis/PG）。"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api import xianzhi_report
from app.core import quota
from app.core.admin_token import create_admin_token
from app.db import principals, report_tasks as rt

pytestmark = pytest.mark.security


class _Redis:
    def __init__(self, count: int):
        self.count = count

    async def eval(self, *args):
        return self.count


def _patch_redis(monkeypatch, count: int | None):
    async def _get():
        return None if count is None else _Redis(count)

    monkeypatch.setattr(quota, "get_redis", _get)


def test_consume_quota_allows_under_limit_and_rejects_over(monkeypatch) -> None:
    _patch_redis(monkeypatch, 1)
    assert asyncio.run(quota.consume_quota("user:u", "report", 10)) is True
    _patch_redis(monkeypatch, 11)
    assert asyncio.run(quota.consume_quota("user:u", "report", 10)) is False


def test_consume_quota_zero_limit_is_unlimited(monkeypatch) -> None:
    async def _no_redis():
        return None

    monkeypatch.setattr(quota, "get_redis", _no_redis)
    assert asyncio.run(quota.consume_quota("user:u", "report", 0)) is True


def test_enforce_quota_maps_over_limit_and_backend_failure(monkeypatch) -> None:
    _patch_redis(monkeypatch, 11)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(quota.enforce_quota("report", {"id": "u1"}, "1.2.3.4", 10))
    assert exc.value.status_code == 429

    _patch_redis(monkeypatch, None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(quota.enforce_quota("report", {"id": "u1"}, "1.2.3.4", 10))
    assert exc.value.status_code == 503


def test_resolve_paid_principal_user_admin_and_invalid(monkeypatch) -> None:
    monkeypatch.setattr(
        principals.user_store, "get_by_token", lambda t: {"id": "u1"} if t == "user-token" else None
    )
    assert asyncio.run(principals.resolve_paid_principal("")) is None
    assert asyncio.run(principals.resolve_paid_principal("user-token")) == {"id": "u1", "kind": "user"}

    token, _ = create_admin_token({"id": "a1", "username": "admin"}, ttl_seconds=60)
    assert asyncio.run(principals.resolve_paid_principal(token)) == {"id": "admin:a1", "kind": "admin"}

    with pytest.raises(principals.InvalidPrincipal):
        asyncio.run(principals.resolve_paid_principal("bad-token"))


def _fake_task(owner: str) -> dict:
    return {
        "id": "t1",
        "kind": "basic_report",
        "status": "pending",
        "error": "",
        "created_at": None,
        "updated_at": None,
        "payload": None,
        "user_id": owner,
    }


def test_report_task_rejects_other_user(monkeypatch) -> None:
    monkeypatch.setattr(rt, "get_task", lambda task_id: _fake_task("user-a"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(xianzhi_report.get_report_task("t1", principal={"id": "user-b"}))
    assert exc.value.status_code == 404


def test_report_task_allows_owner(monkeypatch) -> None:
    monkeypatch.setattr(rt, "get_task", lambda task_id: _fake_task("user-a"))
    out = asyncio.run(xianzhi_report.get_report_task("t1", principal={"id": "user-a"}))
    assert out["task_id"] == "t1"
