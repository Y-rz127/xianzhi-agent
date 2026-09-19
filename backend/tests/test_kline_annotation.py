"""命理 K 线批注层测试：接地、校验门、缓存、以及「批注不许碰分数」。

批注是整个 K 线里唯一引入大模型的环节，因此这里测的不是"文案好不好"，
而是三条红线的**结构性保证**：

1. 打分隔离 —— 批注跑完，`build_kline`/`favor_vector` 的输出必须逐位不变；
2. 事实门 —— 编造命盘没有的神煞，首轮被拦、修复轮再拦，最终**不返回文本**；
3. 接地 —— prompt 必须带上确定性数值（开收高低/干支/关系/喜忌/病因），
   否则模型只能靠编。

模型调用一律用 `FakeModel` 打桩：本文件不联网、不花钱、结果确定。
"""

from __future__ import annotations

import asyncio
import datetime
from functools import lru_cache
from types import SimpleNamespace

from app.agent import kline_annotator as A
from app.agent.workflow.fact_check import SHENSHA_NAMES
from app.agent.workflow.workflow_models import DOMAIN_LABELS
from app.api import xianzhi_kline
from app.domain import fortune_score as FS
from app.domain.chart_builder import build_bazi_chart

BIRTH = "2004-06-22 08:00"
GENDER = "男"
ANCHOR = 2026

# 一段能通过事实校验的干净批注（只提到盘面确有与自己行文一致的内容）
CLEAN = "壬水日主生于午月，原局金重为病；行金运时分低，行水运时得力。"


# ---------------- 桩与夹具 ----------------


class FakeModel:
    """假模型：按序吐出预设回复，并留下收到的 prompt 供断言接地。"""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.prompts: list[list] = []

    def bind(self, **_kwargs):
        return self

    def invoke(self, messages):
        self.prompts.append(messages)
        text = self.replies.pop(0) if self.replies else ""
        return SimpleNamespace(content=text)


@lru_cache(maxsize=1)
def chart():
    return build_bazi_chart(
        BIRTH, GENDER, today=datetime.date(2026, 9, 15), liunian_start_year=2026
    )


@lru_cache(maxsize=1)
def payload() -> dict:
    """走接口自己的载荷构造：批注要吃的就是前端画图的那份数据。"""
    return xianzhi_kline._compute_kline_payload(
        BIRTH, GENDER, 2, 1, None, xianzhi_kline.MAX_AGE_DEFAULT, False, "comprehensive"
    )


def _absent_shensha() -> str:
    """从名册里挑一个该盘**确实没有**的神煞，用来构造"编造"场景。

    动态挑选而非写死：写死会在神煞口径调整后变成"其实盘里有"，测试就白测了。
    """
    from app.agent.workflow.workflow_messages import compact_facts
    from app.agent.workflow.workflow_models import QuestionIntent

    facts = compact_facts(chart(), QuestionIntent(domain="liunian", label="综合", needs_chart=True))
    return next(n for n in SHENSHA_NAMES if n not in facts)


# ---------------- focus 选择：纯函数、可确定 ----------------


def test_select_focus_overview_is_deterministic() -> None:
    first = A.select_focus(payload(), A.SCOPE_OVERVIEW, anchor_year=ANCHOR)
    second = A.select_focus(payload(), A.SCOPE_OVERVIEW, anchor_year=ANCHOR)
    assert first == second


def test_select_focus_overview_covers_band_peak_and_trough() -> None:
    """概览必须交代「当前大运 + 全期最好/最差」——这点信息量是首屏批注的下限。"""
    focus = A.select_focus(payload(), A.SCOPE_OVERVIEW, anchor_year=ANCHOR)
    text = "\n".join(focus["lines"])
    candles = payload()["candles"]
    peak = max(candles, key=lambda c: c["close"])
    trough = min(candles, key=lambda c: c["close"])

    assert focus["currentBand"] is not None
    assert focus["currentBand"]["startYear"] <= ANCHOR <= focus["currentBand"]["endYear"]
    assert str(peak["year"]) in text and str(trough["year"]) in text
    assert str(peak["close"]) in text and str(trough["close"]) in text
    assert focus["anchorYear"] == ANCHOR


def test_select_focus_overview_does_not_repeat_single_extreme() -> None:
    """最高最低落在同一年时只讲一次，否则批注会出现两段一模一样的话。"""
    candles = [
        {"year": 2000, "age": 1, "ganzhi": "庚辰", "dayun": "", "open": 50.0, "close": 50.0,
         "high": 55.0, "low": 45.0, "volume": 1.0, "volatility": 0.5, "relations": [], "isUp": True},
    ]
    focus = A.select_focus({"candles": candles, "dayunBands": []}, A.SCOPE_OVERVIEW, anchor_year=2000)
    assert sum(1 for line in focus["lines"] if "最高分" in line or "最低分" in line) == 1


def test_select_focus_year_targets_exact_candle_and_band() -> None:
    focus = A.select_focus(payload(), A.SCOPE_YEAR, year=2015, anchor_year=ANCHOR)
    candle = next(c for c in payload()["candles"] if c["year"] == 2015)
    text = "\n".join(focus["lines"])
    assert focus["year"] == 2015
    assert candle["ganzhi"] in text
    assert str(candle["open"]) in text and str(candle["close"]) in text
    band = focus and next(
        b for b in payload()["dayunBands"] if b["startYear"] <= 2015 <= b["endYear"]
    )
    assert band["ganzhi"] in text


def test_select_focus_year_outside_range_is_empty_not_crash() -> None:
    focus = A.select_focus(payload(), A.SCOPE_YEAR, year=1800, anchor_year=ANCHOR)
    assert focus["lines"] == [] and focus["missing"] is True


def test_select_focus_handles_empty_payload() -> None:
    focus = A.select_focus({"candles": [], "dayunBands": []}, A.SCOPE_OVERVIEW, anchor_year=ANCHOR)
    assert focus["lines"] == []


# ---------------- prompt 接地 ----------------


def test_prompt_carries_every_deterministic_number() -> None:
    """prompt 里必须出现盘面实测值：分数、干支、关系、喜忌、病因。

    少任一项，模型都会自己编一个 —— 这是"批注与图不一致"的根源。
    """
    p = payload()
    focus = A.select_focus(p, A.SCOPE_OVERVIEW, anchor_year=ANCHOR)
    prompt = A.build_prompt(chart(), p, focus, "comprehensive")
    text = "\n".join(m.content for m in prompt)

    favor = p["favor"]
    assert favor["mostFavored"] in text and favor["mostOpposed"] in text
    assert favor["ailmentNote"] in text, "病因必须进 prompt，否则解释不了喜忌为何这样定"
    for wx, val in favor["favor"].items():
        assert wx in text
        assert f"{val:+.4g}" in text, f"{wx} 的喜忌系数未接地"
    peak = max(p["candles"], key=lambda c: c["close"])
    assert peak["ganzhi"] in text and str(peak["open"]) in text
    # 至少有一年的岁运关系串进了 prompt（关系是"冲主波动"这类解读的依据）
    with_rel = next(c for c in p["candles"] if c["relations"])
    assert with_rel["relations"][0] in text
    assert "不得改写" in text, "缺少「不许改数」的硬约束"


def test_prompt_disambiguates_the_three_amplitude_fields() -> None:
    """`volume` / `volatility` / 高低差 三者不得都叫"波动"。

    事故：批注写「40.1 的波动」（那是 volume），而前端详情卡另有一个标着"波动"的
    `volatility`＝2.8（关系波动量）——两个数都对，读者却会以为算错了。
    故 prompt 必须同时给出三个量、且用三个不同的名字。
    """
    p = payload()
    focus = A.select_focus(p, A.SCOPE_YEAR, year=2009, anchor_year=ANCHOR)
    text = "\n".join(m.content for m in A.build_prompt(chart(), p, focus))
    candle = next(c for c in p["candles"] if c["year"] == 2009)
    assert "年内变化合计" in text and "关系波动量" in text
    assert str(candle["volume"]) in text and str(candle["volatility"]) in text
    # 阈值分隔：三者数值不同，若被合并成一个词，读者对不上号
    assert candle["volume"] != candle["volatility"]
    assert candle["high"] - candle["low"] != candle["volatility"]
    assert "不能" in A.SYSTEM_PROMPT or "别都用" in A.SYSTEM_PROMPT


def test_prompt_maps_every_dimension_to_a_real_domain() -> None:
    """批注要接地到对话领域（复用其规则检索），映射目标必须都是合法领域。"""
    for dim in FS.DIMENSIONS:
        assert A._DIMENSION_DOMAIN[dim] in DOMAIN_LABELS, f"{dim} 映射到未知领域"


def test_prompt_declares_scores_are_not_llm_output() -> None:
    """系统提示必须说清「数字是规则算的、不是你判的」，否则模型会去"修正"分数。"""
    p = payload()
    focus = A.select_focus(p, A.SCOPE_OVERVIEW, anchor_year=ANCHOR)
    system = A.build_prompt(chart(), p, focus)[0].content
    assert "确定性" in system and "不改数" in system


# ---------------- 事实校验门 ----------------


def test_annotation_returns_text_when_check_passes() -> None:
    result = A.annotate(FakeModel(CLEAN), chart(), payload(), anchor_year=ANCHOR)
    assert result["ok"] is True and result["factsOk"] is True
    assert result["text"] == CLEAN
    assert result["source"] == "first"
    assert result["anchorYear"] == ANCHOR


def test_annotation_repairs_when_first_round_fails() -> None:
    """首轮编造 → 修复轮改对 → 采用修复稿，且标 source=repair。"""
    bad = f"你命带{_absent_shensha()}，故少年得志。"
    model = FakeModel(bad, CLEAN)
    result = A.annotate(model, chart(), payload(), anchor_year=ANCHOR)
    assert result["ok"] is True and result["source"] == "repair"
    assert result["text"] == CLEAN
    assert len(model.prompts) == 2, "应恰好调用两次（首轮 + 修复轮）"


def test_annotation_hides_text_when_both_rounds_fail() -> None:
    """两轮都编造 → **不返回文本**。显示一段已知有错的话比不显示更糟。"""
    bad = f"你命带{_absent_shensha()}，故少年得志。"
    result = A.annotate(FakeModel(bad, bad), chart(), payload(), anchor_year=ANCHOR)
    assert result["ok"] is False and result["factsOk"] is False
    assert result["text"] == "", "校验不过时必须清空文本"
    assert result["issues"], "要带上具体问题，便于排查与前端提示"
    assert result["source"] == "repair_failed"


def test_annotation_without_model_is_not_ok() -> None:
    result = A.annotate(None, chart(), payload(), anchor_year=ANCHOR)
    assert result["ok"] is False and result["text"] == ""


def test_annotation_survives_model_exception() -> None:
    """上游超时/限流不能让批注抛出去 —— 它只是文字的增强，不该拖垮接口。"""

    class BrokenModel(FakeModel):
        def invoke(self, messages):
            raise RuntimeError("upstream timeout")

    result = A.annotate(BrokenModel(), chart(), payload(), anchor_year=ANCHOR)
    assert result["ok"] is False and result["text"] == ""
    assert result["issues"]


def test_annotation_year_scope_uses_that_year() -> None:
    result = A.annotate(
        FakeModel(CLEAN), chart(), payload(), scope=A.SCOPE_YEAR, year=2015, anchor_year=ANCHOR
    )
    assert result["ok"] is True
    assert result["year"] == 2015 and result["anchorYear"] == 2015
    assert result["years"] == [2015]


def test_annotation_reports_missing_year() -> None:
    result = A.annotate(
        FakeModel(CLEAN), chart(), payload(), scope=A.SCOPE_YEAR, year=1800, anchor_year=ANCHOR
    )
    assert result["ok"] is False and result["text"] == ""
    assert any("1800" in i for i in result["issues"])


# ---------------- 红线：打分隔离 ----------------


def test_annotation_does_not_touch_scores() -> None:
    """批注跑完，K 线与喜忌必须逐位不变。

    打分在 `domain.fortune_score`（纯确定性、有黄金快照），批注在 agent 层读它的结果。
    这条守卫一旦变红，说明有人在批注里回写了解析结果 —— 那会让曲线随模型抽风而漂移。
    """
    ch = chart()
    before = FS.build_kline(ch, max_age=80)
    before_favor = FS.chart_favor_summary(ch)
    A.annotate(FakeModel(CLEAN), ch, payload(), anchor_year=ANCHOR)
    A.annotate(FakeModel(f"编造{_absent_shensha()}"), ch, payload(), anchor_year=ANCHOR)
    assert FS.build_kline(ch, max_age=80) == before
    assert FS.chart_favor_summary(ch) == before_favor


def test_annotation_does_not_mutate_payload() -> None:
    """批注不得就地改载荷。

    `annotate` 拿到的是**前端画图用的同一份 dict**（接口里可能取自缓存）。
    一旦有人顺手往 payload 里塞字段或改分数，改变的是所有后续请求看到的图 ——
    缓存里的对象会被共享，这类污染比"分数算错"更难查。
    """
    import json

    p = payload()
    snapshot = json.dumps(p, ensure_ascii=False, sort_keys=True, default=str)
    A.annotate(FakeModel(CLEAN), chart(), p, anchor_year=ANCHOR)
    A.annotate(FakeModel(CLEAN), chart(), p, scope=A.SCOPE_YEAR, year=2015, anchor_year=ANCHOR)
    assert json.dumps(p, ensure_ascii=False, sort_keys=True, default=str) == snapshot


def test_kline_scores_do_not_depend_on_today() -> None:
    """分数不得随「今天」漂移 —— 批注缓存与黄金快照都建立在这条之上。"""
    a = build_bazi_chart(BIRTH, GENDER, today=datetime.date(2026, 9, 15), liunian_start_year=2026)
    b = build_bazi_chart(BIRTH, GENDER, today=datetime.date(2027, 3, 1), liunian_start_year=2026)
    assert FS.build_kline(a, max_age=80) == FS.build_kline(b, max_age=80)


# ---------------- 缓存键 ----------------


def test_cache_tool_separates_every_input() -> None:
    keys = {
        A.cache_tool("overview", "comprehensive", None, 2026),
        A.cache_tool("overview", "career", None, 2026),
        A.cache_tool("year", "comprehensive", 2015, 2026),
        A.cache_tool("overview", "comprehensive", None, 2027),
    }
    assert len(keys) == 4, "缓存键必须能区分 scope/维度/年份/锚定年"


# ---------------- 接口契约 ----------------


def _call_endpoint(**overrides):
    body = xianzhi_kline.KlineAnnotationRequest(
        birth_time=overrides.pop("birth_time", BIRTH),
        gender=overrides.pop("gender", GENDER),
        **overrides,
    )
    ctx = SimpleNamespace(chat_model=overrides.pop("chat_model", FakeModel(CLEAN)))
    return asyncio.run(xianzhi_kline.annotate_kline(body, app_ctx=ctx))


def _fresh_cache():
    from app.tools.cache import bazi_cache

    bazi_cache.clear()


def test_endpoint_rejects_unknown_scope() -> None:
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        _call_endpoint(scope="weekly")
    assert e.value.status_code == 400 and "scope" in str(e.value.detail)


def test_max_dayun_reaches_payload(monkeypatch) -> None:
    """覆盖步数必须传进载荷 —— 批注说的"全期极值"得和 /kline 画的是同一段。"""
    import pytest
    from fastapi import HTTPException

    captured: dict = {}
    real = xianzhi_kline._compute_kline_payload

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(xianzhi_kline, "_compute_kline_payload", spy)
    _fresh_cache()
    _call_endpoint(max_dayun=10)
    assert captured["max_dayun"] == 10

    with pytest.raises(HTTPException) as e:
        _call_endpoint(max_dayun=xianzhi_kline.MAX_DAYUN_LIMIT + 1)
    assert e.value.status_code == 400 and "max_dayun" in str(e.value.detail)


def test_endpoint_requires_year_for_year_scope() -> None:
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        _call_endpoint(scope="year")
    assert e.value.status_code == 400 and "year" in str(e.value.detail)


def test_endpoint_rejects_unknown_dimension() -> None:
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        _call_endpoint(dimension="romance")
    assert e.value.status_code == 400


def test_endpoint_reports_503_without_llm() -> None:
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        _call_endpoint(chat_model=None)
    assert e.value.status_code == 503


def test_endpoint_caches_only_successful_annotations() -> None:
    """成功才落缓存；失败不落 —— 一次模型抽风不该让这张盘永远没批注。"""
    _fresh_cache()
    first = _call_endpoint()
    assert first["ok"] is True and first["cached"] is False
    second = _call_endpoint()
    assert second["cached"] is True and second["text"] == CLEAN

    _fresh_cache()
    bad = f"你命带{_absent_shensha()}。"
    failed = _call_endpoint(chat_model=FakeModel(bad, bad))
    assert failed["ok"] is False
    again = _call_endpoint()
    assert again["cached"] is False, "失败的批注不该进缓存"


def test_endpoint_rejects_bad_birth_time() -> None:
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        _call_endpoint(birth_time="不是时间")
    assert e.value.status_code == 400


def test_annotation_route_is_mounted() -> None:
    """忘记 include 是最容易漏的一步：只声明 router 不代表路径存在。"""
    import pytest

    try:
        from main import app
    except Exception as e:  # pragma: no cover
        pytest.skip(f"应用无法导入，跳过挂载校验：{e}")
    paths = set(app.openapi().get("paths", {}))
    assert "/api/ai/xianzhi/kline/annotation" in paths, sorted(
        p for p in paths if "kline" in p
    )
