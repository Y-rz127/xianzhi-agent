from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.liuyao.liuyao_app import cast

router = APIRouter(prefix="/liuyao", tags=["LiuYao"])


@router.post("/cast")
async def cast_liuyao(body: dict):
    method = body.get("method", "coins")
    if method not in {"coins", "numbers", "time"}:
        raise HTTPException(status_code=400, detail="不支持的起卦方式")
    numbers = body.get("numbers")
    if method == "numbers" and (not isinstance(numbers, list) or len(numbers) < 2 or not all(isinstance(n, int) for n in numbers[:2])):
        raise HTTPException(status_code=400, detail="数字起卦需要输入两个整数")
    return cast(method, numbers)
