"""「保存并排盘」接口：出生信息落库 + 先落计算版 + 终审版覆盖写入。

为什么值得一组测试
------------------
这条接口要同时承担四个承诺，任一失效都会退回"填一次算好几份盘 / 重进会话没盘 /
终审永远不落库"的旧状态：

1. **只认保存**：面板草稿不参与，点保存才落库（`session_birth_info`）；
2. **真太阳时按出生地开关**：填了地点按经度校正，没填不校正、也不沿用上一张盘的地点；
3. **先给计算版**：接口必须立刻返回（不能等终审的 150 秒预算）；
4. **终审版覆盖写入**：后台补判跑完，用回调把快照与 payload 缓存一起刷新成终审版。

全程不联网、不碰真库：DB/补判/裁决缓存都打桩，只验"谁在什么时候写了什么"。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.agent import verdict as V
from app.api import xianzhi_chart as C
from app.domain.chart_builder import build_bazi_chart
from app.memory import postgres_memory as memory

BIRTH = "1990-05-20 14:30"
SESSION = "mp-xianzhi__u-test__1"

_VERDICT = {
    "relation_to_engine": "confirm",
    "strength": "中和",
    "special_pattern": "无",
    "special_label": "无",
    "useful_god": "水",
    "avoid_god": "土",
    "xishen": ["金"],
    "choushen": [],
    "pingshen": [],
    "reason": "壬水午月身弱，用印比，土为杀最忌。",
}


@pytest.fixture
def captured(monkeypatch):
    """把落库 / 补判 / 裁决缓存都打桩，返回记录容器。"""
    calls: dict[str, list] = {"birth": [], "snapshot": [], "verdict": [], "access": []}

    monkeypatch.setattr(
        "app.api._xianzhi_common.check_session_access",
        lambda sid, token: calls["access"].append((sid, token)) or asyncio.sleep(0),
    )
    monkeypatch.setattr(
        memory,
        "upsert_session_birth_info",
        lambda *args: calls["birth"].append(args),
    )
    monkeypatch.setattr(
        memory,
        "set_session_chart",
        lambda *args: calls["snapshot"].append(args),
    )
    monkeypatch.setattr(
        V,
        "submit_verdict_background",
        lambda chart, on_done=None: calls["verdict"].append((chart, on_done)),
    )
    # 裁决缓存默认当"没有"：快照里的五神/终审状态不该去碰真库
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: None)
    monkeypatch.setattr(V, "_get_stale_verdict", lambda chash: None)
    return calls


def _save(**over) -> dict:
    fields = {"session_id": SESSION, "birth_time": BIRTH, "gender": "男", **over}
    body = C.ChartSaveRequest(**fields)
    return asyncio.run(C.save_chart(body))


def _payload_cached(payload: dict, ns: str, longitude) -> bool:
    """载荷是否已预热进 /chart 的缓存（key 必须与 get_chart 逐字同构）。"""
    from app.agent.verdict import PROMPT_VERSION
    from app.domain.analysis_calc import ENGINE_VERSION
    from app.tools.cache import bazi_cache

    got = bazi_cache.get(
        "1990-05-20 14:30", "男", 2, 1, f"chart_api:{ns}:{longitude}:{ENGINE_VERSION}:{PROMPT_VERSION}"
    )
    return got is payload


# ---------------- 1. 保存即落库 + 先给计算版 ----------------


def test_save_persists_birth_info_and_returns_computed_chart(captured):
    resp = _save()

    # 落库：出生信息（归一化后的标准写法）+ 命盘快照（pending）
    assert captured["birth"], "点保存必须落库出生信息"
    session_id, birth_time, gender, place, longitude, user_id = captured["birth"][0]
    assert session_id == SESSION
    assert birth_time == "1990-05-20 14:30" and gender == "男"
    assert place == "" and longitude == 0.0, "没填出生地就不能带经度（不做真太阳时校正）"
    assert user_id == ""

    assert captured["snapshot"], "要点保存后立刻落一份命盘快照"
    snap_args = captured["snapshot"][0]
    assert snap_args[0] == SESSION and snap_args[3] == "pending"
    assert snap_args[1]["pillars"] and snap_args[1]["verdict_applied"] is False

    # 返回：计算版 + 待终审
    assert resp["verdict_status"] == "pending" and resp["verdict_applied"] is False
    assert resp["birth_info"] == {"time": "1990-05-20 14:30", "gender": "男", "place": "", "longitude": 0.0}
    assert resp["chart"]["verdict_applied"] is False
    assert _payload_cached(resp["chart"], "p", None), "计算版 payload 要预热，前端进详情页直接命中"


def test_save_dispatches_background_verdict(captured):
    _save()

    assert len(captured["verdict"]) == 1, "没终审就要派后台补判"
    _chart, on_done = captured["verdict"][0]
    assert callable(on_done), "必须挂回调：终审跑完要覆盖写入快照"


# ---------------- 2. 出生地 → 真太阳时 ----------------


def test_save_uses_place_longitude(captured):
    resp = _save(place="广西 南宁")

    _sid, _bt, _g, place, longitude, _uid = captured["birth"][0]
    assert place == "广西 南宁"
    assert longitude and longitude > 100, f"南宁经度应约 108°E，实得 {longitude}"
    assert resp["birth_info"]["longitude"] == longitude
    assert _payload_cached(resp["chart"], "p", longitude), "带经度的盘要按带经度的 key 预热"


def test_save_explicit_longitude_wins_over_place(captured):
    _save(place="广西 南宁", longitude=121.47)

    assert captured["birth"][0][4] == pytest.approx(121.47)


def test_save_without_place_does_not_reuse_old_longitude(captured):
    """不填出生地时经度必须归零：否则上一张盘的真太阳时会串到这张盘上。"""
    _save()
    _save(place="广西 南宁")
    _save()  # 再存一次、这回不填地点

    assert captured["birth"][-1][4] == 0.0


def test_save_rejects_bad_birth_time(captured):
    with pytest.raises(HTTPException) as e:
        _save(birth_time="不是时间")
    assert e.value.status_code == 400


def test_save_reports_503_when_persist_fails(captured, monkeypatch):
    """落库失败必须明确报错：假装保存成功的话，用户重进会话就查不到这张盘了。"""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(memory, "upsert_session_birth_info", _boom)

    with pytest.raises(HTTPException) as e:
        _save()
    assert e.value.status_code == 503


# ---------------- 3. 已有终审：直接应用，不再派补判 ----------------


def test_save_applies_cached_verdict_without_rejudging(captured, monkeypatch):
    applied = V.apply_verdict(build_bazi_chart(BIRTH, "男"), _VERDICT)
    monkeypatch.setattr(V, "chart_with_cached_verdict", lambda chart, allow_stale=True: applied)

    resp = _save()

    assert resp["verdict_status"] == "verdict" and resp["verdict_applied"] is True
    assert captured["verdict"] == [], "已经终审过就不该再烧一次 token"
    assert captured["snapshot"][0][3] == "verdict"
    assert _payload_cached(resp["chart"], "v", None), "终审版 payload 预热到 v 命名空间"


# ---------------- 4. 终审回调：覆盖写入快照 + 缓存 ----------------


def test_verdict_callback_overwrites_snapshot_and_cache(captured, monkeypatch):
    resp = _save()
    _chart, on_done = captured["verdict"][0]
    # 终审落库后，快照里的五神要能读出来
    monkeypatch.setattr(V, "_get_cached_verdict", lambda chash: _VERDICT)

    applied = V.apply_verdict(build_bazi_chart(BIRTH, "男"), _VERDICT)
    on_done(applied)

    # 快照被覆盖成终审版
    last_snapshot = captured["snapshot"][-1]
    assert last_snapshot[3] == "verdict"
    assert last_snapshot[1]["verdict_applied"] is True
    assert last_snapshot[1]["gods"]["yongshen"] == "水"
    # 终审版 payload 预热进 v 命名空间（前端下拉即是终审版）
    from app.agent.verdict import PROMPT_VERSION
    from app.domain.analysis_calc import ENGINE_VERSION
    from app.tools.cache import bazi_cache

    cached = bazi_cache.get(
        "1990-05-20 14:30", "男", 2, 1, f"chart_api:v:None:{ENGINE_VERSION}:{PROMPT_VERSION}"
    )
    assert cached is not None and cached["verdict_applied"] is True
    assert resp["verdict_status"] == "pending"  # 返回给前端的那份仍是计算版（当时还没判完）


def test_verdict_callback_failure_is_swallowed(captured, monkeypatch):
    """回写失败只留日志：不能把已经返回给用户的计算版变成一次 500。"""
    _save()
    _chart, on_done = captured["verdict"][0]

    def _boom(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(memory, "set_session_chart", _boom)
    on_done(V.apply_verdict(build_bazi_chart(BIRTH, "男"), _VERDICT))  # 不抛即通过


# ---------------- 5. 归属校验 ----------------


def test_save_rejects_other_users_session(monkeypatch):
    """有归属的会话只有本人能写出生信息（与 GET birth-info 同口径）。"""
    from app.api import data_access as repo

    async def _owner(_sid):
        return "u-owner"

    async def _token(_t):
        return None

    monkeypatch.setattr(repo, "get_session_owner", _owner)
    monkeypatch.setattr(repo, "get_by_token", _token)

    with pytest.raises(HTTPException) as e:
        _save(token="bad-token")
    assert e.value.status_code == 403
