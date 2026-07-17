"""管理后台：用户管理与用户数据查看。

Web 后台使用（非用户端）。接口挂载于 /ai/admin，受全局 API Key 中间件保护
（生产环境配置 API_KEYS 后整个 /api 需鉴权；本地开发默认关闭）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.common import client_error
from app.db import user_data, users as user_store
from app.logger import log
from app.memory.postgres_memory import get_session_info

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users")
async def list_users(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """列出用户（含各模块数据量统计）与总数。"""
    try:
        rows = user_store.list_users(limit=limit, offset=offset)
        total = user_store.count_users()
        users = []
        for u in rows:
            uid = u["id"]
            sessions = get_session_info(prefix="mp-xianzhi", user_id=uid)
            users.append(
                {
                    **u,
                    "stats": {
                        "profiles": len(user_data.list_profiles(uid)),
                        "favorites": len(user_data.list_favorites(uid)),
                        "tarotRecords": len(user_data.list_tarot_records(uid)),
                        "sessions": len(sessions),
                    },
                }
            )
        return {"total": total, "users": users}
    except Exception as e:
        log.exception("管理后台-用户列表失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/users/{user_id}")
async def get_user_detail(user_id: str):
    """查看单个用户的数据：八字档案 / 命例收藏 / 塔罗记录 / 会话列表。"""
    user = user_store.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    try:
        sessions = get_session_info(prefix="mp-xianzhi", user_id=user_id)
        return {
            "user": user,
            "profiles": user_data.list_profiles(user_id),
            "favorites": user_data.list_favorites(user_id),
            "tarotRecords": user_data.list_tarot_records(user_id),
            "sessions": sessions,
        }
    except Exception as e:
        log.exception("管理后台-用户详情失败")
        raise HTTPException(status_code=500, detail=client_error(e))
