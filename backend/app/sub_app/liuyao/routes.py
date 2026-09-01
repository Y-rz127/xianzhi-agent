"""六爻占卜相关接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.prompts import LIUYAO_SYSTEM_PROMPT
from app.api.context import get_app_context
from app.sub_app.liuyao.liuyao_app import cast

router = APIRouter(prefix="/liuyao", tags=["LiuYao"])


@router.post("/cast")
async def cast_liuyao(body: dict):
    # 起卦方法和数字（可选）
    method = body.get("method", "coins")
    if method not in {"coins", "numbers", "time"}:
        raise HTTPException(status_code=400, detail="不支持的起卦方式")
    numbers = body.get("numbers")
    if method == "numbers" and (
        not isinstance(numbers, list) or len(numbers) < 2 or not all(isinstance(n, int) for n in numbers[:2])
    ):
        raise HTTPException(status_code=400, detail="数字起卦需要输入两个整数")
    return cast(method, numbers)


def _hexagram_text(hexagram: dict | None) -> str:
    name = (hexagram or {}).get("name", "")
    if not name:
        return "无"
    upper = (hexagram.get("upper") or {}).get("name", "")
    lower = (hexagram.get("lower") or {}).get("name", "")
    return f"{name}（上卦{upper}，下卦{lower}）" if upper and lower else name


@router.post("/interpret")
async def interpret_liuyao(body: dict):
    """解读六爻结果"""
    question = str(body.get("question") or "").strip()
    result = body.get("result")
    if not question or not isinstance(result, dict):
        raise HTTPException(status_code=400, detail="请填写问题并先完成起卦")
    lines = {line.get("index"): line for line in result.get("lines") or []}
    moving = result.get("movingLines") or []
    if not moving:
        moving_text = "无（静卦）"
    else:
        moving_text = "；".join(
            f"第{i}爻（老阳，阳动变阴）" if (lines.get(i) or {}).get("value") == 9
            else f"第{i}爻（老阴，阴动变阳）" if (lines.get(i) or {}).get("value") == 6
            else f"第{i}爻"
            for i in moving
        )
    prompt = (
        f"请为以下六爻占卜做深度解读：\n\n"
        f"占问者的问题：{question}\n\n"
        f"本卦：{_hexagram_text(result.get('original'))}\n"
        f"变卦：{_hexagram_text(result.get('changed'))}\n"
        f"动爻：{moving_text}\n\n"
        f"请按照系统提示中的结构解读：卦象主题 → 动爻解读 → 本变卦演变 → 具体建议。\n"
        f"解读要落到占问者的具体问题上。"
    )
    try:
        response = await get_app_context().chat_model.ainvoke(
            [SystemMessage(content=LIUYAO_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        return {"interpretation": str(response.content)}
    except Exception:
        raise HTTPException(status_code=502, detail="AI 解读暂不可用，请稍后再试")