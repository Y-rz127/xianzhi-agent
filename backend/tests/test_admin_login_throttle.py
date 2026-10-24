"""管理员登录防爆破：单 IP 限流与账号连续失败锁定。"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import admin_accounts
from app.core import login_throttle
from app.core.config import settings

pytestmark = pytest.mark.security


def _request(payload: bytes, ip: str = "10.0.0.1") -> Request:
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
            "path": "/admin/accounts/login",
            "headers": [(b"content-type", b"application/json")],
            "client": (ip, 12345),
        },
        receive,
    )


def _setup_account(monkeypatch, tmp_path, password: str = "correct-password") -> None:
    data_file = tmp_path / "admin_accounts.json"
    monkeypatch.setattr(admin_accounts, "ADMIN_DATA_FILE", data_file)
    admin_accounts._save_accounts(
        [{
            "id": "acc_admin",
            "username": "admin",
            "password_hash": admin_accounts._hash_admin_password(password),
            "enabled": True,
        }]
    )


@pytest.fixture(autouse=True)
def _reset_local_state():
    login_throttle._local_ip_hits.clear()
    login_throttle._local_fails.clear()
    login_throttle._local_locks.clear()
    yield
    login_throttle._local_ip_hits.clear()
    login_throttle._local_fails.clear()
    login_throttle._local_locks.clear()


@pytest.fixture
def no_redis(monkeypatch):
    """强制走进程内存兜底，保证用例不依赖本机 Redis。"""

    async def _none():
        return None

    async def _no_rate_limit(key, limit, window_seconds):
        return None

    monkeypatch.setattr(login_throttle, "get_redis", _none)
    monkeypatch.setattr(login_throttle, "rate_limit_allow", _no_rate_limit)


def _login(payload: dict) -> dict:
    import json

    return asyncio.run(admin_accounts.admin_login(_request(json.dumps(payload).encode())))


def test_ip_limit_blocks_before_password_verification(monkeypatch, tmp_path, no_redis):
    _setup_account(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "admin_login_ip_limit", 1)
    monkeypatch.setattr(settings, "admin_login_max_fails", 0)

    with pytest.raises(HTTPException) as first:
        _login({"username": "admin", "password": "wrong"})
    assert first.value.status_code == 401

    # 第二次即使密码正确，也应先被 IP 限流拦下
    with pytest.raises(HTTPException) as second:
        _login({"username": "admin", "password": "correct-password"})
    assert second.value.status_code == 429


def test_account_locks_after_consecutive_failures(monkeypatch, tmp_path, no_redis):
    _setup_account(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "admin_login_ip_limit", 0)
    monkeypatch.setattr(settings, "admin_login_max_fails", 2)
    monkeypatch.setattr(settings, "admin_login_lock_seconds", 300)

    with pytest.raises(HTTPException) as first:
        _login({"username": "admin", "password": "wrong"})
    assert first.value.status_code == 401

    with pytest.raises(HTTPException) as second:
        _login({"username": "admin", "password": "wrong"})
    assert second.value.status_code == 429

    # 锁定期内即使密码正确也不放行
    with pytest.raises(HTTPException) as locked:
        _login({"username": "admin", "password": "correct-password"})
    assert locked.value.status_code == 429


def test_successful_login_clears_failure_counter(monkeypatch, tmp_path, no_redis):
    _setup_account(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "admin_login_ip_limit", 0)
    monkeypatch.setattr(settings, "admin_login_max_fails", 2)
    monkeypatch.setattr(settings, "admin_login_lock_seconds", 300)

    with pytest.raises(HTTPException):
        _login({"username": "admin", "password": "wrong"})
    assert _login({"username": "admin", "password": "correct-password"})["username"] == "admin"

    # 成功登录后计数清零：再错一次只是普通 401，不会直接锁定
    with pytest.raises(HTTPException) as again:
        _login({"username": "admin", "password": "wrong"})
    assert again.value.status_code == 401


class _FakeRedis:
    """最小 Redis 桩：验证失败计数与锁定 key 的写入/清理。"""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.locks: dict[str, int | None] = {}

    async def eval(self, script, numkeys, key, window_ms):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def set(self, key, value, ex=None):
        self.locks[key] = ex

    async def exists(self, key):
        return int(key in self.locks)

    async def delete(self, *keys):
        for key in keys:
            self.counts.pop(key, None)
            self.locks.pop(key, None)


def test_redis_backend_sets_lock_ttl_and_clears(monkeypatch):
    fake = _FakeRedis()

    async def _fake_redis():
        return fake

    monkeypatch.setattr(login_throttle, "get_redis", _fake_redis)
    monkeypatch.setattr(settings, "admin_login_max_fails", 2)
    monkeypatch.setattr(settings, "admin_login_lock_seconds", 300)

    assert asyncio.run(login_throttle.record_login_failure("Admin")) is False
    assert asyncio.run(login_throttle.record_login_failure("admin")) is True
    assert fake.locks[login_throttle._LOCK_KEY_PREFIX + "admin"] == 300
    assert asyncio.run(login_throttle.account_login_locked("admin")) is True

    asyncio.run(login_throttle.clear_login_failures("admin"))
    assert fake.counts == {}
    assert fake.locks == {}
    assert asyncio.run(login_throttle.account_login_locked("admin")) is False
