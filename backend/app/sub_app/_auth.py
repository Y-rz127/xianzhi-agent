"""子应用（塔罗/六爻/紫微/合婚）付费解读的调用主体解析。

sub_app 不能反向依赖 api 层，这里直接复用 db 层的 token 解析。
"""
from __future__ import annotations

from fastapi import Header, HTTPException, Query, WebSocket

from app.core.admin_token import extract_bearer
from app.db.principals import InvalidPrincipal, resolve_paid_principal


async def optional_principal(
    authorization: str = Header(None),
    token: str = Query(None),
) -> dict | None:
    """HTTP 可选主体：无凭证返回 None（游客），凭证无效 401。"""
    t = extract_bearer(authorization) or (token or "").strip()
    if not t:
        return None
    try:
        return await resolve_paid_principal(t)
    except InvalidPrincipal:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")


async def required_principal(
    authorization: str = Header(None),
    token: str = Query(None),
) -> dict:
    """HTTP 必填主体：无凭证/无效凭证 401。"""
    principal = await optional_principal(authorization, token)
    if principal is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return principal


async def principal_from_websocket(websocket: WebSocket) -> dict | None:
    """WS 从 ?token= 解析主体；无 token 返回 None，无效 token 抛 InvalidPrincipal。"""
    token = (websocket.query_params.get("token") or "").strip()
    if not token:
        return None
    return await resolve_paid_principal(token)
