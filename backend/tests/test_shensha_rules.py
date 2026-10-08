"""神煞判定回归：按问真查法锁定的四类修正。

事故锚点（2026-10-08 用户对照问真八字 App 反馈，盘例 庚辰 甲申 辛酉 癸巳 女）：
1. 天罗地网跑到年柱 —— 应记在**触发柱**，且用**查法一**（年/日支查余三支）
2. 日柱多了地转日 —— 天转/地转曾共用一张表，命中任一即两煞全报
3. 月柱少了德秀贵人 —— 曾"德干优先、命中一个就 break"，只产出一条
4. 年柱多了天德贵人 —— 曾查藏干（年柱庚辰藏干含癸，申月天德为癸即被误标）

修完以本文件锁定，防回退。
"""
from __future__ import annotations

from app.domain.chart_builder import build_bazi_chart, parse_gender
from app.domain.shensha_calc import _compute_shensha

# 现场对照盘（问真截图同盘）
BAZI = "2000-08-31 10:00"
# 天罗对照盘：年支戌见月支亥（丙戌 己亥 辛丑 癸巳）
TIANLUO = "2006-11-08 10:00"
# 旧误报盘：月支辰+时支巳共存，但年/日支均非辰巳（癸卯 丙辰 甲午 己巳）
FALSE_HIT = "2023-04-06 10:00"
# 地转对照盘：秋（酉月）·癸酉日（庚辰 乙酉 癸酉 丁巳）
DIZHUAN = "2000-09-12 10:00"


def _pillars(birth: str, gender: str) -> list[str]:
    return [p.ganzhi for p in build_bazi_chart(birth, gender).pillars]


def _where(birth: str, gender: str, name: str) -> list[str]:
    """某神煞命中的柱位列表。"""
    chart = build_bazi_chart(birth, gender)
    return [
        s["pillar"]
        for s in _compute_shensha(chart.pillars, parse_gender(gender))
        if s["name"] == name
    ]


def test_reference_chart_pillars():
    """对照盘本身要稳（四柱变了下面全部断言都失去意义）。"""
    assert _pillars(BAZI, "女") == ["庚辰", "甲申", "辛酉", "癸巳"]
    assert _pillars(TIANLUO, "男") == ["丙戌", "己亥", "辛丑", "癸巳"]
    assert _pillars(FALSE_HIT, "男") == ["癸卯", "丙辰", "甲午", "己巳"]
    assert _pillars(DIZHUAN, "女") == ["庚辰", "乙酉", "癸酉", "丁巳"]


# ---------------- 1. 天德贵人：不查藏干 ----------------


def test_tiande_only_matches_visible_gan():
    """天德只查四柱天干（问真：以月支查四柱干支），藏干不算。

    本盘申月天德为癸：仅时干癸命中；年柱庚辰藏干含癸，不得据此命中。
    """
    assert _where(BAZI, "女", "天德贵人") == ["时柱"]


# ---------------- 2. 德秀贵人：逐柱判定，可多柱 ----------------


def test_dexiu_reports_every_matching_pillar():
    """德秀逐柱判定：月干甲(秀)/日干辛(秀)/时干癸(德) 三柱均标。

    旧实现"德干优先、命中即 break"只产出时柱一条。
    """
    got = _where(BAZI, "女", "德秀贵人")
    assert sorted(got) == sorted(["月柱", "日柱", "时柱"])
    assert len(got) == 3, f"同一柱不得重复产出：{got}"


# ---------------- 3. 天罗地网：查法一 + 记触发柱 ----------------


def test_luowang_marks_trigger_pillar_not_source():
    """年支辰见时支巳 → 地网记在**时柱**（旧实现标在含"辰"的年柱）。"""
    assert _where(BAZI, "女", "地网") == ["时柱"]
    assert _where(BAZI, "女", "天罗") == []


def test_tianluo_case():
    """年支戌见月支亥 → 天罗记在月柱。"""
    assert _where(TIANLUO, "男", "天罗") == ["月柱"]
    assert _where(TIANLUO, "男", "地网") == []


def test_luowang_not_triggered_without_key_branches():
    """月支辰+时支巳共存，但年/日支都不是辰巳 → 查法一不触发。

    旧实现"全盘扫辰巳共存"会误报地网（且标在含辰的月柱）。
    """
    assert _where(FALSE_HIT, "男", "天罗") == []
    assert _where(FALSE_HIT, "男", "地网") == []


# ---------------- 4. 天转日 / 地转日：独立两煞 ----------------


def test_tianzhuan_dizhuan_are_independent():
    """秋·辛酉=天转、秋·癸酉=地转，各报各的，不得"命中任一即全报"。"""
    # 本盘日柱辛酉（秋）→ 只有天转日，无地转日
    assert _where(BAZI, "女", "天转日") == ["日柱"]
    assert _where(BAZI, "女", "地转日") == []
    # 秋·癸酉 → 只有地转日，无天转日
    assert _where(DIZHUAN, "女", "地转日") == ["日柱"]
    assert _where(DIZHUAN, "女", "天转日") == []
