"""文档指纹持久化：本地文件 + PostgreSQL 双写，判断向量索引是否可复用。

容器重启会重置本地文件系统，原指纹文件丢失会导致每次启动误判"需全量重建"，
进而重复 embedding 全部知识片段（约 761 个）。PG 中向量索引本身已持久，
只要指纹存活，重启即可直接复用现成索引、零 embedding。本地文件保留为兜底
（首次迁移 / PG 不可用降级）。

连接统一走 ``app.db.pool`` 的模块级池 —— 本模块曾自建第二个 ConnectionPool
（同 DSN、同 check 逻辑），既多占 1~2 个空闲连接，又让应用关停要分别关两个池。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.core.config import settings
from app.core.logger import log
from app.db.pool import get_pool

_FINGERPRINT_FILE = "knowledge_fingerprint.json"


def _fingerprint_path() -> Path:
    return settings.vector_db_dir / _FINGERPRINT_FILE


def _ensure_table(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rag_fingerprint ("
        " id smallint PRIMARY KEY DEFAULT 1,"
        " data jsonb NOT NULL,"
        " updated_at timestamptz DEFAULT now())"
    )


def _load_pg() -> dict | None:
    try:
        pool = get_pool()
        with pool.connection() as conn:
            _ensure_table(conn)
            row = conn.execute("SELECT data FROM rag_fingerprint WHERE id=1").fetchone()
            if row and row[0] is not None:
                return row[0] if isinstance(row[0], dict) else json.loads(row[0])
    except Exception as e:
        log.warning("PG 指纹读取失败，回退本地文件: {}", e)
    return None


def _save_pg(data: dict) -> None:
    try:
        pool = get_pool()
        with pool.connection() as conn:
            _ensure_table(conn)
            conn.execute(
                "INSERT INTO rag_fingerprint (id, data, updated_at) "
                "VALUES (1, %(data)s::jsonb, now()) "
                "ON CONFLICT (id) DO UPDATE SET data=%(data)s::jsonb, updated_at=now()",
                {"data": json.dumps(data, ensure_ascii=False)},
            )
    except Exception as e:
        log.warning("PG 指纹写入失败（不影响启动，下次从本地文件恢复）: {}", e)


def load() -> dict | None:
    fp = _load_pg()  # 优先 PG：容器重启后本地文件会被清空
    if fp:
        return fp
    p = _fingerprint_path()  # 回退本地文件（兼容首次迁移 / PG 不可用降级）
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save(
    docs_hash: str,
    embedding_id: str,
    store_type: str,
    chunk_size: int,
    chunk_overlap: int,
    meta_version: int = 0,
) -> None:
    data = {
        "docs_hash": docs_hash,
        "embedding_id": embedding_id,
        "store_type": store_type,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "meta_version": meta_version,
        "updated_at": time.time(),
    }
    p = _fingerprint_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _save_pg(data)  # 同时持久化到 PG，避免容器重启后丢失


def is_up_to_date(
    docs_hash: str,
    embedding_id: str,
    store_type: str,
    chunk_size: int,
    chunk_overlap: int,
    meta_version: int = 0,
) -> bool:
    fp = load()
    if not fp:
        return False
    return (
        fp.get("docs_hash") == docs_hash
        and fp.get("embedding_id") == embedding_id
        and fp.get("store_type") == store_type
        and fp.get("chunk_size") == chunk_size
        and fp.get("chunk_overlap") == chunk_overlap
        and fp.get("meta_version", 0) == meta_version
    )
