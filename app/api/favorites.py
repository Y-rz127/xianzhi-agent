"""我的命例收藏（按用户隔离）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.common import client_error
from app.api.deps import get_current_user
from app.db import user_data
from app.logger import log

router = APIRouter(prefix="/favorites", tags=["Favorites"])


@router.get("")
async def list_favorites(current_user: dict = Depends(get_current_user)):
    try:
        return user_data.list_favorites(current_user["id"])
    except Exception as e:
        log.exception("获取收藏失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.post("")
async def add_favorite(body: dict, current_user: dict = Depends(get_current_user)):
    case_id = body.get("case_id") or body.get("caseId")
    if not case_id:
        raise HTTPException(status_code=400, detail="缺少 case_id")
    try:
        user_data.add_favorite(current_user["id"], case_id)
        return {"status": "ok"}
    except Exception as e:
        log.exception("添加收藏失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/{case_id}/status")
async def favorite_status(case_id: str, current_user: dict = Depends(get_current_user)):
    return {"favorited": user_data.is_favorite(current_user["id"], case_id)}


@router.delete("/{case_id}")
async def remove_favorite(case_id: str, current_user: dict = Depends(get_current_user)):
    user_data.remove_favorite(current_user["id"], case_id)
    return {"status": "ok"}
