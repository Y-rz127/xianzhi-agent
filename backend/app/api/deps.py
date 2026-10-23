"""API 层依赖：从请求中提取并校验用户 token，以及注入 AppContext。"""
from __future__ import annotations

from fastapi import Header, HTTPException, Query, Request

from app.agent.context import AppContext
from app.api import data_access as repo
from app.core.admin_token import extract_bearer, verify_admin_token
from app.core.config import settings
from app.db.principals import InvalidPrincipal, resolve_paid_principal


async def app_context_dependency(request: Request) -> AppContext:
    """FastAPI 依赖：HTTP handler 经此注入 AppContext。

    未初始化返回 503（服务尚未就绪），而非 500。
    """
    ctx = getattr(request.app.state, "app_context", None)
    if ctx is None:
        raise HTTPException(status_code=503, detail="服务尚未就绪")
    return ctx


async def get_current_user(
    authorization: str = Header(None),
    token: str = Query(None),
) -> dict:
    """解析 Bearer token 或 ?token= 查询参数，返回当前登录用户。

    用户态接口（档案/收藏/塔罗/我的对话/反馈）必须依赖此函数。
    """
    t = None
    if authorization and authorization.lower().startswith("bearer "):
        t = authorization[7:].strip()
    if not t:
        t = token
    if not t:
        raise HTTPException(status_code=401, detail="未登录或登录已失效")
    user = await repo.get_by_token(t)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已失效")
    return user


async def get_paid_principal(
    authorization: str = Header(None),
    token: str = Query(None),
) -> dict:
    """付费接口必填主体：用户 token 或管理员令牌；无凭证 401。"""
    t = extract_bearer(authorization) or (token or "").strip()
    if not t:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        principal = await resolve_paid_principal(t)
    except InvalidPrincipal:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    if principal is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return principal


async def get_optional_paid_principal(
    authorization: str = Header(None),
    token: str = Query(None),
) -> dict | None:
    """付费接口可选主体：无凭证返回 None（游客），凭证无效 401。"""
    t = extract_bearer(authorization) or (token or "").strip()
    if not t:
        return None
    try:
        principal = await resolve_paid_principal(t)
    except InvalidPrincipal:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return principal


def require_admin(
    authorization: str = Header(None),
    api_key: str = Query(None, alias="api_key"),
    x_api_key: str = Header(None, alias="X-API-Key"),
) -> dict | None:
    """管理类接口依赖：管理员短时令牌优先，API Key 仅供机器/CLI 使用。

    - Authorization: Bearer <管理员令牌> → 校验签名与有效期；
    - 无 Authorization 时回退 X-API-Key / ?api_key（服务端任务、运维脚本）；
    - API_KEYS 与 ADMIN_SESSION_SECRET 都未配置时放行（本地开发）。
    """
    token = extract_bearer(authorization)
    if token:
        payload = verify_admin_token(token)
        if payload is None:
            raise HTTPException(status_code=401, detail="管理员登录已失效，请重新登录")
        return payload

    keys = {k.strip() for k in settings.api_keys.split(",") if k.strip()}
    if not keys and not settings.admin_session_secret.strip():
        return None
    provided = (api_key or x_api_key or "").strip()
    if provided not in keys:
        raise HTTPException(status_code=401, detail="无效或缺失的管理员凭证")
    return None
