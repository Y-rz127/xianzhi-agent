"""六爻占卜接口：铜钱、数字、时间三种起卦，结合 LLM 给出白话解读。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.common import is_message_too_long
from app.api.context import app_context_dependency
from app.core.logger import log
from app.liuyao.liuyao_app import LiuyaoApp

router = APIRouter(prefix="/liuyao", tags=["Liuyao"])

_ALLOWED_METHODS = {"coin", "number", "time"}


class DivineRequest(BaseModel):
    method: str = Field(default="coin", description="起卦方式：coin / number / time")
    question: str = Field(default="", description="所占问题")
    numbers: list[int] = Field(default_factory=list, description="数字起卦时使用的数字列表")


@router.post("/divine")
async def divine(req: DivineRequest, ctx=Depends(app_context_dependency)):
    """六爻起卦并返回完整 AI 解读（非流式）。"""
    if not ctx.liuyao_app:
        raise HTTPException(status_code=503, detail="六爻服务未初始化")

    if req.method not in _ALLOWED_METHODS:
        raise HTTPException(status_code=400, detail="起卦方式必须是 coin / number / time")

    if is_message_too_long(req.question):
        raise HTTPException(status_code=400, detail="问题过长，请缩短后重试")

    if req.method == "number" and not req.numbers:
        raise HTTPException(status_code=400, detail="数字起卦请提供 numbers 参数")

    try:
        lines = ctx.liuyao_app.cast(req.method, numbers=req.numbers)
        result = ctx.liuyao_app.build_result(req.question, lines)
    except Exception:
        log.exception("六爻起卦失败")
        raise HTTPException(status_code=500, detail="起卦失败，请重试")

    # 流式聚合为完整字符串
    interpretation = ""
    try:
        async for chunk in ctx.liuyao_app.interpret_stream(req.question, result):
            interpretation += chunk
    except Exception:
        log.exception("六爻解读失败")
        interpretation = "（AI 解读暂不可用，请稍后再试。）"

    return {
        "success": True,
        "data": {
            "method": req.method,
            "question": req.question,
            "result": result,
            "interpretation": interpretation,
        },
    }
