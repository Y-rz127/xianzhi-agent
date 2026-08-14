"""管理端鉴权：API Key + 管理员登录会话 token。

两种凭据都可访问管理类接口：
- API Key（`X-API-Key` 头或 `?api_key=`）：机器对机器调用、运维脚本；
- 管理员会话 token（`X-Admin-Token` 头或 `?admin_token=`）：由
  `POST /api/ai/admin/accounts/login` 登录后签发，进程内存储、带有效期，
  前端不再内置任何静态密钥。

未配置 API_KEYS 且无有效会话 token 时默认拒绝（fail-closed）；
仅 DEBUG=true 且未配置 API_KEYS 的本地开发场景放行。

会话 token 存于进程内存：多 worker / 多实例部署时需换 Redis 等共享存储，
或统一改用 API Key。
"""
from __future__ import annotations

import hmac
import secrets
import threading
import time

from app.config import settings

# 管理员会话 token 有效期（秒）
ADMIN_TOKEN_TTL = 12 * 3600

_lock = threading.Lock()
_tokens: dict[str, tuple[str, float]] = {}  # token -> (username, expires_at)


def configured_api_keys() -> set[str]:
    return {k.strip() for k in settings.api_keys.split(",") if k.strip()}


def _prune(now: float) -> None:
    for tok in [t for t, (_, exp) in _tokens.items() if exp <= now]:
        _tokens.pop(tok, None)


def issue_admin_token(username: str) -> str:
    """签发管理员会话 token。"""
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _lock:
        _prune(now)
        _tokens[token] = (username, now + ADMIN_TOKEN_TTL)
    return token


def revoke_admin_token(token: str) -> None:
    if not token:
        return
    with _lock:
        _tokens.pop(token, None)


def verify_admin_token(token: str) -> str:
    """校验会话 token，有效返回用户名，否则返回空串。"""
    if not token:
        return ""
    now = time.time()
    with _lock:
        _prune(now)
        entry = _tokens.get(token)
        return entry[0] if entry else ""


def api_key_valid(provided: str) -> bool:
    if not provided:
        return False
    return any(hmac.compare_digest(provided, key) for key in configured_api_keys())


def is_admin_authorized(api_key: str = "", admin_token: str = "") -> bool:
    """管理类接口统一鉴权判定。"""
    if api_key_valid(api_key):
        return True
    if verify_admin_token(admin_token):
        return True
    # 本地开发：DEBUG=true 且未配置 API_KEYS 时放行，便于调试
    return settings.debug and not configured_api_keys()
