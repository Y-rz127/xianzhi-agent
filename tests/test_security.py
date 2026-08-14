"""安全回归测试：管理端鉴权、口令哈希、动态表名校验。

不依赖数据库与外部模型：TestClient 不进入 lifespan，只校验中间件与依赖层行为。
"""
from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from app.api import admin_accounts, admin_auth
from app.memory.postgres_memory import safe_table_name
from main import app

ADMIN_PATHS = [
    "/api/ai/admin/accounts",
    "/api/ai/metrics",
    "/api/ai/rag/status",
    "/api/ai/observability/status",
    "/api/ai/xianzhi/cases",
    "/api/ai/xianzhi/sessions",
]


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """未配置 API_KEYS 且非 DEBUG 的生产式配置。"""
    monkeypatch.setattr(admin_auth.settings, "api_keys", "", raising=False)
    monkeypatch.setattr(admin_auth.settings, "debug", False, raising=False)
    return TestClient(app)


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_admin_paths_reject_anonymous(client: TestClient, path: str) -> None:
    """未配置 API_KEYS 时管理类接口 fail-closed，而不是放行。"""
    assert client.get(path).status_code == 401


def test_admin_paths_accept_session_token(client: TestClient) -> None:
    token = admin_auth.issue_admin_token("pytest")
    try:
        response = client.get("/api/ai/admin/accounts", headers={"X-Admin-Token": token})
        assert response.status_code == 200
    finally:
        admin_auth.revoke_admin_token(token)


def test_revoked_token_is_rejected(client: TestClient) -> None:
    token = admin_auth.issue_admin_token("pytest")
    admin_auth.revoke_admin_token(token)
    assert client.get("/api/ai/admin/accounts", headers={"X-Admin-Token": token}).status_code == 401


def test_session_endpoints_require_ownership(client: TestClient) -> None:
    """会话消息/删除等接口需要归属校验，匿名访问被拒绝。"""
    assert client.get("/api/ai/xianzhi/sessions/other-user-session/messages").status_code == 401
    assert client.delete("/api/ai/xianzhi/sessions/other-user-session").status_code == 401


def test_api_docs_disabled_when_not_debug() -> None:
    from app.config import settings

    if settings.debug:
        pytest.skip("DEBUG=true 时文档按设计开放")
    assert app.openapi_url is None
    assert app.docs_url is None


def test_password_hash_is_salted_pbkdf2() -> None:
    first = admin_accounts._hash_password("s3cret")
    second = admin_accounts._hash_password("s3cret")
    assert first.startswith("pbkdf2$")
    assert first != second  # 每次使用新盐
    assert admin_accounts._verify_password("s3cret", first)
    assert not admin_accounts._verify_password("wrong", first)


def test_legacy_sha256_hash_still_verifies() -> None:
    legacy = hashlib.sha256(b"legacy-pw").hexdigest()
    assert admin_accounts._verify_password("legacy-pw", legacy)
    assert not admin_accounts._verify_password("other", legacy)


@pytest.mark.parametrize("name", ["chat_history; DROP TABLE users", "a-b", "1abc", "", "tbl name"])
def test_safe_table_name_rejects_injection(name: str) -> None:
    with pytest.raises(ValueError):
        safe_table_name(name)


def test_safe_table_name_accepts_identifier() -> None:
    assert safe_table_name("chat_history_v2") == "chat_history_v2"
