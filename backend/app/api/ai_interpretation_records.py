"""通用 AI 解读记录（按用户隔离，面向小程序子应用，但不接入 Web 管理端）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.common import client_error
from app.api.deps import get_current_user
from app.core.logger import log
from app.db import repository as repo

router = APIRouter(prefix="/ai_interpretation_records", tags=["AIInterpretationRecords"])


@router.get("")
async def list_ai_interpretation_records(current_user: dict = Depends(get_current_user)):
    """列出当前用户在小程序子应用中的 AI 解读记录。"""
    try:
        return await repo.list_ai_interpretation_records(current_user["id"])
    except Exception as e:
        log.exception("获取 AI 解读记录失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.post("")
async def create_ai_interpretation_record(body: dict, current_user: dict = Depends(get_current_user)):
    """保存一次通用 AI 解读记录（source/question/payload/interpretation）。"""
    try:
        rid = await repo.add_ai_interpretation_record(
            current_user["id"],
            str(body.get("source") or "unknown"),
            str(body.get("question") or ""),
            body.get("payload") or {},
            str(body.get("interpretation") or ""),
        )
        return {"id": rid}
    except Exception as e:
        log.exception("保存 AI 解读记录失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.delete("/{rid}")
async def delete_ai_interpretation_record(rid: str, current_user: dict = Depends(get_current_user)):
    """删除一条 AI 解读记录。"""
    await repo.delete_ai_interpretation_record(current_user["id"], rid)
    return {"status": "ok"}
