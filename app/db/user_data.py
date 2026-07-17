"""用户私有数据：八字档案 / 命例收藏 / 塔罗记录 / 问题反馈。

全部按 user_id 隔离（user_id 为 users.id 的字符串）。主存储 PostgreSQL，
复用 app.memory.postgres_memory 的模块级连接池。
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from app.logger import log
from app.memory.postgres_memory import _get_pool

_READY = False


def _ensure_tables():
    """惰性建表：首次调用时创建八字档案/命例收藏/塔罗记录/反馈四张表及索引，之后直接返回。"""
    global _READY
    if _READY:
        return
    with _get_pool().connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bazi_profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                relation TEXT DEFAULT '',
                birth_time TEXT NOT NULL,
                gender TEXT NOT NULL,
                sect INT DEFAULT 2,
                yun_sect INT DEFAULT 1,
                chart_data JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_profiles_user ON bazi_profiles(user_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_favorites (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE (user_id, case_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fav_user ON chart_favorites(user_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tarot_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                spread TEXT NOT NULL,
                question TEXT DEFAULT '',
                cards JSONB,
                interpretation TEXT DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tarot_user ON tarot_records(user_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT,
                content TEXT NOT NULL,
                contact TEXT DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
    _READY = True
    log.info("用户私有数据表已就绪")


# ---------------- 八字档案 ----------------

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
    """将数据库行元组转换为前端使用的档案字典（兼容 chart_data 为字符串的情况）。"""
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


# ---------------- 命例收藏 ----------------

def add_favorite(user_id: str, case_id: str) -> str:
    """添加命例收藏（user_id+case_id 唯一，重复收藏不报错），返回收藏记录 id。"""
    _ensure_tables()
    fid = str(uuid.uuid4())
    with _get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO chart_favorites (id, user_id, case_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, case_id) DO NOTHING
            """,
            (fid, user_id, case_id),
        )
    return fid


def list_favorites(user_id: str) -> list:
    """列出某用户收藏的命例（联表获取命例名称/标签/排盘等），按收藏时间倒序。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT f.case_id, c.name, c.tags, c.birth_time, c.gender, c.chart_data, f.created_at
            FROM chart_favorites f
            LEFT JOIN chart_cases c ON c.id::text = f.case_id
            WHERE f.user_id = %s ORDER BY f.created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [
            {
                "caseId": str(r[0]),
                "name": r[1] or "未知命例",
                "tags": list(r[2] or []),
                "birthTime": r[3],
                "gender": r[4],
                "chartData": r[5] if not isinstance(r[5], str) else _safe_json(r[5]),
                "createdAt": str(r[6]) if r[6] else "",
            }
            for r in rows
        ]


def remove_favorite(user_id: str, case_id: str) -> bool:
    """取消收藏；返回是否成功删除。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        cur = conn.execute(
            "DELETE FROM chart_favorites WHERE user_id = %s AND case_id = %s",
            (user_id, case_id),
        )
        return cur.rowcount > 0


def is_favorite(user_id: str, case_id: str) -> bool:
    """判断某命例是否已被该用户收藏。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM chart_favorites WHERE user_id = %s AND case_id = %s",
            (user_id, case_id),
        ).fetchone()
        return row is not None


# ---------------- 塔罗记录 ----------------

def add_tarot_record(user_id: str, spread: str, question: str, cards: list, interpretation: str) -> str:
    """保存一次塔罗占卜记录，返回记录 id。"""
    _ensure_tables()
    rid = str(uuid.uuid4())
    with _get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO tarot_records (id, user_id, spread, question, cards, interpretation)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                rid,
                user_id,
                spread,
                question or "",
                json.dumps(cards or [], ensure_ascii=False),
                interpretation or "",
            ),
        )
    return rid


def list_tarot_records(user_id: str, limit: int = 50) -> list:
    """列出某用户的塔罗记录（默认最近 50 条，倒序）。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, spread, question, cards, interpretation, created_at
            FROM tarot_records WHERE user_id = %s ORDER BY created_at DESC LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()
        return [
            {
                "id": str(r[0]),
                "spread": r[1],
                "question": r[2] or "",
                "cards": r[3] if not isinstance(r[3], str) else _safe_json(r[3]),
                "interpretation": r[4] or "",
                "createdAt": str(r[5]) if r[5] else "",
            }
            for r in rows
        ]


def delete_tarot_record(user_id: str, rid: str) -> bool:
    """删除一条塔罗记录；返回是否成功删除。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        cur = conn.execute(
            "DELETE FROM tarot_records WHERE user_id = %s AND id = %s", (user_id, rid)
        )
        return cur.rowcount > 0


# ---------------- 问题反馈 ----------------

def add_feedback(user_id: str | None, content: str, contact: str = "") -> str:
    """保存用户问题反馈（user_id 可空，表示匿名），返回反馈 id。"""
    _ensure_tables()
    fid = str(uuid.uuid4())
    with _get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO feedback (id, user_id, content, contact) VALUES (%s, %s, %s, %s)",
            (fid, user_id, content, contact or ""),
        )
    return fid


def list_feedback(limit: int = 200) -> list:
    """列出反馈（联表获取昵称），默认最近 200 条倒序。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
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
    with _get_pool().connection() as conn:
        result = conn.execute(
            "DELETE FROM feedback WHERE id = %s", (fid,)
        )
        return result.rowcount > 0
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


def _safe_json(s: str):
    """安全解析 JSON 字符串，解析失败时返回空字典。"""
    try:
        return json.loads(s)
    except Exception:
        return {}
