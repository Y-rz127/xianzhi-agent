"""LLM 降级链管理接口（管理后台，经 API Key 鉴权中间件保护）。

- 降级链：PG `llm_failover_chain`，空数组=回退 .env 主模型单元素链
- 候选模型（快捷提示）：PG `llm_candidates`，可在管理端增删；未配置/存空=回退内置默认候选。
  候选只是输入提示，删掉某个候选**不影响降级链**，也不会让已在链上的模型失效。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.core.llm_failover import get_active_chain, invalidate_chain_cache
from app.core.logger import log

router = APIRouter(prefix="/admin/llm", tags=["Admin-LLM"])

_CHAIN_KEY = "llm_failover_chain"
_CANDIDATES_KEY = "llm_candidates"
_MAX_CHAIN_LEN = 5
_MAX_CANDIDATE_LEN = 20
_MAX_MODEL_NAME_LEN = 64

# 内置默认候选（首次使用/恢复默认时生效；管理端可增删，落库 llm_candidates）
# 注意：这里只放「当前确认可用」的模型。qwen3.8-2.4t-a95b 曾因免费额度耗尽(403
# AllocationQuota.FreeTierOnly)被移出默认清单；额度恢复后要重新加回，请用管理端
# 「添加候选」或改这里。
DEFAULT_CANDIDATE_MODELS = [
    "qwen3.8-27b",
    "qwen3.8-flash",
    "kimi-k3",
    "deepseek-v4-flash-0731",
    "deepseek-v4-pro-0813",
]


def _clean_models(raw: object) -> list[str]:
    """规范化模型名列表：去空、去重、校验合法性（保持原顺序）。"""
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="models 必须是模型名数组")
    out: list[str] = []
    for item in raw:
        name = str(item).strip()
        if not name:
            continue
        if len(name) > _MAX_MODEL_NAME_LEN or any(ch.isspace() for ch in name):
            raise HTTPException(status_code=400, detail=f"模型名不合法：{name[: _MAX_MODEL_NAME_LEN]}")
        if name not in out:
            out.append(name)
    return out


def get_candidates() -> list[str]:
    """当前候选模型清单。

    - 从未配置过（PG 无该 key，或读库失败）→ 内置默认候选；
    - 配置过 → 以库里的清单为准，**含空清单**（管理端可以把候选删光，空就是空，
      不会把已删掉的模型又"回退"出来）。恢复默认走 GET 返回的 default_candidates。
    """
    try:
        from app.db.app_config import get_config

        stored = get_config(_CANDIDATES_KEY)
    except Exception as e:
        log.warning("候选模型配置读取失败，回退默认候选: {}", e)
        return list(DEFAULT_CANDIDATE_MODELS)
    if stored is None:
        return list(DEFAULT_CANDIDATE_MODELS)
    return [str(m).strip() for m in (stored or {}).get("models", []) if str(m).strip()]


@router.get("/chain")
async def get_chain():
    """当前降级链（第一个为主模型）、候选模型清单与内置默认候选。"""
    return {
        "models": get_active_chain(),
        "candidates": get_candidates(),
        "default_candidates": list(DEFAULT_CANDIDATE_MODELS),
    }


@router.put("/chain")
async def update_chain(payload: dict):
    """更新降级链：{"models": [...]}；空数组=回退 .env 主模型单元素链。"""
    from app.db.app_config import set_config

    models = _clean_models(payload.get("models"))
    if len(models) > _MAX_CHAIN_LEN:
        raise HTTPException(status_code=400, detail=f"降级链最多 {_MAX_CHAIN_LEN} 个模型")
    await asyncio.to_thread(set_config, _CHAIN_KEY, {"models": models})
    invalidate_chain_cache()
    log.info("降级链已更新: {}", models or "（空，回退 env 主模型）")
    return {"models": get_active_chain()}


@router.put("/candidates")
async def update_candidates(payload: dict):
    """更新候选模型清单（增/删都走这里）：{"models": [...]}；空数组=候选项清空（不回退默认）。

    只影响管理端的快捷提示，与降级链互不干涉。传 default_candidates 即可恢复内置默认。
    """
    from app.db.app_config import set_config

    models = _clean_models(payload.get("models"))
    if len(models) > _MAX_CANDIDATE_LEN:
        raise HTTPException(status_code=400, detail=f"候选最多 {_MAX_CANDIDATE_LEN} 个")
    await asyncio.to_thread(set_config, _CANDIDATES_KEY, {"models": models})
    log.info("候选模型已更新: {}", models or "（空）")
    return {"candidates": get_candidates()}



# ---------------- LLM 单价（成本折算） ----------------

_PRICE_KEY = "llm_price_map"


@router.get("/price")
async def get_price():
    """当前单价表与候选模型。单价单位：元/百万 token。"""
    from app.core.observability import current_price_map

    return {"prices": current_price_map(), "candidates": get_candidates(), "default_candidates": list(DEFAULT_CANDIDATE_MODELS)}


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