"""命盘画像 / 断事知识 / 结构化命例，按命盘（birth_time + gender）隔离。"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import uuid

from app.core.logger import log
from app.db.pool import get_pool
from app.db.schema import _ensure_tables, _record_error, _safe_json
from app.domain.tables import GAN_WUXING


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
    with get_pool().connection() as conn:
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


_PROFILE_COLUMNS = (
    "id, user_id, chart_hash, birth_time, gender, chart_data, "
    "common_topics, style_preference, feedback_stats, interaction_count, created_at, updated_at"
)


def _row_to_chart_profile(r) -> dict:
    """数据库行 → 命盘画像字典。"""
    return {
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


def get_chart_profile(user_id: str, birth_time: str, gender: str) -> dict | None:
    """获取指定命盘的画像。"""
    _ensure_tables()
    ch = _chart_hash(birth_time, gender)
    with get_pool().connection() as conn:
        row = conn.execute(
            f"""
            SELECT {_PROFILE_COLUMNS}
            FROM chart_profiles
            WHERE user_id = %s AND chart_hash = %s
            """,
            (user_id, ch),
        ).fetchone()
        return _row_to_chart_profile(row) if row else None


def list_chart_profiles_by_user(user_id: str) -> list:
    """列出某用户所有命盘的画像。"""
    _ensure_tables()
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_PROFILE_COLUMNS}
            FROM chart_profiles
            WHERE user_id = %s
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [_row_to_chart_profile(r) for r in rows]


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
    with get_pool().connection() as conn:
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
    with get_pool().connection() as conn:
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
    with get_pool().connection() as conn:
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

    每条摘要截断到 250 字；返回条数由 limit 控制（调用方默认 6 条，SQL LIMIT 兜底）。
    返回 (verified_lines, disputed_lines)。
    """
    _ensure_tables()
    verified: list[str] = []
    disputed: list[str] = []
    with get_pool().connection() as conn:
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
    with get_pool().connection() as conn:
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


def delete_chart_case(cid: str) -> bool:
    """删除 chart_cases 表中一条结构化案例（取消案例沉淀用）。返回是否存在并删除。"""
    _ensure_tables()
    with get_pool().connection() as conn:
        cur = conn.execute(
            "DELETE FROM chart_cases WHERE id = %s",
            (cid,),
        )
        return cur.rowcount > 0


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
        with get_pool().connection() as conn:
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
        _record_error("chart_store.read_chart_cases")
        return []


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
                feats["day_master_wuxing"] = GAN_WUXING.get(day_gan, "")
        analysis_text = chart_data.get("analysisText") or ""
        if analysis_text:
            m = re.search(r"【日主强弱】\s*(\S+)", analysis_text)
            if m:
                feats["strength"] = m.group(1)
    except Exception:
        pass
    return feats


def search_cases_for_rag(limit: int = 200) -> list[dict]:
    """检索 cases 表命例用于 LLM 相似命例注入。

    内容优先级：bio/analysis/keypoints 新字段，缺失时回退 chart_data.analysisText，
    使历史命例无需手工补录即可参与检索；相似匹配特征从 chart_data 实时抽取。
    """
    _ensure_tables()
    try:
        with get_pool().connection() as conn:
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
        _record_error("chart_store.read_cases")
        return []


# ---------------- K 线反馈（校准闭环数据面） ----------------

KLINE_RATING_MIN = 1
KLINE_RATING_MAX = 5
KLINE_SCOPES = ("overview", "year")


def add_kline_feedback(
    birth_time: str,
    gender: str,
    dimension: str,
    scope: str,
    rating: int,
    *,
    year: int | None = None,
    anchor_year: int | None = None,
    accurate: bool | None = None,
    comment: str = "",
    snapshot: dict | None = None,
) -> str:
    """写入一条 K 线反馈，返回 feedback id。

    `rating` 只做**存储层的最低限度校验**（范围/类型）；"scope=year 必须带 year"
    这类业务约束归接口层管 —— 存储层不该猜调用方的语义。
    """
    _ensure_tables()
    # `isinstance(True, int)` 为真，故 bool 必须单独挡：否则 rating=True 会被当成 1 星写进库。
    if isinstance(rating, bool) or not isinstance(rating, int):
        raise ValueError("rating 需为整数星级")
    if not (KLINE_RATING_MIN <= rating <= KLINE_RATING_MAX):
        raise ValueError(f"rating 需为 {KLINE_RATING_MIN}-{KLINE_RATING_MAX} 的整数")
    fid = str(uuid.uuid4())
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO kline_feedback
                (id, chart_hash, birth_time, gender, dimension, scope, year,
                 anchor_year, rating, accurate, comment, snapshot)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                fid,
                _chart_hash(birth_time, gender),
                birth_time,
                gender,
                dimension,
                scope,
                year,
                anchor_year,
                rating,
                accurate,
                comment,
                json.dumps(snapshot or {}, ensure_ascii=False),
            ),
        )
    return fid


def list_kline_feedback(
    birth_time: str = "",
    gender: str = "",
    dimension: str = "",
    limit: int = 100,
) -> list[dict]:
    """按命盘/维度列反馈。三者都为空即"列最近的"（供校准脚本总览）。"""
    _ensure_tables()
    where = "WHERE 1 = 1"
    params: list = []
    if birth_time:
        where += " AND chart_hash = %s"
        params.append(_chart_hash(birth_time, gender))
    if dimension:
        where += " AND dimension = %s"
        params.append(dimension)
    params.append(limit)
    try:
        with get_pool().connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, dimension, scope, year, anchor_year, rating, accurate, comment, created_at
                FROM kline_feedback
                {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
            return [
                {
                    "id": str(r[0]),
                    "dimension": r[1],
                    "scope": r[2],
                    "year": r[3],
                    "anchorYear": r[4],
                    "rating": r[5],
                    "accurate": r[6],
                    "comment": r[7] or "",
                    "createdAt": r[8].isoformat() if r[8] else None,
                }
                for r in rows
            ]
    except Exception as e:
        log.error("读取 kline_feedback 失败: {}", e)
        _record_error("chart_store.read_kline_feedback")
        return []


def kline_feedback_stats(dimension: str = "") -> dict:
    """反馈汇总：总量、均分、吻合率、按维度/按 scope 分布。

    `accurate` 可空（用户只打星不判吻合），故吻合率只对**明确表过态**的样本计算，
    并把样本数一并给出 —— 否则"1 条吻合 / 共 1 条表过态"会被误读成 100% 可信。
    """
    _ensure_tables()
    params: list = []
    where = "WHERE 1 = 1"
    if dimension:
        where += " AND dimension = %s"
        params.append(dimension)
    try:
        with get_pool().connection() as conn:
            total, avg_rating, acc_yes, acc_no = conn.execute(
                f"""
                SELECT COUNT(*), AVG(rating),
                       COUNT(*) FILTER (WHERE accurate IS TRUE),
                       COUNT(*) FILTER (WHERE accurate IS FALSE)
                FROM kline_feedback {where}
                """,
                params,
            ).fetchone()
            by_dim = conn.execute(
                f"""
                SELECT dimension, COUNT(*), AVG(rating)
                FROM kline_feedback {where}
                GROUP BY dimension ORDER BY COUNT(*) DESC
                """,
                params,
            ).fetchall()
            by_scope = conn.execute(
                f"""
                SELECT scope, COUNT(*)
                FROM kline_feedback {where}
                GROUP BY scope ORDER BY COUNT(*) DESC
                """,
                params,
            ).fetchall()
    except Exception as e:
        log.error("统计 kline_feedback 失败: {}", e)
        _record_error("chart_store.stats_kline_feedback")
        return {}
    decided = int(acc_yes or 0) + int(acc_no or 0)
    return {
        "total": int(total or 0),
        "avgRating": round(float(avg_rating), 2) if avg_rating is not None else None,
        "accurateYes": int(acc_yes or 0),
        "accurateNo": int(acc_no or 0),
        "decided": decided,
        "accurateRate": round(int(acc_yes or 0) / decided, 4) if decided else None,
        "byDimension": [
            {"dimension": r[0], "count": int(r[1]), "avgRating": round(float(r[2]), 2) if r[2] is not None else None}
            for r in by_dim
        ],
        "byScope": [{"scope": r[0], "count": int(r[1])} for r in by_scope],
    }


# ---------------- K 线事件标注（回测的真相面） ----------------

KLINE_POLARITIES = (1, 0, -1)  # 吉 / 平 / 凶
KLINE_EVENT_DOMAINS = ("general", "career", "wealth", "love", "health", "study")
# 命理年的合理范围。不是历法限制（lunar-python 覆盖更宽），而是**单位错误护栏**：
# 传成 20260918 这种"日期当成年份"的错，落库后再发现要先跑一遍数据清洗。
KLINE_EVENT_YEAR_MIN = 1000
KLINE_EVENT_YEAR_MAX = 3000


def add_kline_event(
    birth_time: str,
    gender: str,
    ganzhi_year: int,
    polarity: int,
    *,
    sect: int = 2,
    yun_sect: int = 1,
    longitude: float | None = None,
    event_date: str | None = None,
    domain: str = "general",
    source: str = "",
    note: str = "",
    case_id: str = "",
) -> str:
    """写入一条事件标注，返回 event id。

    `ganzhi_year` 必须是**命理年**（立春换岁），由 `xipan.ganzhi_year_of` 由公历日期推出；
    无日期只有年份时可直接给（很多传记只记到年）。

    与 `add_kline_feedback` 同一原则：存储层只做**最低限度**校验（类型/范围），
    「domain 是否合法」「年份是否落在这张盘的 K 线区间内」归接口层与回测层 ——
    存储层不该猜调用方的语义。
    """
    _ensure_tables()
    if isinstance(polarity, bool) or not isinstance(polarity, int):
        raise ValueError("polarity 需为整数（1=吉 / 0=平 / -1=凶）")
    if polarity not in KLINE_POLARITIES:
        raise ValueError("polarity 只能取 1（吉）/ 0（平）/ -1（凶）")
    if isinstance(ganzhi_year, bool) or not isinstance(ganzhi_year, int):
        raise ValueError("ganzhi_year 需为整数命理年")
    if not KLINE_EVENT_YEAR_MIN <= ganzhi_year <= KLINE_EVENT_YEAR_MAX:
        raise ValueError(
            f"ganzhi_year 需在 {KLINE_EVENT_YEAR_MIN}-{KLINE_EVENT_YEAR_MAX} 之间（注意不是公历日期）"
        )
    date_value = None
    if event_date:
        if isinstance(event_date, datetime.datetime):
            date_value = event_date.date()
        elif isinstance(event_date, datetime.date):
            date_value = event_date
        else:
            date_value = datetime.date.fromisoformat(str(event_date).strip()[:10])
    eid = str(uuid.uuid4())
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO kline_events
                (id, chart_hash, birth_time, gender, sect, yun_sect, longitude,
                 ganzhi_year, event_date, polarity, domain, source, note, case_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                eid,
                _chart_hash(birth_time, gender),
                birth_time,
                gender,
                sect,
                yun_sect,
                longitude,
                ganzhi_year,
                date_value,
                polarity,
                domain,
                source,
                note,
                case_id,
            ),
        )
    return eid


def list_kline_events(
    birth_time: str = "",
    gender: str = "",
    ganzhi_year: int | None = None,
    domain: str = "",
    limit: int = 500,
) -> list[dict]:
    """按命盘/年份/领域列事件标注。全空即"列最近的"（供回测脚本总览）。

    返回里带上**重建命盘所需的全部参数**（birth_time/gender/sect/yun_sect/longitude）——
    回测读一次列表就能直接建盘，不必再回查每一张盘的出身。
    """
    _ensure_tables()
    where = "WHERE 1 = 1"
    params: list = []
    if birth_time:
        where += " AND chart_hash = %s"
        params.append(_chart_hash(birth_time, gender))
    if ganzhi_year is not None:
        where += " AND ganzhi_year = %s"
        params.append(ganzhi_year)
    if domain:
        where += " AND domain = %s"
        params.append(domain)
    params.append(limit)
    try:
        with get_pool().connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, birth_time, gender, sect, yun_sect, longitude, ganzhi_year,
                       event_date, polarity, domain, source, note, case_id, created_at
                FROM kline_events
                {where}
                ORDER BY ganzhi_year ASC, created_at DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
            return [
                {
                    "id": str(r[0]),
                    "birth_time": r[1],
                    "gender": r[2],
                    "sect": r[3] if r[3] is not None else 2,
                    "yun_sect": r[4] if r[4] is not None else 1,
                    "longitude": r[5],
                    "ganzhiYear": r[6],
                    "eventDate": r[7].isoformat() if r[7] else "",
                    "polarity": r[8],
                    "domain": r[9] or "general",
                    "source": r[10] or "",
                    "note": r[11] or "",
                    "caseId": r[12] or "",
                    "createdAt": r[13].isoformat() if r[13] else None,
                }
                for r in rows
            ]
    except Exception as e:
        log.error("读取 kline_events 失败: {}", e)
        _record_error("chart_store.read_kline_events")
        return []


def delete_kline_event(event_id: str) -> bool:
    """删除一条事件标注，返回是否确实删掉了一条。

    必须有删除通道：标注是人工录入的，录错一条却删不掉，回测结果就被永久污染，
    最后只能连库去改 —— 这正是 feedback 早期踩过的坑。
    """
    _ensure_tables()
    with get_pool().connection() as conn:
        cur = conn.execute("DELETE FROM kline_events WHERE id = %s", (event_id,))
        return cur.rowcount > 0


def kline_event_stats() -> dict:
    """事件库总览：总量、吉凶分布、领域分布、涉及命盘数、年份跨度。

    回测之前先看它 —— 「样本够不够」是决定要不要看命中率的**前置**问题。
    """
    _ensure_tables()
    try:
        with get_pool().connection() as conn:
            total, charts, years = conn.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT chart_hash),
                       COUNT(DISTINCT ganzhi_year)
                FROM kline_events
                """
            ).fetchone()
            by_polarity = conn.execute(
                """
                SELECT polarity, COUNT(*) FROM kline_events
                GROUP BY polarity ORDER BY COUNT(*) DESC
                """
            ).fetchall()
            by_domain = conn.execute(
                """
                SELECT domain, COUNT(*) FROM kline_events
                GROUP BY domain ORDER BY COUNT(*) DESC
                """
            ).fetchall()
            span = conn.execute(
                "SELECT MIN(ganzhi_year), MAX(ganzhi_year) FROM kline_events"
            ).fetchone()
            top_charts = conn.execute(
                """
                SELECT birth_time, gender, COUNT(*) AS n, MIN(ganzhi_year), MAX(ganzhi_year)
                FROM kline_events
                GROUP BY birth_time, gender
                ORDER BY n DESC
                LIMIT 20
                """
            ).fetchall()
    except Exception as e:
        log.error("统计 kline_events 失败: {}", e)
        _record_error("chart_store.stats_kline_events")
        return {}
    return {
        "total": int(total or 0),
        "charts": int(charts or 0),
        "yearCount": int(years or 0),
        "yearFrom": span[0] if span else None,
        "yearTo": span[1] if span else None,
        "byPolarity": [{"polarity": int(r[0]), "count": int(r[1])} for r in by_polarity],
        "byDomain": [{"domain": r[0], "count": int(r[1])} for r in by_domain],
        "byChart": [
            {
                "birthTime": r[0],
                "gender": r[1],
                "count": int(r[2]),
                "yearFrom": r[3],
                "yearTo": r[4],
            }
            for r in top_charts
        ],
    }


# ---------------- 合盘关系事件标注（共振线的真相面） ----------------

# 关系类型：只是"这个分该怎么读"的解释框架与复盘切片维度，**不参与打分**。
# 给建议值而不是自由文本，是为了分组统计时不会出现「夫妻/夫妻俩/婚姻」三个组。
KLINE_RELATIONS = ("夫妻", "恋人", "亲子", "同事", "朋友", "合作", "其他")


def kline_pair_key(birth_time_a: str, gender_a: str, birth_time_b: str, gender_b: str) -> str:
    """一对人的规范化键：两侧 chart_hash 排序后拼接。

    关系是对称的（共振分交换甲乙逐字相同），故谁在甲谁在乙只影响展示，不该影响分组。
    """
    return "-".join(sorted([_chart_hash(birth_time_a, gender_a), _chart_hash(birth_time_b, gender_b)]))


def add_kline_pair_event(
    birth_time_a: str,
    gender_a: str,
    birth_time_b: str,
    gender_b: str,
    ganzhi_year: int,
    polarity: int,
    *,
    sect: int = 2,
    yun_sect: int = 1,
    longitude_a: float | None = None,
    longitude_b: float | None = None,
    event_date: str | None = None,
    relation: str = "",
    source: str = "",
    note: str = "",
) -> str:
    """写入一条关系事件（那一年这两人到底顺不顺），返回 id。

    `polarity` 是**关系**的吉凶（1=顺/0=平/-1=逆），不是某一方个人的运势 ——
    这正是它与 `add_kline_event` 不能混表的原因：同一年两人可以一个升职一个生病，
    但"我们俩那年顺不顺"只有一个答案。

    与单盘事件同一原则：存储层只做类型/范围校验，语义归接口层与回测层。
    """
    _ensure_tables()
    for pname, value in (("polarity", polarity), ("ganzhi_year", ganzhi_year)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{pname} 需为整数")
    if polarity not in KLINE_POLARITIES:
        raise ValueError("polarity 只能取 1（顺）/ 0（平）/ -1（逆）")
    if not KLINE_EVENT_YEAR_MIN <= ganzhi_year <= KLINE_EVENT_YEAR_MAX:
        raise ValueError(
            f"ganzhi_year 需在 {KLINE_EVENT_YEAR_MIN}-{KLINE_EVENT_YEAR_MAX} 之间（注意不是公历日期）"
        )
    if _chart_hash(birth_time_a, gender_a) == _chart_hash(birth_time_b, gender_b):
        raise ValueError("两侧是同一张盘，不构成合盘")
    date_value = None
    if event_date:
        if isinstance(event_date, datetime.datetime):
            date_value = event_date.date()
        elif isinstance(event_date, datetime.date):
            date_value = event_date
        else:
            date_value = datetime.date.fromisoformat(str(event_date).strip()[:10])
    eid = str(uuid.uuid4())
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO kline_pair_events
                (id, pair_key, birth_time_a, gender_a, birth_time_b, gender_b,
                 sect, yun_sect, longitude_a, longitude_b,
                 ganzhi_year, event_date, polarity, relation, source, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                eid,
                kline_pair_key(birth_time_a, gender_a, birth_time_b, gender_b),
                birth_time_a,
                gender_a,
                birth_time_b,
                gender_b,
                sect,
                yun_sect,
                longitude_a,
                longitude_b,
                ganzhi_year,
                date_value,
                polarity,
                relation,
                source,
                note,
            ),
        )
    return eid


def list_kline_pair_events(
    birth_time_a: str = "",
    gender_a: str = "",
    birth_time_b: str = "",
    gender_b: str = "",
    ganzhi_year: int | None = None,
    limit: int = 500,
) -> list[dict]:
    """列关系事件。四侧生辰都给时按"这一对"过滤，否则列最近的（供回测总览）。

    返回带**两盘重建所需的全部参数**，回测读一次就能建盘。
    """
    _ensure_tables()
    where = "WHERE 1 = 1"
    params: list = []
    if birth_time_a and gender_a and birth_time_b and gender_b:
        where += " AND pair_key = %s"
        params.append(kline_pair_key(birth_time_a, gender_a, birth_time_b, gender_b))
    if ganzhi_year is not None:
        where += " AND ganzhi_year = %s"
        params.append(ganzhi_year)
    params.append(limit)
    try:
        with get_pool().connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, birth_time_a, gender_a, birth_time_b, gender_b, sect, yun_sect,
                       longitude_a, longitude_b, ganzhi_year, event_date, polarity,
                       relation, source, note, created_at
                FROM kline_pair_events
                {where}
                ORDER BY ganzhi_year ASC, created_at DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
            return [
                {
                    "id": str(r[0]),
                    "birthTimeA": r[1],
                    "genderA": r[2],
                    "birthTimeB": r[3],
                    "genderB": r[4],
                    "sect": r[5] if r[5] is not None else 2,
                    "yunSect": r[6] if r[6] is not None else 1,
                    "longitudeA": r[7],
                    "longitudeB": r[8],
                    "ganzhiYear": r[9],
                    "eventDate": r[10].isoformat() if r[10] else "",
                    "polarity": r[11],
                    "relation": r[12] or "",
                    "source": r[13] or "",
                    "note": r[14] or "",
                    "createdAt": r[15].isoformat() if r[15] else None,
                }
                for r in rows
            ]
    except Exception as e:
        log.error("读取 kline_pair_events 失败: {}", e)
        _record_error("chart_store.read_kline_pair_events")
        return []


def delete_kline_pair_event(event_id: str) -> bool:
    """删除一条关系事件。同单盘：人工录入必须有回退通道。"""
    _ensure_tables()
    with get_pool().connection() as conn:
        cur = conn.execute("DELETE FROM kline_pair_events WHERE id = %s", (event_id,))
        return cur.rowcount > 0


def kline_pair_event_stats() -> dict:
    """关系事件总览：总量、顺逆分布、关系类型分布、涉及对数、年份跨度、最活跃的几对。"""
    _ensure_tables()
    try:
        with get_pool().connection() as conn:
            total, pairs, years = conn.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT pair_key), COUNT(DISTINCT ganzhi_year)
                FROM kline_pair_events
                """
            ).fetchone()
            by_polarity = conn.execute(
                """
                SELECT polarity, COUNT(*) FROM kline_pair_events
                GROUP BY polarity ORDER BY COUNT(*) DESC
                """
            ).fetchall()
            by_relation = conn.execute(
                """
                SELECT relation, COUNT(*) FROM kline_pair_events
                GROUP BY relation ORDER BY COUNT(*) DESC
                """
            ).fetchall()
            span = conn.execute(
                "SELECT MIN(ganzhi_year), MAX(ganzhi_year) FROM kline_pair_events"
            ).fetchone()
            top_pairs = conn.execute(
                """
                SELECT birth_time_a, gender_a, birth_time_b, gender_b,
                       COUNT(*) AS n, MIN(ganzhi_year), MAX(ganzhi_year)
                FROM kline_pair_events
                GROUP BY birth_time_a, gender_a, birth_time_b, gender_b
                ORDER BY n DESC
                LIMIT 20
                """
            ).fetchall()
    except Exception as e:
        log.error("统计 kline_pair_events 失败: {}", e)
        _record_error("chart_store.stats_kline_pair_events")
        return {}
    return {
        "total": int(total or 0),
        "pairs": int(pairs or 0),
        "yearCount": int(years or 0),
        "yearFrom": span[0] if span else None,
        "yearTo": span[1] if span else None,
        "byPolarity": [{"polarity": int(r[0]), "count": int(r[1])} for r in by_polarity],
        "byRelation": [{"relation": r[0] or "未标注", "count": int(r[1])} for r in by_relation],
        "byPair": [
            {
                "birthTimeA": r[0],
                "genderA": r[1],
                "birthTimeB": r[2],
                "genderB": r[3],
                "count": int(r[4]),
                "yearFrom": r[5],
                "yearTo": r[6],
            }
            for r in top_pairs
        ],
    }
