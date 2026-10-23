"""请求上下文：X-Request-ID 透传 + 日志关联。

纯 ASGI 中间件而不是 BaseHTTPMiddleware：SSE 的流式 body 在 ASGI app 调用结束前
持续产出，上下文能覆盖到整个流；BaseHTTPMiddleware 提前返回会丢掉生成阶段日志。
"""
from __future__ import annotations

import contextvars
import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def normalize_request_id(value: str | None) -> str:
    """沿用调用方传入的合法 ID，否则生成 16 位短 UUID。"""
    raw = (value or "").strip()
    if _REQUEST_ID_RE.match(raw):
        return raw
    return uuid.uuid4().hex[:16]


def set_request_id(value: str) -> contextvars.Token:
    return _request_id.set(value)


def reset_request_id(token: contextvars.Token) -> None:
    _request_id.reset(token)


def get_request_id() -> str:
    return _request_id.get()


class RequestIdMiddleware:
    """为每个 HTTP/WS 连接设置 request_id，并回写 HTTP 响应头。"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        rid = normalize_request_id(headers.get("x-request-id"))
        token = set_request_id(rid)
        try:
            if scope["type"] == "ws":
                await self.app(scope, receive, send)
                return

            async def send_with_header(message: Message) -> None:
                if message["type"] == "http.response.start":
                    raw_headers = list(message.get("headers", []))
                    if not any(key.lower() == b"x-request-id" for key, _ in raw_headers):
                        raw_headers.append((b"x-request-id", rid.encode("latin-1")))
                    message = {**message, "headers": raw_headers}
                await send(message)

            await self.app(scope, receive, send_with_header)
        finally:
            reset_request_id(token)
