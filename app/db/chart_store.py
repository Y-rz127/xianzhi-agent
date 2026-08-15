"""命盘画像 / 断事知识 / 结构化命例，按命盘（birth_time + gender）隔离。

R9 拆分自 user_data.py。"""
from __future__ import annotations

import hashlib
import json
import re
import uuid

from app.db.schema import _ensure_tables, _record_error, _safe_json
from app.core.logger import log
from app.memory.postgres_memory import _get_pool


def _chart_hash(birth_time: str, gender: str) -> str:
    return hashlib.sha256(f"{birth_time}|{gender}".encode()).hexdigest()[:16]


def upsert_chart_profile(
    user_id: str,
    birth_time: str,
    gender: str,
    chart_data: dict | None = None,
    interaction_count: int = 0,
) -> str:
    """创建或更新命盘画像，返回 profile id。"""
    _ensure_tables()
    ch = _chart_hash(birth_time, gender)
    with _get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id, interaction_count FROM chart_profiles WHERE user_id = %s AND chart_hash = %s",
            (user_id, ch),
        ).fetchone()
        if row:
            pid = str(row[0])
            new_count = (row[1] or 0) + max(interaction_count, 0)
            conn.execute(
                """
                UPDATE chart_profiles
                SET chart_data = %s, interaction_count = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (json.dumps(chart_data or {}, ensure_ascii=False), new_count, pid),
            )
            return pid
        pid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO chart_profiles
                (id, user_id, chart_hash, birth_time, gender, chart_data, interaction_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (pid, user_id, ch, birth_time, gender,
             json.dumps(chart_data or {}, ensure_ascii=False), max(interaction_count, 0)),
        )
    return pid


def get_chart_profile(user_id: str, birth_time: str, gender: str) -> dict | None:
    """获取指定命盘的画像。"""
    _ensure_tables()
    ch = _chart_hash(birth_time, gender)
    with _get_pool().connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, chart_hash, birth_time, gender, chart_data,
                   common_topics, style_preference, feedback_stats, interaction_count,
                   created_at, updated_at
            FROM chart_profiles
            WHERE user_id = %s AND chart_hash = %s
            """,
            (user_id, ch),
        ).fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "user_id": row[1],
            "chart_hash": row[2],
            "birth_time": row[3],
            "gender": row[4],
            "chart_data": row[5] if not isinstance(row[5], str) else _safe_json(row[5]),
            "common_topics": list(row[6] or []),
            "style_preference": row[7] or "",
            "feedback_stats": row[8] if not isinstance(row[8], str) else _safe_json(row[8]),
            "interaction_count": row[9] or 0,
            "created_at": str(row[10]) if row[10] else "",
            "updated_at": str(row[11]) if row[11] else "",
        }


def list_chart_profiles_by_user(user_id: str) -> list:
    """列出某用户所有命盘的画像。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, chart_hash, birth_time, gender, chart_data,
                   common_topics, style_preference, feedback_stats, interaction_count,
                   created_at, updated_at
            FROM chart_profiles
            WHERE user_id = %s
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [
            {
                "id": str(r[0]),
                "user_id": r[1],
                "chart_hash": r[2],
                "birth_time": r[3],
                "gender": r[4],
                "chart_data": r[5] if not isinstance(r[5], str) else _safe_json(r[5]),
                "common_topics": list(r[6] or []),
                "style_preference": r[7] or "",
                "feedback_stats": r[8] if not isinstance(r[8], str) else _safe_json(r[8]),
                "interaction_count": r[9] or 0,
                "created_at": str(r[10]) if r[10] else "",
                "updated_at": str(r[11]) if r[11] else "",
            }
            for r in rows
        ]


def update_chart_profile_stats(
    user_id: str,
    birth_time: str,
    gender: str,
    common_topics: list[str] | None = None,
    style_preference: str | None = None,
    feedback_stats: dict | None = None,
) -> bool:
    """更新画像的统计字段（话题偏好、风格偏好、反馈统计）。"""
    _ensure_tables()
    ch = _chart_hash(birth_time, gender)
    sets: list[str] = []
    params: list = []
    if common_topics is not None:
        sets.append("common_topics = %s")
        params.append(common_topics)
    if style_preference is not None:
        sets.append("style_preference = %s")
        params.append(style_preference)
    if feedback_stats is not None:
        sets.append("feedback_stats = %s")
        params.append(json.dumps(feedback_stats, ensure_ascii=False))
    if not sets:
        return False
    sets.append("updated_at = NOW()")
    params.extend([user_id, ch])
    with _get_pool().connection() as conn:
        cur = conn.execute(
            f"UPDATE chart_profiles SET {', '.join(sets)} WHERE user_id = %s AND chart_hash = %s",
            tuple(params),
        )
        return cur.rowcount > 0


def add_chart_fact(
    user_id: str,
    chart_profile_id: str,
    conversation_id: str,
    question: str,
    answer_snippet: str,
    confidence: str = "verified",
    fact_type: str = "general",
    fact_summary: str = "",
    reason: str = "",
) -> str:
    """添加一条断事知识记录。"""
    _ensure_tables()
    fid = str(uuid.uuid4())
    with _get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO chart_facts
                (id, chart_profile_id, user_id, conversation_id, question,
                 answer_snippet, fact_type, fact_summary, confidence, reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (fid, chart_profile_id, user_id, conversation_id or "",
             question or "", answer_snippet or "", fact_type,
             fact_summary or "", confidence, reason or ""),
        )
    return fid


def get_chart_facts(
    chart_profile_id: str,
    confidence: str | None = "verified",
    limit: int = 20,
) -> list:
    """获取命盘的断事知识，默认只取已验证的。"""
    _ensure_tables()
    where = "WHERE chart_profile_id = %s"
    params: list = [chart_profile_id]
    if confidence:
        where += " AND confidence = %s"
        params.append(confidence)
    with _get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, chart_profile_id, user_id, conversation_id, question,
                   answer_snippet, fact_type, fact_summary, confidence, reason, created_at
            FROM chart_facts
            {where}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            tuple(params + [limit]),
        ).fetchall()
        return [
            {
                "id": str(r[0]),
                "chart_profile_id": str(r[1]),
                "user_id": r[2],
                "conversation_id": r[3] or "",
                "question": r[4] or "",
                "answer_snippet": r[5] or "",
                "fact_type": r[6] or "general",
                "fact_summary": r[7] or "",
                "confidence": r[8],
                "reason": r[9] or "",
                "created_at": str(r[10]) if r[10] else "",
            }
            for r in rows
        ]


def get_chart_facts_for_llm(
    chart_profile_id: str,
    limit: int = 10,
) -> tuple[list[str], list[str]]:
    """获取命盘已验证/已否定的断事摘要，供 LLM 上下文注入。

    每条断事截断到 250 字；返回条数由 limit 控制（调用方默认 6 条，SQL LIMIT 兜底）。

    Returns:
        (verified_lines, disputed_lines): 两个字符串列表，
        分别包含已验证断事和已否定断事的可读摘要。
    """
    _ensure_tables()
    verified: list[str] = []
    disputed: list[str] = []
    with _get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT question, answer_snippet, fact_summary, confidence, reason
            FROM chart_facts
            WHERE chart_profile_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (chart_profile_id, limit),
        ).fetchall()
        for r in rows:
            question = (r[0] or "").strip()
            answer = (r[1] or "").strip()
            summary = (r[2] or "").strip()
            confidence = r[3]
            reason = (r[4] or "").strip()
            if summary:
                line = summary
            elif question and answer:
                line = f"问：{question[:80]} → 答：{answer[:150]}"
            elif answer:
                line = answer[:250]
            else:
                continue
            if reason:
                line += f"（用户反馈：{reason[:60]}）"
            if len(line) > 250:
                line = line[:250]
            if confidence == "verified":
                verified.append(line)
            elif confidence == "disputed":
                disputed.append(line)
    return verified, disputed


def add_chart_case(data: dict) -> str:
    """添加一条结构化案例到 chart_cases 表（用户反馈转换的案例）。"""
    _ensure_tables()
    cid = str(uuid.uuid4())
    with _get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO chart_cases
                (id, title, source, question, analysis, domains, features, rating, verified, keywords, reason, promoted_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                cid,
                data.get("title", ""),
                data.get("source", ""),
                data.get("question", ""),
                data.get("analysis", ""),
                data.get("domains", []) or [],
                json.dumps(data.get("features", {}) or {}, ensure_ascii=False),
                data.get("rating", 4),
                data.get("verified", True),
                data.get("keywords", []) or [],
                data.get("reason", ""),
                data.get("promoted_by", ""),
            ),
        )
    return cid


def search_chart_cases(domain: str = "", min_rating: int = 4, limit: int = 200) -> list[dict]:
    """按领域搜索 chart_cases 表中的高质量案例（种子命例）。"""
    _ensure_tables()
    where = "WHERE verified = TRUE AND rating >= %s"
    params: list = [min_rating]
    if domain:
        where += " AND %s = ANY(domains)"
        params.append(domain)
    params.append(limit)
    try:
        with _get_pool().connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, title, source, question, analysis, domains, features, rating, verified, keywords
                FROM chart_cases
                {where}
                ORDER BY rating DESC, created_at DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
            return [
                {
                    "id": str(r[0]),
                    "title": r[1] or "",
                    "source": r[2] or "chart_cases",
                    "question": r[3] or "",
                    "analysis": r[4] or "",
                    "domains": list(r[5] or []),
                    "features": r[6] if isinstance(r[6], dict) else json.loads(r[6] or "{}"),
                    "rating": r[7] or 4,
                    "verified": bool(r[8]) if r[8] is not None else True,
                    "keywords": list(r[9] or []),
                }
                for r in rows
            ]
    except Exception as e:
        log.error("从 chart_cases 读取失败: {}", e)
        _record_error("user_data.read_chart_cases")
        return []


_GAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火",
    "戊": "土", "己": "土", "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}


def _extract_bazi_features(chart_data: dict | None) -> dict:
    """从 cases 表的 chart_data(JSONB) 抽取相似匹配所需的八字特征。

    返回 {day_master, day_master_wuxing, strength}，缺失字段留空。
    """
    feats: dict = {}
    if not isinstance(chart_data, dict):
        return feats
    try:
        pillars = chart_data.get("pillars")
        if isinstance(pillars, list) and len(pillars) >= 3:
            day_gan = pillars[2].get("gan") if isinstance(pillars[2], dict) else None
            if day_gan:
                feats["day_master"] = day_gan
                feats["day_master_wuxing"] = _GAN_WUXING.get(day_gan, "")
        analysis_text = chart_data.get("analysisText") or ""
        if analysis_text:
            m = re.search(r"【日主强弱】\s*(\S+)", analysis_text)
            if m:
                feats["strength"] = m.group(1)
    except Exception:
        pass
    return feats


def search_cases_for_rag(limit: int = 200) -> list[dict]:
    """检索 cases 表（命理库八字命例）用于 LLM 相似命例注入。

    内容优先级：bio/analysis/keypoints 新字段；若为空则回退 chart_data.analysisText，
    使历史命例（康熙、曾国藩等）无需手工补录即可参与检索。
    相似匹配特征（日主五行/旺衰）从 chart_data 实时抽取。
    """
    _ensure_tables()
    try:
        with _get_pool().connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name, tags, bio, analysis, keypoints, domains, chart_data
                FROM cases
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        records: list[dict] = []
        for r in rows:
            cid, name, tags, bio, analysis, keypoints, domains, chart_data = r
            chart_data = chart_data if isinstance(chart_data, dict) else (json.loads(chart_data) if chart_data else {})
            parts: list[str] = []
            if bio:
                parts.append(f"生平简介：{bio}")
            if analysis:
                parts.append(f"命局结构分析：{analysis}")
            if keypoints:
                parts.append(f"命理特征要点：{keypoints}")
            # 新字段缺失时回退到排盘引擎生成的 analysisText
            if not parts and chart_data.get("analysisText"):
                parts.append(chart_data["analysisText"])
            content = "\n\n".join(parts)
            if not content.strip():
                continue
            records.append({
                "id": str(cid),
                "title": name or "",
                "question_domain": (list(domains)[0] if domains else "general"),
                "domains": list(domains or []),
                "analysis": analysis or "",
                "content": content,
                "source": "cases",
                "rating": 5,
                "verified": True,
                "features": _extract_bazi_features(chart_data),
            })
        return records
    except Exception as e:
        log.error("从 cases 读取命例失败: {}", e)
        _record_error("user_data.read_cases")
        return []
