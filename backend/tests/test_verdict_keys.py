"""命盘指纹（chart_hash）的前后一致性：读侧排盘前、写侧排盘后必须是同一把 key。

为什么单独立一组
----------------
`chart_verdicts` 以 `chart_hash` 为键，写侧（`run_shadow_verdict`）用的是
`chart.birth.solar` —— **真太阳时校正后**的时间。只要读侧拿查询串里的原始时间算，
两边就永远对不上，症状是：

- `verdict_cache_namespace` 恒为 "p" → 详情页永远「终审版生成中」，下拉刷新只命中计算版缓存；
- 每个不同经度（填/不填出生地）都算出新指纹 → 同一张盘被反复重判。

2026-10-24 实测：出生 2004-06-22 08:15 + 经度 108.63 的盘，裁决写在 `2004-06-22 07:28`
（hash 2f629bf2…），而 `/chart`、`/kline` 用 08:15 算出 c621b85b… → 永远 miss。
"""

from __future__ import annotations

import asyncio

from app.agent import verdict as V
from app.db.chart_store import chart_hash_of
from app.domain.chart_builder import build_bazi_chart

BIRTH = "2004-06-22 08:15"
LON_NANNING = 108.63


def test_chart_hash_for_input_matches_built_chart():
    """排盘前算的指纹 == 排盘后 `chart.birth.solar` 的指纹（写侧就是用它做键）。"""
    for birth, gender, longitude in (
        (BIRTH, "男", LON_NANNING),  # 带经度：校正后跨到 07:28，最容易被写错成 08:15
        (BIRTH, "男", None),  # 不带经度：两者本来就相同，防回归
        ("1990-05-20 14:30", "男", 121.47),
        ("1985-01-05 02:40", "女", 87.6),  # 校正 +130 分钟，跨日
    ):
        chart = build_bazi_chart(birth, gender, longitude=longitude)
        assert V.chart_hash_for_input(birth, gender, longitude) == chart_hash_of(
            chart.birth.solar, gender
        ), f"{birth}@{longitude} 的排盘前/后指纹不一致"


def test_chart_hash_for_input_is_stable_and_format_insensitive():
    """同一时刻的不同写法（这里用等价的公历写法）必须同键；不同经度必须异键。"""
    assert V.chart_hash_for_input(BIRTH, "男", LON_NANNING) == V.chart_hash_for_input(
        "2004-06-22 08:15", "男", LON_NANNING
    )
    # 地点不同 → 校正后时刻不同 → 确实是另一张盘（会各自判一次，这是设计而非 bug）
    assert V.chart_hash_for_input(BIRTH, "男", LON_NANNING) != V.chart_hash_for_input(
        BIRTH, "男", None
    )
    # 性别进键
    assert V.chart_hash_for_input(BIRTH, "男", LON_NANNING) != V.chart_hash_for_input(
        BIRTH, "女", LON_NANNING
    )


def test_known_production_hash_is_reachable_before_build():
    """回归锚点：线上那张盘（2004-06-22 08:15 @108.63）的指纹必须是 2f629bf2…。

    这条哈希对应的就是 2026-10-24 20:53 写库的那行裁决；读侧算错的话它永远取不到。
    """
    assert V.chart_hash_for_input(BIRTH, "男", LON_NANNING) == "2f629bf2684259b8"


def test_chart_endpoint_uses_canonical_hash_for_namespace(monkeypatch):
    """/chart 在排盘**之前**查终审命名空间时，也必须用排盘口径的指纹。"""
    from app.api import xianzhi_chart as C

    seen: dict[str, str] = {}

    def _fake_namespace(chash: str) -> str:
        seen["chash"] = chash
        return "p"

    monkeypatch.setattr(V, "verdict_cache_namespace", _fake_namespace)

    asyncio.run(C.get_chart(birth_time=BIRTH, gender="男", longitude=LON_NANNING))

    assert seen.get("chash") == V.chart_hash_for_input(BIRTH, "男", LON_NANNING)


def test_kline_endpoint_uses_canonical_hash_for_namespace(monkeypatch):
    """K 线同一个坑：命名空间也要按排盘口径算。"""
    from app.api import xianzhi_kline as K

    seen: dict[str, str] = {}

    def _fake_namespace(chash: str) -> str:
        seen["chash"] = chash
        return "p"

    monkeypatch.setattr(V, "verdict_cache_namespace", _fake_namespace)

    asyncio.run(K.get_kline(birth_time=BIRTH, gender="男", longitude=LON_NANNING, max_dayun=12))

    assert seen.get("chash") == V.chart_hash_for_input(BIRTH, "男", LON_NANNING)
