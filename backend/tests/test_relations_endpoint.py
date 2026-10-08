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


# ---------------- ②′ 童限：运柱是小运（xiaoyun），与大运互斥 ----------------
def test_xiaoyun_is_accepted_as_the_yunzhu_and_matches_chart_payload():
    """未起运的盘：运柱是小运 ⇒ 传 xiaoyun，结果必须与 /chart 里那一组逐字段一致。

    改前这里只能不传运柱（传 dayun 会被判非法干支 400），于是点选后刷新出来的岁运分析
    比初次加载少一个小运 —— 同一盘面同一组合两套结果。
    """
    import datetime as dt

    birth = (dt.date.today() - dt.timedelta(days=30)).strftime("%Y-%m-%d") + " 10:00"
    xp = api_mod._compute_chart_payload(birth, MALE, 2, 1, None)["xipan"]
    cur = xp["current"]
    assert cur["dayunLabel"] == "小运", "该盘应仍在童限（起运前以当年小运论）"

    got = _relations(
        birth_time=birth, gender=MALE,
        xiaoyun=cur["dayun"], liunian=cur["liunian"], liuyue=cur["liuyue"],
    )

    assert got["suiyun"] == xp["relations"]["suiyun"], "与小运同组合必须与 /chart 逐字段一致"
    assert got["yuanju"] == xp["relations"]["yuanju"]
    assert got["suiyun"]["label"].startswith(f"{cur['dayun']} · "), "小运必须真的参与（不是被静默忽略）"


def test_dayun_and_xiaoyun_are_mutually_exclusive():
    """两个都传无法判断谁是运柱 ⇒ 400（不静默挑一个）。"""
    with pytest.raises(HTTPException) as ei:
        _relations(birth_time=BIRTH, gender=MALE, dayun="壬申", xiaoyun="戊午", liunian="丙午")
    assert ei.value.status_code == 400
    assert "互斥" in ei.value.detail


def test_suiyun_keeps_relations_that_a_sui_zhi_takes_part_in():
    """口径：岁运栏按「**岁运有没有参与**」取舍，**不按「原局有没有」**。

    丙午/丁酉/癸巳/丁巳 这盘：原局 日支巳 + 月支酉 已成 半合金，流月丁酉 再来一个酉
    ⇒ 那是**岁运引动**，必须出现在岁运栏（不能因为"原局已经有了"就去重）。
    """
    got = _relations(birth_time="2026-09-16 10:00", gender=MALE, xiaoyun="戊午", liunian="丙午", liuyue="丁酉")
    sui, yuan = got["suiyun"]["zhi"], got["yuanju"]["zhi"]

    assert "巳酉半合金" in yuan, "原局栏当然有它"
    assert "巳酉半合金" in sui, "原局已有、岁运再来是引动，不能因为原局有就删掉"
    assert "午午自刑" in sui and "酉酉自刑" in sui, "靠岁运那一支才成立的自刑要留"
    assert "丁癸冲" in got["suiyun"]["gan"]


def test_suiyun_drops_groups_that_no_sui_zhi_takes_part_in():
    """真正该去掉的：参与支**一个都不来自岁运**的纯原局局/刑。

    同一张盘换成 戊申 流月（申与原局 巳酉/午/酉 都不成局）⇒ 岁运栏不该再报 巳酉半合金；
    而 巳申合水/巳申破/巳申半刑 是 岁运申 × 原局巳，属正当关系，要留。
    """
    got = _relations(birth_time="2026-09-16 10:00", gender=MALE, xiaoyun="戊午", liunian="丙午", liuyue="戊申")
    sui, yuan = got["suiyun"]["zhi"], got["yuanju"]["zhi"]

    assert "巳酉半合金" in yuan
    assert "巳酉半合金" not in sui, "申月与 巳酉 无关 ⇒ 纯原局的半合不进岁运栏"
    assert "巳申合水" in sui, "岁运申 × 原局巳 是正当的岁运关系"
    assert "午午自刑" in sui, "流年午 参与 ⇒ 留"


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


# ---------------- ③′ 童限段：客户端**不许**把大运列表里的「童限」当干支传 ----------------
def test_tongxian_segment_literal_must_not_be_sent_as_dayun():
    """未起运的盘：细盘大运列表 index=0 的 ganzhi 就是字面量「童限」，且它**正好 2 个字符**。

    2026-09-19 现场：前端用「长度 == 2」判断"是不是真干支"，把「童限」当大运发过来 ⇒
    这里按非法干支打回 400 ⇒ 页面 catch 静默吞掉 ⇒ **未起运的盘点大运时岁运分析永远不更新**。
    故本用例同时钉死两侧：① 后端仍须拒绝这个字面量（否则会以"大运=童限"参与关系计算，语义错的）；
    ② 不传 dayun 时（前端修好后的传法）必须能算出来。
    """
    import datetime as dt

    # 用"一个月前出生"构造未起运的盘，避免写死年份导致用例将来失效
    birth = (dt.date.today() - dt.timedelta(days=30)).strftime("%Y-%m-%d") + " 10:00"
    xp = api_mod._compute_chart_payload(birth, MALE, 2, 1, None)["xipan"]

    tongxian = xp["dayun"][0]
    assert tongxian["index"] == 0
    assert tongxian["ganzhi"] == "童限", f"童限段的 ganzhi 是字面量（{len(tongxian['ganzhi'])} 字符，长度为 2）"
    liunian = xp["liunian"][0]["ganzhi"]
    liuyue = xp["liuyue"][0]["ganzhi"]

    # ① 传字面量 → 400（这就是线上那条 400 的成因）
    with pytest.raises(HTTPException) as ei:
        _relations(birth_time=birth, gender=MALE, dayun="童限", liunian=liunian, liuyue=liuyue)
    assert ei.value.status_code == 400
    assert "不是合法干支" in ei.value.detail

    # ② 不传 dayun → 正常算出（童限没有大运，后端按"缺省项跳过"处理）
    got = _relations(birth_time=birth, gender=MALE, liunian=liunian, liuyue=liuyue)
    assert got["suiyun"]["label"] == f"{liunian} · {liuyue}"
    assert got["suiyun"]["zhi"] is not None


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
