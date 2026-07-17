"""问题反馈（登录用户带 user_id，未登录可匿名提交）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.common import client_error
from app.db import user_data, users as user_store
from app.logger import log

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("")
async def submit_feedback(body: dict, token: str = Query(None)):
    content = (body.get("content") or "").strip()
    if len(content) < 5:
        raise HTTPException(status_code=400, detail="反馈内容至少 5 个字")
    uid = None
    if token:
        u = user_store.get_by_token(token)
        if u:
            uid = u["id"]
    try:
        fid = user_data.add_feedback(uid, content, body.get("contact", ""))
        return {"id": fid}
    except Exception as e:
        log.exception("提交反馈失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.delete("/{fid}")
async def delete_feedback(fid: str):
    try:
        ok = user_data.delete_feedback(fid)
        if not ok:
            raise HTTPException(status_code=404, detail="反馈不存在")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("删除反馈失败")
        raise HTTPException(status_code=500, detail=client_error(e))
@router.get("")
async def get_feedback_list(limit: int = Query(default=200, ge=1, le=1000)):
    """管理员查看反馈列表（按时间倒序）。"""
    try:
        items = user_data.list_feedback(limit)
        return {"items": items}
    except Exception as e:
        log.exception("获取反馈列表失败")
        raise HTTPException(status_code=500, detail=client_error(e))
