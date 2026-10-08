"""PG 实现的 KV 配置存储（infra 层）。

导入本模块即把 ``PostgresKVStore`` 注册进 core 的 KV 注册表，
core 侧因此只依赖 ``KVStore`` 协议、不再反向 import db（原 P0-3 倒置边）。

表结构见 ``migrations/versions/3c1d8f5e92b0_app_config_kv.py``：
``key TEXT 主键 / value JSONB``，故 get 直接返回反序列化后的对象。
"""

from __future__ import annotations

import json

from app.core.config.kv import register_kv_store
from app.db.pool import get_pool


class PostgresKVStore:
    """基于 ``app_config`` 表的 KV 存储。"""

    def get(self, key: str, default=None):
        """读取配置；key 不存在或读取失败返回 default。"""
        try:
            with get_pool().connection() as conn:
                row = conn.execute("SELECT value FROM app_config WHERE key = %s", (key,)).fetchone()
            return row[0] if row else default
        except Exception:
            return default

    def set(self, key: str, value) -> None:
        """写入（UPSERT）配置。"""
        with get_pool().connection() as conn:
            conn.execute(
                """INSERT INTO app_config (key, value, updated_at) VALUES (%s, %s, now())
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
                (key, json.dumps(value, ensure_ascii=False)),
            )


register_kv_store(PostgresKVStore())
