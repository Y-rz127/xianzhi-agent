"""聚合接口：当前用户的资料 + 各模块数据量统计。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.common import client_error
from app.api.deps import get_current_user
from app.db import user_data, users as user_store
from app.logger import log
from app.memory.postgres_memory import get_session_info

router = APIRouter(prefix="/me", tags=["Me"])


@router.get("")
async def my_overview(current_user: dict = Depends(get_current_user)):
    uid = current_user["id"]
    try:
        sessions = get_session_info(prefix="mp-xianzhi", user_id=uid)
        return {
            "user": {
                "id": current_user["id"],
                "nickname": current_user["nickname"],
                "avatar": current_user["avatar"],
            },
            "stats": {
                "profiles": len(user_data.list_profiles(uid)),
                "favorites": len(user_data.list_favorites(uid)),
                "tarotRecords": len(user_data.list_tarot_records(uid)),
                "sessions": len(sessions),
            },
        }
    except Exception as e:
        log.exception("聚合接口失败")
        raise HTTPException(status_code=500, detail=client_error(e))
