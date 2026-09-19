"""命理 K 线接口：确定性运势评分 → 年 K 线（OHLCV + 大运带）。

路由挂在 /xianzhi 前缀下（由 `app.api.xianzhi` 聚合），本模块自持 router。

设计要点
--------
- **纯确定性**：分数由 `app.domain.fortune_score` 算出，不调用任何大模型。
  故本端点无 LLM 成本、无口径漂移，可黄金快照回归。
- **按需计算，不进 /chart 响应**：K 线要遍历 ~80 年 × 12 节气月，若并进 /chart
  会让那个本就偏重的接口再涨一块（历史上 12 步大运 × 1500 条流月曾占 /chart 95% 体积）。
- **月分数默认不返回**：前端画蜡烛只需要 OHLCV；月分数是调试与"每个值有出处"
  的证据链，需要时用 `include_months=1` 取。
- **一次请求一个维度**：`dimension` 决定十神侧重（综合/事业/财运/感情/健康），
  不提供"一次返回全部维度"的批量形态 —— 那会让载荷翻五倍，而切换维度的
  代价只是一次请求（命盘走 `bazi_cache`，二次请求只重算评分）。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api import data_access as repo
from app.api.deps import app_context_dependency
from app.domain import fortune_score, kline_backtest, kline_resonance

router = APIRouter(tags=["Xianzhi"])

MAX_AGE_DEFAULT = 80
# 年龄上限护栏：K 线遍历成本与年数线性相关，放开无上限等于开放一个 CPU 放大点
MAX_AGE_LIMIT = 120

# 按步数覆盖时的上限：与 `_build_chart(dayun_count=12)` 对齐，要第 13 步得先改那里
MAX_DAYUN_LIMIT = 12


def _dayun_end_year(chart, max_dayun: int) -> int | None:
    """第 `max_dayun` 步大运的结束年；若该步已越过年龄上限（起运极晚）则返回 None。

    为什么按"整段大运"收尾而不是按岁数截断：K 线末段只落进几年时，前端那格宽度
    只剩几十 rpx，干支两个字会被 `overflow:hidden` 裁掉 —— 看上去就是最右边那个
    大运"被遮挡"。收在大运边界上，末段才是完整的十年，标签才画得下。
    """
    birth_year = fortune_score.birth_year_of(chart)
    end = None
    for d in chart.dayun[:max_dayun]:
        if d.end_year - birth_year + 1 <= MAX_AGE_LIMIT:
            end = d.end_year
    return end


def _resolve_max_age(chart, *, max_age: int, max_dayun: int) -> int:
    """把「覆盖到第 N 步大运」折算成年龄上限。

    两套口径同时给时**以 `max_dayun` 为准**（0 表示不启用，按 `max_age` 截断）：
    调用方要么说"覆盖到几岁"，要么说"覆盖到第几步大运"，不该两头各要一半。
    """
    if max_dayun <= 0:
        return max_age
    end = _dayun_end_year(chart, max_dayun)
    if end is None:
        return max_age
    return end - fortune_score.birth_year_of(chart) + 1


def _dayun_bands(chart) -> list[dict]:
    """大运带：十年一段的"宏观周期"，供前端画背景色带/均线。

    K 线是「大运为纲、流年为目」：`fortune_score` 里大运权重 0.5 高于流年 0.3，
    本函数把这条口径在可视化层显式化，而不是让前端自己从 dayun 字段猜。
    """
    return [
        {
            "index": d.index,
            "ganzhi": d.ganzhi,
            "startYear": d.start_year,
            "endYear": d.end_year,
            "startAge": d.start_age,
            "endAge": d.end_age,
            "shishenGan": d.shishen_gan,
        }
        for d in chart.dayun
    ]


def _build_chart(
    birth_time: str, gender: str, sect: int, yun_sect: int, longitude: float | None
):
    """按 /kline 的口径构建命盘。**评分与批注必须走同一个入口**：

    批注要吃 `compact_facts`/`check_facts`，也有命盘对象需求；
    若它自己 build 一次、评分再 build 一次，两处流派/经度一旦有人改漏一处，
    就会出现「批注解的盘」和「画出来的曲线」不是同一张。故只留这一个入口。
    """
    from app.domain.chart_builder import build_bazi_chart, parse_birth, parse_gender
    from app.domain.time_parse import _normalize_birth_time

    birth_time = _normalize_birth_time(birth_time)
    parse_birth(birth_time)
    parse_gender(gender)

    return build_bazi_chart(
        birth_time,
        gender,
        sect=sect,
        yun_sect=yun_sect,
        dayun_count=12,
        liunian_years=5,
        longitude=longitude,
    )


def _compute_kline_payload(
    birth_time: str,
    gender: str,
    sect: int,
    yun_sect: int,
    longitude: float | None,
    max_age: int,
    include_months: bool,
    dimension: str,
    max_dayun: int = 0,
) -> dict:
    """同步构建 K 线载荷，输入非法抛 ValueError（由端点翻成 400）。"""
    chart = _build_chart(birth_time, gender, sect, yun_sect, longitude)
    max_age = _resolve_max_age(chart, max_age=max_age, max_dayun=max_dayun)

    candles = []
    for candle in fortune_score.build_kline(chart, max_age=max_age, dimension=dimension):
        row = {k: v for k, v in candle.items() if k != "monthScores"}
        if include_months:
            row["monthScores"] = candle["monthScores"]
        candles.append(row)

    years = fortune_score.kline_years(chart, max_age=max_age)
    return {
        "favor": fortune_score.chart_favor_summary(chart),
        "candles": candles,
        "dayunBands": _dayun_bands(chart),
        "meta": {
            "startYear": years[0] if years else None,
            "endYear": years[-1] if years else None,
            "yearCount": len(years),
            "maxAge": max_age,
            "maxDayun": max_dayun,
            "dimension": dimension,
            "dimensionLabel": fortune_score.DIMENSION_LABELS.get(dimension, ""),
            "dimensionNote": fortune_score.DIMENSION_NOTES.get(dimension, ""),
            "dimensionEmphasis": fortune_score.dimension_emphasis(chart, dimension),
            "availableDimensions": [
                {
                    "key": d,
                    "label": fortune_score.DIMENSION_LABELS[d],
                    "note": fortune_score.DIMENSION_NOTES.get(d, ""),
                }
                for d in fortune_score.DIMENSIONS
            ],
            "kScore": fortune_score.K_SCORE,
            "weightDayun": fortune_score.W_DAYUN,
            "weightLiunian": fortune_score.W_LIUNIAN,
            "weightLiuyue": fortune_score.W_LIUYUE,
            "note": "分数为确定性规则计算（非大模型生成）；流年以立春换岁，"
            "起点为起运年（童限期无大运可论）。维度只改十神侧重，不改干支关系判定。",
        },
    }


@router.get("/kline")
async def get_kline(
    birth_time: str,
    gender: str,
    sect: int = 2,
    yun_sect: int = 1,
    longitude: float | None = None,
    max_age: int = MAX_AGE_DEFAULT,
    max_dayun: int = 0,
    include_months: bool = False,
    dimension: str = fortune_score.DIM_COMPREHENSIVE,
):
    """命理 K 线：1 岁起的年运势蜡烛 + 大运带。

    Args:
        birth_time: 出生时间（支持公历/农历/时辰等格式，与 /chart 同一入口）
        gender: 性别
        sect: 日柱流派（1=晚子时日柱算当天，2=次日）
        yun_sect: 起运流派
        longitude: 出生地经度（真太阳时校正）
        max_age: 覆盖到几岁（默认 80，上限 120）
        max_dayun: 覆盖到第几步大运（默认 0=不启用）。给值时以整段大运收尾并覆盖
            `max_age`：末段截在半个大运上会让最右边那个大运的干支标签被裁掉。
        include_months: 是否附带每年 12 个节气月的分数明细
        dimension: 取象维度（comprehensive/career/wealth/love/health），默认综合
    """
    from app.tools.cache import bazi_cache

    if not 0 < max_age <= MAX_AGE_LIMIT:
        raise HTTPException(status_code=400, detail=f"max_age 需在 1-{MAX_AGE_LIMIT} 之间")
    if not 0 <= max_dayun <= MAX_DAYUN_LIMIT:
        raise HTTPException(
            status_code=400, detail=f"max_dayun 需在 0-{MAX_DAYUN_LIMIT} 之间（0=不启用）"
        )
    if dimension not in fortune_score.DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"dimension 需为 {'/'.join(fortune_score.DIMENSIONS)} 之一",
        )

    cache_tool = (
        f"kline_api:{longitude}:{max_age}:{max_dayun}:{int(include_months)}:{dimension}"
    )
    payload = bazi_cache.get(birth_time, gender, sect, yun_sect, cache_tool)
    if payload is not None:
        return payload
    try:
        payload = await asyncio.to_thread(
            _compute_kline_payload,
            birth_time,
            gender,
            sect,
            yun_sect,
            longitude,
            max_age,
            include_months,
            dimension,
            max_dayun=max_dayun,
        )
        bazi_cache.set(birth_time, gender, payload, sect, yun_sect, cache_tool)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class KlineAnnotationRequest(BaseModel):
    """K 线批注请求体。

    用 POST + body 而不是 GET：批注是「按需生成」的动作，且参数已有 8 个
    （再往 query string 上叠会很难读）；也方便将来加 feedback 类字段。
    """

    birth_time: str = Field(..., description="出生时间，与 /kline 同一入口")
    gender: str
    sect: int = 2
    yun_sect: int = 1
    longitude: float | None = None
    dimension: str = fortune_score.DIM_COMPREHENSIVE
    scope: str = Field(default="overview", description="overview=当前大运与全期极值；year=指定流年")
    year: int | None = Field(default=None, description="scope=year 时的目标年份")
    max_dayun: int = Field(
        default=0,
        description="覆盖到第几步大运（0=不启用。须与 /kline 同值，否则批注说的'全期'与图上区间不是一段）",
    )


@router.post("/kline/annotation")
async def annotate_kline(
    body: KlineAnnotationRequest,
    app_ctx=Depends(app_context_dependency),
):
    """给 K 线的一段运势生成解读（**不影响任何分数**）。

    打分在 `domain.fortune_score`（纯确定性），本端点读它的现成输出再交给大模型解读。
    校验不过时不返回文本，只回 `factsOk=false` 与 `issues` —— 由前端决定怎么提示。
    """
    from app.agent import kline_annotator as annotator
    from app.tools.cache import bazi_cache

    if body.dimension not in fortune_score.DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"dimension 需为 {'/'.join(fortune_score.DIMENSIONS)} 之一",
        )
    if body.scope not in annotator.SCOPES:
        raise HTTPException(
            status_code=400, detail=f"scope 需为 {'/'.join(annotator.SCOPES)} 之一"
        )
    if body.scope == annotator.SCOPE_YEAR and body.year is None:
        raise HTTPException(status_code=400, detail="scope=year 时必须给 year")
    if not 0 <= body.max_dayun <= MAX_DAYUN_LIMIT:
        raise HTTPException(
            status_code=400, detail=f"max_dayun 需在 0-{MAX_DAYUN_LIMIT} 之间（0=不启用）"
        )

    chat_model = getattr(app_ctx, "chat_model", None)
    if chat_model is None:
        raise HTTPException(status_code=503, detail="LLM 未就绪，批注暂不可用")

    anchor_year = annotator.today_year()
    # 覆盖步数要进缓存键：批注写的是"全期最高/最低"，区间一变文案就该变
    tool = (
        f"{annotator.cache_tool(body.scope, body.dimension, body.year, anchor_year)}"
        f"|dayun{body.max_dayun}"
    )
    hit = bazi_cache.get(body.birth_time, body.gender, body.sect, body.yun_sect, tool)
    if hit is not None:
        return {**hit, "cached": True}

    try:
        # 批注读的是本接口自己的载荷（同一套 max_age/维度），命盘构建走同一入口
        payload = await asyncio.to_thread(
            _compute_kline_payload,
            body.birth_time,
            body.gender,
            body.sect,
            body.yun_sect,
            body.longitude,
            MAX_AGE_DEFAULT,
            False,
            body.dimension,
            max_dayun=body.max_dayun,
        )
        chart = await asyncio.to_thread(
            _build_chart, body.birth_time, body.gender, body.sect, body.yun_sect, body.longitude
        )
        result = await asyncio.to_thread(
            annotator.annotate,
            chat_model,
            chart,
            payload,
            scope=body.scope,
            year=body.year,
            dimension=body.dimension,
            anchor_year=anchor_year,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result["dimension"] = body.dimension
    # 只缓存成功的批注：一次模型抽风不该被缓存成"这盘永远没批注"
    if result.get("ok"):
        bazi_cache.set(
            body.birth_time, body.gender, result, body.sect, body.yun_sect, tool
        )
    return {**result, "cached": False}


def _resolve_pair_max_age(chart_a, chart_b, *, max_age: int, max_dayun: int) -> int:
    """合盘口径：把「各自覆盖到第 N 步大运」折成两盘共用的年龄上限。

    `build_resonance` 取两盘年份的交集，而两盘起运年不同，故这里先各自算到第 N 步
    大运的结束年、取更早的那个，再折回「相对出生更早那盘」的虚岁。这样交集右端
    与单盘 K 线右端对齐，页面上两条曲线才不会被看出长短不一。
    """
    if max_dayun <= 0:
        return max_age
    ends = [_dayun_end_year(ch, max_dayun) for ch in (chart_a, chart_b)]
    if any(e is None for e in ends):
        return max_age
    earliest_birth = min(fortune_score.birth_year_of(chart_a), fortune_score.birth_year_of(chart_b))
    return min(ends) - earliest_birth + 1


def _compute_resonance_payload(
    birth_a: str,
    gender_a: str,
    birth_b: str,
    gender_b: str,
    sect: int,
    yun_sect: int,
    longitude_a: float | None,
    longitude_b: float | None,
    max_age: int,
    dimension: str,
    max_dayun: int = 0,
) -> dict:
    """同步构建合盘共振载荷，输入非法抛 ValueError（由端点翻成 400）。"""
    chart_a = _build_chart(birth_a, gender_a, sect, yun_sect, longitude_a)
    chart_b = _build_chart(birth_b, gender_b, sect, yun_sect, longitude_b)
    max_age = _resolve_pair_max_age(chart_a, chart_b, max_age=max_age, max_dayun=max_dayun)
    payload = kline_resonance.build_resonance(
        chart_a, chart_b, max_age=max_age, dimension=dimension
    )
    # 两盘各自的喜忌摘要随共振线一起给：前端画共振线时通常要在同一屏显示双方用神，
    # 缺了它前端得再打两次 /kline，而这两张盘后端刚刚已经建好了。
    payload["favorA"] = fortune_score.chart_favor_summary(chart_a)
    payload["favorB"] = fortune_score.chart_favor_summary(chart_b)
    payload["meta"]["dimensionLabel"] = fortune_score.DIMENSION_LABELS.get(dimension, "")
    payload["meta"]["availableDimensions"] = [
        {
            "key": d,
            "label": fortune_score.DIMENSION_LABELS[d],
            "note": fortune_score.DIMENSION_NOTES.get(d, ""),
        }
        for d in fortune_score.DIMENSIONS
    ]
    return payload


class KlineResonanceRequest(BaseModel):
    """合盘共振请求体：两个人的出生信息 + 共同口径。"""

    birth_time_a: str = Field(..., description="甲方出生时间，与 /kline 同一入口")
    gender_a: str
    birth_time_b: str = Field(..., description="乙方出生时间")
    gender_b: str
    sect: int = 2
    yun_sect: int = 1
    longitude_a: float | None = None
    longitude_b: float | None = None
    max_age: int = MAX_AGE_DEFAULT
    dimension: str = fortune_score.DIM_COMPREHENSIVE
    max_dayun: int = Field(
        default=0, description="覆盖到第几步大运（0=不启用。与 /kline 同值才能对齐两图右端）"
    )


@router.post("/kline/resonance")
async def get_kline_resonance(body: KlineResonanceRequest):
    """合盘共振线：两条单盘 K 线之上的**只读**叠加层。

    只算「关系顺逆」，不改任何单盘分数；年份取两盘 K 线年份的交集
    （起运年不同，童限期没有共同刻度）。权重是待校准先验，
    前端应把它读作**相对次序**（哪几年比哪几年更顺），不是绝对吉凶。
    """
    from app.tools.cache import bazi_cache

    if not 0 < body.max_age <= MAX_AGE_LIMIT:
        raise HTTPException(status_code=400, detail=f"max_age 需在 1-{MAX_AGE_LIMIT} 之间")
    if not 0 <= body.max_dayun <= MAX_DAYUN_LIMIT:
        raise HTTPException(
            status_code=400, detail=f"max_dayun 需在 0-{MAX_DAYUN_LIMIT} 之间（0=不启用）"
        )
    if body.dimension not in fortune_score.DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"dimension 需为 {'/'.join(fortune_score.DIMENSIONS)} 之一",
        )

    # 缓存 key 的主键仍是「甲」，乙的完整身份编进 tool 串 —— BaziCache 的 key 是
    # 五元组的 md5，tool 只要确定即可，不必为成对场景另造一套缓存结构。
    tool = (
        f"kline_resonance:{body.birth_time_b}|{body.gender_b}|{body.longitude_b}"
        f"|{body.max_age}|{body.dimension}|dayun{body.max_dayun}"
    )
    hit = bazi_cache.get(body.birth_time_a, body.gender_a, body.sect, body.yun_sect, tool)
    if hit is not None:
        return {**hit, "cached": True}

    try:
        payload = await asyncio.to_thread(
            _compute_resonance_payload,
            body.birth_time_a,
            body.gender_a,
            body.birth_time_b,
            body.gender_b,
            body.sect,
            body.yun_sect,
            body.longitude_a,
            body.longitude_b,
            body.max_age,
            body.dimension,
            max_dayun=body.max_dayun,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    bazi_cache.set(
        body.birth_time_a, body.gender_a, payload, body.sect, body.yun_sect, tool
    )
    return {**payload, "cached": False}


# ---------------- 反馈闭环 ----------------


class KlineFeedbackRequest(BaseModel):
    """K 线反馈请求体：把"这段解读准不准"沉淀成可校准的数据。

    带上维度与年份是刻意的 —— 反馈只有能定位到「哪张盘的哪一年、哪个维度」
    才有校准价值；只存一句"不准"等于没存。
    """

    birth_time: str = Field(..., description="出生时间，与 /kline 同一入口")
    gender: str
    dimension: str = fortune_score.DIM_COMPREHENSIVE
    scope: str = Field(default="overview", description="overview=整段概览；year=指定流年")
    year: int | None = Field(default=None, description="scope=year 时的目标年份")
    anchor_year: int | None = Field(
        default=None, description="生成批注时的当前年（批注含「当前大运」类措辞，须留锚点）"
    )
    rating: int = Field(..., ge=1, le=5, description="1-5 星认可度")
    accurate: bool | None = Field(default=None, description="与实际是否吻合；未表态留空")
    comment: str = Field(default="", max_length=500)
    snapshot: dict | None = Field(default=None, description="当时的批注/曲线指纹，便于事后复盘")


@router.post("/kline/feedback")
async def submit_kline_feedback(body: KlineFeedbackRequest):
    """记一条 K 线反馈。**只写不读，不影响任何分数。**"""
    from app.agent import kline_annotator as annotator
    from app.db.chart_store import KLINE_RATING_MAX, KLINE_RATING_MIN

    if body.dimension not in fortune_score.DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"dimension 需为 {'/'.join(fortune_score.DIMENSIONS)} 之一",
        )
    if body.scope not in annotator.SCOPES:
        raise HTTPException(
            status_code=400, detail=f"scope 需为 {'/'.join(annotator.SCOPES)} 之一"
        )
    if body.scope == annotator.SCOPE_YEAR and body.year is None:
        raise HTTPException(status_code=400, detail="scope=year 时必须给 year")
    if not KLINE_RATING_MIN <= body.rating <= KLINE_RATING_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"rating 需在 {KLINE_RATING_MIN}-{KLINE_RATING_MAX} 之间",
        )

    try:
        fid = await repo.add_kline_feedback(
            body.birth_time,
            body.gender,
            body.dimension,
            body.scope,
            body.rating,
            year=body.year,
            anchor_year=body.anchor_year,
            accurate=body.accurate,
            comment=body.comment,
            snapshot=body.snapshot,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "id": fid}


@router.get("/kline/feedback")
async def list_kline_feedback_endpoint(
    birth_time: str = "",
    gender: str = "",
    dimension: str = "",
    limit: int = 100,
):
    """列反馈（校准脚本与复盘用）。`birth_time` 为空即"列最近的"。"""
    if dimension and dimension not in fortune_score.DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"dimension 需为 {'/'.join(fortune_score.DIMENSIONS)} 之一",
        )
    if not 0 < limit <= 500:
        raise HTTPException(status_code=400, detail="limit 需在 1-500 之间")
    items = await repo.list_kline_feedback(birth_time, gender, dimension, limit)
    return {"items": items, "count": len(items)}


@router.get("/kline/feedback/stats")
async def kline_feedback_stats_endpoint(dimension: str = ""):
    """反馈汇总：均分 / 吻合率 / 按维度分布。回测校准的输入端。"""
    if dimension and dimension not in fortune_score.DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"dimension 需为 {'/'.join(fortune_score.DIMENSIONS)} 之一",
        )
    return await repo.kline_feedback_stats(dimension)


# ---------------- 事件标注（回测的真相面） ----------------

# 回测是 CPU 放大点：每张盘要跑 100 年 × 最多 5 个维度（实测约 0.03s/盘·维度）。
# 仍设上限，避免有人把整个库丢进来把请求拖成长任务。
MAX_BACKTEST_CHARTS = 20
MAX_BACKTEST_EVENTS = 2000
MAX_EVENT_NOTE = 500


class KlineEventRequest(BaseModel):
    """事件标注请求体：一条「某人某年实际发生了吉/凶之事」。

    年份有两个来源：`ganzhi_year`（直接给命理年）或 `event_date`（给公历日期，后端按立春换岁推出）。
    两者都允许，但**不能都不给**；都给时会互相校验 —— 1-2 月的事件按公历年填是最高频的录入错误，
    后端静默改写会让人以为"我填的是对的"，直接报错才纠得回来。
    """

    birth_time: str = Field(..., description="出生时间，与 /kline 同一入口")
    gender: str
    sect: int = 2
    yun_sect: int = 1
    longitude: float | None = None
    ganzhi_year: int | None = Field(default=None, description="命理年（立春换岁）")
    event_date: str = Field(default="", description="原始公历日期 YYYY-MM-DD，用于推导命理年")
    polarity: int = Field(..., description="1=吉 / 0=平 / -1=凶")
    domain: str = Field(default="general", description="general/career/wealth/love/health")
    source: str = Field(default="", description="来源：传记 / 自述 / 案例库 / 人工")
    note: str = Field(default="", max_length=MAX_EVENT_NOTE)
    case_id: str = ""


def _resolve_ganzhi_year(ganzhi_year: int | None, event_date: str) -> int:
    """命理年：优先信任显式值，但给了日期就交叉校验。"""
    from app.domain.xipan import ganzhi_year_of

    derived: int | None = None
    if event_date:
        try:
            derived = ganzhi_year_of(event_date)
        except ValueError:
            # 不透传 `Invalid isoformat string: '...'` 这种 Python 内部文案：
            # 录入的人要的是"该填什么格式"，不是标准库抛了什么。
            raise HTTPException(
                status_code=400, detail=f"event_date 需为 YYYY-MM-DD 格式（收到「{event_date}」）"
            )
    if ganzhi_year is None:
        if derived is None:
            raise HTTPException(status_code=400, detail="ganzhi_year 与 event_date 至少给一个")
        return derived
    if derived is not None and derived != ganzhi_year:
        raise HTTPException(
            status_code=400,
            detail=(
                f"ganzhi_year={ganzhi_year} 与 event_date={event_date} 不符："
                f"按立春换岁该日期属 {derived} 年。1-2 月的事件请确认是按公历年还是命理年填的。"
            ),
        )
    return ganzhi_year


@router.post("/kline/events")
async def submit_kline_event(body: KlineEventRequest):
    """录一条真实事件标注。**只写不读，不影响任何分数。**"""
    from app.db.chart_store import (
        KLINE_EVENT_DOMAINS,
        KLINE_EVENT_YEAR_MAX,
        KLINE_EVENT_YEAR_MIN,
        KLINE_POLARITIES,
    )

    if body.polarity not in KLINE_POLARITIES:
        raise HTTPException(status_code=400, detail="polarity 只能取 1（吉）/ 0（平）/ -1（凶）")
    if body.domain not in KLINE_EVENT_DOMAINS:
        raise HTTPException(
            status_code=400, detail=f"domain 需为 {'/'.join(KLINE_EVENT_DOMAINS)} 之一"
        )
    ganzhi_year = _resolve_ganzhi_year(body.ganzhi_year, body.event_date)
    if not KLINE_EVENT_YEAR_MIN <= ganzhi_year <= KLINE_EVENT_YEAR_MAX:
        raise HTTPException(status_code=400, detail=f"ganzhi_year 需在 {KLINE_EVENT_YEAR_MIN}-{KLINE_EVENT_YEAR_MAX} 之间")
    if body.sect not in (1, 2):
        raise HTTPException(status_code=400, detail="sect 需为 1 或 2")

    # 起盘校验：年份在命理上"存在"不代表在这张盘上存在，出生信息非法就没法回测。
    try:
        await asyncio.to_thread(
            _build_chart, body.birth_time, body.gender, body.sect, body.yun_sect, body.longitude
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        eid = await repo.add_kline_event(
            body.birth_time,
            body.gender,
            ganzhi_year,
            body.polarity,
            sect=body.sect,
            yun_sect=body.yun_sect,
            longitude=body.longitude,
            event_date=body.event_date or None,
            domain=body.domain,
            source=body.source,
            note=body.note,
            case_id=body.case_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "id": eid, "ganzhiYear": ganzhi_year}


@router.get("/kline/events")
async def list_kline_events_endpoint(
    birth_time: str = "",
    gender: str = "",
    ganzhi_year: int | None = None,
    domain: str = "",
    limit: int = 500,
):
    """列事件标注（CLI / 复盘用）。`birth_time` 为空即"列最近的"。"""
    from app.db.chart_store import KLINE_EVENT_DOMAINS

    if domain and domain not in KLINE_EVENT_DOMAINS:
        raise HTTPException(
            status_code=400, detail=f"domain 需为 {'/'.join(KLINE_EVENT_DOMAINS)} 之一"
        )
    if not 0 < limit <= MAX_BACKTEST_EVENTS:
        raise HTTPException(status_code=400, detail=f"limit 需在 1-{MAX_BACKTEST_EVENTS} 之间")
    items = await repo.list_kline_events(birth_time, gender, ganzhi_year, domain, limit)
    return {"items": items, "count": len(items)}


@router.get("/kline/events/stats")
async def kline_event_stats_endpoint():
    """事件库总览：总量 / 吉凶分布 / 领域分布 / 涉及命盘。回测前先看它。"""
    return await repo.kline_event_stats()


@router.delete("/kline/events/{event_id}")
async def delete_kline_event_endpoint(event_id: str):
    """删一条录错的标注。**标注是人工录的，必须能删** —— 否则回测被永久污染。"""
    ok = await repo.delete_kline_event(event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="未找到该事件标注")
    return {"ok": True}


# ---------------- 合盘关系事件标注（共振权重的真相面） ----------------
#
# 单盘事件校准的是「这个人这年过得好不好」；共振分的权重校准需要的是
# 「这两人这年顺不顺」。两者是**两套预测源、两套真相**，故从存储到接口全部独立：
# 单盘主键是「盘 × 年 × 领域」，关系事件没有领域切片（同一年两人可以一个升职
# 一个生病，但"我们俩这一年"只有一个答案），硬塞一张表会让"哪些列该为空"变成隐性契约。

# 合盘回测比单盘更贵（每对要跑一趟双盘年表），而关系事件天然比个人事件少，
# 故对数上限比单盘的盘数上限更紧。
MAX_BACKTEST_PAIRS = 10


class KlinePairEventRequest(BaseModel):
    """一对人「某年顺不顺」的标注。

    `polarity` 是**关系**的吉凶（1=顺 / 0=平 / -1=逆），不是某一方的个人运势。
    `relation` 只是复盘切片维度（按"夫妻""亲子"分组看命中率差异），不参与预测 ——
    引擎对任何一对都算同一套四项 term，关系类型只影响这分数该怎么读。
    """

    birth_time_a: str = Field(..., description="甲方出生时间，与 /kline 同一入口")
    gender_a: str
    birth_time_b: str = Field(..., description="乙方出生时间")
    gender_b: str
    sect: int = 2
    yun_sect: int = 1
    longitude_a: float | None = None
    longitude_b: float | None = None
    ganzhi_year: int | None = Field(default=None, description="命理年（立春换岁）")
    event_date: str = Field(default="", description="原始公历日期 YYYY-MM-DD，用于推导命理年")
    polarity: int = Field(..., description="1=顺 / 0=平 / -1=逆（关系本身，不是某一方）")
    relation: str = Field(default="", description="夫妻/恋人/亲子/同事/朋友/合作/其他")
    source: str = Field(default="", description="来源：自述 / 传记 / 案例库 / 人工")
    note: str = Field(default="", max_length=MAX_EVENT_NOTE)


@router.post("/kline/pair-events")
async def submit_kline_pair_event(body: KlinePairEventRequest):
    """录一条关系事件。**只写不读，不影响任何分数。**"""
    from app.db.chart_store import (
        KLINE_EVENT_YEAR_MAX,
        KLINE_EVENT_YEAR_MIN,
        KLINE_POLARITIES,
        KLINE_RELATIONS,
    )

    if body.polarity not in KLINE_POLARITIES:
        raise HTTPException(status_code=400, detail="polarity 只能取 1（顺）/ 0（平）/ -1（逆）")
    if body.relation and body.relation not in KLINE_RELATIONS:
        raise HTTPException(
            status_code=400, detail=f"relation 需为 {'/'.join(KLINE_RELATIONS)} 之一或留空"
        )
    ganzhi_year = _resolve_ganzhi_year(body.ganzhi_year, body.event_date)
    if not KLINE_EVENT_YEAR_MIN <= ganzhi_year <= KLINE_EVENT_YEAR_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"ganzhi_year 需在 {KLINE_EVENT_YEAR_MIN}-{KLINE_EVENT_YEAR_MAX} 之间",
        )
    if body.sect not in (1, 2):
        raise HTTPException(status_code=400, detail="sect 需为 1 或 2")

    # 两侧都起盘校验：任一侧出生信息非法，这一对就没法回测。
    # 同时这也是"同一张盘不构成合盘"的兜底 —— 真正的判定在存储层（按 chart_hash）。
    try:
        await asyncio.to_thread(
            _build_chart, body.birth_time_a, body.gender_a, body.sect, body.yun_sect, body.longitude_a
        )
        await asyncio.to_thread(
            _build_chart, body.birth_time_b, body.gender_b, body.sect, body.yun_sect, body.longitude_b
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        eid = await repo.add_kline_pair_event(
            body.birth_time_a,
            body.gender_a,
            body.birth_time_b,
            body.gender_b,
            ganzhi_year,
            body.polarity,
            sect=body.sect,
            yun_sect=body.yun_sect,
            longitude_a=body.longitude_a,
            longitude_b=body.longitude_b,
            event_date=body.event_date or None,
            relation=body.relation,
            source=body.source,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "id": eid, "ganzhiYear": ganzhi_year}


@router.get("/kline/pair-events")
async def list_kline_pair_events_endpoint(
    birth_time_a: str = "",
    gender_a: str = "",
    birth_time_b: str = "",
    gender_b: str = "",
    ganzhi_year: int | None = None,
    limit: int = 500,
):
    """列关系事件。四侧生辰都给时按「这一对」过滤，否则列最近的。"""
    if not 0 < limit <= MAX_BACKTEST_EVENTS:
        raise HTTPException(status_code=400, detail=f"limit 需在 1-{MAX_BACKTEST_EVENTS} 之间")
    items = await repo.list_kline_pair_events(
        birth_time_a, gender_a, birth_time_b, gender_b, ganzhi_year, limit
    )
    return {"items": items, "count": len(items)}


@router.get("/kline/pair-events/stats")
async def kline_pair_event_stats_endpoint():
    """关系事件总览：总量 / 顺逆分布 / 关系类型分布 / 对数。回测前先看它。"""
    return await repo.kline_pair_event_stats()


@router.delete("/kline/pair-events/{event_id}")
async def delete_kline_pair_event_endpoint(event_id: str):
    """删一条录错的关系事件。"""
    ok = await repo.delete_kline_pair_event(event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="未找到该关系事件")
    return {"ok": True}


# ---------------- 回测 ----------------

def _backtest_pairs(events: list[dict], *, max_charts: int | None = None) -> tuple[list[tuple], int]:
    """按「同一张盘」把事件分组并建盘。返回 ([(chart, events)], 被忽略的盘数)。

    分组键含 sect/yun_sect/longitude：同一个人换流派就是另一张盘，
    混在一起会让"预测"与"标注"对不上号。

    先按事件条数截断再建盘（不是建完再丢）：建盘约 0.35s/张，
    样本最少的盘对命中率的贡献也最小，先丢它们最划算。
    """
    groups: dict[tuple, list[dict]] = {}
    for e in events:
        key = (
            e.get("birth_time", ""),
            e.get("gender", ""),
            e.get("sect", 2),
            e.get("yun_sect", 1),
            e.get("longitude"),
        )
        groups.setdefault(key, []).append(e)

    items = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    truncated = 0
    if max_charts is not None and len(items) > max_charts:
        truncated = len(items) - max_charts
        items = items[:max_charts]
    return [(_build_chart(*key), rows) for key, rows in items], truncated


@router.get("/kline/backtest")
async def run_kline_backtest_endpoint(
    birth_time: str = "",
    gender: str = "",
    dimension: str = kline_backtest.DIMENSION_AUTO,
    predictor: str = kline_backtest.PREDICTOR_CLOSE,
    min_samples: int = kline_backtest.DEFAULT_MIN_SAMPLES,
):
    """用事件标注回测：命中率 / 随机基线 / lift / 置信区间。

    `birth_time` 为空则把库里所有盘一起回测（校准脚本的用法）；
    注意"吉"始终是**该盘自己的高位**，不是跨盘绝对刻度。
    """
    if dimension != kline_backtest.DIMENSION_AUTO and dimension not in fortune_score.DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"dimension 需为 {kline_backtest.DIMENSION_AUTO}/{'/'.join(fortune_score.DIMENSIONS)} 之一",
        )
    if predictor not in kline_backtest.PREDICTORS:
        raise HTTPException(
            status_code=400, detail=f"predictor 需为 {'/'.join(kline_backtest.PREDICTORS)} 之一"
        )
    if not 0 < min_samples <= MAX_BACKTEST_EVENTS:
        raise HTTPException(status_code=400, detail=f"min_samples 需在 1-{MAX_BACKTEST_EVENTS} 之间")

    events = await repo.list_kline_events(birth_time, gender, None, "", MAX_BACKTEST_EVENTS)
    if not events:
        return {
            "events": {"total": 0, "used": 0, "unmatched": 0, "invalid": 0, "duplicate": 0},
            "summary": {"samples": 0, "ok": False, "hitRate": None},
            "ageSpan": kline_backtest.AGE_SPAN,
            "spanFrom": None,
            "spanTo": None,
            "warnings": ["事件库为空：先用 POST /kline/events 录入真实事件标注。"],
        }

    def _run() -> dict:
        pairs, truncated = _backtest_pairs(events, max_charts=MAX_BACKTEST_CHARTS)
        result = kline_backtest.run_backtest(
            pairs, dimension=dimension, predictor=predictor, min_samples=min_samples
        )
        if truncated:
            result["warnings"].append(
                f"命盘过多，已按事件条数取前 {MAX_BACKTEST_CHARTS} 张（忽略 {truncated} 张）。"
            )
        return result

    try:
        return await asyncio.to_thread(_run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _backtest_pair_groups(
    events: list[dict], *, max_pairs: int | None = None
) -> tuple[list[tuple], int]:
    """按「同一对人」把关系事件分组并建盘。返回 ([(甲盘, 乙盘, events)], 被忽略的对数)。

    分组键用 `kline_pair_key`（两侧 chart_hash 排序后拼接）而不是原始四侧生辰：
    录入时谁填在甲、谁填在乙是随手的事，同一对倒过来录一次就是两组不同的事件流，
    分开建盘会让本该合并的样本各自不足。选代表时按 chart_hash 排序决定甲乙顺序，
    这样同一对每次建出的两张盘顺序一致 —— 共振分对称，顺序不影响结果，但要可复现。

    `sect`/`yun_sect` 进分组键：`_chart_hash` 只认生辰与性别，
    同一个人换流派是另一张盘，混在一起会让"预测"与"标注"对不上号。

    截断同单盘口径：先按事件条数截断再建盘（建一对约 0.7s），先丢样本最少的对。
    """
    from app.db.chart_store import kline_pair_key

    groups: dict[tuple, list[dict]] = {}
    for e in events:
        a = (e.get("birthTimeA", ""), e.get("genderA", ""))
        b = (e.get("birthTimeB", ""), e.get("genderB", ""))
        key = (
            kline_pair_key(a[0], a[1], b[0], b[1]),
            e.get("sect", 2),
            e.get("yunSect", 1),
        )
        groups.setdefault(key, []).append(e)

    items = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    truncated = 0
    if max_pairs is not None and len(items) > max_pairs:
        truncated = len(items) - max_pairs
        items = items[:max_pairs]

    out: list[tuple] = []
    for (_, sect, yun_sect), rows in items:
        e = rows[0]
        a = (e.get("birthTimeA", ""), e.get("genderA", ""), e.get("longitudeA"))
        b = (e.get("birthTimeB", ""), e.get("genderB", ""), e.get("longitudeB"))
        # 定序：chart_hash 小的一侧固定当甲，避免同一对在两次回测里甲乙互换
        if _pair_side_key(a) > _pair_side_key(b):
            a, b = b, a
        out.append(
            (
                _build_chart(a[0], a[1], sect, yun_sect, a[2]),
                _build_chart(b[0], b[1], sect, yun_sect, b[2]),
                rows,
            )
        )
    return out, truncated


def _pair_side_key(side: tuple) -> str:
    """定序用的稳定键：与 `chart_store._chart_hash` 同口径，但避免跨层引私有函数。"""
    from hashlib import sha256

    return sha256(f"{side[0]}|{side[1]}".encode()).hexdigest()[:16]


@router.get("/kline/pair-backtest")
async def run_kline_pair_backtest_endpoint(
    birth_time_a: str = "",
    gender_a: str = "",
    birth_time_b: str = "",
    gender_b: str = "",
    dimension: str = fortune_score.DIM_COMPREHENSIVE,
    min_samples: int = kline_backtest.DEFAULT_MIN_SAMPLES,
):
    """用关系事件回测共振线：命中率 / 随机基线 / lift / 逐项诊断。

    这是**共振权重唯一的校准数据源**：单盘事件只能校准单盘打分口径，
    "这两人某年如何"才是共振分该对得上的真相。

    `birth_time_a` 为空则把库里所有对一起回测；
    没有 `predictor` 参数 —— 合盘只有一个预测源（共振分），给了也没别的可换。
    """
    if dimension not in fortune_score.DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"dimension 需为 {'/'.join(fortune_score.DIMENSIONS)} 之一",
        )
    if not 0 < min_samples <= MAX_BACKTEST_EVENTS:
        raise HTTPException(status_code=400, detail=f"min_samples 需在 1-{MAX_BACKTEST_EVENTS} 之间")

    events = await repo.list_kline_pair_events(
        birth_time_a, gender_a, birth_time_b, gender_b, None, MAX_BACKTEST_EVENTS
    )
    if not events:
        return {
            "events": {"total": 0, "used": 0, "unmatched": 0, "invalid": 0, "duplicate": 0},
            "summary": {"samples": 0, "ok": False, "hitRate": None},
            "ageSpan": kline_backtest.AGE_SPAN,
            "spanFrom": None,
            "spanTo": None,
            "warnings": ["关系事件库为空：先用 POST /kline/pair-events 录入「这两人某年」的标注。"],
        }

    def _run() -> dict:
        pairs, truncated = _backtest_pair_groups(events, max_pairs=MAX_BACKTEST_PAIRS)
        result = kline_backtest.run_pair_backtest(
            pairs, dimension=dimension, min_samples=min_samples
        )
        if truncated:
            result["warnings"].append(
                f"配对过多，已按事件条数取前 {MAX_BACKTEST_PAIRS} 对（忽略 {truncated} 对）。"
            )
        return result

    try:
        return await asyncio.to_thread(_run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
