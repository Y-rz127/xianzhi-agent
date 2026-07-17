"""账号登录接口：注册 / 登录 / 获取与修改个人资料 / 微信登录。"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.api.common import client_error
from app.api.deps import get_current_user
from app.config import settings
from app.db import users as user_store
from app.logger import log

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register")
async def register(body: dict):
    """注册：昵称 + 密码，返回 token 与用户资料。"""
    try:
        user = user_store.create_user(body.get("nickname", ""), body.get("password", ""))
        return {"token": user["token"], "user": _safe(user)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("注册失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.post("/login")
async def login(body: dict):
    """登录：昵称 + 密码，返回 token 与用户资料。"""
    user = user_store.authenticate(body.get("nickname", ""), body.get("password", ""))
    if not user:
        raise HTTPException(status_code=401, detail="昵称或密码错误")
    return {"token": user["token"], "user": _safe(user)}


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户资料（需 Bearer token 或 ?token=）。"""
    return _safe(current_user)


@router.put("/me")
async def update_me(body: dict, current_user: dict = Depends(get_current_user)):
    """修改昵称 / 头像 / 密码。"""
    try:
        updated = user_store.update_user(
            current_user["id"],
            nickname=body.get("nickname"),
            avatar=body.get("avatar"),
            password=body.get("password"),
        )
        return {"user": _safe(updated)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("更新资料失败")
        raise HTTPException(status_code=500, detail=client_error(e))


def _safe(u: dict) -> dict:
    return {"id": u.get("id"), "nickname": u.get("nickname"), "avatar": u.get("avatar", "")}


@router.post("/wx-login")
async def wx_login(body: dict):
    """微信小程序登录：接收 uni.login 的 code，换取 openid，自动注册或登录。"""
    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="缺少 code 参数")
    if not settings.wechat_appid or not settings.wechat_secret:
        raise HTTPException(status_code=501, detail="未配置微信登录（需设置 WECHAT_APPID / WECHAT_SECRET）")
    try:
        url = "https://api.weixin.qq.com/sns/jscode2session"
        params = {
            "appid": settings.wechat_appid,
            "secret": settings.wechat_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
        data = resp.json()
        openid = data.get("openid")
        err_msg = data.get("errcode")
        if err_msg:
            log.warning("微信 code2session 失败: errcode=%s errmsg=%s", err_msg, data.get("errmsg"))
            raise HTTPException(status_code=400, detail=f"微信登录失败: {data.get('errmsg', '未知错误')}")
        if not openid:
            raise HTTPException(status_code=400, detail="未能获取微信 openid")
        user = user_store.create_or_get_by_wxopenid(openid)
        return {"token": user["token"], "user": _safe(user)}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("微信登录异常")
        raise HTTPException(status_code=500, detail=client_error(e))
