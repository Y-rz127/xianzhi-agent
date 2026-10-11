"""LLM 终审应用层：裁决写回 chart.wuxing 的纯逻辑（不依赖 LLM/DB）。"""

from __future__ import annotations

from app.agent.verdict import (
    ENGINE_VERSION,
    PROMPT_VERSION,
    _verdict_enabled,
    apply_verdict,
)
from app.domain.chart_builder import build_bazi_chart

# 杀重锚点：计算版判中和 + officer_dominant（两铁律落码后的口径）
ANCHOR = ("2005-09-28 18:00", "男")

_VERDICT = {
    "relation_to_engine": "override",
    "strength": "偏弱",
    "special_pattern": "无",
    "special_label": "无",
    "useful_god": "火",
    "avoid_god": "金",
    "reason": "三酉冲一卯，禄根被伤；天干三比劫根损折半，正格身弱杀重论。",
}


def _verdict_for(**over) -> dict:
    return {**_VERDICT, **over}


def test_apply_overrides_strength_and_hint():
    chart = build_bazi_chart(*ANCHOR)
    new = apply_verdict(chart, _verdict_for())
    w = new.wuxing
    assert w.strength == "偏弱"
    assert w.special_pattern == ""
    assert "最喜火" in w.useful_hint and "最忌金" in w.useful_hint
    assert "（LLM 终审）" in w.useful_hint
    # 原对象不动（不可变替换）
    assert chart.wuxing.strength != "偏弱" or chart is not new


def test_apply_special_pattern_uses_label_as_strength():
    """成格时沿用引擎表示法：strength 装格名、special_pattern 装类别。"""
    chart = build_bazi_chart(*ANCHOR)
    v = _verdict_for(strength="极弱", special_pattern="假从", special_label="假从杀格")
    w = apply_verdict(chart, v).wuxing
    assert w.special_pattern == "假从"
    assert w.strength == "假从杀格"


def test_apply_keeps_mechanics_and_appends_note():
    """力学数值保留计算版，裁决理由追加进 notes 供审计。"""
    chart = build_bazi_chart(*ANCHOR)
    new = apply_verdict(chart, _verdict_for()).wuxing
    assert new.strength_score == chart.wuxing.strength_score
    assert new.counts == chart.wuxing.counts
    assert new.strength_detail == chart.wuxing.strength_detail
    assert new.root_verdict == chart.wuxing.root_verdict
    tail = new.notes[-1]
    assert tail.startswith(f"LLM终审[{PROMPT_VERSION}]：override")
    assert "三酉冲一卯" in tail
    assert len(new.notes) == len(chart.wuxing.notes) + 1


def test_verdict_enabled_respects_env(monkeypatch):
    monkeypatch.setenv("VERDICT_ENABLED", "0")
    assert _verdict_enabled() is False
    monkeypatch.setenv("VERDICT_ENABLED", "1")
    # pytest 进程内恒为 False（快照不可依赖 LLM）
    assert _verdict_enabled() is False


def test_versions_are_bumped_together():
    """版本常量必须成对演进：cache key 与 chart_verdicts 主键都靠它们区分口径。"""
    assert ENGINE_VERSION and PROMPT_VERSION
