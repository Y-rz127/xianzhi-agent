"""用神喜忌守卫：病药论修正（印重之病）。

事故锚点
--------
一张 2004-06-22 08:00 男命（甲申 庚午 壬申 甲辰，日主壬水、中和、正格）。
用户指出「最忌金，因为金旺夺食；忌土生金；最喜水泄金调候，火制金、木抒发」，
而引擎给出「最喜土 / 最忌水」——两处完全相反。

根因不是数据算错，是**方向表只看强弱档**：`signs` 是档位常量，五行分布进不了门。
该盘金权重 4.40（占 32.7%，五行之最重），水仅 1.70，却是「最忌水」——
因为比劫的基准系数 1.0 是五路里最大的，「最忌」由系数而非病神决定。
「最喜」同理：官杀系数 0.8 > 财 0.7 > 食伤 0.55，于是任何偏旺盘都必然「最喜官杀」。

修法：《滴天髓》病药论（knowledge_docs/04_用神喜忌.md §三.2）——
「印多之病：以财制印、以比劫泄印为药」，官杀生印反助病。

**术语**：印为忌时财克印是「财制印」（药）；印为用时被财克才叫「财坏印」（破格）。
两者字面相近而吉凶相反 —— 曾经错写成「以财坏印为药」，等于把药说成坏事。

本文件守卫病药路径的四条性质，任何一条被改坏都会让用神结论重新错回去：

1. 印重盘的「最忌」必须是病神（印），不能被基准系数截胡；
2. 官杀必须由喜转忌（生印助病），否则等于给病神添柴；
3. 药（财 / 比劫 / 食伤）必须为正；食伤虽由印所克，是被病神伤到的一路；
4. 判据不得滥判 —— 印虽最重但未显著重于比劫的盘应留在原扶抑路径，
   偏弱、极旺、专旺、从格全部不得进入此路径。
"""

from __future__ import annotations

import datetime
from functools import lru_cache

from app.domain import fortune_score as FS
from tests import kline_golden as K

# 事故锚点命盘：报障时提供的八字
REPORTED = {"id": "reg_ailment_yin_zhong", "birth": "2004-06-22 08:00", "gender": "男"}

# 纯五行岁运柱：金 土 木 火 水 各取两支（天干地支同气，避免藏干干扰）
PURE_GANZHI = {
    "金": ("庚申", "辛酉"),
    "土": ("戊辰", "己未"),
    "木": ("甲寅", "乙卯"),
    "火": ("丙午", "丁巳"),
    "水": ("壬子", "癸亥"),
}


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


def all_cases():
    return K.load_cases()


def charts_with_ailment():
    """黄金盘中落入病药路径的命盘。"""
    out = []
    for case in all_cases():
        chart = K.cached_chart(case["id"])
        if FS.detect_ailment(chart):
            out.append((case["id"], chart))
    return out


# ---------------- 事故锚点：逐条对齐用户给出的读数 ----------------


def test_reported_chart_ranks_element_as_user_read() -> None:
    """报障盘的喜忌排序：水 > 火 > 木 > 0 > 土 > 金。

    用户的原话是「最忌金…忌土生金，最喜水…火制金、木抒发」。
    顺序也一并断言 —— 只断言正负号会放过「水和火谁更高」这类回退。
    """
    favor = FS.chart_favor_summary(reported_chart())["favor"]
    assert favor["金"] < favor["土"] < 0, f"金土应并忌且金更忌，实得 {favor}"
    assert favor["木"] > 0 and favor["火"] > 0 and favor["水"] > 0, f"木火水应并喜，实得 {favor}"
    assert favor["水"] > favor["火"] > favor["木"], f"喜神次序应为 水>火>木，实得 {favor}"


def test_reported_chart_extremes() -> None:
    """最喜水、最忌金 —— 修前是「最喜土、最忌水」，两处都反。"""
    summary = FS.chart_favor_summary(reported_chart())
    assert summary["mostFavored"] == "水", f"最喜应为水，实得 {summary['mostFavored']}"
    assert summary["mostOpposed"] == "金", f"最忌应为金，实得 {summary['mostOpposed']}"


def test_reported_chart_ailment_detected() -> None:
    """该盘必须被判为印重之病：金占 32.7% 为五行之最重，且为比劫（水）的 2.6 倍。"""
    assert FS.detect_ailment(reported_chart()) == "resource_dominant"
    note = FS.chart_favor_summary(reported_chart())["ailmentNote"]
    assert note and "印重" in note


def test_reported_chart_year_pillars_score_in_expected_order() -> None:
    """岁运行为：走金最低、走水最高。这是「金旺夺食不该涨」的直接体现。

    断言的是**区间归属**而非精确分数 —— 精确值由黄金快照负责，
    这里负责证明方向，两者分工不同。
    """
    chart = reported_chart()
    band = {}
    for wx, ganzhis in PURE_GANZHI.items():
        band[wx] = [
            FS.delta_to_score(FS.score_delta(chart, dayun=gz)) for gz in ganzhis
        ]
    assert max(band["金"]) < 50, f"走金应全部低于 50 分，实得 {band['金']}"
    assert max(band["土"]) < 50, f"走土（生金助病）应低于 50 分，实得 {band['土']}"
    assert min(band["木"]) > 50, f"走木应高于 50 分，实得 {band['木']}"
    assert min(band["火"]) > 50, f"走火应高于 50 分，实得 {band['火']}"
    assert min(band["水"]) > 50, f"走水应高于 50 分，实得 {band['水']}"
    assert max(band["金"]) < min(band["水"]), "金应显著低于水"


# ---------------- 病药路径的通用性质（跑遍全部黄金盘） ----------------


def test_ailment_note_says_zhiyin_not_huaijin() -> None:
    """术语守卫：印为忌时财克印是「财制印」（药），不是「财坏印」（破格）。

    「坏」带贬义 —— 印为**用神**被财破才叫坏印。把药写成坏事，
    既让文案自相矛盾，也会经 RAG 教出错误的吉凶方向。此条由用户指正后补上，
    并同时钉住知识库口径源（改了代码没改文档 = 没有单一事实源）。
    """
    from pathlib import Path

    for code, note in FS.AILMENT_NOTES.items():
        assert "坏印" not in note, f"{code} 的说明把用药写成了「坏印」：{note}"
    note = FS.AILMENT_NOTES["resource_dominant"]
    assert "财制印" in note and "比劫泄印" in note

    doc = (
        Path(FS.__file__).resolve().parents[1] / "rag" / "knowledge_docs" / "04_用神喜忌.md"
    )
    text = doc.read_text(encoding="utf-8")
    assert "以财制印" in text, "04 文档 §三.2 未同步术语"
    assert "以财坏印" not in text, "04 文档仍在用「财坏印」描述用药"
    assert "财制印" in text and "财坏印" in text, "应保留「制印/坏印」的辨析说明"


def test_ailment_path_is_actually_covered() -> None:
    """病药路径必须有真实命盘覆盖，且应是小众路径 —— 滥判说明判据太松。"""
    flagged = charts_with_ailment()
    total = len(all_cases())
    assert len(flagged) >= 1, "没有命盘落入病药路径，守卫等于空转"
    assert len(flagged) <= total // 3, f"{len(flagged)}/{total} 盘被判为印重，判据过松"


def test_ailment_makes_resource_the_worst_and_officer_opposed() -> None:
    """核心性质：病神（印）为最忌，官杀由喜转忌。

    官杀在原扶抑档是正号（偏旺喜官杀制身）。若此处仍为正，等于给病神添柴。
    """
    for case_id, chart in charts_with_ailment():
        w = chart.wuxing
        day_wx = w.day_master_wuxing
        resource = FS._producer_of(day_wx)
        officer = FS._controller_of(day_wx)
        favor = FS.favor_vector(chart)
        assert favor[resource] < 0, f"{case_id} 印重却喜印（{resource}）：{favor}"
        assert favor[officer] < 0, f"{case_id} 印重却喜官杀（{officer}），助病：{favor}"
        summary = FS.chart_favor_summary(chart)
        assert summary["mostOpposed"] == resource, (
            f"{case_id} 最忌应为病神 {resource}，实得 {summary['mostOpposed']}"
        )


def test_ailment_medicines_are_all_favored() -> None:
    """药：财（制印）、比劫（泄印）为正；食伤被病神所克，同为受损一路，亦为正。"""
    for case_id, chart in charts_with_ailment():
        w = chart.wuxing
        day_wx = w.day_master_wuxing
        favor = FS.favor_vector(chart)
        for label, wx in (
            ("财", FS.CONTROLS.get(day_wx, "")),
            ("比劫", day_wx),
            ("食伤", FS.GENERATES.get(day_wx, "")),
        ):
            assert favor.get(wx, 0.0) > 0, f"{case_id} 印重之药「{label}」（{wx}）却非喜神：{favor}"


def test_ailment_only_for_normal_pattern() -> None:
    """专旺 / 从格 / 假从有各自的取用，不得被病药路径覆盖。"""
    for case in all_cases():
        chart = K.cached_chart(case["id"])
        w = chart.wuxing
        if not w.special_pattern:
            continue
        assert FS.detect_ailment(chart) == "", (
            f"{case['id']} 为 {w.special_pattern}，不该走病药路径"
        )


def test_ailment_never_for_weak_day_master() -> None:
    """偏弱 / 极弱盘里印是日主的靠山，不是病（04 文档 §三.1「母灭子」的成立条件）。"""
    for case in all_cases():
        chart = K.cached_chart(case["id"])
        if chart.wuxing.strength not in ("偏弱", "极弱"):
            continue
        assert FS.detect_ailment(chart) == "", (
            f"{case['id']} {chart.wuxing.strength}，印为靠山，不该判印重之病"
        )


def test_ailment_never_for_extreme_prosperity() -> None:
    """极旺已近专旺，口径是顺其旺势，不在此改向。"""
    for case in all_cases():
        chart = K.cached_chart(case["id"])
        if chart.wuxing.strength != "极旺":
            continue
        assert FS.detect_ailment(chart) == "", f"{case['id']} 极旺，不该走病药路径"


def test_ailment_requires_positive_strength_score() -> None:
    """中和但落在偏弱侧（score ≤ 0）时印仍是靠山，不判病。"""
    for case in all_cases():
        chart = K.cached_chart(case["id"])
        w = chart.wuxing
        if not w.special_pattern and w.strength == "中和" and w.strength_score <= 0:
            assert FS.detect_ailment(chart) == "", (
                f"{case['id']} 中和偏弱侧（score={w.strength_score}），不该判印重之病"
            )


# ---------------- 判据本身：边界用合成权重钉死 ----------------


def test_resource_dominant_needs_resource_to_be_heaviest() -> None:
    """印非最重者 → 不是印重之病。"""
    counts = {"金": 3.0, "木": 4.0, "水": 2.0, "火": 3.0, "土": 2.5}
    assert FS._resource_dominant(counts, same="水", resource="金") is False


def test_resource_dominant_needs_margin_over_same() -> None:
    """印最重但仅略高于比劫 → 旺由两者共致，留在原扶抑路径。

    这条边界对应真实命盘 `shensha_sanqi`（印 32.1% / 比 29.1%，比值 1.10）：
    若判据只看「印最重」，该盘会被误判成印重之病。
    """
    counts = {"金": 4.0, "木": 1.0, "水": 3.6, "火": 1.0, "土": 1.0}
    assert FS._resource_dominant(counts, same="水", resource="金") is False
    assert FS._resource_dominant({"金": 4.0, "木": 1.0, "水": 2.0, "火": 1.0, "土": 1.0},
                                 same="水", resource="金") is True


def test_resource_dominant_handles_missing_and_empty() -> None:
    """零权重与空表不得抛异常 —— 探针与 API 都可能拿到退化输入。"""
    assert FS._resource_dominant({}, same="水", resource="金") is False
    assert FS._resource_dominant({"金": 0.0, "水": 0.0}, same="水", resource="金") is False
    assert FS._resource_dominant({"金": 1.0}, same="水", resource="不存在") is False


def test_ailment_codes_all_have_notes() -> None:
    """病神代号与说明必须成对 —— 前端直接显示 `ailmentNote`，缺了就是空白行。"""
    for code in FS.AILMENT_NOTES:
        assert FS.AILMENT_NOTES[code].strip()
    healthy = FS.chart_favor_summary(K.cached_chart(all_cases()[0]["id"]))
    if not healthy["ailment"]:
        assert healthy["ailmentNote"] == ""


def test_ailment_detection_is_deterministic() -> None:
    """纯函数：同盘多次调用结论全等（黄金快照的前提）。"""
    for case in all_cases():
        chart = K.cached_chart(case["id"])
        codes = {FS.detect_ailment(chart) for _ in range(3)}
        assert len(codes) == 1, f"{case['id']} 病神判定不确定：{codes}"


def test_ailment_plates_have_both_up_and_down_candles() -> None:
    """改向不得把某些盘的 K 线压成单向：阳线阴线都必须还在。

    历史事故：全阳或全阴的实体零信息量（见 kline_diagnose.py 判据 3）。
    """
    flagged = charts_with_ailment()
    assert flagged, "没有命盘落入病药路径，本条守卫空转"
    for case_id, _chart in flagged:
        candles = K.cached_kline(case_id)
        ups = sum(1 for c in candles if c["isUp"])
        assert 0 < ups < len(candles), f"{case_id} 单向后改向：{ups}/{len(candles)} 为阳线"
