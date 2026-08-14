"""API 层依赖：从请求中提取并校验用户 token。"""
from __future__ import annotations

from fastapi import Header, HTTPException, Query

from app.config import settings
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


def user_id_from_token(token: str | None) -> str:
    """token → user_id；未传 token 或 token 失效时返回空串（匿名可用的接口用）。"""
    if not token:
        return ""
    user = user_store.get_by_token(token)
    return user["id"] if user else ""


def require_user_by_token(token: str | None) -> dict:
    """?token= 形式的强制登录校验（无法使用 Depends 注入的查询参数接口用）。"""
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    user = user_store.get_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期")
    return user


def require_admin(api_key: str = Query(None, alias="api_key"),
                  x_api_key: str = Header(None, alias="X-API-Key")) -> None:
    """管理类接口依赖：校验 API Key。

    生产环境（API_KEYS 非空）必须提供有效 API Key；
    本地开发（API_KEYS 为空）放行，便于调试。
    用于命例库管理、反馈审核/导出等管理类接口。
    """
    keys = {k.strip() for k in settings.api_keys.split(",") if k.strip()}
    if not keys:
        # 本地开发模式：未配置 API_KEYS 时放行
        return
    provided = (api_key or x_api_key or "").strip()
    if provided not in keys:
        raise HTTPException(status_code=401, detail="无效或缺失的管理员 API Key")
