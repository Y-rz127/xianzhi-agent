"""管理后台模型角色配置。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.agent.context import AppContext
from app.api.deps import app_context_dependency, require_admin
from app.core.config import settings
from app.core.config.kv import set_config
from app.core.logger import log
from app.core.model_config import (
    LLM_MODEL_ROLES,
    MODEL_CONFIG_KEY,
    default_model_config,
    get_model_config,
)

router = APIRouter(prefix="/admin/models", tags=["Admin-Models"])
_MAX_VALUE_LENGTH = 64


def _validate_models(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="models 必须是模型配置对象")
    defaults = default_model_config()
    allowed = set(defaults)
    if set(raw) != allowed:
        raise HTTPException(status_code=400, detail="models 必须包含全部模型配置项")

    cleaned: dict[str, str] = {}
    for key in defaults:
        value = raw[key]
        if not isinstance(value, str):
            raise HTTPException(status_code=400, detail=f"{key} 必须是字符串")
        value = value.strip()
        if len(value) > _MAX_VALUE_LENGTH or any(ch.isspace() for ch in value):
            raise HTTPException(status_code=400, detail=f"{key} 长度不能超过 {_MAX_VALUE_LENGTH} 且不能包含空白")
        if key not in LLM_MODEL_ROLES and not value:
            raise HTTPException(status_code=400, detail=f"{key} 不能为空")
        cleaned[key] = value
    return cleaned


@router.get("")
async def read_models(_admin: dict | None = Depends(require_admin)):
    defaults = default_model_config()
    return {
        "models": get_model_config(),
        "defaults": defaults,
        "main_model": settings.dashscope_model,
    }


@router.put("")
async def update_models(
    payload: dict,
    _admin: dict | None = Depends(require_admin),
    app_ctx: AppContext = Depends(app_context_dependency),
):
    models = _validate_models(payload.get("models"))
    await asyncio.to_thread(set_config, MODEL_CONFIG_KEY, {"models": models})
    app_ctx.refresh_configured_models(models)
    log.info("运行时模型配置已更新")
    return {
        "models": models,
        "defaults": default_model_config(),
        "main_model": settings.dashscope_model,
    }
