"""运行时配置 KV 存储（同步 psycopg；用于管理后台可动态修改的配置，如 LLM 降级链）。

- 修改即热生效（读取方带短 TTL 缓存）
- 数据库不可达时读取方走各自默认值（见 llm_failover.get_active_chain）
"""
from __future__ import annotations

import json

from app.db.pool import get_pool


def get_config(key: str, default=None):
    """读取配置；key 不存在或读取失败返回 default。"""
    try:
        with get_pool().connection() as conn:
            row = conn.execute("SELECT value FROM app_config WHERE key = %s", (key,)).fetchone()
        return row[0] if row else default
    except Exception:
        return default


def set_config(key: str, value) -> None:
    """写入（UPSERT）配置。"""
    with get_pool().connection() as conn:
        conn.execute(
            """INSERT INTO app_config (key, value, updated_at) VALUES (%s, %s, now())
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
            (key, json.dumps(value, ensure_ascii=False)),
        )