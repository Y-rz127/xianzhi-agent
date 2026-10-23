"""付费接口调用主体解析：用户 token 或管理员短时令牌。"""
from __future__ import annotations

import asyncio

from app.core.admin_token import verify_admin_token
from app.db import users as user_store


class InvalidPrincipal(ValueError):
    """token 无法解析为用户或管理员。"""


async def resolve_paid_principal(token: str | None) -> dict | None:
    """解析 token；空 token 返回 None（游客），无效 token 抛 InvalidPrincipal。"""
    t = (token or "").strip()
    if not t:
        return None
    user = await asyncio.to_thread(user_store.get_by_token, t)
    if user:
        return {"id": str(user["id"]), "kind": "user"}
    payload = verify_admin_token(t)
    if payload:
        return {"id": "admin:" + str(payload["sub"]), "kind": "admin"}
    raise InvalidPrincipal("登录已失效")
