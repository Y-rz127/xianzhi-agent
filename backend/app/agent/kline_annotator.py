"""命理 K 线的 LLM 批注层：把已经算好的分数翻成人话。

定位与三条红线
--------------
K 线的数值由 `domain.fortune_score` 确定性算出，可黄金快照回归。本模块**只做解读**，
因此有三条不能破的约束：

1. **不参与打分**。批注晚于 `build_kline`，读的是现成结果；
   改这里的任何文案/模型/温度，K 线数值一个都不会变
   （守卫见 `tests/test_kline_annotation.py::test_annotation_does_not_touch_scores`）。
2. **必须过 `check_facts`**。批注不得编造命盘里没有的十神/神煞/干支。
   校验不过先修一次；仍不过就**不返回文本**——宁可没有批注，也不显示错的。
3. **不得改数**。分数、干支、关系串由模板注入，模型只解释；
   复述时改了数字会被第 2 条的正则层直接拦下。

粒度（与前端约定）
------------------
- `overview`：当前大运 + 全期最高/最低年份 —— 进页面即给，按盘缓存。
- `year`：指定某一流年 —— 点了才给，按年缓存。

之所以不按年预先全量生成（75 年 = 75 次调用）：批注是**按需阅读**的产物，
预先算完既费钱又没人看；而首屏没有解读体验又太干。故取「概览先给 + 年份按需」。
"""

from __future__ import annotations

import datetime
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.workflow.workflow_messages import compact_facts
from app.agent.workflow.workflow_models import QuestionIntent
from app.core.logger import log

SCOPE_OVERVIEW = "overview"
SCOPE_YEAR = "year"
SCOPES = (SCOPE_OVERVIEW, SCOPE_YEAR)

# 批注是"读一段话"，不是"写一份报告"：单次调用给 3 分钟足够，
# 超时按失败处理（报告那种 300s 的长调用是另一回事）。
ANNOTATION_TIMEOUT = 120.0

# 维度 → 对话领域的映射。批注要接地到某一路断法上，才能复用领域简报/规则检索，
# 而不是让模型自由发挥。comprehensive 没有对应领域，落到"大运流年"这条最接近的。
_DIMENSION_DOMAIN = {
    "comprehensive": "liunian",
    "career": "career",
    "wealth": "wealth",
    "love": "love",
    "health": "health",
}

SYSTEM_PROMPT = """你是八字命理分析师，负责解读一张**已经算好的**运势 K 线图。

图上的数字由确定性规则算出（大运权重 0.5、流年 0.3、流月 0.2，喜忌方向来自原局），
**不是**你的判断结果。你的任务是解释这些数字为什么是这样，以及它对命主意味着什么。

必须遵守：
1. 只解读、不改数。分数、干支、关系一律照抄给定事实，禁止另行计算或"修正"。
2. 禁止编造。命盘事实里没有的十神、神煞、干支，一个字都不要写。
3. 提到年份时，必须同时核对该年流年干支与所在大运，不得张冠李戴。
4. 不做绝对化断言（"必然""一定会"），也不给医疗、投资、法律等越界建议；
   健康维度只谈体质倾向与调养方向，不诊断疾病。
5. 用 200-400 字讲清楚，说人话，不要复述分数明细表。
6. 三个量各叫各的名字，别都用"波动"：**「年内变化合计」**是年内十二个节气月分数的变化总和；
   **「关系波动量」**是岁运合冲刑害对振幅的放大/压缩（合会压缩、冲刑害破放大），
   它不等于高低差，也不是实体长度；**实际高低差**是「高 − 低」。"""


def _candle_brief(candle: dict[str, Any]) -> str:
    """单根年 K 线 → 一句事实。分数照抄，不做任何再加工。

    **三个易混量必须各叫各的名字**（都曾被我含糊地叫过"波动"）：
    - `volume`：年内十二个节气月分数的变化总和 + 年初跳空；
    - `volatility`：**关系波动量**，合冲刑害对振幅的放大/压缩之和
      （`REL_VOL` 加总），既不是高低差、也不是影线本身；
    - 实际高低差：`high - low`，由 12 月极值 ± 关系波动量得出。
    早期只写"年内波动 {volume}"，模型于是拿 volume 当"波动"讲，
    而前端另有一个标着"波动"的 `volatility` —— 读者对不上号。
    """
    trend = "涨" if candle.get("isUp") else "跌"
    rel = "、".join(candle.get("relations") or []) or "无"
    return (
        f"{candle['year']} 年（虚岁 {candle['age']}）流年 {candle['ganzhi']}，"
        f"所在大运 {candle.get('dayun') or '童限期（未起运）'}；"
        f"开 {candle['open']} / 收 {candle['close']} / 高 {candle['high']} / 低 {candle['low']}，"
        f"{trend}；年内变化合计 {candle['volume']}，"
        f"关系波动量 {candle['volatility']}（合会压缩、冲刑害破放大振幅）；"
        f"岁运关系：{rel}"
    )


def _band_brief(band: dict[str, Any]) -> str:
    return (
        f"第 {band['index']} 步大运 {band['ganzhi']}"
        f"（{band['startYear']}-{band['endYear']} 年，虚岁 {band['startAge']}-{band['endAge']}）"
        f"，大运天干十神：{band.get('shishenGan') or '—'}"
    )


def _current_band(dayun_bands: list[dict[str, Any]], anchor_year: int) -> dict[str, Any] | None:
    for band in dayun_bands:
        if band["startYear"] <= anchor_year <= band["endYear"]:
            return band
    return None


def select_focus(
    payload: dict[str, Any],
    scope: str,
    year: int | None = None,
    anchor_year: int | None = None,
) -> dict[str, Any]:
    """挑出这次批注要讲的对象。纯函数，同输入同输出。

    `anchor_year` 是「当下」的年份（决定 overview 讲哪一步大运）。显式传入而非读系统时间，
    是为了可测、且缓存键能跟着它走。
    """
    candles: list[dict[str, Any]] = payload.get("candles") or []
    bands: list[dict[str, Any]] = payload.get("dayunBands") or []
    if not candles:
        return {"scope": scope, "lines": [], "years": []}

    if scope == SCOPE_OVERVIEW:
        anchor = anchor_year if anchor_year is not None else candles[-1]["year"]
        band = _current_band(bands, anchor)
        peak = max(candles, key=lambda c: c["close"])
        trough = min(candles, key=lambda c: c["close"])
        # 极值同一年时不要重复讲两遍
        lines = [f"全期覆盖 {candles[0]['year']}-{candles[-1]['year']} 年，共 {len(candles)} 根年 K 线。"]
        if band:
            lines.append(f"当前大运（{anchor} 年所在）：" + _band_brief(band))
        else:
            lines.append(f"{anchor} 年尚未起运（童限期）。")
        lines.append("全期最高分：" + _candle_brief(peak))
        if trough["year"] != peak["year"]:
            lines.append("全期最低分：" + _candle_brief(trough))
        return {
            "scope": scope,
            "anchorYear": anchor,
            "years": sorted({peak["year"], trough["year"], anchor}),
            "currentBand": band,
            "lines": lines,
        }

    target = next((c for c in candles if c["year"] == year), None)
    if target is None:
        return {"scope": scope, "year": year, "lines": [], "years": [], "missing": True}
    band = _current_band(bands, year)
    lines = [_candle_brief(target)]
    if band:
        lines.append("所处大运：" + _band_brief(band))
    return {"scope": scope, "year": year, "anchorYear": year, "years": [year], "lines": lines}


def _intent(dimension: str, payload: dict[str, Any]) -> QuestionIntent:
    """维度 → 对话意图。批注接地到某一路断法上，复用其领域简报而不是自由发挥。"""
    return QuestionIntent(
        domain=_DIMENSION_DOMAIN.get(dimension, "liunian"),
        label=(payload.get("meta") or {}).get("dimensionLabel") or "综合",
        needs_chart=True,
    )


def build_prompt(
    chart: Any,
    payload: dict[str, Any],
    focus: dict[str, Any],
    dimension: str = "comprehensive",
    facts: str | None = None,
) -> list[Any]:
    """组装批注 prompt。命盘事实走 `compact_facts`，与对话链路同一口径。

    `facts` 可由调用方传入**同一份**文本：`check_facts` 要靠它知道"模型看到了什么"，
    两处各算一遍一旦分叉，就会出现"模型没见过的神煞被判成编造"的误杀。
    """
    meta = payload.get("meta") or {}
    favor = payload.get("favor") or {}
    if facts is None:
        facts = compact_facts(chart, _intent(dimension, payload))

    favor_lines = "、".join(f"{k} {v:+.4g}" for k, v in (favor.get("favor") or {}).items())
    human = (
        f"【命盘事实】\n{facts}\n\n"
        f"【喜忌方向（原局，正=喜 负=忌）】\n{favor_lines}\n"
        f"最喜 {favor.get('mostFavored') or '—'}、最忌 {favor.get('mostOpposed') or '—'}"
    )
    if favor.get("ailmentNote"):
        human += f"\n定喜忌的依据：{favor['ailmentNote']}"
    human += (
        f"\n\n【本次解读维度】\n{meta.get('dimensionLabel') or '综合'}"
        f"（{meta.get('dimensionNote') or ''}）"
        f"\n口径说明：{meta.get('note') or ''}"
        f"\n\n【要解读的对象】\n" + "\n".join(focus.get("lines") or [])
    )
    human += (
        "\n\n【输出要求】\n"
        "用 200-400 字解读这段运势：分数的高低起伏对应什么、"
        "喜忌之神在岁运里到位与否、以及在对应维度上该注意什么。"
        "分数与干支只能照抄上述事实，不得改写；不要输出表格或分数清单。"
    )
    return [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=human)]


def _repair_prompt(original: str, issues: list[str]) -> list[Any]:
    """校验不过时的修复轮：把问题原样回给模型，要求只改事实错误。"""
    issue_lines = "\n".join(f"- {i}" for i in issues)
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "上面那段批注经系统排盘校验后发现以下**事实性错误**：\n"
                f"{issue_lines}\n\n"
                "请重写这段批注：只修正上述事实错误，其余内容与篇幅保持原样，"
                "不要新增任何命盘事实里没有的十神、神煞或干支。\n\n"
                f"【原批注】\n{original}"
            )
        ),
    ]


def annotate(
    chat_model: BaseChatModel | None,
    chart: Any,
    payload: dict[str, Any],
    *,
    scope: str = SCOPE_OVERVIEW,
    year: int | None = None,
    dimension: str = "comprehensive",
    anchor_year: int | None = None,
) -> dict[str, Any]:
    """生成一段批注。返回 dict，**不抛业务异常**（调用方按 `ok`/`text` 处理）。

    校验不过时返回空文本而非原始文本：批注是给人看的结论，
    显示一段被证实有错的话，比不显示更糟。
    """
    if chat_model is None:
        return {"ok": False, "text": "", "factsOk": False, "issues": ["LLM 未就绪"], "scope": scope}

    focus = select_focus(payload, scope, year, anchor_year=anchor_year)
    if not focus.get("lines"):
        reason = f"命盘 K 线中不存在 {year} 年" if scope == SCOPE_YEAR else "K 线为空"
        return {"ok": False, "text": "", "factsOk": False, "issues": [reason], "scope": scope,
                "year": year, "anchorYear": focus.get("anchorYear")}

    facts = compact_facts(chart, _intent(dimension, payload))
    messages = build_prompt(chart, payload, focus, dimension, facts=facts)
    text = _invoke(chat_model, messages)
    check = _check(text, chart, facts)
    source = "first"

    if not check["ok"] and text:
        log.info("[K线批注] 首轮校验未通过（{} 项），进入修复", len(check["issues"]))
        repaired = _invoke(chat_model, _repair_prompt(text, check["issues"]))
        if repaired:
            recheck = _check(repaired, chart, facts)
            if recheck["ok"]:
                text, check, source = repaired, recheck, "repair"
            else:
                # 修复也没过：宁可空着，也不给一段已知有错的解读
                log.warning("[K线批注] 修复后仍未通过：{}", recheck["issues"])
                return {
                    "ok": False,
                    "text": "",
                    "factsOk": False,
                    "issues": recheck["issues"],
                    "scope": scope,
                    "year": focus.get("year"),
                    "anchorYear": focus.get("anchorYear"),
                    "source": "repair_failed",
                }

    return {
        "ok": bool(text) and check["ok"],
        "text": text,
        "factsOk": check["ok"],
        "issues": check["issues"],
        "scope": scope,
        "year": focus.get("year"),
        "anchorYear": focus.get("anchorYear"),
        "years": focus.get("years") or [],
        "source": source,
    }


def _invoke(chat_model: BaseChatModel, messages: list[Any]) -> str:
    """单次模型调用。批注失败不该把整个接口拖成 500，故这里吞掉异常返回空串。"""
    try:
        response = chat_model.bind(timeout=ANNOTATION_TIMEOUT).invoke(messages)
    except Exception as e:  # noqa: BLE001 - 上游超时/限流/网络都可能，统一降级
        log.warning("[K线批注] 模型调用失败：{}", e)
        return ""
    content = getattr(response, "content", "") or ""
    return content.strip() if isinstance(content, str) else ""


def _check(text: str, chart: Any, facts: str) -> dict[str, Any]:
    """走 `check_facts` 的正则层：不联网、纯函数，可单测。"""
    from app.agent.workflow.fact_check import check_facts

    if not text:
        return {"ok": False, "issues": ["模型未返回内容"]}
    result = check_facts(text, chart, needs_chart=True, facts_text=facts)
    return {"ok": bool(result.ok), "issues": list(result.issues)}


def cache_tool(scope: str, dimension: str, year: int | None, anchor_year: int | None) -> str:
    """批注缓存键后缀。

    带上 anchor_year：`overview` 的「当前大运」随年份变，
    不带它的话跨年后会一直返回旧年份算出的那段。
    """
    return f"kline_anno:{scope}:{dimension}:{year if year is not None else '-'}:{anchor_year or '-'}"


def today_year() -> int:
    return datetime.date.today().year
