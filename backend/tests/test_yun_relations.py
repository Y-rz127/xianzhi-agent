"""yun_relations.py 岁运关系计算层单测。

覆盖：干支关系判定、touched_pillars 宫位归位、大运指认解析（resolve_target_dayuns）、
童限期、effective_target_years 合并、liuyue_line 流月行。
"""

import datetime as dt

from app.domain.chart_builder import build_bazi_chart
from app.domain.yun_relations import (
    SuiRelations,
    dayun_relations,
    effective_target_years,
    format_sui_relations,
    liunian_relations,
    liuyue_line,
    relations_for,
    resolve_target_dayuns,
)

MALE = "\u7537"


def _chart(birth_time: str = "1990-05-20 14:30", gender: str = MALE, **kw):
    return build_bazi_chart(birth_time, gender, liunian_years=30, liunian_start_year=1990, **kw)


def test_resolve_target_dayuns_current():
    chart = _chart()
    hits = resolve_target_dayuns(chart, "当前")
    # 当前年 2026 落在第4步乙酉(2025-2034)
    assert len(hits) == 1
    assert hits[0].index == 4
    assert hits[0].ganzhi == "乙酉"


def test_resolve_target_dayuns_by_seq():
    chart = _chart()
    hits = resolve_target_dayuns(chart, "3")
    assert len(hits) == 1
    assert hits[0].index == 3
    assert hits[0].ganzhi == "甲申"


def test_resolve_target_dayuns_by_age_range_returns_two():
    chart = _chart()
    hits = resolve_target_dayuns(chart, "30-40")
    # 30-40 岁与第3步(26-35)第4步(36-45)均有交集 → 跨两步返回 2 个
    assert len(hits) == 2
    assert {d.index for d in hits} == {3, 4}


def test_resolve_target_dayuns_by_ganzhi():
    chart = _chart()
    hits = resolve_target_dayuns(chart, "丙午")
    assert len(hits) == 0  # 大运序列无丙午，仅作负例：干支不匹配不出结果
    hits2 = resolve_target_dayuns(chart, "甲申")
    assert len(hits2) == 1
    assert hits2[0].index == 3


def test_resolve_target_dayuns_invalid_returns_empty():
    chart = _chart()
    assert resolve_target_dayuns(chart, "乱填一番") == []
    assert resolve_target_dayuns(chart, "") == []
    assert resolve_target_dayuns(chart, "      ") == []


def test_resolve_target_dayuns_next():
    chart = _chart()
    nxt = resolve_target_dayuns(chart, "下一步")
    # 当前为乙酉(2025-2034)，下一步即丙戌
    assert len(nxt) == 1
    assert nxt[0].ganzhi == "丙戌"


def test_tongxian_current_uses_xiaoyun():
    """童限期（未交大运）：未成年命例指认「当前」应返回童限项、is_tongxian=True。"""
    chart = build_bazi_chart("2020-06-15 10:00", MALE, liunian_years=3, liunian_start_year=2026)
    # 童限期：无真实大运步骤覆盖今天
    today = dt.date.today()
    assert not [d for d in chart.dayun if d.start_year <= today.year <= d.end_year]
    from app.domain.yun_relations import current_sui

    gz, is_tongxian = current_sui(chart)
    assert is_tongxian is True
    assert len(gz) == 2


def test_relations_for_tian_ke_di_chong():
    """流年 vs 大运构成天克地冲时置位 tian_ke_di_chong。"""
    chart = _chart()
    # 丙午 vs 壬子：丙克壬（干克）、午冲子（支冲）→ 天克地冲
    rel = relations_for(chart, dayun_ganzhi="壬子", liunian_ganzhi="丙午")
    assert rel.tian_ke_di_chong is True


def test_relations_for_sui_yun_bing_lin():
    """流年干支 == 大运干支 → 岁运并临。"""
    chart = _chart()
    rel = relations_for(chart, dayun_ganzhi="甲申", liunian_ganzhi="甲申")
    assert rel.sui_yun_bing_lin is True


def test_relations_for_touched_pillars_translates_to_palace():
    """被岁运地支冲到的原局柱应翻译为「柱(宫位)」。"""
    chart = _chart()
    # 用与年支午相冲的子：子午冲 → 引动年柱
    rel = relations_for(chart, dayun_ganzhi="壬子")
    touched = rel.touched_pillars
    assert any("年柱" in t for t in touched)
    assert any("祖上父母宫" in t for t in touched)


def test_dayun_relations_labels():
    chart = _chart()
    items = dayun_relations(chart, limit=12)
    assert len(items) == 12
    assert items[0].label.startswith("第1步")
    assert all(len(it.ganzhi) == 2 for it in items)


def test_liunian_relations_bind_dayun():
    chart = _chart()
    items = liunian_relations(chart, [2015, 2016])
    assert len(items) == 2
    assert items[0].label == "2015乙未"
    # 2015 属于甲申大运（2015-2024）
    assert items[0].ganzhi == "乙未"


def test_effective_target_years_merges():
    chart = _chart()
    # 纯年份
    assert effective_target_years(chart, [2020, 2021], "") == [2020, 2021]
    # 纯大运（第3步甲申 2015-2024）
    ys = effective_target_years(chart, [], "3")
    assert ys == list(range(2015, 2025))
    # 年份 ∪ 大运
    ys = effective_target_years(chart, [2030], "3")
    assert 2030 in ys and 2015 in ys


def test_format_sui_relations_tongxian_placeholder():
    item = SuiRelations(label="丙子", ganzhi="丙子", shishen_gan="正印", is_tongxian=True)
    text = format_sui_relations([item])
    assert "未交大运" in text
    assert "丙子" in text


def test_liuyue_line_has_twelve_months():
    chart = _chart()
    line = liuyue_line(chart, 2027)
    assert line.startswith("流月 2027（节气月")
    months = [ln for ln in line.splitlines() if ln.strip().startswith("月") or (ln.strip() and "起)" in ln)]
    assert len(months) == 12
