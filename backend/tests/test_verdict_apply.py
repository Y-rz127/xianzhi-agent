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
    monkeypatch.setattr(V, "_get_stale_verdict", lambda chash: None)
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
    monkeypatch.setattr(V, "_get_stale_verdict", lambda chash: None)
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


def test_chart_payload_carries_five_gods(monkeypatch):
    """命盘详情页在「喜忌用神」处显示五神：载荷必须带 gods，且只含判得出来的类别。

    计算版 `gods == {}`（前端整块不出现）；终审版才逐条给出用/喜/忌/仇/平。
    """
    from app.agent import verdict as V
    from app.api.xianzhi_chart import _format_chart_payload

    chart = build_bazi_chart(*ANCHOR)
    assert _format_chart_payload(chart)["gods"] == {}

    verdict = _verdict_for(xishen=["木"], choushen=["水"])
    applied = V.apply_verdict(chart, verdict)
    monkeypatch.setattr(V, "_hash_of", lambda c: "hash-gods")
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: verdict)

    gods = _format_chart_payload(applied)["gods"]
    assert gods == {"yongshen": "火", "xishen": "木", "jishen": "金", "choushen": "水"}
    assert "pingshen" not in gods, "没判出来的类别不该出现空标签"


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
    monkeypatch.setattr(V, "_get_stale_verdict", lambda chash: None)

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


# ---------------- 五神（用/喜/忌/仇/平） ----------------
#
# 契约：用神、忌神必填（apply_verdict 的 hint 与缓存口径都依赖它们）；
# 喜神/仇神/平神**可选**——分析不出就不给，不允许因此把整份裁决判成 invalid。

_JSON_BASE = (
    '{"relation_to_engine":"confirm","strength":"中和","special_pattern":"无","special_label":"无",'
    '"useful_god":"水","avoid_god":"土",'
)


def _verdict_json(extra: str = "", reason: str = "壬水生于午月身弱，取印比为用，土为杀最忌。") -> str:
    return _JSON_BASE + extra + f'"reason":"{reason}"' + "}"


def test_parse_verdict_reads_optional_gods():
    from app.agent.verdict import parse_verdict

    v = parse_verdict(_verdict_json('"xishen":["金"],"choushen":["火"],"pingshen":["木"],'))
    assert v["xishen"] == ["金"]
    assert v["choushen"] == ["火"]
    assert v["pingshen"] == ["木"]


def test_parse_verdict_tolerates_missing_optional_gods():
    """模型没给喜/仇/平 → 空的，不是无效：漏给 ≠ 写错。"""
    from app.agent.verdict import parse_verdict

    v = parse_verdict(_verdict_json())
    assert v["xishen"] == [] and v["choushen"] == [] and v["pingshen"] == []
    # 空数组同样合法（"分析不出"的显式写法）
    v2 = parse_verdict(_verdict_json('"xishen":[],"choushen":[],"pingshen":[],'))
    assert v2["xishen"] == []


def test_parse_verdict_accepts_gods_written_as_string():
    """容忍 "金、水" 这种串行写法（模型偶尔不按数组输出）。"""
    from app.agent.verdict import parse_verdict

    v = parse_verdict(_verdict_json('"xishen":"金、木",'))
    assert v["xishen"] == ["金", "木"]


def test_parse_verdict_dedupes_across_categories_and_caps_size():
    """一行只归一类的口径：用神/忌神占过的五行不再进其它类；每类最多两个。"""
    from app.agent.verdict import parse_verdict

    v = parse_verdict(_verdict_json('"xishen":["水","金","木","火"],"choushen":["土","火"],'))
    assert v["xishen"] == ["金", "木"], "水在用神、土在忌神，且每类最多两个"
    # 火被"每类最多两个"挤出喜神后，仍可作为仇神显示——不因截断把整类吞掉
    assert v["choushen"] == ["火"]


def test_parse_verdict_rejects_illegal_god():
    from app.agent.verdict import parse_verdict

    with pytest.raises(ValueError):
        parse_verdict(_verdict_json('"xishen":["雷"],'))


def test_five_gods_only_include_categories_that_were_judged():
    """判得出来的才出键：前端按"有就显示"渲染，缺项不显示空标签。"""
    from app.agent.verdict import five_gods_from_verdict

    gods = five_gods_from_verdict({
        "useful_god": "水", "avoid_god": "土", "xishen": ["金"], "choushen": [], "pingshen": [],
    })
    assert gods == {"yongshen": "水", "xishen": "金", "jishen": "土"}
    assert "choushen" not in gods and "pingshen" not in gods


def test_five_gods_join_multiple_elements():
    from app.agent.verdict import five_gods_from_verdict

    gods = five_gods_from_verdict({"useful_god": "水", "avoid_god": "土", "xishen": ["金", "木"]})
    assert gods["xishen"] == "金、木"


def test_verdict_five_gods_empty_for_computed_chart():
    """计算版没有终审结论 → 空 dict（前端回退「最喜/最忌」），且不该去碰 DB。"""
    from app.agent import verdict as V

    chart = build_bazi_chart(*ANCHOR)
    assert V.verdict_five_gods(chart) == {}


def test_verdict_five_gods_reads_cached_verdict(monkeypatch):
    from app.agent import verdict as V

    chart = V.apply_verdict(build_bazi_chart(*ANCHOR), _verdict_for(xishen=["木"], choushen=["水"]))
    monkeypatch.setattr(V, "_hash_of", lambda c: "hash-x")
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: _verdict_for(xishen=["木"], choushen=["水"]))

    gods = V.verdict_five_gods(chart)
    assert gods["yongshen"] == "火" and gods["jishen"] == "金"
    assert gods["xishen"] == "木"
    # 水同时被当成仇神与"用神候选"的冲突由 parse 层处理，这里只验透传
    assert gods["choushen"] == "水"


def test_verdict_five_gods_survives_db_failure(monkeypatch):
    """读不到裁决不能让接口挂掉：降级为空 dict。"""
    from app.agent import verdict as V

    chart = V.apply_verdict(build_bazi_chart(*ANCHOR), _verdict_for())
    monkeypatch.setattr(V, "_hash_of", lambda c: "hash-y")
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: (_ for _ in ()).throw(RuntimeError("db down")))

    assert V.verdict_five_gods(chart) == {}


# ---------------- 旧版终审顶替（版本升级不阻塞用户） ----------------
#
# 现场（2026-10-22）：版本一 bump，chat_verdicts 同版本全 miss，/chart 同步判 LLM；
# 聊天页命盘按钮 v-if=chartData 要等排盘返回，于是按钮凭空消失直到终审跑完。
# 口径：旧版结论先顶上（标注"旧版"），后台静默重判当前版本，下拉刷新即得新版。


def test_stale_verdict_applied_without_blocking(monkeypatch):
    """同版本 miss、旧版有裁决 → 立刻返回旧版结论 + 派后台重判，不调 LLM。"""
    from app.agent import verdict as V

    chart = build_bazi_chart(*ANCHOR)
    monkeypatch.setattr(V, "_verdict_enabled", lambda: True)
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: None)
    monkeypatch.setattr(V, "_get_stale_verdict", lambda chash: _verdict_for())
    scheduled: list[str] = []
    monkeypatch.setattr(V, "_submit_background_verdict", lambda c, m, h: scheduled.append(h))

    async def _boom(*a, **k):
        raise AssertionError("旧版可顶替时不应同步调 LLM")

    monkeypatch.setattr(V, "run_shadow_verdict", _boom)

    out = asyncio.run(V.chart_with_verdict(chart))

    assert out.wuxing.strength == "偏弱"
    assert V.verdict_is_stale(out) is True, "必须是旧版标记，否则缓存会当成同版本终审"
    assert V.verdict_applied(out) is True
    assert len(scheduled) == 1


def test_background_verdict_does_not_short_circuit_on_stale(monkeypatch):
    """后台线程必须 allow_stale=False：否则一直返回旧版，新裁决永远不产生。"""
    from app.agent import verdict as V

    chart = build_bazi_chart(*ANCHOR)
    captured: dict = {}

    async def _fake(c, model=None, *, allow_stale=True):
        captured["allow_stale"] = allow_stale
        return c

    monkeypatch.setattr(V, "chart_with_verdict", _fake)

    V._background_verdict(chart, None, "hash-bg")

    assert captured["allow_stale"] is False


def test_cache_namespace_marks_stale_as_s(monkeypatch):
    """只有旧版裁决时命名空间是 s：既区别于 v（新裁决落库后要能失效），也区别于 p。"""
    from app.agent import verdict as V

    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: None)
    monkeypatch.setattr(V, "_get_stale_verdict", lambda chash: _verdict_for())
    assert V.verdict_cache_namespace("h-s") == "s"


def test_sync_wrapper_applies_stale_and_schedules_background(monkeypatch):
    """挂盘路径同理：旧版先应用，后台补判照派。"""
    from app.agent import verdict as V

    chart = build_bazi_chart(*ANCHOR)
    monkeypatch.setattr(V, "_verdict_enabled", lambda: True)
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: None)
    monkeypatch.setattr(V, "_get_stale_verdict", lambda chash: _verdict_for())
    scheduled: list[str] = []
    monkeypatch.setattr(V, "_submit_background_verdict", lambda c, m, h: scheduled.append(h))

    out = V.chart_with_verdict_sync(chart)

    assert out is not chart
    assert out.wuxing.strength == "偏弱"
    assert V.verdict_is_stale(out) is True
    assert len(scheduled) == 1


def test_verdict_five_gods_falls_back_to_stale(monkeypatch):
    """旧版顶替时五神也要给：否则页面有结论、喜忌却是空的。"""
    from app.agent import verdict as V

    chart = V.apply_verdict(build_bazi_chart(*ANCHOR), _verdict_for(xishen=["木"]), stale=True)
    monkeypatch.setattr(V, "_hash_of", lambda c: "hash-stale")
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: None)
    monkeypatch.setattr(V, "_get_stale_verdict", lambda chash: _verdict_for(xishen=["木"]))

    gods = V.verdict_five_gods(chart)

    assert gods["yongshen"] == "火" and gods["xishen"] == "木"
