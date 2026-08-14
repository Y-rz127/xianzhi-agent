"""聚合接口：当前用户的资料 + 各模块数据量统计。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.common import api_guard
from app.api.deps import get_current_user
from app.db import user_data

router = APIRouter(prefix="/me", tags=["Me"])


@router.get("")
async def my_overview(current_user: dict = Depends(get_current_user)):
    """聚合返回当前用户的资料与各模块数据量统计（档案/收藏/塔罗/会话）。"""
    with api_guard("聚合接口失败"):
        return {
            "user": {
                "id": current_user["id"],
                "nickname": current_user["nickname"],
                "avatar": current_user["avatar"],
            },
            "stats": user_data.count_user_data(current_user["id"]),
        }
