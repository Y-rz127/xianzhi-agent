"""安全中间件：管理端鉴权 + 单 IP 滑动窗口限流。

- 鉴权：仅对管理后台路径校验，接受 API Key 或管理员会话 token；
  未配置 API_KEYS 且无有效会话 token 时默认拒绝（仅 DEBUG=true 的本地开发放行）。
  HTTP 支持 X-API-Key / X-Admin-Token 请求头或 ?api_key= / ?admin_token= 查询参数；
  WebSocket 同规则（小程序无法自定义头时用 query）。
- 限流：内存滑动窗口，单 IP 每分钟 RATE_LIMIT_PER_MINUTE 次（0=不限流）。
  多 worker 部署时应换 Redis 等共享存储，本实现覆盖单进程场景。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from urllib.parse import parse_qs

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.admin_auth import is_admin_authorized
from app.config import settings

# 豁免鉴权的路径：健康检查、API 文档、静态资源、管理员登录
_AUTH_EXEMPT_PREFIXES = (
    "/api/ai/health",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/ai/admin/accounts/login",
    "/assets/",
    "/static/",
    "/favicon",
)

# 豁免限流的路径：登录接口必须限流（防止密码爆破），故不在此列表
_RATE_EXEMPT_PREFIXES = tuple(
    p for p in _AUTH_EXEMPT_PREFIXES if p != "/api/ai/admin/accounts/login"
)

# 管理后台路径（需 API Key 鉴权；普通用户接口不受影响）
_ADMIN_PREFIXES = (
    "/api/ai/admin/",
    "/api/ai/metrics",
    "/api/ai/rag/",
    "/api/ai/observability/",
    # 命例库管理（增删改查、导入导出）属于管理类操作，需 API Key
    "/api/ai/xianzhi/cases",
    # 反馈管理类接口（回答反馈列表/导出/审核/转案例）需 API Key
    # 注意：submit_feedback(POST /feedback)、submit_answer_feedback(POST /feedback/answer) 仍为用户接口
    # GET /feedback（反馈列表）、DELETE /feedback/{fid} 通过 Depends(require_admin) 鉴权
    "/api/ai/feedback/answers",
)


def _is_auth_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES)


def _is_rate_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in _RATE_EXEMPT_PREFIXES)


def _is_admin_path(path: str) -> bool:
    return any(path.startswith(p) for p in _ADMIN_PREFIXES)


def _extract_credentials(scope: Scope) -> tuple[str, str]:
    """从请求头或查询参数提取 (api_key, admin_token)。"""
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    api_key = headers.get("x-api-key", "")
    admin_token = headers.get("x-admin-token", "")
    if not api_key or not admin_token:
        qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        api_key = api_key or (qs.get("api_key") or [""])[0]
        admin_token = admin_token or (qs.get("admin_token") or [""])[0]
    return api_key.strip(), admin_token.strip()


class ApiKeyAuthMiddleware:
    """管理端鉴权（HTTP + WebSocket 纯 ASGI 中间件）。"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        # CORS 预检请求（OPTIONS）不带自定义头，直接放行
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        # 只对管理后台路径要求管理员凭据，普通用户接口不受影响
        if _is_auth_exempt(path) or not _is_admin_path(path):
            await self.app(scope, receive, send)
            return
        if is_admin_authorized(*_extract_credentials(scope)):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401, "reason": "Unauthorized"})
            return
        response = JSONResponse({"detail": "无效或缺失的管理员凭据"}, status_code=401)
        await response(scope, receive, send)


class RateLimitMiddleware:
    """单 IP 滑动窗口限流（内存实现，单进程有效）。"""

    def __init__(self, app: ASGIApp):
        self.app = app
        self._hits: dict[str, deque] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def _sweep(self, now: float):
        """每分钟清理一次空窗口，防止 IP 表无限增长。"""
        if now - self._last_sweep < 60:
            return
        self._last_sweep = now
        empty = [ip for ip, w in self._hits.items() if not w or now - w[-1] > 120]
        for ip in empty:
            self._hits.pop(ip, None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        limit = settings.rate_limit_per_minute
        if scope["type"] not in ("http", "websocket") or limit <= 0:
            await self.app(scope, receive, send)
            return
        if _is_rate_exempt(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        now = time.monotonic()
        window = self._hits[ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 429, "reason": "Too Many Requests"})
                return
            response = JSONResponse({"detail": "请求过于频繁，请稍后再试"}, status_code=429)
            await response(scope, receive, send)
            return
        window.append(now)
        self._sweep(now)
        await self.app(scope, receive, send)