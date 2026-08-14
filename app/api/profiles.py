"""我的八字档案（按用户隔离）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.common import api_guard
from app.api.deps import get_current_user
from app.db import user_data

router = APIRouter(prefix="/profiles", tags=["Profiles"])


@router.get("")
async def list_profiles(current_user: dict = Depends(get_current_user)):
    """列出当前用户的八字档案。"""
    with api_guard("获取档案列表失败"):
        return user_data.list_profiles(current_user["id"])


@router.post("")
async def create_profile(body: dict, current_user: dict = Depends(get_current_user)):
    """创建八字档案（需 birth_time / gender / name）。"""
    if not body.get("birth_time") or not body.get("gender"):
        raise HTTPException(status_code=400, detail="缺少 birth_time / gender")
    if not body.get("name"):
        raise HTTPException(status_code=400, detail="请填写档案名称")
    with api_guard("创建档案失败"):
        pid = user_data.create_profile(current_user["id"], body)
        return {"id": pid}


@router.get("/{pid}")
async def get_profile(pid: str, current_user: dict = Depends(get_current_user)):
    """获取单条八字档案；不存在返回 404。"""
    prof = user_data.get_profile(current_user["id"], pid)
    if not prof:
        raise HTTPException(status_code=404, detail="档案不存在")
    return prof


@router.put("/{pid}")
async def update_profile(pid: str, body: dict, current_user: dict = Depends(get_current_user)):
    """更新八字档案；不存在返回 404。"""
    with api_guard("更新档案失败"):
        ok = user_data.update_profile(current_user["id"], pid, body)
        if not ok:
            raise HTTPException(status_code=404, detail="档案不存在")
        return {"status": "ok"}


@router.delete("/{pid}")
async def delete_profile(pid: str, current_user: dict = Depends(get_current_user)):
    """删除八字档案。"""
    user_data.delete_profile(current_user["id"], pid)
    return {"status": "ok"}
