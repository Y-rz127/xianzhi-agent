"""API 层依赖：从请求中提取并校验用户 token。"""
from __future__ import annotations

from fastapi import Header, HTTPException, Query

from app.api.admin_auth import is_admin_authorized
from app.db import users as user_store


def get_current_user(
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
    user = user_store.get_by_token(t)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已失效")
    return user


def require_admin(api_key: str = Query(None, alias="api_key"),
                  x_api_key: str = Header(None, alias="X-API-Key"),
                  admin_token: str = Query(None, alias="admin_token"),
                  x_admin_token: str = Header(None, alias="X-Admin-Token")) -> None:
    """管理类接口依赖：校验 API Key 或管理员会话 token。

    默认拒绝：未配置 API_KEYS 且无有效管理员会话 token 时返回 401
    （仅 DEBUG=true 且未配置 API_KEYS 的本地开发场景放行）。
    用于命例库管理、反馈审核/导出、用户与账号管理等接口。
    """
    if is_admin_authorized((api_key or x_api_key or "").strip(),
                           (admin_token or x_admin_token or "").strip()):
        return
    raise HTTPException(status_code=401, detail="无效或缺失的管理员凭据")


def require_session_access(
    session_id: str,
    authorization: str = Header(None),
    token: str = Query(None),
    api_key: str = Query(None, alias="api_key"),
    x_api_key: str = Header(None, alias="X-API-Key"),
    admin_token: str = Query(None, alias="admin_token"),
    x_admin_token: str = Header(None, alias="X-Admin-Token"),
) -> None:
    """会话粒度授权：管理员凭据，或会话归属人本人。

    防止越权访问/删除他人会话（包含出生时间、对话内容等敏感信息）。
    无归属的会话（如未登录的 PC 端会话）仅管理员可访问。
    """
    if is_admin_authorized((api_key or x_api_key or "").strip(),
                           (admin_token or x_admin_token or "").strip()):
        return
    t = None
    if authorization and authorization.lower().startswith("bearer "):
        t = authorization[7:].strip()
    t = t or token
    user = user_store.get_by_token(t) if t else None
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已失效")
    from app.memory.postgres_memory import get_session_owner
    owner = get_session_owner(session_id)
    if not owner or owner != user["id"]:
        raise HTTPException(status_code=403, detail="无权访问该会话")
