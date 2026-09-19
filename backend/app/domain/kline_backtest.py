"""命理 K 线回测：拿**真实事件**检验确定性评分到底有没有区分度。

要回答的问题
------------
`fortune_score` 的曲线好看、有分布、有维度区分度（`scripts/kline_diagnose.py` 已验），
但「分高的年份真的更好过吗」是另一回事 —— 形状判据证明不了预测力。
本模块只做一件事：把「模型说吉/平/凶」与「实际发生了吉/平/凶」逐条对上，算命中率。

三条口径（都是刻意的，不是随手取的）
------------------------------------
1. **阈值取自该盘全期分布，不取自事件年份。**
   吉/凶的界线按该盘 K 线的分位数切（`UP_QUANTILE` / `DOWN_QUANTILE`），
   而不是让标注数据来切。否则样本越少阈值越偏，一张盘只有 3 条事件时会得出
   「3 年全吉」这种荒谬刻度，回测就变成自证。
   全期的基准跨度固定为 `AGE_SPAN`（不随事件年份伸缩），保证同一张盘两次回测
   阈值不漂 —— 加一条晚年事件不该改变早年事件的预测标签。

2. **必须给随机基线。** 只报「命中率 55%」是没有信息量的：三分类随机猜也有约 1/3，
   若事件的吉凶本来就偏成一堆（比如 80% 是凶），"全猜凶"的命中率就有 80%。
   故同时给出 `randomBaseline`（按预测/实际的边缘分布独立随机猜的期望命中率）
   与 `majorityBaseline`（恒猜多数类），并给出 Wilson 置信区间 ——
   只有区间下界高过基线，才算"看得出区分度"。

3. **样本不足要明说，而不是照样给个百分比。** 少于 `DEFAULT_MIN_SAMPLES` 条时
   `ok=False` 并在 `warnings` 里写明；CLI 会打印警示。

维度怎么对齐
------------
`dimension="auto"` 时，**按事件的领域选维度**：事业事件用事业维度打分、感情事件用感情维度。
这是本模块唯一有实质主张的设计 —— 拿综合维度去评判一条"那年离婚了"的标注，
问的其实是另一个问题。需要"统一用某维度"时显式传具体维度即可（`dimension="career"`）。

本模块是**纯函数**：只吃 `BaziChart` 与事件字典列表，不读库、不起盘、不调模型。
事件从哪来（库/JSON）由调用方决定，故回测逻辑可以拿合成标注单测。
"""

from __future__ import annotations

import math
from typing import Any

from app.domain.fortune_score import (
    DIM_COMPREHENSIVE,
    DIMENSIONS,
    build_kline,
)
from app.domain.kline_resonance import build_resonance
from app.domain.models import BaziChart

__all__ = [
    "DEFAULT_MIN_SAMPLES",
    "DIMENSION_AUTO",
    "LABELS",
    "LABEL_DOWN",
    "LABEL_MID",
    "LABEL_UP",
    "PAIR_PREDICTOR_RESONANCE",
    "POLARITY_DOWN",
    "POLARITY_LABELS",
    "POLARITY_NEUTRAL",
    "POLARITY_UP",
    "PREDICTORS",
    "PREDICTOR_CLOSE",
    "PREDICTOR_MEAN",
    "TERMS_ORDER",
    "dimension_for_domain",
    "predict_chart",
    "predict_pair",
    "run_backtest",
    "run_pair_backtest",
    "wilson_interval",
    "year_score",
]

# ---------------- 极性（真相） ----------------

POLARITY_UP = 1
POLARITY_NEUTRAL = 0
POLARITY_DOWN = -1
POLARITY_LABELS = {POLARITY_UP: "吉", POLARITY_NEUTRAL: "平", POLARITY_DOWN: "凶"}

LABEL_UP = "吉"
LABEL_MID = "平"
LABEL_DOWN = "凶"
LABELS = (LABEL_UP, LABEL_MID, LABEL_DOWN)

# ---------------- 预测器 ----------------

PREDICTOR_CLOSE = "close"
PREDICTOR_MEAN = "mean"
PREDICTORS = (PREDICTOR_CLOSE, PREDICTOR_MEAN)

# ---------------- 阈值与样本 ----------------

# 吉/凶分位。取 1/3 与 2/3：三分类下各类样本量最均衡，随机基线也最好解释。
UP_QUANTILE = 2.0 / 3.0
DOWN_QUANTILE = 1.0 / 3.0

# 阈值基准跨度：固定覆盖到 100 虚岁，不随事件年份伸缩（见模块 docstring 第 1 条）。
AGE_SPAN = 100
# 起盘年龄上限护栏：跑一批盘的 100 年 K 线是 CPU 放大点，接口层据此卡住异常入参。
MAX_AGE_LIMIT = 120

DEFAULT_MIN_SAMPLES = 20

# 错判样例最多列几条（用于人工复盘，不是统计结果）
MISS_EXAMPLES = 10
# 落在 K 线区间外的事件年份最多列几个
UNMATCHED_EXAMPLES = 20

DIMENSION_AUTO = "auto"

# 事件领域 → 评分维度。general（说不清哪一路）用综合维度。
DOMAIN_DIMENSIONS = {
    "general": DIM_COMPREHENSIVE,
    "career": "career",
    "wealth": "wealth",
    "love": "love",
    "health": "health",
}


def dimension_for_domain(domain: str) -> str:
    """事件领域 → 评分维度。未知领域退化为综合维度（宁可粗，不可错配）。"""
    return DOMAIN_DIMENSIONS.get(domain or "", DIM_COMPREHENSIVE)


# ---------------- 单年预测 ----------------

def year_score(candle: dict, predictor: str = PREDICTOR_CLOSE) -> float:
    """一根年 K 线 → 该年的"运势水平"标量。

    - `close`：年末分（丑月小寒分 + 关系修正）。**默认取它**，因为它就是前端展示的那个值 ——
      回测的预测器与用户看到的口径必须是同一个，否则"回测通过"不代表"页面可信"。
    - `mean`：12 个节气月分数均值 + 关系修正。单月取值噪声更小，作为稳健性对照。

    关系修正对两种预测器都加上：它是"这年的干支关系带来的加减分"，与用哪个月无关。
    """
    if predictor == PREDICTOR_CLOSE:
        return float(candle.get("close") or 0.0)
    if predictor == PREDICTOR_MEAN:
        months = candle.get("monthScores") or []
        if not months:
            return float(candle.get("close") or 0.0)
        return round(sum(months) / len(months) + float(candle.get("relationAdj") or 0.0), 4)
    raise ValueError(f"predictor 需为 {'/'.join(PREDICTORS)} 之一")


def _percentile(values: list[float], q: float) -> float:
    """最近秩分位（与 `scripts/kline_diagnose.py` 同一算法，口径不另起一套）。"""
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return ordered[idx]


def label_of(score: float, down_cut: float, up_cut: float) -> str:
    """分数 → 吉/平/凶。阈值重合时按「先吉后凶」判，见 `predict_chart` 的告警。"""
    if score >= up_cut:
        return LABEL_UP
    if score <= down_cut:
        return LABEL_DOWN
    return LABEL_MID


def predict_chart(
    chart: BaziChart,
    *,
    dimension: str = DIM_COMPREHENSIVE,
    predictor: str = PREDICTOR_CLOSE,
    max_age: int = AGE_SPAN,
) -> dict[str, Any]:
    """一张盘的逐年预测标签：{年份: {label, score, ganzhi}} + 阈值。

    阈值在该盘**全期**（起运年 → `max_age` 虚岁）上取分位，故"吉"是"这盘自己一辈子里的高位"，
    而不是跨盘可比的绝对刻度 —— 命理本就该看相对起伏，且各盘量纲（K_SCORE）相同、
    分布形状不同，跨盘绝对阈值会让偏旺盘全线偏高。
    """
    if predictor not in PREDICTORS:
        raise ValueError(f"predictor 需为 {'/'.join(PREDICTORS)} 之一")
    if dimension not in DIMENSIONS:
        raise ValueError(f"dimension 需为 {'/'.join(DIMENSIONS)} 之一")
    if not 0 < max_age <= MAX_AGE_LIMIT:
        raise ValueError(f"max_age 需在 1-{MAX_AGE_LIMIT} 之间")

    candles = build_kline(chart, max_age=max_age, dimension=dimension)
    scores = [year_score(c, predictor) for c in candles]
    down_cut = _percentile(scores, DOWN_QUANTILE) if scores else 0.0
    up_cut = _percentile(scores, UP_QUANTILE) if scores else 0.0
    years = {
        c["year"]: {
            "label": label_of(s, down_cut, up_cut),
            "score": s,
            "ganzhi": c.get("ganzhi") or "",
        }
        for c, s in zip(candles, scores)
    }
    return {
        "dimension": dimension,
        "predictor": predictor,
        "thresholds": {"down": down_cut, "up": up_cut, "collapsed": up_cut <= down_cut},
        "startYear": candles[0]["year"] if candles else None,
        "endYear": candles[-1]["year"] if candles else None,
        "years": years,
    }


# ---------------- 统计 ----------------

def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """命中率的 Wilson 置信区间。小样本下比正态近似稳，n=0 时返回 None。

    用途：把"命中率比基线高"和"命中率比基线高得**不是噪声**"分开。
    20 条样本上 60% 与 33% 的差别，区间大概率是重叠的 —— 那时候不该下结论。
    """
    if n <= 0:
        return None
    p = hits / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def _confusion(rows: list[dict]) -> dict[str, dict[str, int]]:
    """预测 → 实际 的混淆矩阵（行列都含 吉/平/凶）。"""
    conf = {p: dict.fromkeys(LABELS, 0) for p in LABELS}
    for r in rows:
        conf[r["pred"]][r["truth"]] += 1
    return conf


def _rowsum(conf: dict[str, dict[str, int]], label: str) -> int:
    """某预测标签的总出现次数。"""
    return sum(conf[label].values())


def _colsum(conf: dict[str, dict[str, int]], label: str) -> int:
    """某实际标签的总出现次数。"""
    return sum(conf[p][label] for p in LABELS)


def _summarize(rows: list[dict]) -> dict[str, Any]:
    """一组对齐记录 → 指标块。全体与各分组都用它，保证组内口径与总口径一致。"""
    n = len(rows)
    if not n:
        return {
            "samples": 0,
            "decided": 0,
            "hits": 0,
            "hitRate": None,
            "hitRateStrict": None,
            "randomBaseline": None,
            "randomBaselineStrict": None,
            "majorityBaseline": None,
            "lift": None,
            "liftStrict": None,
            "ci95": None,
        }
    conf = _confusion(rows)
    hits = sum(conf[k][k] for k in LABELS)
    # 独立随机的期望命中率：预测按自己的边缘分布、实际按自己的边缘分布。
    random_base = sum(_rowsum(conf, k) / n * _colsum(conf, k) / n for k in LABELS)
    majority = max(_colsum(conf, k) for k in LABELS) / n

    # 严格口径：只看"实际有吉凶"的样本（排除实际为平的），且预测为平一律算错。
    # 这是多数人真正关心的那个数 —— 「说吉的年份真的吉了吗」。
    decided = _colsum(conf, LABEL_UP) + _colsum(conf, LABEL_DOWN)
    if decided:
        strict_hits = conf[LABEL_UP][LABEL_UP] + conf[LABEL_DOWN][LABEL_DOWN]
        # 严格子集上预测标签的分布：只数实际非平的那些行。
        p_pred2 = {
            k: sum(conf[k][t] for t in (LABEL_UP, LABEL_DOWN)) / decided for k in LABELS
        }
        p_true2 = {k: _colsum(conf, k) / decided for k in (LABEL_UP, LABEL_DOWN)}
        random_strict = sum(p_pred2[k] * p_true2[k] for k in (LABEL_UP, LABEL_DOWN))
        hit_strict: float | None = strict_hits / decided
        lift_strict: float | None = round(hit_strict - random_strict, 4)
    else:
        strict_hits = 0
        random_strict = 0.0
        hit_strict = None
        lift_strict = None

    rate = hits / n
    return {
        "samples": n,
        "decided": decided,
        "hits": hits,
        "hitRate": round(rate, 4),
        "hitRateStrict": round(hit_strict, 4) if hit_strict is not None else None,
        "randomBaseline": round(random_base, 4),
        "randomBaselineStrict": round(random_strict, 4) if decided else None,
        "majorityBaseline": round(majority, 4),
        "lift": round(rate - random_base, 4),
        "liftStrict": lift_strict,
        "ci95": wilson_interval(hits, n),
    }


def _group(rows: list[dict], key: str, label_name: str) -> list[dict]:
    """按某个字段分组，每组给一份与总口径一致的指标块。样本多的组排前面。"""
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        buckets.setdefault(str(r.get(key, "")), []).append(r)
    out = [
        {label_name: name, **_summarize(group)}
        for name, group in buckets.items()
    ]
    out.sort(key=lambda g: (-g["samples"], g[label_name]))
    return out


def _surprise(row: dict) -> float:
    """错判的"惊讶度"：预判越吉却实际凶（或反之）越值得人看。"""
    return row["score"] if row["truth"] == LABEL_DOWN else 100.0 - row["score"]


# ---------------- 回测主入口 ----------------

def run_backtest(
    pairs: list[tuple[BaziChart, list[dict]]],
    *,
    dimension: str = DIMENSION_AUTO,
    predictor: str = PREDICTOR_CLOSE,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> dict[str, Any]:
    """跑一次回测。

    Args:
        pairs: [(命盘, 该盘的事件列表)]。单盘传一个元素，多盘汇总就传多个；
            汇总时**阈值仍按各盘自己的分布取**（见 `predict_chart`），
            故"吉"在同一批结果里始终表示"该盘自己的高位"。
        dimension: `auto` 按事件领域选维度；否则强制统一维度。
        predictor: 见 `year_score`。
        min_samples: 低于此样本数即判为不可用（`ok=False` + 告警），但仍会算出来。

    事件字典只需三个键：`ganzhiYear` / `polarity` / `domain`，
    可选 `note` / `source` / `eventDate` / `id` 会原样带进 `misses` 便于复盘。
    """
    if dimension != DIMENSION_AUTO and dimension not in DIMENSIONS:
        raise ValueError(f"dimension 需为 {DIMENSION_AUTO}/{'/'.join(DIMENSIONS)} 之一")
    if predictor not in PREDICTORS:
        raise ValueError(f"predictor 需为 {'/'.join(PREDICTORS)} 之一")
    if min_samples < 1:
        raise ValueError("min_samples 需为正整数")

    warnings: list[str] = []
    rows: list[dict] = []
    unmatched: list[dict] = []
    invalid = 0
    collapsed: list[str] = []
    chart_keys: list[str] = []
    span_from: int | None = None
    span_to: int | None = None

    for chart, events in pairs:
        key = f"{chart.birth.solar}|{chart.birth.gender}"
        chart_keys.append(key)
        dims = (
            sorted({dimension_for_domain(e.get("domain", "")) for e in events})
            if dimension == DIMENSION_AUTO
            else [dimension]
        ) or [DIM_COMPREHENSIVE]
        preds = {
            d: predict_chart(chart, dimension=d, predictor=predictor, max_age=AGE_SPAN)
            for d in dims
        }
        for d, p in preds.items():
            if p["thresholds"]["collapsed"]:
                collapsed.append(f"{key}/{d}")
            # 把各盘预测区间并起来回报：事件落在区间外时，调用方得说得出"区间是多少"
            if p["startYear"] is not None:
                span_from = p["startYear"] if span_from is None else min(span_from, p["startYear"])
                span_to = p["endYear"] if span_to is None else max(span_to, p["endYear"])

        for e in events:
            truth = POLARITY_LABELS.get(e.get("polarity"))
            if truth is None:
                invalid += 1
                continue
            dom = e.get("domain", "") or "general"
            dim = dimension_for_domain(dom) if dimension == DIMENSION_AUTO else dimension
            pred = preds.get(dim) or next(iter(preds.values()))
            year = e.get("ganzhiYear")
            hit = pred["years"].get(year)
            if hit is None:
                unmatched.append({"chart": key, "ganzhiYear": year, "note": e.get("note", "")})
                continue
            rows.append(
                {
                    "chart": key,
                    "dimension": dim,
                    "domain": dom,
                    "year": year,
                    "ganzhi": hit["ganzhi"],
                    "score": hit["score"],
                    "pred": hit["label"],
                    "truth": truth,
                    "note": e.get("note", ""),
                    "source": e.get("source", ""),
                    "id": e.get("id", ""),
                }
            )

    # 重复锚点：同盘同年同域同极性记了两遍。不拦（可能是两次独立事件），但要报 ——
    # 否则条数被默默加权，命中率的样本数会被虚高。
    seen: dict[tuple, int] = {}
    for r in rows:
        anchor = (r["chart"], r["year"], r["domain"], r["truth"])
        seen[anchor] = seen.get(anchor, 0) + 1
    duplicates = sum(v - 1 for v in seen.values() if v > 1)

    summary = _summarize(rows)
    summary["ok"] = bool(summary["samples"] >= min_samples)
    summary["significant"] = bool(
        summary["ok"]
        and summary["ci95"] is not None
        and summary["ci95"][0] > (summary["randomBaseline"] or 0.0)
    )

    if not rows:
        warnings.append("没有任何可用样本：事件要么为空，要么全部落在 K 线区间之外。")
    elif summary["samples"] < min_samples:
        warnings.append(
            f"样本不足：可用 {summary['samples']} 条 < 下限 {min_samples} 条，"
            "命中率不具统计意义，只能当方向性参考。"
        )
    if duplicates:
        warnings.append(f"存在 {duplicates} 条重复锚点（同盘·同年·同域·同极性），命中率被重复计入。")
    if unmatched:
        warnings.append(
            f"{len(unmatched)} 条事件的命理年不在该盘 K 线区间内（起运前童限期或超出 {AGE_SPAN} 虚岁），已排除。"
        )
    if invalid:
        warnings.append(f"{invalid} 条事件的 polarity 非法，已跳过。")
    if collapsed:
        warnings.append(f"以下命盘/维度分数取值过少导致吉凶阈值重合，标签退化：{collapsed[:5]}")

    misses = sorted(
        (r for r in rows if r["truth"] != LABEL_MID and r["pred"] != r["truth"]),
        key=_surprise,
        reverse=True,
    )[:MISS_EXAMPLES]
    years = sorted({r["year"] for r in rows})

    return {
        "dimension": dimension,
        "predictor": predictor,
        "minSamples": min_samples,
        "charts": len({r["chart"] for r in rows}),
        "yearFrom": years[0] if years else None,
        "yearTo": years[-1] if years else None,
        # 回测**窗口**（各盘预测区间的并集），与 yearFrom/yearTo（实际命中样本的年份范围）
        # 不是一回事：窗口外的年份永远回测不了，前端要拿它提示"这条进不了命中率"。
        "ageSpan": AGE_SPAN,
        "spanFrom": span_from,
        "spanTo": span_to,
        "events": {
            "total": len(rows) + len(unmatched) + invalid,
            "used": len(rows),
            "unmatched": len(unmatched),
            "invalid": invalid,
            "duplicate": duplicates,
        },
        "unmatchedYears": unmatched[:UNMATCHED_EXAMPLES],
        "summary": summary,
        "byDomain": _group(rows, "domain", "domain"),
        "byDimension": _group(rows, "dimension", "dimension"),
        "byChart": _group(rows, "chart", "chart"),
        "misses": [
            {k: r[k] for k in ("chart", "year", "ganzhi", "pred", "truth", "score", "domain", "note")}
            for r in misses
        ],
        "warnings": warnings,
        "note": (
            f"阈值为各盘全期({AGE_SPAN}虚岁内)分布分位：吉=上 1/3、凶=下 1/3；"
            "命中率须与 randomBaseline 一并读，只有 ci95 下界高于基线才算有区分度。"
        ),
    }


# ---------------- 合盘（关系）回测 ----------------
# 单盘事件校准"这个人这年过得好不好"；双盘关系事件校准"这两人这年顺不顺"。
# 两者共用同一套统计（分位阈值 / 随机基线 / Wilson / 严格口径），只有预测源不同：
# 单盘吃 `build_kline` 的分数，合盘吃 `build_resonance` 的共振分。

PAIR_PREDICTOR_RESONANCE = "resonance"

# 共振分的四个逐年项。顺序即输出顺序（前端与诊断报告都按它排）
TERMS_ORDER = ("trend", "align", "sync", "palace")


def predict_pair(
    chart_a: BaziChart,
    chart_b: BaziChart,
    *,
    dimension: str = DIM_COMPREHENSIVE,
    max_age: int = AGE_SPAN,
) -> dict[str, Any]:
    """一对盘的逐年关系标签：{年份: {label, score, ganzhi, terms}} + 阈值。

    阈值取**该对全期共振分的分布**分位，与单盘口径一致：「顺」是「这一对自己一辈子里的
    高位」，不是跨对可比的绝对刻度 —— 各对的静态基线本来就不一样（`pair_base`），
    拿一条绝对线去切会把基线高的对全判成顺。

    年份范围是两盘 K 线的**交集**（起运年不同，童限期没有共同刻度），故比单盘短。
    """
    if dimension not in DIMENSIONS:
        raise ValueError(f"dimension 需为 {'/'.join(DIMENSIONS)} 之一")
    if not 0 < max_age <= MAX_AGE_LIMIT:
        raise ValueError(f"max_age 需在 1-{MAX_AGE_LIMIT} 之间")

    payload = build_resonance(chart_a, chart_b, max_age=max_age, dimension=dimension)
    rows = payload["years"]
    scores = [float(r.get("resonance") or 0.0) for r in rows]
    down_cut = _percentile(scores, DOWN_QUANTILE) if scores else 0.0
    up_cut = _percentile(scores, UP_QUANTILE) if scores else 0.0
    years = {
        r["year"]: {
            "label": label_of(s, down_cut, up_cut),
            "score": s,
            "ganzhi": r.get("ganzhi") or "",
            "terms": dict(r.get("terms") or {}),
        }
        for r, s in zip(rows, scores)
    }
    return {
        "dimension": dimension,
        "predictor": PAIR_PREDICTOR_RESONANCE,
        "thresholds": {"down": down_cut, "up": up_cut, "collapsed": up_cut <= down_cut},
        "startYear": rows[0]["year"] if rows else None,
        "endYear": rows[-1]["year"] if rows else None,
        "years": years,
    }


def _term_diagnostics(rows: list[dict]) -> list[dict]:
    """逐项诊断：每个 term 在"实际吉"的年份是不是真的更高。

    这是**反推权重的直接依据**，比总命中率有用得多：总命中率只能告诉你"合起来不准"，
    而逐项均值差能指出是哪一项在帮倒忙 ——
    `delta <= 0` 说明该项（或其符号）与现实相反：那是权重调参该先看的地方。
    """
    up: dict[str, list[float]] = {t: [] for t in TERMS_ORDER}
    down: dict[str, list[float]] = {t: [] for t in TERMS_ORDER}
    for r in rows:
        if r["truth"] == LABEL_UP:
            bucket = up
        elif r["truth"] == LABEL_DOWN:
            bucket = down
        else:
            continue
        for t in TERMS_ORDER:
            v = (r.get("terms") or {}).get(t)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                bucket[t].append(float(v))

    out = []
    for t in TERMS_ORDER:
        u, d = up[t], down[t]
        if not u or not d:
            out.append(
                {
                    "term": t,
                    "meanUp": round(sum(u) / len(u), 3) if u else None,
                    "meanDown": round(sum(d) / len(d), 3) if d else None,
                    "delta": None,
                    "signOk": None,
                    "samplesUp": len(u),
                    "samplesDown": len(d),
                }
            )
            continue
        mu, md = sum(u) / len(u), sum(d) / len(d)
        out.append(
            {
                "term": t,
                "meanUp": round(mu, 3),
                "meanDown": round(md, 3),
                "delta": round(mu - md, 3),
                "signOk": mu > md,
                "samplesUp": len(u),
                "samplesDown": len(d),
            }
        )
    return out


def run_pair_backtest(
    pairs: list[tuple[BaziChart, BaziChart, list[dict]]],
    *,
    dimension: str = DIM_COMPREHENSIVE,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> dict[str, Any]:
    """跑一次合盘（关系）回测。

    Args:
        pairs: [(甲盘, 乙盘, 该对的关系事件列表)]。共振分对甲乙**是对称的**
            （`kline_resonance` 有交换对称单测），故同一对不分谁在甲谁在乙；
            调用方按规范化后的对分组即可（接口层就是这么做的）。
        dimension: 关系事件没有"事业/健康"之分，故不做 `auto` 映射，默认综合。
        min_samples: 同单盘口径，低于此数即 `ok=False` + 告警，但仍会算出来。

    与单盘回测的三点差别（都是刻意的）
    ----------------------------------
    1. 阈值在**该对**的全期共振分布上取分位（各对基线不同，不能跨对用绝对线）。
    2. 事件字典带 `relation`（夫妻/亲子/同事…），只用于分组复盘，不参与预测。
    3. 额外给 `termDiagnostics` —— 关系回测的产出不只是"准不准"，
       而是"哪一项 term 的方向与现实相反"，那才是校准权重的输入。
    """
    if dimension not in DIMENSIONS:
        raise ValueError(f"dimension 需为 {'/'.join(DIMENSIONS)} 之一")
    if min_samples < 1:
        raise ValueError("min_samples 需为正整数")

    warnings: list[str] = []
    rows: list[dict] = []
    unmatched: list[dict] = []
    invalid = 0
    collapsed: list[str] = []
    span_from: int | None = None
    span_to: int | None = None

    for chart_a, chart_b, events in pairs:
        key = f"{chart_a.birth.solar}×{chart_b.birth.solar}"
        pred = predict_pair(chart_a, chart_b, dimension=dimension, max_age=AGE_SPAN)
        if pred["thresholds"]["collapsed"]:
            collapsed.append(key)
        # 把各对的预测区间并起来回报：事件落在区间外时，调用方得说得出"区间是多少"，
        # 否则用户只看到"没有可用样本"，会以为是自己没录进去。
        if pred["startYear"] is not None:
            span_from = pred["startYear"] if span_from is None else min(span_from, pred["startYear"])
            span_to = pred["endYear"] if span_to is None else max(span_to, pred["endYear"])

        for e in events:
            truth = POLARITY_LABELS.get(e.get("polarity"))
            if truth is None:
                invalid += 1
                continue
            year = e.get("ganzhiYear")
            hit = pred["years"].get(year)
            if hit is None:
                unmatched.append({"pair": key, "ganzhiYear": year, "note": e.get("note", "")})
                continue
            rows.append(
                {
                    "pair": key,
                    "relation": e.get("relation", "") or "未标注",
                    "year": year,
                    "ganzhi": hit["ganzhi"],
                    "score": hit["score"],
                    "pred": hit["label"],
                    "truth": truth,
                    "terms": hit["terms"],
                    "note": e.get("note", ""),
                    "source": e.get("source", ""),
                    "id": e.get("id", ""),
                }
            )

    seen: dict[tuple, int] = {}
    for r in rows:
        anchor = (r["pair"], r["year"], r["truth"])
        seen[anchor] = seen.get(anchor, 0) + 1
    duplicates = sum(v - 1 for v in seen.values() if v > 1)

    summary = _summarize(rows)
    summary["ok"] = bool(summary["samples"] >= min_samples)
    summary["significant"] = bool(
        summary["ok"]
        and summary["ci95"] is not None
        and summary["ci95"][0] > (summary["randomBaseline"] or 0.0)
    )

    if not rows:
        warnings.append(
            "没有任何可用样本：关系事件要么为空，要么全部落在两盘共振区间之外。"
            f"（回测区间固定为 1-{AGE_SPAN} 虚岁）"
        )
    elif summary["samples"] < min_samples:
        warnings.append(
            f"样本不足：可用 {summary['samples']} 条 < 下限 {min_samples} 条，"
            "命中率不具统计意义，只能当方向性参考。"
        )
    if duplicates:
        warnings.append(f"存在 {duplicates} 条重复锚点（同对·同年·同极性），命中率被重复计入。")
    if unmatched:
        warnings.append(
            f"{len(unmatched)} 条事件的命理年不在该对共振区间内（两盘起运年交集之外），已排除。"
        )
    if invalid:
        warnings.append(f"{invalid} 条事件的 polarity 非法，已跳过。")
    if collapsed:
        warnings.append(f"以下配对共振分取值过少导致顺逆阈值重合，标签退化：{collapsed[:5]}")

    misses = sorted(
        (r for r in rows if r["truth"] != LABEL_MID and r["pred"] != r["truth"]),
        key=_surprise,
        reverse=True,
    )[:MISS_EXAMPLES]
    years = sorted({r["year"] for r in rows})

    return {
        "dimension": dimension,
        "predictor": PAIR_PREDICTOR_RESONANCE,
        "minSamples": min_samples,
        "pairs": len({r["pair"] for r in rows}),
        "yearFrom": years[0] if years else None,
        "yearTo": years[-1] if years else None,
        # 回测**窗口**（各对预测区间的并集），与 yearFrom/yearTo（实际命中样本的年份范围）
        # 不是一回事：窗口外的年份永远回测不了，前端要拿它提示"这条进不了命中率"。
        "ageSpan": AGE_SPAN,
        "spanFrom": span_from,
        "spanTo": span_to,
        "events": {
            "total": len(rows) + len(unmatched) + invalid,
            "used": len(rows),
            "unmatched": len(unmatched),
            "invalid": invalid,
            "duplicate": duplicates,
        },
        "unmatchedYears": unmatched[:UNMATCHED_EXAMPLES],
        "summary": summary,
        "byRelation": _group(rows, "relation", "relation"),
        "byPair": _group(rows, "pair", "pair"),
        "termDiagnostics": _term_diagnostics(rows),
        "misses": [
            {k: r[k] for k in ("pair", "year", "ganzhi", "pred", "truth", "score", "relation", "note")}
            for r in misses
        ],
        "warnings": warnings,
        "note": (
            f"阈值为各对全期({AGE_SPAN}虚岁内)共振分布分位：顺=上 1/3、逆=下 1/3；"
            "命中率须与 randomBaseline 一并读；termDiagnostics 的 delta<=0 表示该项方向与现实相反。"
        ),
    }
