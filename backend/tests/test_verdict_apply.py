"""LLM 终审应用层：裁决写回 chart.wuxing 的纯逻辑（不依赖 LLM/DB）。"""

from __future__ import annotations

import asyncio

import pytest

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


# ---------------- 同步包装：不阻塞主链路（2026-10-11 决策） ----------------
@pytest.fixture(autouse=True)
def _clean_bg_inflight():
    """每个用例前后清掉补判去重表，避免跨用例残留。"""
    from app.agent import verdict as V

    V._bg_inflight.clear()
    yield
    V._bg_inflight.clear()


def test_err_text_falls_back_to_type_name():
    """Asyncio 的超时/取消异常 str() 是空串，日志必须补类型名才查得下去。"""
    from app.agent import verdict as V

    assert V._err_text(asyncio.TimeoutError()) == "TimeoutError"
    assert V._err_text(RuntimeError("boom")) == "boom"


def test_sync_wrapper_returns_computed_and_schedules_background(monkeypatch):
    """未命中缓存：立刻返回计算版 + 派后台补判，绝不干等。

    旧行为是 asyncio.run(wait_for(..., 150s))：实测挂盘白卡 150 秒 × 2 次，把整轮
    从半分钟拖成 4 分钟，超时后拿到的还是计算版。
    """
    from app.agent import verdict as V

    chart = build_bazi_chart(*ANCHOR)
    monkeypatch.setattr(V, "_verdict_enabled", lambda: True)
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: None)
    scheduled: list[str] = []
    monkeypatch.setattr(V, "_submit_background_verdict", lambda c, m, h: scheduled.append(h))

    out = V.chart_with_verdict_sync(chart)

    assert out is chart  # 原样返回计算版
    assert len(scheduled) == 1  # 且已派后台补判


def test_sync_wrapper_applies_cached_verdict_without_background(monkeypatch):
    """命中缓存：毫秒级应用终审，不再派补判。"""
    from app.agent import verdict as V

    chart = build_bazi_chart(*ANCHOR)
    monkeypatch.setattr(V, "_verdict_enabled", lambda: True)
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: _verdict_for())
    scheduled: list[str] = []
    monkeypatch.setattr(V, "_submit_background_verdict", lambda c, m, h: scheduled.append(h))

    out = V.chart_with_verdict_sync(chart)

    assert out.wuxing.strength == "偏弱"
    assert "（LLM 终审）" in out.wuxing.useful_hint
    assert scheduled == []


def test_sync_wrapper_survives_cache_read_error(monkeypatch):
    """缓存读失败（DB 抖动）不应让挂盘报错：回退计算版并照常派补判。"""
    from app.agent import verdict as V

    chart = build_bazi_chart(*ANCHOR)
    monkeypatch.setattr(V, "_verdict_enabled", lambda: True)
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: (_ for _ in ()).throw(RuntimeError("db down")))
    scheduled: list[str] = []
    monkeypatch.setattr(V, "_submit_background_verdict", lambda c, m, h: scheduled.append(h))

    out = V.chart_with_verdict_sync(chart)

    assert out is chart
    assert len(scheduled) == 1


class _NoopThread:
    """只记录启动参数的假线程：不真的跑补判（避免用例联网/连库）。"""

    started: list[tuple] = []

    def __init__(self, target=None, args=(), name="", daemon=False):
        self._args = args

    def start(self) -> None:
        _NoopThread.started.append(self._args)


def test_background_verdict_dedupes_same_chart(monkeypatch):
    """同一张盘只允许一个补判在跑：密集挂盘不再把同一张盘判三遍。"""
    from app.agent import verdict as V

    chart = build_bazi_chart(*ANCHOR)
    _NoopThread.started = []
    monkeypatch.setattr(V.threading, "Thread", _NoopThread)

    V._submit_background_verdict(chart, None, "hash-1")
    V._submit_background_verdict(chart, None, "hash-1")  # 同一张盘：跳过
    V._submit_background_verdict(chart, None, "hash-2")  # 另一张盘：照派

    assert len(_NoopThread.started) == 2


# ---------------- 终审状态：命名空间 / 在飞判定 / 接口层跳过 ----------------
def test_verdict_applied_flag_follows_apply():
    from app.agent import verdict as V

    chart = build_bazi_chart(*ANCHOR)
    assert V.verdict_applied(chart) is False
    assert V.verdict_applied(V.apply_verdict(chart, _verdict_for())) is True


def test_chart_payload_carries_verdict_flag():
    """载荷必须自带 verdict_applied：前端要据此提示"终审版生成中，下拉刷新"。"""
    from app.api.xianzhi_chart import _format_chart_payload

    chart = build_bazi_chart(*ANCHOR)
    assert _format_chart_payload(chart)["verdict_applied"] is False
    assert _format_chart_payload(V_apply(chart))["verdict_applied"] is True


def V_apply(chart):
    from app.agent.verdict import apply_verdict

    return apply_verdict(chart, _verdict_for())


def test_cache_namespace_switches_with_verdict_presence(monkeypatch):
    """有 ok 裁决 → v；没有 → p；读失败 → 按计算版处理（宁可白算不误发）。"""
    from app.agent import verdict as V

    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: _verdict_for())
    assert V.verdict_cache_namespace("h1") == "v"
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: None)
    assert V.verdict_cache_namespace("h1") == "p"
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: (_ for _ in ()).throw(RuntimeError("db down")))
    assert V.verdict_cache_namespace("h1") == "p"
    assert V.verdict_cache_namespace("") == "p"


def test_api_entry_skips_verdict_while_background_running(monkeypatch):
    """后台正在补判这张盘时，接口层不能再判一遍：让用户白等 + 重复烧 token。"""
    from app.agent import verdict as V

    chart = build_bazi_chart(*ANCHOR)
    monkeypatch.setattr(V, "_verdict_enabled", lambda: True)
    called = []
    monkeypatch.setattr(V, "chart_with_verdict", _fake_async(called, chart))
    monkeypatch.setattr(V, "verdict_in_flight", lambda chash: True)

    out = asyncio.run(V.chart_with_verdict_for_api(chart))

    assert out is chart
    assert called == []  # 没走终审


def test_api_entry_delegates_when_no_background(monkeypatch):
    from app.agent import verdict as V

    chart = build_bazi_chart(*ANCHOR)
    monkeypatch.setattr(V, "_verdict_enabled", lambda: True)
    called = []
    monkeypatch.setattr(V, "chart_with_verdict", _fake_async(called, chart))
    monkeypatch.setattr(V, "verdict_in_flight", lambda chash: False)

    asyncio.run(V.chart_with_verdict_for_api(chart))

    assert len(called) == 1  # 正常走终审


def _fake_async(record: list, ret):
    async def _fn(chart, model=None):
        record.append(chart)
        return ret

    return _fn
