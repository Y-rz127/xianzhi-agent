"""安全中间件：API Key 鉴权 + 单 IP 滑动窗口限流。

- 鉴权：API_KEYS 为空时关闭；非空时仅校验管理后台路径。
  HTTP 支持 X-API-Key 请求头或 ?api_key= 查询参数；WebSocket 同规则。
- 限流：优先 Redis 滑动窗口（多副本共享同一上限）；
  Redis 未配置/不可用时降级为进程内存滑动窗口（单机兜底，
  多副本场景每副本各限一份，上限按副本数放宽）。
  经可信代理（CDN/CLB）部署时开启 TRUST_PROXY_HEADERS，
  从 X-Forwarded-For 取真实客户端 IP（前提：容器仅能经网关访问）。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from urllib.parse import parse_qs

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings

# 豁免路径：健康检查、文档、静态资源不限流不鉴权
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
# 命例库/反馈管理类接口属管理操作；submit_feedback 等用户接口不在此列
_ADMIN_PREFIXES = (
    "/api/ai/admin/",
    "/api/ai/metrics",
    "/api/ai/rag/",
    "/api/ai/observability/",
    "/api/ai/xianzhi/cases",
    "/api/ai/feedback/answers",
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


def _client_ip(scope: Scope) -> str:
    """取真实客户端 IP。TRUST_PROXY_HEADERS 开启时从 X-Forwarded-For 首段取，
    否则用直连地址（本地开发/未过代理场景，防伪造）。"""
    client = scope.get("client")
    ip = client[0] if client else "unknown"
    if settings.trust_proxy_headers:
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        xff = headers.get("x-forwarded-for", "")
        if xff:
            ip = xff.split(",")[0].strip() or ip
    return ip


class ApiKeyAuthMiddleware:
    """API Key 鉴权（HTTP + WebSocket 纯 ASGI 中间件）。"""

    def __init__(self, app: ASGIApp):
        self.app = app
        self._api_keys = {k.strip() for k in settings.api_keys.split(",") if k.strip()}

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        # CORS 预检请求（OPTIONS）不带自定义头，直接放行
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        # 关闭鉴权或非管理路径时不校验
        if not self._api_keys or _is_exempt(path) or not _is_admin_path(path):
            await self.app(scope, receive, send)
            return
        if _extract_api_key(scope) in self._api_keys:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401, "reason": "Unauthorized"})
            return
        await JSONResponse({"detail": "无效或缺失的 API Key"}, status_code=401)(scope, receive, send)


class RateLimitMiddleware:
    """单 IP 滑动窗口限流：Redis 共享判定为主，进程内存为兜底。"""

    def __init__(self, app: ASGIApp):
        self.app = app
        self._hits: dict[str, deque] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def _sweep(self, now: float):
        """每分钟清理空窗口，防止 IP 表无限增长。"""
        if now - self._last_sweep >= 60:
            self._last_sweep = now
            for ip, w in list(self._hits.items()):
                if not w or now - w[-1] > 120:
                    del self._hits[ip]

    def _local_allow(self, ip: str, limit: int) -> bool:
        """进程内存滑动窗口判定（Redis 不可用时的单机兜底）。"""
        now = time.monotonic()
        window = self._hits[ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        self._sweep(now)
        return True

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 429, "reason": "Too Many Requests"})
        else:
            await JSONResponse({"detail": "请求过于频繁，请稍后再试"}, status_code=429)(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        limit = settings.rate_limit_per_minute
        if scope["type"] not in ("http", "websocket") or limit <= 0 or _is_exempt(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        ip = _client_ip(scope)
        from app.core.redis_client import rate_limit_allow

        verdict = await rate_limit_allow(f"rl:{ip}", limit, 60)
        if verdict is None:
            verdict = self._local_allow(ip, limit)
        if not verdict:
            await self._reject(scope, receive, send)
            return
        await self.app(scope, receive, send)
