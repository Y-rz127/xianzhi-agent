"""/relations（按点选的大运/流年/流月现算六栏）回归测试。

背景：细盘页的「岁运分析 / 原局分析」原先是页面加载时算好的固定快照（对应"今天"那一组），
用户点别的大运/流年/流月不会变。现在改为点选后回调 /relations 现算，本模块钉死：

① 与 /chart 里算好的那一组**逐字段一致**（同一盘面同一组合不能两套结果）；
② 换大运/流年/流月真的会变（不是永远返回同一份）；
③ 校验：空参数、非法干支、非法出生时间都返回 400；
④ 四柱按出生信息缓存（点一次算一次全量排盘是不可接受的）。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api import xianzhi as api_mod

BIRTH = "2004-06-22 08:00"
MALE = "男"


def _relations(**kwargs):
    return asyncio.run(api_mod.get_relations(**kwargs))


def _chart_relations(birth_time: str = BIRTH, gender: str = MALE) -> dict:
    payload = api_mod._compute_chart_payload(birth_time, gender, 2, 1, None)
    return payload["xipan"]["relations"]


# ---------------- ① 与 /chart 的那一组一致 ----------------
def test_matches_chart_payload_for_current_triple():
    """页面初次加载用 /chart 的 relations，点选后走 /relations——同一组合必须一致。"""
    expected = _chart_relations()
    sui = expected["suiyun"]["label"].split(" · ")
    assert len(sui) == 3, sui  # 壬申 · 丙午 · 丁酉

    got = _relations(birth_time=BIRTH, gender=MALE, dayun=sui[0], liunian=sui[1], liuyue=sui[2])

    assert got["suiyun"] == expected["suiyun"]
    assert got["yuanju"] == expected["yuanju"]


# ---------------- ② 跟随点选变化 ----------------
def test_dayun_change_alters_result():
    base = _relations(birth_time=BIRTH, gender=MALE, dayun="壬申", liunian="丙午", liuyue="丁酉")
    other = _relations(birth_time=BIRTH, gender=MALE, dayun="乙亥", liunian="丙午", liuyue="丁酉")

    assert other["suiyun"]["label"] == "乙亥 · 丙午 · 丁酉"
    assert other["suiyun"]["zhi"] != base["suiyun"]["zhi"]
    assert "申亥害" in other["suiyun"]["zhi"], other["suiyun"]["zhi"]  # 乙亥 与原局申 相害
    # 壬申 与原局日柱壬申 伏吟；换乙亥 后该整柱关系消失
    assert base["suiyun"]["zhu"] == ["壬申伏吟"]
    assert other["suiyun"]["zhu"] == []
    # 原局只与四柱有关，两种组合下必须完全一致
    assert other["yuanju"] == base["yuanju"]


def test_liunian_and_liuyue_change_alters_result():
    a = _relations(birth_time=BIRTH, gender=MALE, dayun="壬申", liunian="丙午", liuyue="丁酉")
    b = _relations(birth_time=BIRTH, gender=MALE, dayun="壬申", liunian="甲辰", liuyue="戊辰")

    assert b["suiyun"]["label"] == "壬申 · 甲辰 · 戊辰"
    assert b["suiyun"]["gan"] != a["suiyun"]["gan"]
    assert b["suiyun"]["zhi"] != a["suiyun"]["zhi"]


def test_partial_selection_allowed():
    """童限没有大运：允许只传流年/流月。"""
    only_year = _relations(birth_time=BIRTH, gender=MALE, liunian="甲辰")
    assert only_year["suiyun"]["label"] == "甲辰"
    assert only_year["suiyun"]["zhi"]

    year_month = _relations(birth_time=BIRTH, gender=MALE, liunian="丙午", liuyue="丁酉")
    assert year_month["suiyun"]["label"] == "丙午 · 丁酉"


# ---------------- ③ 校验 ----------------
def test_rejects_empty_selection():
    with pytest.raises(HTTPException) as ei:
        _relations(birth_time=BIRTH, gender=MALE)
    assert ei.value.status_code == 400


@pytest.mark.parametrize("bad", ["XY", "壬", "壬申酉", "申壬"])
def test_rejects_invalid_ganzhi(bad):
    with pytest.raises(HTTPException) as ei:
        _relations(birth_time=BIRTH, gender=MALE, liunian=bad)
    assert ei.value.status_code == 400


def test_rejects_invalid_birth_time():
    with pytest.raises(HTTPException) as ei:
        _relations(birth_time="不是时间", gender=MALE, liunian="甲辰")
    assert ei.value.status_code == 400


# ---------------- ④ 四柱缓存 ----------------
def test_pillars_are_cached_per_birth(monkeypatch):
    """同一次出生信息只排一次盘：点流年/流月是高频动作。"""
    from app.domain import chart_builder as _chart_builder_mod

    calls = {"n": 0}
    real = _chart_builder_mod.build_bazi_chart

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(_chart_builder_mod, "build_bazi_chart", counting)
    api_mod._PILLAR_CACHE.clear()

    _relations(birth_time=BIRTH, gender=MALE, dayun="壬申", liunian="丙午", liuyue="丁酉")
    _relations(birth_time=BIRTH, gender=MALE, dayun="乙亥", liunian="丙午", liuyue="丁酉")
    _relations(birth_time=BIRTH, gender=MALE, liunian="甲辰")

    assert calls["n"] == 1, f"四柱应缓存复用，实际排盘 {calls['n']} 次"
