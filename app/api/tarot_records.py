"""我的塔罗记录（按用户隔离）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.common import api_guard
from app.api.deps import get_current_user
from app.db import user_data

router = APIRouter(prefix="/tarot_records", tags=["TarotRecords"])


@router.get("")
async def list_tarot_records(current_user: dict = Depends(get_current_user)):
    """列出当前用户的塔罗记录。"""
    with api_guard("获取塔罗记录失败"):
        return user_data.list_tarot_records(current_user["id"])


@router.post("")
async def create_tarot_record(body: dict, current_user: dict = Depends(get_current_user)):
    """保存一次塔罗占卜记录（spread/question/cards/interpretation）。"""
    with api_guard("保存塔罗记录失败"):
        rid = user_data.add_tarot_record(
            current_user["id"],
            body.get("spread", "daily"),
            body.get("question", ""),
            body.get("cards", []),
            body.get("interpretation", ""),
        )
        return {"id": rid}


@router.delete("/{rid}")
async def delete_tarot_record(rid: str, current_user: dict = Depends(get_current_user)):
    """删除一条塔罗记录。"""
    user_data.delete_tarot_record(current_user["id"], rid)
    return {"status": "ok"}
