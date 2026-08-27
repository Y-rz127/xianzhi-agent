"""合婚接口（URL 与历史一致：/ai/xianzhi/hehun）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.api.common import client_error
from app.api.context import get_app_context
from app.core.logger import log
from app.sub_app.hehun.hehun_app import analyze

router = APIRouter(prefix="/xianzhi", tags=["Tools"])


@router.get("/hehun")
async def hehun(
    birth_time_a: str,
    gender_a: str,
    birth_time_b: str,
    gender_b: str,
    sect: int = 2,
    longitude_a: float | None = None,
    longitude_b: float | None = None,
):
    """合婚分析：先调规则工具拿基础数据，再调 LLM 做综合解读。"""
    try:
        # 排盘与 LLM 调用均为同步阻塞计算，放线程池避免卡住事件循环
        try:
            llm = get_app_context().chat_model
        except RuntimeError:
            llm = None
        result = await asyncio.to_thread(
            analyze,
            birth_time_a, gender_a, birth_time_b, gender_b,
            sect=sect,
            longitude_a=longitude_a,
            longitude_b=longitude_b,
            chat_model=llm,
        )
        if result.startswith("合婚失败"):
            raise HTTPException(status_code=400, detail=result)
        return {"result": result}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("合婚分析失败")
        raise HTTPException(status_code=500, detail=client_error(e))