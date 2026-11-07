"""用户自定义问答模型的实例缓存与数据装配。

core 层只提供纯校验与模型构造；本模块负责读取用户配置、短 TTL 缓存与连通测试。
按 user_id 隔离，配置变化时由 ``invalidate_user_model_cache`` 立即失效。
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from langchain_openai import ChatOpenAI

from app.core.logger import log
from app.core.user_llm import build_user_model, validate_llm_base_url
from app.db.user_ai_settings import get_user_ai_settings

_CACHE_TTL = 60.0
_CACHE_MAX = 32
_lock = threading.Lock()
_cache: dict[str, dict] = {}


def _cached(user_id: str) -> Optional[dict]:
    now = time.time()
    with _lock:
        entry = _cache.get(user_id)
    if not entry or now - entry["at"] >= _CACHE_TTL:
        return None
    return entry


def get_user_model(user_id: str) -> Optional[ChatOpenAI]:
    """按用户取自定义模型实例；未配置/配置不全/校验失败返回 None。"""
    if not user_id:
        return None
    entry = _cached(user_id)
    if entry:
        return entry["model"]
    cfg = get_user_ai_settings(user_id)
    if not (cfg.get("llm_base_url") and cfg.get("llm_model") and cfg.get("llm_api_key")):
        return None
    try:
        # 缓存过期后重新做 DNS 与目标校验，避免旧配置绕过当前安全策略。
        validate_llm_base_url(cfg["llm_base_url"])
        model = build_user_model(cfg)
    except Exception as e:
        log.warning("[user-llm] 构建用户模型失败 uid={}: {}", user_id[-8:], e)
        return None
    with _lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)), None)
        _cache[user_id] = {"at": time.time(), "model": model}
    return model


def invalidate_user_model_cache(user_id: str) -> None:
    """用户修改/清除模型配置后立即失效。"""
    with _lock:
        _cache.pop(user_id, None)


def test_user_model(user_id: str) -> tuple[bool, str]:
    """连通性测试：调用户模型生成一个 token；返回 (ok, 说明文字)。"""
    model = get_user_model(user_id)
    if model is None:
        cfg = get_user_ai_settings(user_id)
        if not (cfg.get("llm_base_url") and cfg.get("llm_model") and cfg.get("llm_api_key")):
            return False, "模型配置不完整（地址/密钥/模型名缺一不可）"
        return False, "模型配置无效或接口地址不可用"
    try:
        from langchain_core.messages import HumanMessage

        model.invoke([HumanMessage(content="ping")], max_tokens=5)
        return True, "连接成功"
    except Exception as e:
        message = str(e).replace(str(get_user_ai_settings(user_id).get("llm_api_key") or ""), "***")
        return False, f"连接失败：{type(e).__name__}: {message[:160]}"
