"""命例收藏 / 塔罗记录 / 问题反馈 / 答案反馈与训练样本导出，按 user_id 隔离。

R9 拆分自 user_data.py。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from app.core.logger import log
from app.db.chart_store import add_chart_case, delete_chart_case
from app.db.schema import (
    _ensure_tables,
    _safe_json,
)
from app.domain.bazi_engine import (
    extract_bazi_brief,  # noqa: F401  (命盘摘要提取，重复定义已收敛至 domain 层)
)
from app.memory.postgres_memory import _get_pool


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
                "bazi": extract_bazi_brief(chart_data),
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
                   af.reviewed, af.reviewed_by, af.case_id,
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
                "case_id": r[11] or "",
                "user_nickname": r[12] if r[12] else None,
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
                   rating, reason, chart_snapshot, created_at, reviewed, reviewed_by, case_id
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
            "case_id": row[11] or "",
        }


def _first(*values, default=None):
    """返回第一个真值（promote_to_case 多层特征回退提取用）。"""
    for v in values:
        if v:
            return v
    return default


def _extract_case_features(chart: dict) -> dict:
    """多层回退提取排盘特征：features -> chartData -> chartData.wuxing -> chart。

    小程序/Web 两端传的 chart_snapshot 结构不一致（camelCase/snake_case 混用），
    故逐字段多源回退，全部落空时字符串取 ""、列表取 []。
    """
    cd = chart.get("chartData") or {}
    fr = chart.get("features", {}) or {}
    wx = cd.get("wuxing") if isinstance(cd.get("wuxing"), dict) else {}
    return {
        "day_master": _first(fr.get("day_master"), cd.get("dayMaster"), cd.get("day_master"),
                             chart.get("day_master"), wx.get("day_master"), wx.get("dayMaster"), default=""),
        "day_master_wuxing": _first(fr.get("day_master_wuxing"), cd.get("dayMasterWuxing"),
                                    cd.get("day_master_wuxing"), chart.get("day_master_wuxing"),
                                    wx.get("day_master_wuxing"), wx.get("dayMasterWuxing"), default=""),
        "strength": _first(fr.get("strength"), cd.get("strength"), chart.get("strength"),
                           wx.get("strength"), default=""),
        "pattern": _first(fr.get("pattern"), cd.get("pattern"), chart.get("pattern"), default=""),
        "useful_god": _first(fr.get("useful_god"), cd.get("usefulGod"), cd.get("useful_god"),
                             chart.get("useful_god"), default=""),
        "key_traits": _first(fr.get("key_traits"), cd.get("keyTraits"), cd.get("key_traits"),
                             chart.get("key_traits"), default=[]),
        "combinations": _first(fr.get("combinations"), cd.get("combinations"),
                               chart.get("combinations"), default=[]),
        "clashes": _first(fr.get("clashes"), cd.get("clashes"), chart.get("clashes"), default=[]),
        "sects": _first(fr.get("sects"), cd.get("sects"), chart.get("sects"), default=[]),
    }


def _refill_features_by_rechart(chart: dict, feats: dict) -> None:
    """特征全空但有出生信息时，重新排盘回填（仅回填仍为空的字段）。"""
    if feats["day_master"]:
        return
    birth_time = _first(chart.get("birth_time"),
                        (chart.get("birthInfo") or {}).get("time"),
                        (chart.get("chartData") or {}).get("birth_time"), default="")
    gender = _first(chart.get("gender"),
                    (chart.get("birthInfo") or {}).get("gender"),
                    (chart.get("chartData") or {}).get("gender"), default="")
    if not birth_time or not gender:
        return
    try:
        # 延迟导入避免 user_records -> bazi_engine 的循环依赖
        from app.domain.bazi_engine import build_bazi_chart
        bazi = build_bazi_chart(birth_time, gender, sect=2, yun_sect=1, dayun_count=10, liunian_years=8)
        feats["day_master"] = bazi.wuxing.day_master or ""
        feats["day_master_wuxing"] = bazi.wuxing.day_master_wuxing or ""
        feats["strength"] = bazi.wuxing.strength or ""
        feats["pattern"] = feats["pattern"] or bazi.analysis.pattern_hint or ""
        feats["useful_god"] = feats["useful_god"] or bazi.wuxing.useful_hint or ""
        feats["combinations"] = feats["combinations"] or list(bazi.analysis.combinations or [])
        feats["clashes"] = feats["clashes"] or list(bazi.analysis.clashes or [])
        log.info("转案例时重新排盘获取特征: {} {}", birth_time, gender)
    except Exception as e:
        log.warning("重新排盘获取特征失败: {}", e)


def promote_to_case(fid: str, reviewer: str = "") -> tuple[str, str] | None:
    """将已审核的好评/差评回答转为结构化案例（写入 chart_cases 表）。

    返回 (case_id, file_path) 或 None（失败时）。
    幂等：若该反馈已转过案例（answer_feedback.case_id 已存在且对应行仍在），直接返回旧值，
    避免重复 INSERT 造成 chart_cases 中产生重复案例。
    """
    _ensure_tables()
    item = get_answer_feedback(fid)
    if not item:
        return None
    if item["rating"] not in {"up", "down"}:
        return None
    mark_answer_reviewed(fid, reviewer)

    # 幂等：已转过则直接返回旧 case_id（chart_cases 行可能已被外部删，重置回退到再次插入）
    existing_cid = (item.get("case_id") or "").strip()
    if existing_cid:
        log.info("反馈已转过案例，幂等返回: fid={} case_id={}", fid, existing_cid)
        return existing_cid, existing_cid

    # 延迟导入避免 db -> rag 的循环依赖
    from app.rag.retrieval import detect_domain as _detect_domain

    case_id = f"case_feedback_{fid[:8]}"
    chart = item.get("chart_snapshot") or {}
    features = _extract_case_features(chart)
    _refill_features_by_rechart(chart, features)

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
        "features": features,
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
    # 回填 answer_feedback.case_id，便于列表展示/幂等/取消
    try:
        with _get_pool().connection() as conn:
            conn.execute(
                "UPDATE answer_feedback SET case_id = %s WHERE id = %s",
                (cid, fid),
            )
    except Exception as e:
        log.warning("回填 answer_feedback.case_id 失败（chart_cases 已写入，不影响主流程）: {}", e)
    log.info("案例已沉淀到DB: {} → chart_cases/{}", fid, cid)
    return cid, str(cid)


def unpromote_answer_to_case(fid: str) -> bool:
    """取消已沉淀的案例：删除 chart_cases 行 + 清空 answer_feedback.case_id。

    返回是否有内容被撤销（False 表示该反馈从未转过案例）。
    """
    _ensure_tables()
    item = get_answer_feedback(fid)
    if not item:
        return False
    case_id = (item.get("case_id") or "").strip()
    if not case_id:
        return False
    deleted = delete_chart_case(case_id)
    with _get_pool().connection() as conn:
        conn.execute(
            "UPDATE answer_feedback SET case_id = NULL WHERE id = %s",
            (fid,),
        )
    if deleted:
        log.info("案例沉淀已取消: fid={} case_id={}", fid, case_id)
    else:
        log.info("案例沉淀取消（chart_cases 中无对应行，仅清空 case_id 引用）: fid={} case_id={}", fid, case_id)
    return True


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
