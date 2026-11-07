"""运行时可配置的模型角色。"""
from __future__ import annotations

from app.core.config import settings
from app.core.config.kv import get_config

MODEL_CONFIG_KEY = "llm_model_roles"
LLM_MODEL_ROLES = ("decompose_model", "reviewer_model", "sub_app_model")


def default_model_config() -> dict[str, str]:
    return {
        "decompose_model": settings.decompose_model,
        "reviewer_model": settings.reviewer_model,
        "sub_app_model": settings.sub_app_model,
        "asr_model": settings.asr_model,
        "tts_model": settings.tts_model,
        "tts_voice": settings.tts_voice,
    }


def get_model_config() -> dict[str, str]:
    """返回模型配置；未在管理台配置的项使用环境变量默认值。"""
    defaults = default_model_config()
    stored = get_config(MODEL_CONFIG_KEY)
    if not isinstance(stored, dict):
        return defaults
    models = stored.get("models")
    if not isinstance(models, dict):
        return defaults
    for key in defaults:
        value = models.get(key)
        if isinstance(value, str):
            defaults[key] = value
    return defaults
