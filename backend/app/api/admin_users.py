"""管理后台：用户管理与用户数据查看。

Web 后台使用（非用户端）。接口挂载于 /ai/admin，受全局 API Key 中间件保护
（生产环境配置 API_KEYS 后整个 /api 需鉴权；本地开发默认关闭）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.common import client_error
from app.core.logger import log
from app.db import repository as repo

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users")
async def list_users(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """列出用户（含各模块数据量统计）与总数。"""
    try:
        rows = await repo.list_users(limit=limit, offset=offset)
        total = await repo.count_users()
        users = []
        for u in rows:
            uid = u["id"]
            sessions = await repo.get_session_info(prefix="mp-xianzhi", user_id=uid)
            users.append(
                {
                    **u,
                    "stats": {
                        "profiles": len(await repo.list_profiles(uid)),
                        "favorites": len(await repo.list_favorites(uid)),
                        "tarotRecords": len(await repo.list_tarot_records(uid)),
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
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    try:
        sessions = await repo.get_session_info(prefix="mp-xianzhi", user_id=user_id)
        return {
            "user": user,
            "profiles": await repo.list_profiles(user_id),
            "favorites": await repo.list_favorites(user_id),
            "tarotRecords": await repo.list_tarot_records(user_id),
            "sessions": sessions,
        }
    except Exception as e:
        log.exception("管理后台-用户详情失败")
        raise HTTPException(status_code=500, detail=client_error(e))
