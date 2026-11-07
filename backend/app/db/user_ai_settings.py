"""用户 AI 偏好存储（按 user_id 隔离）：LLM 审核开关 + 自定义问答模型配置。

独立于 users 表：这些是「可选的个性化设置」，放主表会让每行膨胀；按 user_id 一对一的
子表更清晰，且删用户时级联清理。API key 用 app.core.crypto_util 静态加密后再落库，
读接口绝不回传明文（只回 has_key 标记）。
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from app.core.config import settings
from app.core.crypto_util import (
    SecretConfigError,
    SecretDecryptError,
    decrypt_secret,
    encrypt_secret,
)
from app.core.logger import log
from app.db.pool import get_pool

_TABLE_READY = False
_lock = threading.Lock()

# 模型配置缓存（跨会话复用，用户装填后不必每个会话都查库；配置写入时立即失效）
_TTL_SECONDS = 60.0
_CACHE_MAX = 256
_cache: dict[str, tuple[float, dict]] = {}  # user_id -> (expire_at, settings dict)


def _ensure_table():
    global _TABLE_READY
    if _TABLE_READY:
        return
    try:
        with get_pool().connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_ai_settings (
                    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    review_enabled BOOLEAN,
                    llm_base_url TEXT NOT NULL DEFAULT '',
                    llm_api_key_enc TEXT NOT NULL DEFAULT '',
                    llm_model TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
        _TABLE_READY = True
        log.info("用户 AI 设置表(user_ai_settings)已就绪")
    except Exception as e:
        log.warning("用户 AI 设置表(user_ai_settings)创建失败: {}", e)


def invalidate_user_cache(user_id: str) -> None:
    """配置写入后同时失效设置与模型实例缓存，保证下一轮立即使用新值。"""
    with _lock:
        _cache.pop(user_id, None)
    # 延迟导入避免模块加载环：db.user_llm 读取本模块的设置。
    from app.db.user_llm import invalidate_user_model_cache

    invalidate_user_model_cache(user_id)


def _row_to_settings(row) -> dict:
    (
        review_enabled,
        llm_base_url,
        llm_api_key_enc,
        llm_model,
        updated_at,
    ) = row
    api_key = ""
    key_error = ""
    if llm_api_key_enc:
        try:
            api_key = decrypt_secret(llm_api_key_enc)
        except (SecretDecryptError, SecretConfigError):
            # 密钥被换过或服务端密钥缺失：按无 key 处理并告警，绝不回传密文。
            log.warning("用户 API key 解密失败（加密密钥已更换或未配置），按未配置处理")
            api_key = ""
            key_error = "加密密钥已变更，请重新填写 API Key"
    return {
        # None=用户未设置（跟随全局 env 默认）；True/False=用户明确选择
        "review_enabled": (
            settings.workflow_llm_review_enabled if review_enabled is None else bool(review_enabled)
        ),
        "review_set": review_enabled is not None,
        "llm_base_url": llm_base_url or "",
        "llm_api_key": api_key,
        "llm_model": llm_model or "",
        # has_key=「当前是否真的有一把可用的密钥」：解密失败时密文虽在，但调不通，
        # 若仍报 True，前端会显示「已保存密钥」而实际连不上。
        "has_key": bool(api_key),
        "key_error": key_error,
        "updated_at": str(updated_at) if updated_at else "",
    }


def get_user_ai_settings(user_id: str) -> dict:
    """读取用户 AI 设置（60s 进程内缓存）；查不到返回全空默认。"""
    if not user_id:
        return _row_default()
    now = time.time()
    with _lock:
        hit = _cache.get(user_id)
    if hit and now < hit[0]:
        return dict(hit[1])
    _ensure_table()
    try:
        with get_pool().connection() as conn:
            row = conn.execute(
                """
                SELECT review_enabled, llm_base_url, llm_api_key_enc, llm_model, updated_at
                FROM user_ai_settings WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
    except Exception as e:
        log.warning("读取用户 AI 设置失败 uid={}: {}", user_id[-8:], e)
        return _row_default()
    if not row:
        result = _row_default()
    else:
        result = _row_to_settings(row)
    with _lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)), None)
        _cache[user_id] = (now + _TTL_SECONDS, dict(result))
    return result


def _row_default() -> dict:
    return {
        "review_enabled": settings.workflow_llm_review_enabled,
        "review_set": False,
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "has_key": False,
        "key_error": "",
        "updated_at": "",
    }


def save_user_ai_settings(
    user_id: str,
    *,
    review_enabled: Optional[bool] = None,
    llm_base_url: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    clear_model: bool = False,
) -> dict:
    """保存用户 AI 设置（upsert）；返回保存后的完整设置（脱敏，无明文 key）。

    None=不动该字段；llm_api_key 传空串=清除；clear_model=True 清空模型三项。
    """
    _ensure_table()
    cols: list[str] = []
    params: list = [user_id]
    if review_enabled is not None:
        cols.append("review_enabled")
        params.append(bool(review_enabled))
    if clear_model:
        cols += ["llm_base_url", "llm_api_key_enc", "llm_model"]
        params += ["", "", ""]
    else:
        if llm_base_url is not None:
            cols.append("llm_base_url")
            params.append((llm_base_url or "").strip())
        if llm_api_key is not None:
            key = (llm_api_key or "").strip()
            cols.append("llm_api_key_enc")
            params.append(encrypt_secret(key) if key else "")
        if llm_model is not None:
            cols.append("llm_model")
            params.append((llm_model or "").strip())
    if not cols:
        return public_settings(user_id)

    placeholders = ", ".join(["%s"] * len(cols))
    on_conflict = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    sql = (
        f"INSERT INTO user_ai_settings (user_id, {', '.join(cols)}) "
        f"VALUES (%s, {placeholders}) "
        f"ON CONFLICT (user_id) DO UPDATE SET {on_conflict}, updated_at = NOW()"
    )
    try:
        with get_pool().connection() as conn:
            conn.execute(sql, tuple(params))
    except Exception as e:
        log.warning("保存用户 AI 设置失败 uid={}: {}", user_id[-8:], e)
        raise
    invalidate_user_cache(user_id)
    return public_settings(user_id)


def public_settings(user_id: str) -> dict:
    """给前端的设置视图：字段白名单，明文/密文密钥都不可能外泄。"""
    s = get_user_ai_settings(user_id)
    return {
        key: s.get(key)
        for key in (
            "review_enabled",
            "review_set",
            "llm_base_url",
            "llm_model",
            "has_key",
            "key_error",
            "updated_at",
        )
    }
