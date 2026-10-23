"""日志隐私辅助：默认不输出用户原文/生辰，只输出长度或哈希。

排查需要原文时显式设 `LOG_LLM_CONTENT=true`；生产环境必须保持 false。
"""
from __future__ import annotations

import hashlib

from app.core.config import settings


def log_content_enabled() -> bool:
    return bool(settings.log_llm_content)


def safe_text(text: str, limit: int = 80) -> str:
    """日志用文本：关闭内容日志时只给长度，避免用户问题/回答落盘。"""
    raw = text or ""
    if log_content_enabled():
        return raw[:limit]
    return f"<{len(raw)} chars>"


def safe_birth_time(value: str) -> str:
    """生辰日志标识：关闭内容日志时用稳定哈希代替明文。"""
    raw = (value or "").strip()
    if not raw:
        return "-"
    if log_content_enabled():
        return raw
    return "birth#" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def safe_id(value: str) -> str:
    """用户/会话标识日志：默认只输出稳定哈希。"""
    raw = (value or "").strip()
    if not raw:
        return "-"
    return "id#" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
