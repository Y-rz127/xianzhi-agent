"""三合化局条件：化神得时（月令旺/相）才整支并入；休囚死合而不化、各归本位。

2026-10-12 用户裁决（报障盘 庚辰 庚辰 庚申 丙子，2000-05-02 子时）：
申子辰三合水局生于辰月（水死），原实现无条件整支并入，把申禄根与两辰印星
一并化入水，日主被判偏弱；用户对账主流「合化须化神得时，辰库收水不化」。
三会方不受此条件约束（三支齐全即当季方气聚，见边界用例）。
"""

from __future__ import annotations

from app.domain.analysis_calc import _chart_relation_adjust
from app.domain.chart_builder import build_bazi_chart

_BASE = {"金": 1.0, "木": 1.0, "水": 1.0, "火": 1.0, "土": 1.0}


def _adjust(pillars: list[str]):
    return _chart_relation_adjust(pillars, dict(_BASE))


def test_sanhe_merges_when_element_wang():
    """申子辰生于子月（水旺）：整支并入水，权重发生变化。"""
    adjusted, notes, _ = _adjust(["庚辰", "丙子", "庚申", "丙子"])
    assert any(n.endswith("参与支力量并入水") for n in notes)
    assert adjusted["水"] > _BASE["水"]


def test_sanhe_no_merge_when_element_dead():
    """申子辰生于辰月（水死）：合而不化，各归本位（权重原地不动）。"""
    adjusted, notes, _ = _adjust(["庚辰", "庚辰", "庚申", "丙子"])
    assert any("合而不化，各归本位" in n for n in notes)
    assert not any("参与支力量并入" in n for n in notes)
    assert adjusted == _BASE


def test_sanhui_merges_unconditionally():
    """申酉戌会金生于午月（金死）：三会无条件成局。"""
    adjusted, notes, _ = _adjust(["壬申", "庚午", "庚酉", "丙戌"])
    assert any("参与支力量并入金" in n for n in notes)
    assert adjusted["金"] > _BASE["金"]


def test_reported_chart_judged_prosperous():
    """报障盘回锚：辰月申子辰不化，庚金三透坐申禄 → 偏旺，泄秀之水为用。"""
    chart = build_bazi_chart("2000-05-02 00:00", "男")
    w = chart.wuxing
    assert [p.ganzhi for p in chart.pillars] == ["庚辰", "庚辰", "庚申", "丙子"]
    assert w.strength == "偏旺"
    assert w.strength_score == 2.62
    assert any("合而不化" in n for n in w.notes)
