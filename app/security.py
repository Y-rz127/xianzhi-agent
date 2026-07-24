"""安全中间件：API Key 鉴权 + 单 IP 滑动窗口限流。

- 鉴权：API_KEYS 为空时关闭（本地开发默认）；非空时仅对管理后台路径校验。
  HTTP 支持 X-API-Key 请求头或 ?api_key= 查询参数；WebSocket 同规则（小程序无法自定义头时用 query）。
- 限流：内存滑动窗口，单 IP 每分钟 RATE_LIMIT_PER_MINUTE 次（0=不限流）。
  多 worker 部署时应换 Redis 等共享存储，本实现覆盖单进程场景。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from urllib.parse import parse_qs

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings

# 豁免路径：健康检查、API 文档、静态资源不限流不鉴权
_EXEMPT_PREFIXES = (
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

# 管理后台路径（需 API Key 鉴权；普通用户接口不受影响）
_ADMIN_PREFIXES = (
    "/api/ai/admin/",
    "/api/ai/metrics",
    "/api/ai/rag/",
    "/api/ai/observability/",
)


def _is_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in _EXEMPT_PREFIXES)


def _is_admin_path(path: str) -> bool:
    return any(path.startswith(p) for p in _ADMIN_PREFIXES)


def _extract_api_key(scope: Scope) -> str:
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    provided = headers.get("x-api-key", "")
    if not provided:
        qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        provided = (qs.get("api_key") or [""])[0]
    return provided


class ApiKeyAuthMiddleware:
    """API Key 鉴权（HTTP + WebSocket 纯 ASGI 中间件）。"""

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
        keys = {k.strip() for k in settings.api_keys.split(",") if k.strip()}
        path = scope.get("path", "")
        if not keys or _is_exempt(path):
            await self.app(scope, receive, send)
            return
        # 只对管理后台路径要求 API Key，普通用户接口不受影响
        if not _is_admin_path(path):
            await self.app(scope, receive, send)
            return
        if _extract_api_key(scope) in keys:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401, "reason": "Unauthorized"})
            return
        response = JSONResponse({"detail": "无效或缺失的 API Key"}, status_code=401)
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
        if _is_exempt(scope.get("path", "")):
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