"""用户问题反馈：user_id 可空（匿名）。"""

from __future__ import annotations

import uuid

from app.db import user_records


# 经包级转发，使测试可对 user_records._ensure_tables / get_pool 打桩
def _ensure_tables() -> None:
    user_records._ensure_tables()


def get_pool():
    return user_records.get_pool()


def add_feedback(user_id: str | None, content: str, contact: str = "") -> str:
    """保存用户问题反馈（user_id 可空，表示匿名），返回反馈 id。"""
    _ensure_tables()
    fid = str(uuid.uuid4())
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO feedback (id, user_id, content, contact) VALUES (%s, %s, %s, %s)",
            (fid, user_id, content, contact or ""),
        )
    return fid


def list_feedback(limit: int = 200) -> list:
    """列出反馈（联表获取昵称），默认最近 200 条倒序。"""
    _ensure_tables()
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT f.id, f.user_id, f.content, f.contact, f.created_at,
                   u.nickname AS user_nickname
            FROM feedback f
            LEFT JOIN users u ON u.id = f.user_id::uuid
            ORDER BY f.created_at DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": str(r[0]),
                "user_id": r[1],
                "content": r[2],
                "contact": r[3] or "",
                "created_at": str(r[4]) if r[4] else "",
                "user_nickname": r[5] if r[5] else None,
            }
            for r in rows
        ]


def delete_feedback(fid: str) -> bool:
    """删除一条反馈；返回是否成功删除。"""
    _ensure_tables()
    with get_pool().connection() as conn:
        result = conn.execute("DELETE FROM feedback WHERE id = %s", (fid,))
        return result.rowcount > 0
