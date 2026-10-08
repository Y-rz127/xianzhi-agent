"""通用 AI 解读记录：按 user_id 隔离。"""

from __future__ import annotations

import json
import uuid

from app.db import user_records
from app.db.schema import _safe_json


# 经包级转发，使测试可对 user_records._ensure_tables / get_pool 打桩
def _ensure_tables() -> None:
    user_records._ensure_tables()


def get_pool():
    return user_records.get_pool()


def add_ai_interpretation_record(
    user_id: str, source: str, question: str, payload: dict | None, interpretation: str
) -> str:
    """保存一次通用 AI 解读记录，返回记录 id。"""
    _ensure_tables()
    rid = str(uuid.uuid4())
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO ai_interpretation_records (id, user_id, source, question, payload, interpretation)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                rid,
                user_id,
                source or "unknown",
                question or "",
                json.dumps(payload or {}, ensure_ascii=False),
                interpretation or "",
            ),
        )
    return rid


def list_ai_interpretation_records(user_id: str, limit: int = 50) -> list:
    """列出某用户的通用 AI 解读记录（默认最近 50 条，倒序）。"""
    _ensure_tables()
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, source, question, payload, interpretation, created_at
            FROM ai_interpretation_records WHERE user_id = %s ORDER BY created_at DESC LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()
        return [
            {
                "id": str(r[0]),
                "source": r[1],
                "question": r[2] or "",
                "payload": r[3] if not isinstance(r[3], str) else _safe_json(r[3]),
                "interpretation": r[4] or "",
                "createdAt": str(r[5]) if r[5] else "",
            }
            for r in rows
        ]


def delete_ai_interpretation_record(user_id: str, rid: str) -> bool:
    """删除一条通用 AI 解读记录；返回是否成功删除。"""
    _ensure_tables()
    with get_pool().connection() as conn:
        cur = conn.execute(
            "DELETE FROM ai_interpretation_records WHERE user_id = %s AND id = %s",
            (user_id, rid),
        )
        return cur.rowcount > 0
