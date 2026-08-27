from __future__ import annotations

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage

from app.api.context import get_app_context
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


@router.post("/interpret")
async def interpret_liuyao(body: dict):
    question = str(body.get("question") or "").strip()
    result = body.get("result")
    if not question or not isinstance(result, dict):
        raise HTTPException(status_code=400, detail="请填写问题并先完成起卦")
    original = (result.get("original") or {}).get("name", "")
    changed = (result.get("changed") or {}).get("name", "")
    moving = "、".join(map(str, result.get("movingLines") or [])) or "无"
    prompt = f"用户所问：{question}\n本卦：{original}\n变卦：{changed or '无'}\n动爻：{moving}\n\n请以传统六爻的视角给出克制、清晰的解读：先说明卦象主题，再联系问题分析变化，最后给出可行动的建议。避免断言性预测，提醒用户把结果作为自省与决策参考。"
    try:
        response = await get_app_context().chat_model.ainvoke([SystemMessage(content="你是严谨、温和的六爻解读助手。"), HumanMessage(content=prompt)])
        return {"interpretation": str(response.content)}
    except Exception:
        raise HTTPException(status_code=502, detail="AI 解读暂不可用，请稍后再试")
