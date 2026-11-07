"""用户 AI 设置接口：LLM 审核开关 + 自定义主问答模型（按登录用户隔离）。

- GET /user/ai-settings：读当前设置（API Key 不回传，只回 has_key）
- PUT /user/ai-settings：增量保存；公网 OpenAI 兼容地址，密钥认证加密后入库
- POST /user/ai-settings/test-model：用已保存配置做连通测试
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.core.crypto_util import SecretConfigError
from app.core.logger import log
from app.core.user_llm import InvalidBaseURLError, validate_llm_base_url
from app.db import user_ai_settings as store
from app.db.user_llm import test_user_model

router = APIRouter(prefix="/user/ai-settings", tags=["User-AI"])

_MODEL_FIELDS = ("llm_base_url", "llm_model")
_MAX_LENGTHS = {"llm_base_url": 200, "llm_model": 100, "llm_api_key": 300}


def _string_field(body: dict, field: str) -> str:
    value = body.get(field)
    if value is not None and not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field} 需为字符串")
    value = (value or "").strip()
    if len(value) > _MAX_LENGTHS[field]:
        raise HTTPException(status_code=400, detail=f"{field} 长度不能超过 {_MAX_LENGTHS[field]}")
    return value


@router.get("")
async def get_settings(current_user: dict = Depends(get_current_user)):
    """读当前用户 AI 设置（脱敏）。"""
    return await asyncio.to_thread(store.public_settings, str(current_user["id"]))


@router.put("")
async def save_settings(body: dict, current_user: dict = Depends(get_current_user)):
    """增量保存：只更新请求中出现的字段，返回脱敏后的完整设置。"""
    uid = str(current_user["id"])
    payload: dict = {}
    if "review_enabled" in body:
        value = body.get("review_enabled")
        # null=重置为「跟随服务端全局默认」；true/false=用户明确选择
        if value is not None and not isinstance(value, bool):
            raise HTTPException(status_code=400, detail="review_enabled 需为布尔值或 null")
        payload["review_enabled"] = value
    if "clear_model" in body:
        clear_model = body.get("clear_model")
        if not isinstance(clear_model, bool):
            raise HTTPException(status_code=400, detail="clear_model 需为布尔值")
        if clear_model:
            payload["clear_model"] = True
    if not payload.get("clear_model"):
        for field in _MODEL_FIELDS:
            if field in body:
                payload[field] = _string_field(body, field)
        if "llm_api_key" in body:
            payload["llm_api_key"] = _string_field(body, "llm_api_key")
    if payload.get("llm_base_url"):
        try:
            payload["llm_base_url"] = await asyncio.to_thread(
                validate_llm_base_url, payload["llm_base_url"]
            )
        except InvalidBaseURLError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return await asyncio.to_thread(store.save_user_ai_settings, uid, **payload)
    except SecretConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.warning("[user-ai] 保存设置失败 uid={}: {}", uid[-8:], exc)
        raise HTTPException(status_code=500, detail="设置保存失败") from exc


@router.post("/test-model")
async def test_model(current_user: dict = Depends(get_current_user)):
    """用已保存的模型配置做一次连通测试；返回 {ok, message}。"""
    ok, message = await asyncio.to_thread(test_user_model, str(current_user["id"]))
    return {"ok": ok, "message": message}
