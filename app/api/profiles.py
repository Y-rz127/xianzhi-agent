"""我的八字档案（按用户隔离）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.common import client_error
from app.api.deps import get_current_user
from app.db import user_data
from app.logger import log

router = APIRouter(prefix="/profiles", tags=["Profiles"])


@router.get("")
async def list_profiles(current_user: dict = Depends(get_current_user)):
    try:
        return user_data.list_profiles(current_user["id"])
    except Exception as e:
        log.exception("获取档案列表失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.post("")
async def create_profile(body: dict, current_user: dict = Depends(get_current_user)):
    if not body.get("birth_time") or not body.get("gender"):
        raise HTTPException(status_code=400, detail="缺少 birth_time / gender")
    if not body.get("name"):
        raise HTTPException(status_code=400, detail="请填写档案名称")
    try:
        pid = user_data.create_profile(current_user["id"], body)
        return {"id": pid}
    except Exception as e:
        log.exception("创建档案失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/{pid}")
async def get_profile(pid: str, current_user: dict = Depends(get_current_user)):
    prof = user_data.get_profile(current_user["id"], pid)
    if not prof:
        raise HTTPException(status_code=404, detail="档案不存在")
    return prof


@router.put("/{pid}")
async def update_profile(pid: str, body: dict, current_user: dict = Depends(get_current_user)):
    try:
        ok = user_data.update_profile(current_user["id"], pid, body)
        if not ok:
            raise HTTPException(status_code=404, detail="档案不存在")
        return {"status": "ok"}
    except Exception as e:
        log.exception("更新档案失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.delete("/{pid}")
async def delete_profile(pid: str, current_user: dict = Depends(get_current_user)):
    user_data.delete_profile(current_user["id"], pid)
    return {"status": "ok"}
