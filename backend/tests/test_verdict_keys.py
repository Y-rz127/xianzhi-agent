"""命盘裁决指纹的语义：**四柱 + 性别**是身份，出生时刻只做画像/兜底。

为什么单独立一组
----------------
裁决的每一项输入（强弱/格局/用神/五神）都是四柱+性别的函数，所以：
- 同一张嘴的盘，不管用户填公历还是农历、带不带出生地、填 07:05 还是 08:55（同一辰时），
  都该命中**同一份**裁决 —— 这是"很多人排盘一致就用库里那份"的来源；
- 反过来，凡是**用年份**的东西（完整命盘 payload、K 线评分）必须仍按精确出生时刻缓存，
  因为四柱相同并不保证起运岁数相同。本组测试把这两条都钉住。

历史事故：2026-10-24 之前指纹只含出生时刻，且读侧用原始时间、写侧用真太阳时校正后的时间，
于是 08:15+经度 108.63 的盘裁决写在 07:28（`2f629bf2…`），读侧算出 `c621b85b…` 永远 miss
→ 详情页恒显示「终审版生成中」+ 反复重判。
"""

from __future__ import annotations

import asyncio

from app.agent import verdict as V
from app.db.chart_store import chart_hash_of
from app.domain.chart_builder import build_bazi_chart

BIRTH = "2004-06-22 08:15"
LON_NANNING = 108.63


# ---------------- 四柱指纹（裁决身份） ----------------


def test_pillars_key_is_shared_by_any_input_resolving_to_same_pillars():
    """同一张嘴的盘：不同时刻（同辰时）/ 是否带出生地 → 同一裁决指纹。"""
    base = V.verdict_key_for_input(BIRTH, "男", 2, LON_NANNING)
    # 同一辰时的另一个时刻：四柱相同（起运岁数可能不同，但裁决不含年份）
    assert V.verdict_key_for_input("2004-06-22 07:05", "男", 2, None) == base
    assert V.verdict_key_for_input("2004-06-22 08:55", "男", 2, LON_NANNING) == base
    # 不带出生地（未做真太阳时校正）但四柱不变 → 仍命中同一份
    assert V.verdict_key_for_input(BIRTH, "男", 2, None) == base


def test_pillars_key_differs_by_gender_pillars_and_sect():
    base = V.verdict_key_for_input(BIRTH, "男", 2, LON_NANNING)
    assert V.verdict_key_for_input(BIRTH, "女", 2, LON_NANNING) != base  # 性别进键
    assert V.verdict_key_for_input("1990-05-20 14:30", "男", 2, None) != base  # 四柱进键
    # 晚子时换日：sect 决定日柱，因此也必须换键
    assert V.verdict_key_for_input("2004-06-22 23:40", "男", 1, None) != V.verdict_key_for_input(
        "2004-06-22 23:40", "男", 2, None
    )


def test_pillars_key_matches_built_chart():
    """排盘前算的四柱指纹 == 排盘后按 chart.pillars 算的（两条路径必须同一把钥匙）。"""
    for birth, gender, sect, lon in (
        (BIRTH, "男", 2, LON_NANNING),
        (BIRTH, "男", 2, None),
        ("1990-05-20 14:30", "女", 2, 121.47),
        ("2004-06-22 23:40", "男", 1, None),
    ):
        chart = build_bazi_chart(birth, gender, sect=sect, longitude=lon)
        assert V.verdict_key_for_input(birth, gender, sect, lon) == V.verdict_key_of_chart(chart)


# ---------------- 出生时刻指纹（画像 / 老行兜底，仍须前后一致） ----------------


def test_chart_hash_for_input_matches_built_chart():
    """排盘前的时刻指纹必须与 `chart.birth.solar`（校正后）的指纹一致。"""
    for birth, gender, longitude in (
        (BIRTH, "男", LON_NANNING),  # 校正后 07:28，最容易被错算成 08:15
        (BIRTH, "男", None),
        ("1985-01-05 02:40", "女", 87.6),  # 校正 +130 分钟，跨日
    ):
        chart = build_bazi_chart(birth, gender, longitude=longitude)
        assert V.chart_hash_for_input(birth, gender, longitude) == chart_hash_of(
            chart.birth.solar, gender
        ), f"{birth}@{longitude} 的排盘前/后时刻指纹不一致"


def test_known_production_hash_is_reachable_before_build():
    """回归锚点：线上那张盘（2004-06-22 08:15 @108.63）的时刻指纹是 2f629bf2…。"""
    assert V.chart_hash_for_input(BIRTH, "男", LON_NANNING) == "2f629bf2684259b8"


# ---------------- 命中即回放，不再调 LLM ----------------


class _CountingModel:
    """假模型：只数调用次数（命中缓存时必须是 0 次）。"""

    model_name = "fake-verdict-model"

    def __init__(self):
        self.calls = 0

    async def ainvoke(self, messages, **kwargs):  # pragma: no cover - 命中时不该走到
        self.calls += 1
        raise AssertionError("命中裁决时不应调用 LLM")


def _verdict() -> dict:
    return {
        "relation_to_engine": "confirm",
        "strength": "中和",
        "special_pattern": "无",
        "special_label": "无",
        "useful_god": "水",
        "avoid_god": "土",
        "reason": "壬水午月身弱，用印比，土为杀最忌。",
    }


def test_cached_verdict_is_replayed_without_llm(monkeypatch):
    """已是当前版本 → 直接回放，LLM 调用次数为 0（毫秒级返回）。"""
    chart = build_bazi_chart(BIRTH, "男", longitude=LON_NANNING)
    model = _CountingModel()
    monkeypatch.setattr(V, "_verdict_enabled", lambda: True)
    monkeypatch.setattr(V, "_lookup_current", lambda *a, **k: _verdict())
    monkeypatch.setattr(V, "_submit_background_verdict", lambda *a, **k: None)

    applied = asyncio.run(V.chart_with_verdict(chart, model, allow_stale=False))

    assert V.verdict_applied(applied) is True
    assert applied.wuxing.strength == "中和"
    assert model.calls == 0


def test_lookup_uses_pillars_key_before_birth_key(monkeypatch):
    """查找顺序：先四柱指纹（跨人复用），miss 才用出生时刻（老行兜底）。"""
    seen: list[tuple[str, str]] = []

    def _fetch(key, by, *, any_version=False):
        seen.append((by, key))
        return None

    monkeypatch.setattr(V, "_fetch_verdict", _fetch)

    assert V._lookup_current("birth-key", "pillars-key") is None
    assert seen == [("verdict_key", "pillars-key"), ("chart_hash", "birth-key")]


# ---------------- 接口层：命名空间用四柱指纹 ----------------


def test_chart_endpoint_namespace_uses_pillars_key(monkeypatch):
    from app.api import xianzhi_chart as C

    seen: dict[str, str] = {}

    def _fake_namespace(birth_key="", verdict_key=""):
        seen["birth_key"] = birth_key
        seen["verdict_key"] = verdict_key
        return "p"

    monkeypatch.setattr(V, "verdict_cache_namespace", _fake_namespace)

    asyncio.run(C.get_chart(birth_time=BIRTH, gender="男", longitude=LON_NANNING))

    assert seen["verdict_key"] == V.verdict_key_for_input(BIRTH, "男", 2, LON_NANNING)
    assert seen["birth_key"] == V.chart_hash_for_input(BIRTH, "男", LON_NANNING)


def test_kline_endpoint_namespace_uses_pillars_key(monkeypatch):
    from app.api import xianzhi_kline as K

    seen: dict[str, str] = {}

    def _fake_namespace(birth_key="", verdict_key=""):
        seen["verdict_key"] = verdict_key
        return "p"

    monkeypatch.setattr(V, "verdict_cache_namespace", _fake_namespace)

    asyncio.run(K.get_kline(birth_time=BIRTH, gender="男", longitude=LON_NANNING, max_dayun=12))

    assert seen["verdict_key"] == V.verdict_key_for_input(BIRTH, "男", 2, LON_NANNING)
