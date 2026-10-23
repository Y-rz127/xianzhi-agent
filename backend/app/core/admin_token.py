"""管理员短时签名令牌（HMAC-SHA256，无外部依赖）。

令牌只用于管理后台浏览器会话；机器/CLI 仍可通过 API_KEYS 访问。
多副本必须配置同一个 ADMIN_SESSION_SECRET，否则令牌无法互认。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import settings
from app.core.logger import log

_TOKEN_VERSION = 1
_PROCESS_SECRET = secrets.token_hex(32)
_warned = False


def _warn_once(message: str) -> None:
    global _warned
    if _warned:
        return
    _warned = True
    log.warning("[admin-token] {}", message)


def _signing_key() -> bytes:
    """签名密钥：独立配置优先；缺失时回退 API_KEYS，最后用进程随机密钥兜底。"""
    raw = (settings.admin_session_secret or "").strip()
    if raw:
        return raw.encode("utf-8")
    api_key = next((k.strip() for k in settings.api_keys.split(",") if k.strip()), "")
    if api_key:
        _warn_once("ADMIN_SESSION_SECRET 未配置，临时用 API_KEYS 派生签名密钥；生产环境必须配置独立密钥")
        return ("admin-session:" + api_key).encode("utf-8")
    _warn_once("ADMIN_SESSION_SECRET 与 API_KEYS 均未配置，使用进程随机密钥；重启/多副本会使令牌失效")
    return _PROCESS_SECRET.encode("utf-8")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_admin_token(account: dict, ttl_seconds: int | None = None) -> tuple[str, int]:
    """签发管理员令牌，返回 (token, expires_in)。"""
    ttl = int(ttl_seconds if ttl_seconds is not None else settings.admin_token_ttl_seconds)
    now = int(time.time())
    payload = {
        "typ": "admin",
        "v": _TOKEN_VERSION,
        "sub": str(account.get("id") or ""),
        "u": str(account.get("username") or ""),
        "iat": now,
        "exp": now + ttl,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signature = _b64e(hmac.new(_signing_key(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}", ttl


def verify_admin_token(token: str) -> dict | None:
    """校验签名与有效期，失败返回 None。"""
    if not token or token.count(".") != 1:
        return None
    body, signature = token.split(".", 1)
    try:
        expected = hmac.new(_signing_key(), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(signature), expected):
            return None
        payload = json.loads(_b64d(body).decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("typ") != "admin":
            return None
        if int(payload.get("exp") or 0) <= int(time.time()):
            return None
        if not str(payload.get("sub") or "").strip():
            return None
        return payload
    except Exception:
        return None


def extract_bearer(value: str | None) -> str:
    """从 Authorization 头提取 Bearer token；非 Bearer 返回空串。"""
    if not value:
        return ""
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""
