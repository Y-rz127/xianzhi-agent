"""HTTP/WebSocket 客户端 IP 解析（与限流中间件同一套可信代理规则）。"""
from __future__ import annotations

from starlette.requests import Request
from starlette.websockets import WebSocket

from app.core.config import settings


def _header_ip(headers, fallback: str) -> str:
    if settings.trust_proxy_headers:
        xff = headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip() or fallback
    return fallback


def client_ip_from_request(request: Request) -> str:
    fallback = request.client.host if request.client else "unknown"
    return _header_ip(request.headers, fallback)


def client_ip_from_websocket(websocket: WebSocket) -> str:
    fallback = websocket.client.host if websocket.client else "unknown"
    return _header_ip(websocket.headers, fallback)
