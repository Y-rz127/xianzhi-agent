"""用神喜忌守卫：病药论修正（杀重之病）。

事故锚点
--------
2005-09-28 18:00 男命（乙酉 乙酉 乙卯 乙酉，日主乙木、中和、正格）。
外部命理工具判「身偏弱、喜火水木、忌金土」，而引擎给出「最喜金、最忌木」——两处相反。

根因不是数据算错，是**档位只看总分、看不见总分的结构**：三酉冲一卯伤了日主唯一的
禄根，但天干四乙在纯数量加权下把 score 补成 +0.44（中和正侧），方向表按「略偏旺」
取克泄耗，官杀系数 0.8 又是克泄耗三路里最大的，于是「最喜官杀」——给病神添柴。
这与印重事故（test_favor_yongshen.py）同构：比劫党众硬抗 ≠ 官杀被制化。

修法：04 文档 §三.2「官杀重之病：以食伤制杀、以印化杀为药」。判据四条：
官杀为五行之最重；印与食伤皆不足以制化（杀印相生 / 食神制杀是成格不是病）；
官杀显著重于比劫，或比劫之根被原局六冲伤及；不落偏弱/极弱/极旺/专旺/从格。

**术语**：杀为病时食伤克杀是「制杀」（药）；杀为用（从杀、杀印相生）时食伤克杀
才是「破格」。与印重路径的「财制印/财坏印」辨析同构，见 04 文档 §三.2 辨析段。

本文件守卫杀重路径的性质，任何一条被改坏都会让用神结论重新错回去：
1. 事故盘的喜忌次序必须是 火 > 水 > 木 > 0 > 土 > 金（制杀为先，化杀次之）；
2. 病神（官杀）必须落最忌，财滋杀同忌；
3. 杀印相生 / 食神制杀 / 偏弱 / 极旺 / 从格 / 中和负侧全部不得进入此路径；
4. 36 个黄金盘零命中 —— 这是 K 线快照全等的结构性保证。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.domain import fortune_score as FS
from tests import kline_golden as K

# 事故锚点命盘：乙酉 乙酉 乙卯 乙酉（天干四乙、地支三酉冲一卯、缺火缺水缺土）
REPORTED = {"id": "reg_ailment_sha_zhong", "birth": "2005-09-28 18:00", "gender": "男"}

# 纯五行岁运柱：金 土 木 火 水 各取两支（天干地支同气，避免藏干干扰）
PURE_GANZHI = {
    "金": ("庚申", "辛酉"),
    "土": ("戊辰", "己未"),
    "木": ("甲寅", "乙卯"),
    "火": ("丙午", "丁巳"),
    "水": ("壬子", "癸亥"),
}

# 报障盘同构的最小桩：乙木日主、中和正侧、金最重、印食俱缺、卯根被冲
SHA_COUNTS = {"金": 7.2, "木": 6.2, "水": 0.0, "火": 0.0, "土": 0.0}
SHA_ZHIS = ("酉", "酉", "卯", "酉")


@dataclass(frozen=True)
class _StubPillar:
    zhi: str


@dataclass(frozen=True)
class _StubWuxing:
    day_master_wuxing: str = "木"
    strength: str = "中和"
    strength_score: float = 0.44
    special_pattern: str = ""
    counts: dict = field(default_factory=lambda: dict(SHA_COUNTS))


@dataclass(frozen=True)
class _StubChart:
    wuxing: _StubWuxing = field(default_factory=_StubWuxing)
    pillars: tuple = tuple(_StubPillar(z) for z in SHA_ZHIS)


@lru_cache(maxsize=1)
def reported_chart():
    """事故锚点命盘。基准日与黄金快照一致，避免随系统日期漂移。"""
    from app.domain.chart_builder import build_bazi_chart

    return build_bazi_chart(
        REPORTED["birth"],
        REPORTED["gender"],
        today=datetime.date(2026, 9, 15),
        liunian_start_year=2026,
    )


# ---------------- 事故锚点：逐条对齐外部工具给出的读数 ----------------


def test_reported_chart_ranks_elements_as_expected() -> None:
    """报障盘的喜忌排序：火 > 水 > 木 > 0 > 土 > 金。

    外部工具口径：「火为第一用神（制杀+调候），水为次（化杀通关），忌金土」。
    顺序也一并断言 —— 只断言正负号会放过「火和水谁更高」这类回退。
    """
    favor = FS.chart_favor_summary(reported_chart())["favor"]
    assert favor["金"] < favor["土"] < 0, f"金土应并忌且金更忌，实得 {favor}"
    assert favor["木"] > 0 and favor["火"] > 0 and favor["水"] > 0, f"木火水应并喜，实得 {favor}"
    assert favor["火"] > favor["水"] > favor["木"], f"喜神次序应为 火>水>木，实得 {favor}"


def test_reported_chart_extremes() -> None:
    """最喜火、最忌金 —— 修前是「最喜金、最忌木」，两处都反。"""
    summary = FS.chart_favor_summary(reported_chart())
    assert summary["mostFavored"] == "火", f"最喜应为火，实得 {summary['mostFavored']}"
    assert summary["mostOpposed"] == "金", f"最忌应为金，实得 {summary['mostOpposed']}"


def test_reported_chart_ailment_detected() -> None:
    """该盘必须被判为杀重之病：金 7.2 为五行之最重，印食俱缺（无制无化）。"""
    assert FS.detect_ailment(reported_chart()) == "officer_dominant"
    note = FS.chart_favor_summary(reported_chart())["ailmentNote"]
    assert note and "杀重" in note


def test_reported_chart_year_pillars_score_in_expected_order() -> None:
    """岁运行为：走金土最低、走火水木最高。这是「七杀攻身不该涨」的直接体现。

    断言的是**区间归属**而非精确分数 —— 精确值由黄金快照负责，
    这里负责证明方向，两者分工不同。
    """
    chart = reported_chart()
    band = {}
    for wx, ganzhis in PURE_GANZHI.items():
        band[wx] = [FS.delta_to_score(FS.score_delta(chart, dayun=gz)) for gz in ganzhis]
    assert max(band["金"]) < 50, f"走金应全部低于 50 分，实得 {band['金']}"
    assert max(band["土"]) < 50, f"走土（财滋杀）应低于 50 分，实得 {band['土']}"
    assert min(band["木"]) > 50, f"走木应高于 50 分，实得 {band['木']}"
    assert min(band["水"]) > 50, f"走水应高于 50 分，实得 {band['水']}"
    assert min(band["火"]) > 50, f"走火应高于 50 分，实得 {band['火']}"
    assert max(band["金"]) < min(band["火"]), "金应显著低于火（第一用神）"


def test_reported_chart_kline_has_both_directions() -> None:
    """改向不得把 K 线压成单向：阳线阴线都必须还在。"""
    candles = FS.build_kline(reported_chart(), max_age=80)
    ups = sum(1 for c in candles if c["isUp"])
    assert 0 < ups < len(candles), f"{ups}/{len(candles)} 为阳线，单向塌缩"


def test_reported_detection_is_deterministic() -> None:
    """纯函数：同盘多次调用结论全等（黄金快照的前提）。"""
    chart = reported_chart()
    codes = {FS.detect_ailment(chart) for _ in range(3)}
    assert len(codes) == 1, f"病神判定不确定：{codes}"


# ---------------- 路径的结构性排除（桩盘钉死） ----------------


def test_never_for_weak_day_master() -> None:
    """偏弱档官杀是明面上的压制，五档已走「喜印比、忌克泄耗」，方向本就对。"""
    assert FS.detect_ailment(_StubChart(wuxing=_StubWuxing(strength="偏弱"))) == ""
    assert FS.detect_ailment(_StubChart(wuxing=_StubWuxing(strength="极弱"))) == ""


def test_never_for_extreme_prosperity() -> None:
    """极旺近专旺，口径是顺其旺势，官杀本就是忌神，不在此改向。"""
    assert FS.detect_ailment(_StubChart(wuxing=_StubWuxing(strength="极旺", strength_score=7.5))) == ""


def test_never_for_special_pattern() -> None:
    """从杀格顺势喜官杀，与病药方向完全相反，不得覆盖。"""
    assert FS.detect_ailment(_StubChart(wuxing=_StubWuxing(special_pattern="从格"))) == ""
    assert FS.detect_ailment(_StubChart(wuxing=_StubWuxing(special_pattern="假从"))) == ""


def test_never_for_neutral_negative_side() -> None:
    """中和负侧（score ≤ 0）方向表本就喜印比、忌官杀，不得改向。"""
    assert FS.detect_ailment(_StubChart(wuxing=_StubWuxing(strength_score=0.0))) == ""
    assert FS.detect_ailment(_StubChart(wuxing=_StubWuxing(strength_score=-0.5))) == ""


def test_never_when_medicine_present() -> None:
    """杀印相生 / 食神制杀是成格：官杀是被用的对象，不是病。

    印或食伤 ≥ 官杀 × OFFICER_MEDICINE_RATIO 即视为有制有化。
    若此处误判，会把「印夺食 / 伤用神」说成吉。
    """
    sha_yin = _StubChart(wuxing=_StubWuxing(counts={"金": 5.5, "木": 3.0, "水": 4.9, "火": 0.0, "土": 0.0}))
    assert FS.detect_ailment(sha_yin) == "", "杀印相生（印足化杀）不该判杀重之病"
    sha_shi = _StubChart(wuxing=_StubWuxing(counts={"金": 5.5, "木": 3.0, "水": 0.0, "火": 3.0, "土": 0.0}))
    assert FS.detect_ailment(sha_shi) == "", "食神制杀（食伤足制杀）不该判杀重之病"


def test_neutral_negative_side_golden_case_stays_out() -> None:
    """stem_bing 官杀（水）最重、中和，但 score=-1.07 落负侧：方向已对，不得改向。"""
    chart = K.cached_chart("stem_bing")
    assert FS.detect_ailment(chart) == ""
    summary = FS.chart_favor_summary(chart)
    assert summary["mostOpposed"] == "水", f"中和负侧最忌应仍为官杀（水），实得 {summary['mostOpposed']}"


# ---------------- 判据本身：边界用合成权重钉死 ----------------


def test_officer_needs_to_be_heaviest() -> None:
    """官杀非最重者 → 不是杀重之病。"""
    counts = {"金": 3.0, "木": 4.0, "水": 2.0, "火": 1.0, "土": 1.0}
    assert (
        FS._officer_dominant(counts, list(SHA_ZHIS), same="木", resource="水", output="火", officer="金")
        is False
    )


def test_officer_ratio_boundary() -> None:
    """官杀 ≥ 比劫 × 1.15 成立即病（报障盘 7.2/6.2=1.16 走此路）；略欠则不算。"""
    assert FS._officer_dominant({"金": 7.2, "木": 6.2}, list(SHA_ZHIS), "木", "水", "火", "金") is True
    assert (
        FS._officer_dominant({"金": 6.8, "木": 6.2}, ["子", "午", "丑", "未"], "木", "水", "火", "金")
        is False
    )


def test_officer_root_clash_substitutes_for_ratio() -> None:
    """比劫之根被冲 → 门槛降为「最重即可」（根气虚浮，计数高估了比劫一党）。"""
    counts = {"金": 6.5, "木": 6.2}  # 6.5 < 6.2×1.15，单看比值不够
    assert FS._officer_dominant(counts, ["酉", "酉", "卯", "酉"], "木", "水", "火", "金") is True
    assert FS._officer_dominant(counts, ["子", "午", "丑", "未"], "木", "水", "火", "金") is False


def test_officer_handles_missing_and_empty() -> None:
    """零权重与空表不得抛异常 —— 探针与 API 都可能拿到退化输入。"""
    assert FS._officer_dominant({}, list(SHA_ZHIS), "木", "水", "火", "金") is False
    assert FS._officer_dominant({"金": 0.0, "木": 0.0}, list(SHA_ZHIS), "木", "水", "火", "金") is False
    assert FS._officer_dominant({"金": 1.0}, list(SHA_ZHIS), "木", "水", "火", "不存在") is False


def test_same_root_clashed_main_qi_only() -> None:
    """根 = 主气属比劫的地支；藏干余气（如辰中乙木）不算，防门槛失真。"""
    assert FS._same_root_clashed(["酉", "酉", "卯", "酉"], "木") is True
    assert FS._same_root_clashed(["卯", "子", "午", "丑"], "木") is False  # 卯在局而无酉
    assert FS._same_root_clashed(["辰", "戌", "子", "午"], "木") is False  # 辰戌冲但辰非木根
    assert FS._same_root_clashed(["午", "子", "卯", "酉"], "火") is True  # 火根午被子冲
    assert FS._same_root_clashed(["寅", "申", "午", "子"], "木") is True  # 寅申冲
    assert FS._same_root_clashed([], "木") is False


# ---------------- 术语守卫（代码与知识库口径一致） ----------------


def test_officer_note_says_zhisha_not_poge() -> None:
    """术语守卫：杀为病时食伤克杀是「食伤制杀」（药），不是「破格」。

    「破格」带贬义 —— 杀为**用神**被食伤破才叫破格（从杀格、杀印相生）。
    把药写成破格会让文案自相矛盾，也会经 RAG 教出错误的吉凶方向。
    同时钉住知识库口径源（改了代码没改文档 = 没有单一事实源）。
    """
    note = FS.AILMENT_NOTES["officer_dominant"]
    assert "食伤制杀" in note and "化杀" in note, f"药必须写明制杀与化杀：{note}"
    assert "财滋杀" in note, f"忌神方向必须点到财滋杀：{note}"
    assert "破格" not in note, f"把用药写成了「破格」：{note}"

    doc = Path(FS.__file__).resolve().parents[1] / "rag" / "knowledge_docs" / "04_用神喜忌.md"
    text = doc.read_text(encoding="utf-8")
    assert "官杀重之病" in text, "04 文档 §三.2 缺「官杀重之病」药方"
    assert "食伤制杀" in text, "04 文档 §三.2 未同步术语"
    assert "杀为病" in text and "杀为用" in text, "04 文档缺「制杀」两种语境的辨析"


# ---------------- 零漂移锚点 ----------------


def test_golden_cases_never_enter_officer_path() -> None:
    """36 个黄金盘无一进入杀重路径 —— K 线快照全等的结构性保证。

    若此条失败，说明判据变松、波及了黄金盘：必须先重审判据，
    再（若确属口径演进）重生成快照并人工核对 diff，不可顺手 UPDATE_GOLDEN。
    """
    for case in K.load_cases():
        chart = K.cached_chart(case["id"])
        assert FS.detect_ailment(chart) != "officer_dominant", f"{case['id']} 进入杀重路径，快照已漂移"


def test_ailment_path_stays_minority() -> None:
    """病药路径总体仍是小众路径（印重 + 杀重合计 ≤ 1/3）—— 滥判说明判据太松。"""
    cases = K.load_cases()
    flagged = sum(1 for c in cases if FS.detect_ailment(K.cached_chart(c["id"])))
    assert flagged <= len(cases) // 3, f"{flagged}/{len(cases)} 盘被判病，判据过松"
