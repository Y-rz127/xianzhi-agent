"""用户私有数据：八字档案 / 命例收藏 / 塔罗记录 / 问题反馈 / 命盘画像 / 断事知识。

全部按 user_id 隔离（user_id 为 users.id 的字符串）。主存储 PostgreSQL，
复用 app.memory.postgres_memory 的模块级连接池。

命盘画像（chart_profiles）按 命盘（birth_time + gender）隔离，而非按用户隔离：
一个命盘对应一条画像记录，同一用户可拥有多个命盘的画像。
断事知识（chart_facts）存储用户 ✓ 确认过的 AI 断事内容，供后续对话学习。
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS answer_feedback (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT,
                conversation_id TEXT DEFAULT '',
                question TEXT DEFAULT '',
                answer TEXT NOT NULL,
                rating TEXT NOT NULL,
                reason TEXT DEFAULT '',
                chart_snapshot JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_answer_feedback_created ON answer_feedback(created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_answer_feedback_rating ON answer_feedback(rating)"
        )
        conn.execute(
            "ALTER TABLE answer_feedback ADD COLUMN IF NOT EXISTS reviewed BOOLEAN DEFAULT FALSE"
        )
        conn.execute(
            "ALTER TABLE answer_feedback ADD COLUMN IF NOT EXISTS reviewed_by TEXT DEFAULT ''"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_answer_feedback_reviewed ON answer_feedback(reviewed)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                chart_hash TEXT NOT NULL,
                birth_time TEXT NOT NULL,
                gender TEXT NOT NULL,
                chart_data JSONB,
                common_topics TEXT[] DEFAULT '{}',
                style_preference TEXT DEFAULT '',
                feedback_stats JSONB DEFAULT '{}',
                interaction_count INT DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE (user_id, chart_hash)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_profiles_user ON chart_profiles(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_profiles_hash ON chart_profiles(chart_hash)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_facts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                chart_profile_id UUID REFERENCES chart_profiles(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                conversation_id TEXT DEFAULT '',
                question TEXT DEFAULT '',
                answer_snippet TEXT DEFAULT '',
                fact_type TEXT DEFAULT 'general',
                fact_summary TEXT DEFAULT '',
                confidence TEXT NOT NULL DEFAULT 'verified',
                reason TEXT DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_facts_profile ON chart_facts(chart_profile_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_facts_user ON chart_facts(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_facts_confidence ON chart_facts(confidence)"
        )
        # 命理库八字信息（Web 端新建命例）：cases 表（Bazi 结构）
        # 新增 bio/analysis/keypoints/domains 用于承载命例解读文案（替代已废弃的 markdown 种子文档）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT NOT NULL,
                tags TEXT[] DEFAULT '{}',
                birth_time TEXT NOT NULL,
                gender TEXT NOT NULL,
                chart_data JSONB,
                bio TEXT DEFAULT '',
                analysis TEXT DEFAULT '',
                keypoints TEXT DEFAULT '',
                domains TEXT[] DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        # 对已经存在的 cases 表做在线迁移（新列不会破坏旧数据），必须在建索引前完成
        for col, col_type in [
            ("bio", "TEXT DEFAULT ''"),
            ("analysis", "TEXT DEFAULT ''"),
            ("keypoints", "TEXT DEFAULT ''"),
            ("domains", "TEXT[] DEFAULT '{}'"),
        ]:
            conn.execute(
                f"ALTER TABLE cases ADD COLUMN IF NOT EXISTS {col} {col_type}"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cases_tags ON cases USING GIN (tags)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cases_domains ON cases USING GIN (domains)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cases_updated ON cases(updated_at DESC)"
        )
        # 用户反馈转换的结构化案例库：chart_cases 表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_cases (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title TEXT DEFAULT '',
                source TEXT DEFAULT '',
                question TEXT DEFAULT '',
                analysis TEXT NOT NULL,
                domains TEXT[] DEFAULT '{}',
                features JSONB DEFAULT '{}',
                rating INT DEFAULT 4,
                verified BOOLEAN DEFAULT TRUE,
                keywords TEXT[] DEFAULT '{}',
                promoted_by TEXT DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                reason TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_cases_domains ON chart_cases USING GIN (domains)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_cases_rating ON chart_cases(rating DESC)"
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
    """列出某用户收藏的命例。

    主要联 cases 表（八字命例），同时兼容 chart_cases 表（Web端命例）。
    返回格式以 cases 字段为主（title/source/question/analysis/domains/features），
    chart_cases 的字段做兼容映射（name→title, chart_data→features 等）。
    """
    _ensure_tables()
    result = []
    with _get_pool().connection() as conn:
        # 主查询：联 cases 表（命理库八字 / Web 端新建命例，Bazi 结构）
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
            result.append({
                "caseId": str(r[0]),
                "title": r[1] or "",
                "name": r[1] or "",
                "source": "cases",
                "birthTime": r[3] or "",
                "gender": r[4] or "",
                "tags": list(r[2] or []),
                "chartData": chart_data,
                "bazi": _extract_bazi_brief(chart_data),
                "createdAt": str(r[6]) if r[6] else "",
            })

        # 兼容查询：联 chart_cases 表（用户反馈转换的结构化案例库）
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
            result.append({
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
            })

    result.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
    return result


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


# ---------------- 回答偏好反馈 ----------------

def add_answer_feedback(
    user_id: str | None,
    conversation_id: str,
    question: str,
    answer: str,
    rating: str,
    reason: str = "",
    chart_snapshot: dict | None = None,
) -> str:
    """保存单次 AI 回答的点赞/点踩反馈，用于后续案例筛选、DPO 和评估集构建。"""
    _ensure_tables()
    if rating not in {"up", "down"}:
        raise ValueError("rating 必须是 up 或 down")
    fid = str(uuid.uuid4())
    with _get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO answer_feedback
                (id, user_id, conversation_id, question, answer, rating, reason, chart_snapshot)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                fid,
                user_id,
                conversation_id or "",
                question or "",
                answer,
                rating,
                reason or "",
                json.dumps(chart_snapshot or {}, ensure_ascii=False),
            ),
        )
    return fid


def list_answer_feedback(limit: int = 200, rating: str | None = None) -> list:
    """列出回答偏好反馈，供后台筛选高质量样本。"""
    _ensure_tables()
    where = "WHERE af.rating = %s" if rating in {"up", "down"} else ""
    params = (rating, limit) if where else (limit,)
    with _get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            SELECT af.id, af.user_id, af.conversation_id, af.question, af.answer,
                   af.rating, af.reason, af.chart_snapshot, af.created_at,
                   af.reviewed, af.reviewed_by,
                   u.nickname AS user_nickname
            FROM answer_feedback af
            LEFT JOIN users u ON u.id = af.user_id::uuid
            {where}
            ORDER BY af.created_at DESC LIMIT %s
            """,
            params,
        ).fetchall()
        return [
            {
                "id": str(r[0]),
                "user_id": r[1],
                "conversation_id": r[2] or "",
                "question": r[3] or "",
                "answer": r[4] or "",
                "rating": r[5],
                "reason": r[6] or "",
                "chart_snapshot": r[7] if not isinstance(r[7], str) else _safe_json(r[7]),
                "created_at": str(r[8]) if r[8] else "",
                "reviewed": bool(r[9]) if r[9] is not None else False,
                "reviewed_by": r[10] or "",
                "user_nickname": r[11] if r[11] else None,
            }
            for r in rows
        ]


def export_sft_samples(limit: int = 1000, rating: str = "up") -> list[dict]:
    """导出 SFT 样本：优先使用好评回答，供 LoRA 微调前人工审核。"""
    items = list_answer_feedback(limit=limit, rating=rating)
    samples: list[dict] = []
    for item in items:
        question = (item.get("question") or "").strip()
        answer = (item.get("answer") or "").strip()
        if not question or not answer:
            continue
        chart_snapshot = item.get("chart_snapshot") or {}
        samples.append({
            "id": item["id"],
            "messages": [
                {
                    "role": "system",
                    "content": "你是先知，精通八字命理。请以系统排盘事实为准，结合命理规则和案例经验，给出克制、具体、可复核的分析。",
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "question": question,
                        "chart_snapshot": chart_snapshot,
                    }, ensure_ascii=False),
                },
                {"role": "assistant", "content": answer},
            ],
            "metadata": {
                "conversation_id": item.get("conversation_id", ""),
                "rating": item.get("rating", ""),
                "reason": item.get("reason", ""),
                "created_at": item.get("created_at", ""),
            },
        })
    return samples


def _safe_json(s: str):
    """安全解析 JSON 字符串，解析失败时返回空字典。"""
    try:
        return json.loads(s)
    except Exception:
        return {}


def _extract_bazi_brief(chart_data: Any) -> str | None:
    """从 chart_data JSON 中提取四柱干支摘要，如 '辛卯 丁酉 庚午 丙子'。"""
    try:
        pillars = chart_data.get("pillars")
        if isinstance(pillars, list) and len(pillars) >= 4:
            parts = []
            for p in pillars:
                gz = p.get("ganzhi") if isinstance(p, dict) else None
                if isinstance(gz, list) and len(gz) >= 2:
                    parts.append(f"{gz[0]}{gz[1]}")
                elif isinstance(gz, str):
                    parts.append(gz)
            if len(parts) >= 4:
                return " ".join(parts[:4])
    except Exception:
        pass
    return None


def mark_answer_reviewed(fid: str, reviewer: str = "") -> bool:
    """标记回答反馈为已审核。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        cur = conn.execute(
            "UPDATE answer_feedback SET reviewed = TRUE, reviewed_by = %s WHERE id = %s",
            (reviewer, fid),
        )
        return cur.rowcount > 0


def get_answer_feedback(fid: str) -> dict | None:
    """查询单条回答反馈。"""
    _ensure_tables()
    with _get_pool().connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, conversation_id, question, answer,
                   rating, reason, chart_snapshot, created_at, reviewed, reviewed_by
            FROM answer_feedback WHERE id = %s
            """,
            (fid,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "user_id": row[1],
            "conversation_id": row[2] or "",
            "question": row[3] or "",
            "answer": row[4] or "",
            "rating": row[5],
            "reason": row[6] or "",
            "chart_snapshot": row[7] if not isinstance(row[7], str) else _safe_json(row[7]),
            "created_at": str(row[8]) if row[8] else "",
            "reviewed": bool(row[9]) if row[9] is not None else False,
            "reviewed_by": row[10] or "",
        }


def promote_to_case(fid: str, reviewer: str = "") -> tuple[str, str] | None:
    """将已审核的好评回答转为结构化案例 JSON 文件。

    返回 (case_id, file_path) 或 None（失败时）。
    """
    _ensure_tables()
    item = get_answer_feedback(fid)
    if not item:
        return None
    if item["rating"] not in {"up", "down"}:
        return None
    mark_answer_reviewed(fid, reviewer)
    from datetime import datetime
    from app.rag.retrieval import detect_domain as _detect_domain
    
    case_id = f"case_feedback_{fid[:8]}"
    chart = item.get("chart_snapshot") or {}
    
    # 从 chartData 提取特征（小程序传的 chart_snapshot.chartData 结构）
    chart_data_obj = chart.get("chartData") or {}
    features_raw = chart.get("features", {}) or {}
    
    # 多层回退提取特征：features -> chartData -> chartData.wuxing -> chart
    day_master = (features_raw.get("day_master") or 
                  chart_data_obj.get("dayMaster") or 
                  chart_data_obj.get("day_master") or 
                  chart.get("day_master") or "")
    day_master_wuxing = (features_raw.get("day_master_wuxing") or 
                         chart_data_obj.get("dayMasterWuxing") or 
                         chart_data_obj.get("day_master_wuxing") or 
                         chart.get("day_master_wuxing") or "")
    strength = (features_raw.get("strength") or 
                chart_data_obj.get("strength") or 
                chart.get("strength") or "")
    pattern = (features_raw.get("pattern") or 
               chart_data_obj.get("pattern") or 
               chart.get("pattern") or "")
    useful_god = (features_raw.get("useful_god") or 
                  chart_data_obj.get("usefulGod") or 
                  chart_data_obj.get("useful_god") or 
                  chart.get("useful_god") or "")
    key_traits = (features_raw.get("key_traits") or 
                  chart_data_obj.get("keyTraits") or 
                  chart_data_obj.get("key_traits") or 
                  chart.get("key_traits") or [])
    combinations = (features_raw.get("combinations") or 
                    chart_data_obj.get("combinations") or 
                    chart.get("combinations") or [])
    clashes = (features_raw.get("clashes") or 
               chart_data_obj.get("clashes") or 
               chart.get("clashes") or [])
    sects = (features_raw.get("sects") or 
             chart_data_obj.get("sects") or 
             chart.get("sects") or [])
    
    # 从 chart_data_obj 的 wuxing 子结构补充提取（wuxing 可能是 dict 或 list）
    if chart_data_obj:
        wuxing = chart_data_obj.get("wuxing") or {}
        if isinstance(wuxing, dict):
            day_master = day_master or wuxing.get("day_master") or wuxing.get("dayMaster") or ""
            day_master_wuxing = day_master_wuxing or wuxing.get("day_master_wuxing") or wuxing.get("dayMasterWuxing") or ""
            strength = strength or wuxing.get("strength") or ""
    
    # 如果特征仍然为空，但提供了 birth_time/gender，则重新排盘获取
    if not day_master:
        birth_time = (chart.get("birth_time") or 
                      (chart.get("birthInfo") or {}).get("time") or 
                      (chart.get("chartData") or {}).get("birth_time") or "")
        gender = (chart.get("gender") or 
                  (chart.get("birthInfo") or {}).get("gender") or 
                  (chart.get("chartData") or {}).get("gender") or "")
        if birth_time and gender:
            try:
                from app.domain.bazi_engine import build_bazi_chart
                bazi = build_bazi_chart(birth_time, gender, sect=2, yun_sect=1, dayun_count=10, liunian_years=8)
                day_master = bazi.wuxing.day_master or ""
                day_master_wuxing = bazi.wuxing.day_master_wuxing or ""
                strength = bazi.wuxing.strength or ""
                pattern = pattern or bazi.analysis.pattern_hint or ""
                useful_god = useful_god or bazi.wuxing.useful_hint or ""
                combinations = combinations or list(bazi.analysis.combinations or [])
                clashes = clashes or list(bazi.analysis.clashes or [])
                log.info("转案例时重新排盘获取特征: {} {}", birth_time, gender)
            except Exception as e:
                log.warning("重新排盘获取特征失败: {}", e)
    
    # 根据 question + answer 推断 domain
    detected_domain = _detect_domain(item["question"] + " " + item["answer"]) or "general"
    domains = chart.get("domains")
    if not domains or domains == ["general"]:
        domains = [detected_domain]
    
    is_positive = item["rating"] == "up"
    case_data = {
        "id": case_id,
        "source": "用户反馈",
        "type": "真实反馈案例",
        "title": f"用户反馈案例 - {item['question'][:30]}",
        "features": {
            "day_master": day_master,
            "day_master_wuxing": day_master_wuxing,
            "strength": strength,
            "pattern": pattern,
            "useful_god": useful_god,
            "key_traits": key_traits,
            "combinations": combinations,
            "clashes": clashes,
            "sects": sects,
        },
        "domains": domains,
        "question": item["question"],
        "analysis": item["answer"],
        "conclusion": "",
        "keywords": chart.get("keywords", []),
        "rating": 5 if is_positive else 2,
        "verified": is_positive,
        "promoted_at": datetime.now().isoformat(),
        "promoted_by": reviewer,
    }
    # 写入数据库 chart_cases 表
    cid = add_chart_case({
        "title": case_data["title"],
        "source": case_data["source"],
        "question": case_data["question"],
        "analysis": case_data["analysis"],
        "domains": case_data["domains"],
        "features": case_data["features"],
        "rating": case_data["rating"],
        "verified": case_data["verified"],
        "keywords": case_data["keywords"],
        "promoted_by": case_data["promoted_by"],
        "reason": item.get("reason", ""),
    })
    log.info("案例已沉淀到DB: {} → chart_cases/{}", fid, cid)
    return cid, str(cid)


def export_dpo_samples(limit: int = 500) -> list[dict]:
    """导出 DPO 偏好对：同一 question 下有 up 和 down 回答的配对。

    用于 DPO 训练：chosen = up 回答, rejected = down 回答。
    """
    _ensure_tables()
    with _get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            SELECT question, rating, answer, chart_snapshot
            FROM answer_feedback
            WHERE question != '' AND answer != ''
            ORDER BY question, rating DESC, created_at DESC
            LIMIT {int(limit * 2)}
            """
        ).fetchall()
    grouped: dict[str, dict] = {}
    for r in rows:
        q = (r[0] or "").strip()
        if not q:
            continue
        key = q[:120]
        if key not in grouped:
            grouped[key] = {"question": q, "up": None, "down": None, "chart_snapshot": None}
        rating = r[1]
        answer = (r[2] or "").strip()
        if rating == "up" and grouped[key]["up"] is None:
            grouped[key]["up"] = answer
            grouped[key]["chart_snapshot"] = r[3] if not isinstance(r[3], str) else _safe_json(r[3])
        elif rating == "down" and grouped[key]["down"] is None:
            grouped[key]["down"] = answer
    samples: list[dict] = []
    for entry in grouped.values():
        if entry["up"] and entry["down"]:
            samples.append({
                "prompt": entry["question"],
                "chosen": entry["up"],
                "rejected": entry["down"],
                "metadata": {
                    "chart_snapshot": entry["chart_snapshot"] or {},
                },
            })
    return samples


# ---------------- 命盘画像（按命盘隔离，一个 birth_time+gender 一个画像） ----------------


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


# ---------------- 断事知识（用户 ✓ 确认过的 AI 断事，按命盘隔离） ----------------


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

    每条断事截断到 250 字，正负反馈总计不超过 2500 字。

    Returns:
        (verified_lines, disputed_lines): 两个字符串列表，
        分别包含已验证断事和已否定断事的可读摘要。
    """
    _ensure_tables()
    verified: list[str] = []
    disputed: list[str] = []
    total_chars = 0
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
            if total_chars >= 2500:
                break
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
            total_chars += len(line)
    return verified, disputed


# ---------------- 结构化案例库（替代 data/cases/*.json） ----------------


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
        log.warning("从 chart_cases 读取失败: {}", e)
        return []


# 天干 -> 五行 映射（用于从 cases.chart_data 抽取日主五行）
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
        log.warning("从 cases 读取命例失败: {}", e)
        return []


def migrate_json_cases_to_db() -> int:
    """将 data/cases/*.json 文件迁移到 chart_cases 表（结构化案例库）。"""
    import json as _json
    from pathlib import Path as _Path
    cases_dir = _Path("data/cases")
    if not cases_dir.exists():
        log.info("[cases迁移] data/cases 目录不存在，跳过")
        return 0
    count = 0
    for path in sorted(cases_dir.glob("*.json")):
        try:
            payload = _json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("[cases迁移] 读取失败 {}: {}", path, e)
            continue
        items = payload.get("cases", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            items = [items]
        for item in items:
            if not isinstance(item, dict):
                continue
            analysis = (item.get("answer") or item.get("analysis") or item.get("content") or "").strip()
            if not analysis:
                continue
            try:
                add_chart_case({
                    "title": item.get("title") or item.get("name") or f"{path.stem}",
                    "source": item.get("source") or path.name,
                    "question": item.get("question") or "",
                    "analysis": analysis,
                    "domains": item.get("domains") or [item.get("domain") or "general"],
                    "features": item.get("features") or {},
                    "rating": item.get("rating") or 4,
                    "verified": item.get("verified", True),
                    "keywords": item.get("keywords") or [],
                    "promoted_by": item.get("promoted_by") or "",
                })
                count += 1
            except Exception as e:
                log.warning("[cases迁移] 写入失败 {}: {}", path, e)
    log.info("[cases迁移] 完成，共迁移 {} 条案例", count)
    return count


def backfill_chart_facts_from_feedback() -> int:
    """从 answer_feedback 表回填 chart_profiles 和 chart_facts。"""
    _ensure_tables()
    count = 0
    with _get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, conversation_id, question, answer, rating, reason, chart_snapshot
            FROM answer_feedback
            WHERE chart_snapshot IS NOT NULL
            ORDER BY created_at ASC
            """
        ).fetchall()
    for r in rows:
        fid = str(r[0])
        user_id = (r[1] or "").strip() or r[2] or "anonymous"
        chart = r[7] or {}
        if isinstance(chart, str):
            chart = json.loads(chart)
        # 兼容多种数据结构：
        # 1. 直接字段: chart_snapshot.birth_time / chart_snapshot.gender
        # 2. 嵌套 birthInfo: chart_snapshot.birthInfo.time / chart_snapshot.birthInfo.gender
        # 3. 嵌套 chartData.birth: chart_snapshot.chartData.birth.solar / chart_snapshot.chartData.birth.gender
        birth_time = ""
        gender = ""
        if "birth_time" in chart:
            birth_time = (chart.get("birth_time") or "").strip()
            gender = (chart.get("gender") or "").strip()
        elif "birthInfo" in chart:
            birth_info = chart.get("birthInfo") or {}
            birth_time = (birth_info.get("time") or "").strip()
            gender = (birth_info.get("gender") or "").strip()
        elif "chartData" in chart:
            chart_data = chart.get("chartData") or {}
            birth_data = chart_data.get("birth") or {}
            birth_time = (birth_data.get("solar") or birth_data.get("time") or "").strip()
            gender = (birth_data.get("gender") or "").strip()
        if not birth_time or not gender:
            continue
        pid = upsert_chart_profile(user_id, birth_time, gender, chart, interaction_count=1)
        confidence = "verified" if r[5] == "up" else "disputed"
        add_chart_fact(
            user_id=user_id,
            chart_profile_id=pid,
            conversation_id=r[2] or "",
            question=r[3] or "",
            answer_snippet=(r[4] or "")[:500],
            confidence=confidence,
            reason=r[6] or "",
        )
        count += 1
    log.info("[回填] 从 answer_feedback 补了 {} 条断事知识", count)
    return count