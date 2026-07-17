"""API 层依赖：从请求中提取并校验用户 token。"""
from __future__ import annotations

from fastapi import Header, HTTPException, Query

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
