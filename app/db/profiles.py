"""八字档案（bazi_profiles）CRUD，按 user_id 隔离。"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from app.db.schema import _ensure_tables
from app.memory.postgres_memory import _get_pool


def create_profile(user_id: str, data: dict) -> str:
    """创建一条八字档案，返回新记录 id。"""
    _ensure_tables()
    pid = str(uuid.uuid4())
    with _get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO bazi_profiles
                (id, user_id, name, relation, birth_time, gender, sect, yun_sect, chart_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                pid,
                user_id,
                data["name"],
                data.get("relation", ""),
                data["birth_time"],
                data["gender"],
                int(data.get("sect", 2)),
                int(data.get("yun_sect", 1)),
                json.dumps(data.get("chart_data") or {}, ensure_ascii=False),
            ),
        )
    return pid


def list_profiles(user_id: str) -> list:
    """列出某用户全部八字档案（按创建时间倒序）。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, relation, birth_time, gender, sect, yun_sect, chart_data, created_at
            FROM bazi_profiles WHERE user_id = %s ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [_row_to_profile(r) for r in rows]


def get_profile(user_id: str, pid: str) -> Optional[dict]:
    """查询单条八字档案；不属于该用户或不存在时返回 None。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        row = conn.execute(
            """
            SELECT id, name, relation, birth_time, gender, sect, yun_sect, chart_data, created_at
            FROM bazi_profiles WHERE user_id = %s AND id = %s
            """,
            (user_id, pid),
        ).fetchone()
        return _row_to_profile(row) if row else None


def update_profile(user_id: str, pid: str, data: dict) -> bool:
    """更新八字档案字段；返回是否命中并修改了记录。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        cur = conn.execute(
            """
            UPDATE bazi_profiles SET
                name = %s, relation = %s, birth_time = %s, gender = %s,
                sect = %s, yun_sect = %s, chart_data = %s, updated_at = NOW()
            WHERE user_id = %s AND id = %s
            """,
            (
                data.get("name"),
                data.get("relation", ""),
                data.get("birth_time"),
                data.get("gender"),
                int(data.get("sect", 2)),
                int(data.get("yun_sect", 1)),
                json.dumps(data.get("chart_data") or {}, ensure_ascii=False),
                user_id,
                pid,
            ),
        )
        return cur.rowcount > 0


def delete_profile(user_id: str, pid: str) -> bool:
    """删除八字档案；返回是否成功删除。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        cur = conn.execute(
            "DELETE FROM bazi_profiles WHERE user_id = %s AND id = %s", (user_id, pid)
        )
        return cur.rowcount > 0


def _row_to_profile(r) -> dict:
    """数据库行 → 前端档案字典（兼容 chart_data 为字符串的情况）。"""
    chart = r[7]
    if isinstance(chart, str):
        try:
            chart = json.loads(chart)
        except Exception:
            chart = {}
    return {
        "id": str(r[0]),
        "name": r[1],
        "relation": r[2] or "",
        "birthTime": r[3],
        "gender": r[4],
        "sect": r[5],
        "yunSect": r[6],
        "chartData": chart or {},
        "createdAt": str(r[8]) if r[8] else "",
    }
