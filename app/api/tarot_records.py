"""我的塔罗记录（按用户隔离）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.common import client_error
from app.api.deps import get_current_user
from app.db import user_data
from app.logger import log

router = APIRouter(prefix="/tarot_records", tags=["TarotRecords"])


@router.get("")
async def list_tarot_records(current_user: dict = Depends(get_current_user)):
    try:
        return user_data.list_tarot_records(current_user["id"])
    except Exception as e:
        log.exception("获取塔罗记录失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.post("")
async def create_tarot_record(body: dict, current_user: dict = Depends(get_current_user)):
    try:
        rid = user_data.add_tarot_record(
            current_user["id"],
            body.get("spread", "daily"),
            body.get("question", ""),
            body.get("cards", []),
            body.get("interpretation", ""),
        )
        return {"id": rid}
    except Exception as e:
        log.exception("保存塔罗记录失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.delete("/{rid}")
async def delete_tarot_record(rid: str, current_user: dict = Depends(get_current_user)):
    user_data.delete_tarot_record(current_user["id"], rid)
    return {"status": "ok"}
