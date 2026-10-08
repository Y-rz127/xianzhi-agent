"""命理 K 线接口测试。

刻意不依赖完整应用栈：端点把重活放在同步辅助 `_compute_kline_payload` 里，
测试直接调它即可覆盖全部构造逻辑；只有"路由是否真的挂上"一项需要 app 实例，
那项在拿不到 app 时跳过而非失败。

快照与数值口径的回归由 `tests/test_kline_golden.py` 负责，本文件只管接口契约。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api import xianzhi_kline
from app.domain import fortune_score

BIRTH_TIME = "1990-05-20 14:30"
GENDER = "男"


def _payload(**overrides):
    kwargs = {
        "birth_time": BIRTH_TIME,
        "gender": GENDER,
        "sect": 2,
        "yun_sect": 1,
        "longitude": None,
        "max_age": xianzhi_kline.MAX_AGE_DEFAULT,
        "include_months": False,
        "dimension": fortune_score.DIM_COMPREHENSIVE,
    }
    kwargs.update(overrides)
    return xianzhi_kline._compute_kline_payload(**kwargs)


# ---------------- 路由契约 ----------------


def test_router_declares_kline_path() -> None:
    paths = {(r.path, m) for r in xianzhi_kline.router.routes for m in getattr(r, "methods", set())}
    assert ("/kline", "GET") in paths, f"K 线端点未声明，实际：{sorted(paths)}"


def test_endpoint_is_mounted_on_app() -> None:
    """真正挂到 /api/ai/xianzhi/kline —— 只声明 router 而忘了 include 是最容易漏的一步。

    路径由三层前缀拼成：主应用 `/api` + 聚合器 `/ai` + 先知 `/xianzhi`。
    刻意走 `app.openapi()`：本项目的聚合用的是自定义 `_IncludedRouter` 懒挂载，
    直接遍历 `app.routes` 拿不到子路由的 path（只会看到一个 `_IncludedRouter` 壳）。
    """
    try:
        from main import app
    except Exception as e:  # pragma: no cover - 缺少启动依赖时跳过
        pytest.skip(f"应用无法导入，跳过挂载校验：{e}")
    paths = set(app.openapi().get("paths", {}))
    assert "/api/ai/xianzhi/kline" in paths, (
        f"K 线端点未挂载。含 xianzhi 的路径：{sorted(p for p in paths if 'xianzhi' in p)[:10]}"
    )


# ---------------- 载荷结构 ----------------


def test_payload_shape() -> None:
    p = _payload()
    assert set(p) == {"favor", "candles", "dayunBands", "meta"}
    assert p["candles"], "K 线为空"
    assert p["dayunBands"], "大运带为空"


def test_candle_count_matches_meta() -> None:
    p = _payload()
    assert len(p["candles"]) == p["meta"]["yearCount"]
    assert p["candles"][0]["year"] == p["meta"]["startYear"]
    assert p["candles"][-1]["year"] == p["meta"]["endYear"]


def test_candles_are_contiguous_years() -> None:
    years = [c["year"] for c in _payload()["candles"]]
    assert years == list(range(years[0], years[0] + len(years))), "K 线年份不连续"


def test_month_scores_omitted_by_default_included_on_demand() -> None:
    """月分数是调试用的证据链，默认不该进响应体。"""
    assert all("monthScores" not in c for c in _payload()["candles"])
    with_months = _payload(include_months=True)["candles"]
    assert all(len(c["monthScores"]) == 12 for c in with_months)


def test_ohlc_invariants_hold_over_wire() -> None:
    for c in _payload()["candles"]:
        assert 0.0 <= c["low"] <= min(c["open"], c["close"]) <= max(c["open"], c["close"]) <= c["high"] <= 100.0


def test_favor_summary_is_complete() -> None:
    favor = _payload()["favor"]
    assert set(favor["favor"]) == {"金", "木", "水", "火", "土"}
    assert favor["mostFavored"] != favor["mostOpposed"]
    # 方向必须与强弱一致，否则前端图例会指导反了
    if favor["strength"] in ("偏弱", "极弱"):
        assert favor["favor"][favor["dayMasterWuxing"]] > 0
    elif favor["strength"] in ("偏旺", "极旺"):
        assert favor["favor"][favor["dayMasterWuxing"]] < 0


def test_dayun_bands_cover_candles() -> None:
    p = _payload()
    years = [c["year"] for c in p["candles"]]
    covered = set()
    for band in p["dayunBands"]:
        covered.update(range(band["startYear"], band["endYear"] + 1))
    assert set(years) <= covered, "存在不属于任何大运带的年份（前端画不出背景带）"


def test_max_age_controls_span() -> None:
    short = _payload(max_age=30)
    long = _payload(max_age=60)
    assert short["meta"]["yearCount"] < long["meta"]["yearCount"]
    assert short["candles"][-1]["age"] == 30
    assert long["candles"][-1]["age"] == 60


def test_max_dayun_ends_on_whole_band() -> None:
    """按步数覆盖时右端必须收在整段大运上。

    末段只落进几年的话，前端那一格宽度只剩几十 rpx，干支两个字会被 overflow:hidden
    裁掉 —— 看上去就是"最右边那个大运被遮挡"。故断言：可见的每一段都被蜡烛完整覆盖。
    """
    p = _payload(max_dayun=10)
    candles, bands = p["candles"], p["dayunBands"]
    first, last = candles[0]["year"], candles[-1]["year"]
    visible = [b for b in bands if b["startYear"] <= last and b["endYear"] >= first]
    assert len(visible) == 10, f"应覆盖 10 步大运，实际 {len(visible)}"
    assert visible[-1]["endYear"] == last, "K 线右端没有收在第 10 步大运的结束年"
    for b in visible:
        assert b["startYear"] >= first and b["endYear"] <= last, (
            f"{b['ganzhi']} 只有部分年份落在 K 线里，前端画不完整"
        )
    assert p["meta"]["maxDayun"] == 10


def test_max_dayun_beats_max_age() -> None:
    """两套口径同时给时以步数为准；0 才回落到 max_age。"""
    by_age = _payload(max_age=30)
    by_dayun = _payload(max_age=30, max_dayun=10)
    assert by_dayun["meta"]["yearCount"] > by_age["meta"]["yearCount"]
    assert (
        _payload(max_age=30, max_dayun=0)["meta"]["yearCount"]
        == by_age["meta"]["yearCount"]
    )


def test_max_dayun_beyond_built_steps_falls_back() -> None:
    """步数顶到上限时：超出年龄上限的那几步被跳过，右端仍收在完整大运边界上。"""
    p = _payload(max_dayun=xianzhi_kline.MAX_DAYUN_LIMIT)
    last = p["candles"][-1]["year"]
    visible = [b for b in p["dayunBands"] if b["startYear"] <= last]
    assert visible[-1]["endYear"] == last
    assert p["candles"][-1]["age"] <= xianzhi_kline.MAX_AGE_LIMIT


def test_meta_records_weights_for_traceability() -> None:
    """权重与 K 值必须随响应返回 —— 前端要对齐口径时不该去猜后端常量。"""
    meta = _payload()["meta"]
    assert meta["weightDayun"] > meta["weightLiunian"] > meta["weightLiuyue"] > 0
    assert meta["kScore"] > 0


# ---------------- 维度契约 ----------------


def test_meta_lists_available_dimensions() -> None:
    """前端维度 tab 由后端给，避免两边各写一份枚举而漂移。"""
    meta = _payload()["meta"]
    keys = [d["key"] for d in meta["availableDimensions"]]
    assert keys == list(fortune_score.DIMENSIONS)
    assert all(d["label"] for d in meta["availableDimensions"])
    assert meta["dimension"] == fortune_score.DIM_COMPREHENSIVE
    assert meta["dimensionLabel"] == fortune_score.DIMENSION_LABELS[fortune_score.DIM_COMPREHENSIVE]
    assert meta["dimensionNote"] == fortune_score.DIMENSION_NOTES[fortune_score.DIM_COMPREHENSIVE]
    assert all(d["note"] for d in meta["availableDimensions"]), "维度说明不该为空（前端要当副标题）"
    assert meta["dimensionEmphasis"] == {}, "综合维度不该带侧重表"


def test_meta_reports_emphasis_for_non_comprehensive_dimension() -> None:
    meta = _payload(dimension="career")["meta"]
    assert meta["dimension"] == "career"
    assert meta["dimensionLabel"] == "事业"
    empha = meta["dimensionEmphasis"]
    assert set(empha) == {"金", "木", "水", "火", "土"}
    assert abs(sum(empha.values()) / len(empha) - 1.0) < 1e-3, "侧重表未均值归一"


def test_favor_carries_ailment_reason() -> None:
    """喜忌结论必须带依据：前端只显示 `ailmentNote`，不自行解释命理口径。

    无病时两者为空串，前端整行不渲染 —— 所以「有 note 必有 code」这条要成立。
    """
    favor = _payload()["favor"]
    assert "ailment" in favor and "ailmentNote" in favor
    if favor["ailment"]:
        assert favor["ailmentNote"] == fortune_score.AILMENT_NOTES[favor["ailment"]]
    else:
        assert favor["ailmentNote"] == ""


def test_ailment_flips_officer_and_resource_over_wire() -> None:
    """报障盘（2004-06-22 08:00 男）走接口时：最忌金、最喜水，且带印重说明。

    钉在接口层是因为前端读的就是这两个字段 —— 引擎修好了但接口没透传，
    用户看到的仍旧是错的那一版。
    """
    payload = _payload(birth_time="2004-06-22 08:00", gender="男")
    favor = payload["favor"]
    assert favor["mostOpposed"] == "金", f"最忌应为金，实得 {favor['mostOpposed']}"
    assert favor["mostFavored"] == "水", f"最喜应为水，实得 {favor['mostFavored']}"
    assert favor["ailment"] == "resource_dominant"
    assert "印重" in favor["ailmentNote"]
    assert favor["favor"]["金"] < favor["favor"]["土"] < 0
    assert favor["favor"]["水"] > favor["favor"]["火"] > favor["favor"]["木"] > 0


def test_dimension_changes_the_curve() -> None:
    """切维度必须真的换曲线，否则前端 tab 是摆设。"""
    base = [c["close"] for c in _payload()["candles"]]
    for dim in fortune_score.DIMENSIONS:
        if dim == fortune_score.DIM_COMPREHENSIVE:
            continue
        closes = [c["close"] for c in _payload(dimension=dim)["candles"]]
        ratio = sum(1 for a, b in zip(base, closes) if a != b) / len(base)
        assert ratio > 0.8, f"{dim} 维度只有 {ratio:.0%} 年份与综合不同"


def test_dimension_does_not_change_relations_over_wire() -> None:
    base = [c["relations"] for c in _payload()["candles"]]
    for dim in fortune_score.DIMENSIONS:
        if dim == fortune_score.DIM_COMPREHENSIVE:
            continue
        assert [c["relations"] for c in _payload(dimension=dim)["candles"]] == base


# ---------------- 入参校验 ----------------


def _call_endpoint(**overrides):
    kwargs = {
        "birth_time": BIRTH_TIME,
        "gender": GENDER,
        "sect": 2,
        "yun_sect": 1,
        "longitude": None,
        "max_age": xianzhi_kline.MAX_AGE_DEFAULT,
        "include_months": False,
        "dimension": fortune_score.DIM_COMPREHENSIVE,
    }
    kwargs.update(overrides)
    return asyncio.run(xianzhi_kline.get_kline(**kwargs))


def test_max_age_out_of_range_rejected() -> None:
    for bad in (0, -1, xianzhi_kline.MAX_AGE_LIMIT + 1):
        with pytest.raises(HTTPException) as e:
            _call_endpoint(max_age=bad)
        assert e.value.status_code == 400


def test_invalid_birth_time_rejected() -> None:
    with pytest.raises(HTTPException) as e:
        _call_endpoint(birth_time="不是时间")
    assert e.value.status_code == 400


def test_invalid_gender_rejected() -> None:
    with pytest.raises(HTTPException) as e:
        _call_endpoint(gender="未知")
    assert e.value.status_code == 400


def test_invalid_dimension_rejected() -> None:
    """非法维度报 400 而不是静默退化成综合 —— 前端拼错参数时要能立刻发现。"""
    with pytest.raises(HTTPException) as e:
        _call_endpoint(dimension="财运")
    assert e.value.status_code == 400
    assert "dimension" in str(e.value.detail)


def test_max_dayun_out_of_range_rejected() -> None:
    for bad in (-1, xianzhi_kline.MAX_DAYUN_LIMIT + 1):
        with pytest.raises(HTTPException) as e:
            _call_endpoint(max_dayun=bad)
        assert e.value.status_code == 400
        assert "max_dayun" in str(e.value.detail)
