"""按模型能力收敛采样参数，避免把模型不支持的参数发给上游。"""
from __future__ import annotations

from app.core.config import settings


def temperature_for(model_name: str, requested: float | None) -> float | None:
    """返回该模型可接受的 temperature；不支持的模型返回 None（请求中省略）。"""
    blocked = {m.strip() for m in settings.llm_no_temperature_models.split(",") if m.strip()}
    if any(model_name.startswith(prefix) for prefix in blocked):
        return None
    return requested
