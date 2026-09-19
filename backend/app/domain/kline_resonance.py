"""合盘共振线：两张命盘逐年的「关系顺逆」确定性评分。

与 `fortune_score` 的关系
-------------------------
本模块**不重算运势**，只做两件事：
1. 复用 `fortune_score` 的 `favor_vector` / `effective_favor` / `pillar_delta` /
   `build_kline` —— 单盘口径只有一处事实源，改单盘不会让共振线悄悄漂移。
2. 在两张单盘曲线之上再算**双盘交互项**（喜忌是否同向、夫妻宫是否被引动）。

为什么不复用 `bazi_hehun`
------------------------
`app.tools.bazi.bazi_hehun` 是**纯文本**产出，其「五行互补评分」上限实际只有 55 分，
且**完全不含双盘干支关系**——拿它当共振分会导致「年份变了分数不变」。
故共振必须自建确定性核；`bazi_hehun` 的文本仍可作为 LLM 批注的上下文（见 annotator）。

三年刻度
--------
共振分由 **1 个静态基线 + 4 个逐年项** 合成，每一项都单独留在输出里
（`terms`），因为共振线的价值一半在「几分」，另一半在「为什么是这个分」：

======================  ================================================
项                     含义
======================  ================================================
``base``               双盘静态契合：日主五行关系 + 五行互补 + 夫妻宫（日支）关系。不随年份变。
``trend``              双方该年 K 线同比走向（收盘 − 开盘）的均值：定关系顺逆的主项之一。
``align``              该年流年干支与**双方原局喜忌**点乘的均值：定关系顺逆的主项之二。
``sync``               同步度修正：走向同号、喜忌同号各记一次，同号加分、异号扣分。
``palace``             该年地支对双方**日支**的引动：合加分，冲刑害破扣分。
======================  ================================================

`trend` / `align` 是主项（决定「这段关系今年顺不顺」），`sync` 是修正项
（决定「两人是不是在同一条船上」）—— 分开列而不是揉进主项，是为了让
「顺但各走各的」与「逆但同进退」这两种情况在输出里可分辨。

**权重是待校准的先验，不是已验证的结论。** 当前没有任何「真实吉凶」样本可以回归，
所以 `*_UNIT` 是按量级取的先验值。Phase 4 的事件标注表建好后，应当用命中率反推
这些权重；在此之前，共振分只应读作**相对次序**（哪几年比哪几年更顺），
不应读作绝对吉凶。
"""

from __future__ import annotations

from typing import Any

from app.domain.fortune_score import (
    DIM_COMPREHENSIVE,
    SCORE_MAX,
    SCORE_MIN,
    build_kline,
    effective_favor,
    pillar_delta,
)
from app.domain.ganzhi_relations import branch_relations
from app.domain.models import BaziChart
from app.domain.tables import CONTROLS, GENERATES

__all__ = [
    "BASE_SCORE",
    "VERDICT_BANDS",
    "build_resonance",
    "day_zhi",
    "pair_base",
    "pair_relation_kind",
    "palace_relation",
    "verdict_of",
    "year_resonance",
]


# ---------------- 权重（先验，待回测校准） ----------------

BASE_SCORE = 50.0
BASE_UNIT = 4.0          # 基线每点折合分
TREND_UNIT = 8.0         # 双方同比走向（主项）
ALIGN_UNIT = 10.0        # 流年干支对双方喜忌（主项）
SYNC_UNIT = 3.0          # 同步度修正（走向同号 / 喜忌同号，共用同一权重）
PALACE_UNIT = 5.0        # 夫妻宫引动

MOVE_SPAN = 20.0         # 价格同比走向归一的满量程（分）
ALIGN_SPAN = 0.5         # pillar_delta 归一的满量程

# 日主五行关系的基线点（相生互补 > 同类 > 相克）
_DAY_MASTER_POINTS = {"相生": 2.0, "同类": 0.5, "相克": -2.0}

# 夫妻宫（日支）关系的基线点
_PALACE_BASE_POINTS = {
    "合": 2.0,
    "同支": 0.5,
    "冲": -2.0,
    "刑": -1.5,
    "害": -1.0,
    "破": -1.0,
    "": 0.0,
}

# 流年地支引动夫妻宫的逐年点
_PALACE_YEAR_POINTS = {"合": 0.5, "同支": 0.0, "冲": -1.0, "刑": -0.6, "害": -0.4, "破": -0.4, "": 0.0}

# 共振强度档位（分数下界，标签）。顺序即优先级，从高到低。
VERDICT_BANDS: tuple[tuple[float, str], ...] = (
    (72.0, "强共振"),
    (58.0, "偏顺"),
    (42.0, "平稳"),
    (30.0, "偏逆"),
    (0.0, "背离"),
)


def verdict_of(score: float) -> str:
    """共振分 → 档位标签。"""
    for floor, label in VERDICT_BANDS:
        if score >= floor:
            return label
    return VERDICT_BANDS[-1][1]


def _clamp(v: float, lo: float = SCORE_MIN, hi: float = SCORE_MAX) -> float:
    return max(lo, min(hi, v))


def _sgn(v: float) -> int:
    return (v > 0) - (v < 0)


def _sync_of(a: float, b: float) -> int:
    """同步度：同号为 +1、异号为 −1、任一侧无数值（＝0）时记 0。

    任一侧为 0 时「同不同步」无从谈起，记 0 而不是记 −1 ——
    否则一个完全没有流年作用的年份会被当成"不同步"而扣分。
    """
    sa, sb = _sgn(a), _sgn(b)
    if sa == 0 or sb == 0:
        return 0
    return 1 if sa == sb else -1


def day_zhi(chart: BaziChart) -> str:
    """日支（夫妻宫）。四柱不全时返回空串，由调用方按「无引动」处理。"""
    pillars = chart.pillars
    if len(pillars) < 3:
        return ""
    return pillars[2].zhi or ""


def pair_relation_kind(chart_a: BaziChart, chart_b: BaziChart) -> str:
    """双盘日主五行的关系类别：相生 / 同类 / 相克。"""
    wx_a = chart_a.wuxing.day_master_wuxing
    wx_b = chart_b.wuxing.day_master_wuxing
    if not wx_a or not wx_b:
        return ""
    if wx_a == wx_b:
        return "同类"
    if GENERATES.get(wx_a) == wx_b or GENERATES.get(wx_b) == wx_a:
        return "相生"
    if CONTROLS.get(wx_a) == wx_b or CONTROLS.get(wx_b) == wx_a:
        return "相克"
    return ""


def palace_relation(zhi_a: str, zhi_b: str) -> str:
    """两支的关系归一到单一类别：合 / 冲 / 刑 / 害 / 破 / 同支 / 空串。

    一支可能同时落进多张表，取哪一个必须写死，否则结论会随字典顺序变化。
    次序取 **合 > 冲 > 刑 > 害 > 破**：

    - 「合」放最前，因为**合破/合刑可以同见** —— 巳申既六合又六破还半刑、寅亥既六合又六破。
      若把破排在合前，巳申、寅亥这两个强六合会被报成最弱的关系，明显失真。
      共振线是关系顺逆的粗刻度，取不到"合中带刑"这种中间态，故取更主导的合。
    - 冲 > 刑 > 害 > 破 依伤害量级排列（与 `fortune_score.REL_VOL` 的量级一致）。
    """
    if not zhi_a or not zhi_b:
        return ""
    if zhi_a == zhi_b:
        return "同支"
    rel = branch_relations([zhi_a, zhi_b])
    if rel.liu_he or rel.san_he or rel.ban_he or rel.gong_he or rel.hui:
        return "合"
    if rel.chong:
        return "冲"
    if rel.san_xing or rel.ban_xing:
        return "刑"
    if rel.hai:
        return "害"
    if rel.po:
        return "破"
    return ""


def _complement(counts_from: dict[str, float], counts_to: dict[str, float], weak: str) -> bool:
    """`counts_to` 中 `weak` 的占比是否不低于其自身五行均值（即"对方相对不缺"）。"""
    if not counts_to or not weak:
        return False
    vals = [v for v in counts_to.values()]
    if not vals:
        return False
    avg = sum(vals) / len(vals)
    return counts_to.get(weak, 0.0) >= avg


def pair_base(chart_a: BaziChart, chart_b: BaziChart) -> dict[str, Any]:
    """双盘静态契合：不随年份变的那部分。

    输出同时给出 `points`（各项原始点）与 `score`（折合到 0-100），
    便于批注解释「这两个人本身合不合」。
    """
    kind = pair_relation_kind(chart_a, chart_b)
    day_pt = _DAY_MASTER_POINTS.get(kind, 0.0)

    weak_a = chart_a.wuxing.weakest
    weak_b = chart_b.wuxing.weakest
    comp_a = _complement(chart_a.wuxing.counts, chart_b.wuxing.counts, weak_a)
    comp_b = _complement(chart_b.wuxing.counts, chart_a.wuxing.counts, weak_b)
    comp_pt = float(comp_a) + float(comp_b)

    zhi_a, zhi_b = day_zhi(chart_a), day_zhi(chart_b)
    palace_kind = palace_relation(zhi_a, zhi_b)
    palace_pt = _PALACE_BASE_POINTS.get(palace_kind, 0.0)

    points = {
        "dayMasterRelation": day_pt,
        "complement": comp_pt,
        "palace": palace_pt,
    }
    total = sum(points.values())
    return {
        "relationKind": kind,
        "complement": {"aNeeds": weak_a, "bCovers": comp_a, "bNeeds": weak_b, "aCovers": comp_b},
        "dayZhi": {"a": zhi_a, "b": zhi_b, "relation": palace_kind},
        "points": points,
        "score": round(_clamp(BASE_SCORE + total * BASE_UNIT), 1),
    }


def _trend_term(candle_a: dict, candle_b: dict) -> tuple[float, float]:
    """双方同比走向：返回（归一后的平均走向, 原始走向差值）。"""
    move_a = (candle_a.get("close") or 0.0) - (candle_a.get("open") or 0.0)
    move_b = (candle_b.get("close") or 0.0) - (candle_b.get("open") or 0.0)
    norm = max(-1.0, min(1.0, (move_a + move_b) / MOVE_SPAN))
    return norm, move_a - move_b


def _align_term(favor_a: dict[str, float], favor_b: dict[str, float], ganzhi: str) -> tuple[float, dict]:
    """流年干支与双方原局喜忌：返回（归一后的平均作用, 明细）。

    主项取 `(da + db) / 2` 的归一值 —— 它表达"这一年对两人合起来是好是坏"；
    一利一损之所以不抹平成 0，是因为归一后的均值本来就不为零（谁受益多就偏谁）。
    「同步度」另由 `sync` 项承担，不在这里重复扣分。
    """
    da = pillar_delta(favor_a, ganzhi)
    db = pillar_delta(favor_b, ganzhi)
    sa, sb = _sgn(da), _sgn(db)
    if sa > 0 and sb > 0:
        label = "双利"
    elif sa < 0 and sb < 0:
        label = "双损"
    elif sa != 0 and sb != 0:
        label = "一利一损"
    else:
        label = "无明显作用"
    norm = max(-1.0, min(1.0, (da + db) / 2.0 / ALIGN_SPAN))
    return norm, {"deltaA": round(da, 4), "deltaB": round(db, 4), "label": label}


def _palace_year_term(zhi_a: str, zhi_b: str, liunian_zhi: str) -> tuple[float, dict]:
    """流年地支引动双方夫妻宫。"""
    rel_a = palace_relation(liunian_zhi, zhi_a)
    rel_b = palace_relation(liunian_zhi, zhi_b)
    pt = _PALACE_YEAR_POINTS.get(rel_a, 0.0) + _PALACE_YEAR_POINTS.get(rel_b, 0.0)
    return pt, {"a": rel_a, "b": rel_b}


def year_resonance(
    candle_a: dict,
    candle_b: dict,
    favor_a: dict[str, float],
    favor_b: dict[str, float],
    zhi_a: str,
    zhi_b: str,
    base_score: float,
) -> dict[str, Any]:
    """单年共振：基线 + 三项逐年修正，全部留在 `terms` 里。"""
    ganzhi = candle_a.get("ganzhi") or ""
    trend_v, move_gap = _trend_term(candle_a, candle_b)
    align_v, align_detail = _align_term(favor_a, favor_b, ganzhi)
    palace_v, palace_detail = _palace_year_term(zhi_a, zhi_b, ganzhi[1] if len(ganzhi) == 2 else "")

    # 同步度：走向与喜忌各自贡献一次，任一侧无数值时该项记 0（见 _sync_of）。
    sync_hits = _sync_of(
        (candle_a.get("close") or 0.0) - (candle_a.get("open") or 0.0),
        (candle_b.get("close") or 0.0) - (candle_b.get("open") or 0.0),
    ) + _sync_of(align_detail["deltaA"], align_detail["deltaB"])
    terms = {
        "trend": round(trend_v * TREND_UNIT, 2),
        "align": round(align_v * ALIGN_UNIT, 2),
        "sync": round(sync_hits * SYNC_UNIT, 2),
        "palace": round(palace_v * PALACE_UNIT, 2),
    }
    score = round(_clamp(base_score + sum(terms.values())), 1)
    return {
        "year": candle_a.get("year"),
        "ganzhi": ganzhi,
        "dayun": candle_a.get("dayun") or "",
        "scoreA": candle_a.get("close"),
        "scoreB": candle_b.get("close"),
        "isUpA": candle_a.get("isUp"),
        "isUpB": candle_b.get("isUp"),
        "sameDirection": _sync_of(
            (candle_a.get("close") or 0.0) - (candle_a.get("open") or 0.0),
            (candle_b.get("close") or 0.0) - (candle_b.get("open") or 0.0),
        ) > 0,
        "moveGap": round(move_gap, 2),
        "align": align_detail,
        "palace": palace_detail,
        "terms": terms,
        "resonance": score,
        "verdict": verdict_of(score),
    }


def build_resonance(
    chart_a: BaziChart,
    chart_b: BaziChart,
    *,
    max_age: int = 80,
    dimension: str = DIM_COMPREHENSIVE,
) -> dict[str, Any]:
    """整条共振线：基线 + 逐年序列 + 口径说明。

    `dimension` 只通过 `effective_favor` 影响喜忌权重，与单盘 K 线同口径 ——
    所以切维度时两条单盘线与共振线会一起变，不会出现"线变了但依据没变"。
    """
    favor_a = effective_favor(chart_a, dimension)
    favor_b = effective_favor(chart_b, dimension)
    zhi_a, zhi_b = day_zhi(chart_a), day_zhi(chart_b)
    base = pair_base(chart_a, chart_b)

    row_a = {c["year"]: c for c in build_kline(chart_a, max_age=max_age, dimension=dimension)}
    row_b = {c["year"]: c for c in build_kline(chart_b, max_age=max_age, dimension=dimension)}
    years = sorted(set(row_a) & set(row_b))
    rows = [
        year_resonance(row_a[y], row_b[y], favor_a, favor_b, zhi_a, zhi_b, base["score"])
        for y in years
    ]

    scores = [r["resonance"] for r in rows]
    peak = max(rows, key=lambda r: r["resonance"]) if rows else None
    trough = min(rows, key=lambda r: r["resonance"]) if rows else None
    return {
        "base": base,
        "years": rows,
        "meta": {
            "startYear": years[0] if years else None,
            "endYear": years[-1] if years else None,
            "yearCount": len(years),
            "maxAge": max_age,
            "dimension": dimension,
            "meanScore": round(sum(scores) / len(scores), 1) if scores else None,
            "peakYear": peak["year"] if peak else None,
            "troughYear": trough["year"] if trough else None,
            "weights": {
                "base": BASE_UNIT,
                "trend": TREND_UNIT,
                "align": ALIGN_UNIT,
                "sync": SYNC_UNIT,
                "palace": PALACE_UNIT,
            },
            "note": (
                "共振分为确定性规则计算（非大模型生成），由静态基线 + 逐年四项（走向 / 喜忌 / 同步 / 夫妻宫）合成；"
                "权重为待校准先验，只应读作相对次序（哪几年更顺），不应读作绝对吉凶。"
            ),
        },
    }
