"""命例收藏：按 user_id 隔离。"""

from __future__ import annotations

import uuid

from app.db import user_records
from app.db.schema import _safe_json
from app.domain.chart_format import extract_bazi_brief


# 经包级转发，使测试可对 user_records._ensure_tables / get_pool 打桩
def _ensure_tables() -> None:
    user_records._ensure_tables()


def get_pool():
    return user_records.get_pool()


def add_favorite(user_id: str, case_id: str) -> str:
    """添加命例收藏（user_id+case_id 唯一，重复收藏不报错），返回收藏记录 id。"""
    _ensure_tables()
    fid = str(uuid.uuid4())
    with get_pool().connection() as conn:
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
    """列出某用户收藏的命例。

    主联 cases 表（八字命例），并兼容联 chart_cases 表（Web 端命例，字段做映射）。
    """
    _ensure_tables()
    result = []
    with get_pool().connection() as conn:
        # 联 cases 表（八字命例）
        rows_cases = conn.execute(
            """
            SELECT f.case_id, c.name, c.tags, c.birth_time, c.gender, c.chart_data, f.created_at
            FROM chart_favorites f
            LEFT JOIN cases c ON c.id::text = f.case_id
            WHERE f.user_id = %s AND c.id IS NOT NULL
            """,
            (user_id,),
        ).fetchall()
        for r in rows_cases:
            chart_data = r[5] if isinstance(r[5], dict) else _safe_json(r[5]) if r[5] else {}
            result.append(
                {
                    "caseId": str(r[0]),
                    "title": r[1] or "",
                    "name": r[1] or "",
                    "source": "cases",
                    "birthTime": r[3] or "",
                    "gender": r[4] or "",
                    "tags": list(r[2] or []),
                    "chartData": chart_data,
                    "bazi": extract_bazi_brief(chart_data),
                    "createdAt": str(r[6]) if r[6] else "",
                }
            )

        # 兼容联 chart_cases 表（用户反馈转换的结构化案例库）
        rows_chart = conn.execute(
            """
            SELECT f.case_id, c.title, c.source, c.question, c.analysis,
                   c.domains, c.features, c.rating, c.verified, f.created_at
            FROM chart_favorites f
            LEFT JOIN chart_cases c ON c.id::text = f.case_id
            WHERE f.user_id = %s AND c.id IS NOT NULL
            """,
            (user_id,),
        ).fetchall()
        for r in rows_chart:
            result.append(
                {
                    "caseId": str(r[0]),
                    "title": r[1] or "",
                    "source": r[2] or "",
                    "question": r[3] or "",
                    "analysis": r[4] or "",
                    "domains": list(r[5] or []),
                    "features": r[6] if not isinstance(r[6], str) else _safe_json(r[6]),
                    "rating": r[7] or 4,
                    "verified": bool(r[8]) if r[8] is not None else True,
                    "createdAt": str(r[9]) if r[9] else "",
                }
            )

    result.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
    return result


def remove_favorite(user_id: str, case_id: str) -> bool:
    """取消收藏；返回是否成功删除。"""
    _ensure_tables()
    with get_pool().connection() as conn:
        cur = conn.execute(
            "DELETE FROM chart_favorites WHERE user_id = %s AND case_id = %s",
            (user_id, case_id),
        )
        return cur.rowcount > 0


def is_favorite(user_id: str, case_id: str) -> bool:
    """判断某命例是否已被该用户收藏。"""
    _ensure_tables()
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM chart_favorites WHERE user_id = %s AND case_id = %s",
            (user_id, case_id),
        ).fetchone()
        return row is not None
