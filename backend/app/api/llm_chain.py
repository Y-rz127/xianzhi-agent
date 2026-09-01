"""LLM 降级链管理接口（管理后台，经 API Key 鉴权中间件保护）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.core.llm_failover import get_active_chain, invalidate_chain_cache
from app.core.logger import log

router = APIRouter(prefix="/admin/llm", tags=["Admin-LLM"])

_CHAIN_KEY = "llm_failover_chain"
_MAX_CHAIN_LEN = 5

# Web 端快捷候选（仅提示用，不限制用户填其他模型名）
CANDIDATE_MODELS = [
    "qwen3.8-27b",
    "qwen3.8-flash",
    "qwen3.8-2.4t-a95b",
    "kimi-k3",
    "deepseek-v4-flash-0731",
    "deepseek-v4-pro-0813",
]


@router.get("/chain")
async def get_chain():
    """当前降级链（第一个为主模型）与候选模型清单。"""
    return {"models": get_active_chain(), "candidates": CANDIDATE_MODELS}


@router.put("/chain")
async def update_chain(payload: dict):
    """更新降级链：{"models": [...]}；空数组=回退 .env 主模型单元素链。"""
    from app.db.app_config import set_config

    raw = payload.get("models")
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="models 必须是模型名数组")
    models = [str(m).strip() for m in raw if str(m).strip()]
    if len(models) > _MAX_CHAIN_LEN:
        raise HTTPException(status_code=400, detail=f"降级链最多 {_MAX_CHAIN_LEN} 个模型")
    await asyncio.to_thread(set_config, _CHAIN_KEY, {"models": models})
    invalidate_chain_cache()
    log.info("降级链已更新: {}", models or "（空，回退 env 主模型）")
    return {"models": get_active_chain()}


# ---------------- LLM 单价（成本折算） ----------------

_PRICE_KEY = "llm_price_map"


@router.get("/price")
async def get_price():
    """当前单价表与候选模型。单价单位：元/百万 token。"""
    from app.core.observability import current_price_map

    return {"prices": current_price_map(), "candidates": CANDIDATE_MODELS}


@router.put("/price")
async def update_price(payload: dict):
    """更新单价表：{"prices": {"模型名": {"input": 输入单价, "output": 输出单价}}}。

    {"prices": {}} = 清空（不折算成本，回退 env LLM_PRICE_MAP）。
    """
    from app.core.observability import invalidate_price_cache
    from app.db.app_config import set_config

    prices = payload.get("prices")
    if not isinstance(prices, dict):
        raise HTTPException(status_code=400, detail="prices 必须是 模型名→{input, output} 的对象")
    cleaned: dict = {}
    for model, p in prices.items():
        if not isinstance(p, dict):
            raise HTTPException(status_code=400, detail=f"{model} 的单价必须是 {{input, output}} 对象")
        try:
            cleaned[str(model)] = {"input": round(float(p.get("input", 0)), 4), "output": round(float(p.get("output", 0)), 4)}
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{model} 的单价必须是数字（元/百万 token）")
    await asyncio.to_thread(set_config, _PRICE_KEY, {"prices": cleaned})
    invalidate_price_cache()
    log.info("LLM 单价表已更新: {} 个模型", len(cleaned))
    from app.core.observability import current_price_map

    return {"prices": current_price_map()}