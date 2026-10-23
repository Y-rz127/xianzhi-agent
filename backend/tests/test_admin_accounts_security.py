"""管理员本地账号的密码哈希与兼容迁移测试。"""
from __future__ import annotations

import asyncio
import hashlib

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import admin_accounts
from app.api.admin_accounts import _hash_admin_password, _verify_admin_password
from app.api.deps import require_admin
from app.core.admin_token import create_admin_token, verify_admin_token

pytestmark = pytest.mark.security


def _json_request(payload: bytes) -> Request:
    """构造供路由函数直接调用的最小 JSON 请求。"""
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/login",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )


def test_admin_password_uses_versioned_salted_pbkdf2() -> None:
    first = _hash_admin_password("correct horse battery staple")
    second = _hash_admin_password("correct horse battery staple")

    assert first.startswith("pbkdf2_sha256$")
    assert first != second
    assert _verify_admin_password("correct horse battery staple", first) == (True, False)
    assert _verify_admin_password("wrong password", first) == (False, False)


def test_legacy_sha256_is_accepted_only_for_migration() -> None:
    legacy = hashlib.sha256("old-password".encode("utf-8")).hexdigest()

    assert _verify_admin_password("old-password", legacy) == (True, True)
    assert _verify_admin_password("wrong-password", legacy) == (False, True)


def test_login_migrates_legacy_hash(monkeypatch, tmp_path) -> None:
    data_file = tmp_path / "admin_accounts.json"
    monkeypatch.setattr(admin_accounts, "ADMIN_DATA_FILE", data_file)
    legacy = hashlib.sha256("old-password".encode("utf-8")).hexdigest()
    admin_accounts._save_accounts(
        [{"id": "legacy", "username": "admin", "password_hash": legacy, "enabled": True}]
    )

    request = _json_request(b'{"username":"admin","password":"old-password"}')
    result = asyncio.run(admin_accounts.admin_login(request))

    assert result["id"] == "legacy"
    assert admin_accounts._load_accounts()[0]["password_hash"].startswith("pbkdf2_sha256$")
    payload = verify_admin_token(result["token"])
    assert payload is not None and payload["sub"] == "legacy"


def test_malformed_hash_fails_closed() -> None:
    assert _verify_admin_password("password", "pbkdf2_sha256$bad") == (False, False)
    assert _verify_admin_password("password", None) == (False, False)
    assert _verify_admin_password(
        "password", "pbkdf2_sha256$1000001$00$00"
    ) == (False, False)


def test_admin_token_round_trip_and_rejects_tamper_and_expiry() -> None:
    token, ttl = create_admin_token({"id": "acc_1", "username": "admin"}, ttl_seconds=60)
    payload = verify_admin_token(token)
    assert ttl == 60
    assert payload is not None and payload["sub"] == "acc_1"

    # 改签名中段而不是末位：base64url 末位有非规范填充位，改末位可能解码出同一字节
    payload_part, sig = token.rsplit(".", 1)
    middle = len(sig) // 2
    tampered_sig = sig[:middle] + ("a" if sig[middle] != "a" else "b") + sig[middle + 1:]
    assert verify_admin_token(f"{payload_part}.{tampered_sig}") is None

    expired, _ = create_admin_token({"id": "acc_1", "username": "admin"}, ttl_seconds=-1)
    assert verify_admin_token(expired) is None


def test_require_admin_accepts_bearer_token_and_rejects_invalid_token() -> None:
    token, _ = create_admin_token({"id": "acc_1", "username": "admin"}, ttl_seconds=60)
    payload = require_admin(authorization=f"Bearer {token}", api_key=None, x_api_key=None)
    assert payload is not None and payload["sub"] == "acc_1"

    with pytest.raises(HTTPException) as exc:
        require_admin(authorization="Bearer invalid", api_key=None, x_api_key=None)
    assert exc.value.status_code == 401
