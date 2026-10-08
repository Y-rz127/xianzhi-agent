"""K 线反馈闭环单测（存储层 SQL + 接口契约）。

刻意**不连真实 PostgreSQL**：这里要验的是「SQL 语句与参数对不对」「业务校验拦不拦得住」，
用 FakePool 打桩即可。真库的建表由 `_ensure_tables` 的既有测试与部署期验证覆盖。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.api import data_access as _REAL_REPO, xianzhi_kline
from app.db import chart_store
from app.domain import fortune_score as FS

# 导入期抓取原始函数（在任何 monkeypatch 之前），供守卫自检比对。
_ORIGINAL_REPO = {
    name: getattr(_REAL_REPO, name)
    for name in ("add_kline_feedback", "list_kline_feedback", "kline_feedback_stats")
}


class _FakeCursor:
    def __init__(self, calls, row=None, rows=None):
        self._calls = calls
        self._row = row
        self._rows = rows or []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._calls.append((sql, params))
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, calls, row=None, rows=None):
        self._calls = calls
        self._row = row
        self._rows = rows or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._calls.append((sql, params))
        return _FakeCursor(self._calls, self._row, self._rows)


class _FakePool:
    def __init__(self, calls, row=None, rows=None):
        self._calls = calls
        self._row = row
        self._rows = rows or []

    def connection(self):
        return _FakeConn(self._calls, self._row, self._rows)


@pytest.fixture()
def store(monkeypatch):
    """返回 (calls, pool_factory)：calls 收集 SQL，pool_factory 可在测试内换返回行。"""
    calls: list = []
    monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)

    def install(row=None, rows=None):
        pool = _FakePool(calls, row, rows)
        monkeypatch.setattr(chart_store, "get_pool", lambda: pool)
        return pool

    install()
    return calls, install


# 本文件**任何**测试都不许碰真实 PostgreSQL。
#
# 教训：这条兜底是补上来的 —— 起初只有一个类级 autouse 去打桩 repo，
# 而模块级的 `test_feedback_does_not_touch_scoring` 不在那个类里，于是它真的
# 往线上库写了 4 条 "不错" 的反馈行。类是类、模块是模块，autouse 不会跨过去。
_CALLS: list = []


@pytest.fixture(autouse=True)
def _never_touch_real_db(monkeypatch):
    async def _add(*a, **kw):
        _CALLS.append(("add", a, kw))
        return "stub-id"

    async def _list(*a, **kw):
        _CALLS.append(("list", a, kw))
        return []

    async def _stats(*a, **kw):
        _CALLS.append(("stats", a, kw))
        return {}

    monkeypatch.setattr(xianzhi_kline.repo, "add_kline_feedback", _add)
    monkeypatch.setattr(xianzhi_kline.repo, "list_kline_feedback", _list)
    monkeypatch.setattr(xianzhi_kline.repo, "kline_feedback_stats", _stats)
    _CALLS.clear()
    yield


def test_module_guard_blocks_real_db_writes(_never_touch_real_db):
    """兜底守卫自检：repo 三个入口都必须已被换成 stub。

    必须在**导入期**先抓住原始函数再比 —— `xianzhi_kline.repo` 与
    `app.api.data_access` 是同一个模块对象，拿两者互比是恒真/恒假的假测试。
    """
    for name in ("add_kline_feedback", "list_kline_feedback", "kline_feedback_stats"):
        assert getattr(xianzhi_kline.repo, name) is not _ORIGINAL_REPO[name], f"{name} 没被守卫换掉"
    out = asyncio.run(xianzhi_kline.repo.add_kline_feedback("x", "男", "comprehensive", "overview", 4))
    assert out == "stub-id"
    assert _CALLS[-1][0] == "add"


# ---------------- 存储层 ----------------


class TestAddKlineFeedback:
    def _add(self, **overrides):
        kwargs = {
            "birth_time": "1990-05-20 14:30",
            "gender": "男",
            "dimension": "comprehensive",
            "scope": "year",
            "rating": 4,
            "year": 2026,
            "anchor_year": 2026,
            "accurate": True,
            "comment": "说到点上了",
            "snapshot": {"resonance": 61.2},
        }
        kwargs.update(overrides)
        return chart_store.add_kline_feedback(**kwargs)

    def test_inserts_with_expected_columns(self, store):
        calls, _ = store
        fid = self._add()
        assert isinstance(fid, str) and len(fid) == 36
        sql, params = calls[-1]
        assert "INSERT INTO kline_feedback" in sql
        for col in ("chart_hash", "dimension", "scope", "year", "anchor_year", "rating", "accurate", "comment", "snapshot"):
            assert col in sql, f"INSERT 语句缺少列 {col}"
        assert params[0] == fid
        assert params[2] == "1990-05-20 14:30"
        assert params[4] == "comprehensive"
        assert params[5] == "year"
        assert params[6] == 2026
        assert params[7] == 2026
        assert params[8] == 4
        assert params[9] is True
        assert params[10] == "说到点上了"

    def test_chart_hash_is_derived_from_birth_and_gender(self, store):
        """chart_hash 必须由出生信息推出（不是外键），且性别参与 —— 同日不同性别是两张盘。"""
        calls, _ = store
        self._add()
        hash_male = calls[-1][1][1]
        self._add(gender="女")
        hash_female = calls[-1][1][1]
        assert hash_male == chart_store._chart_hash("1990-05-20 14:30", "男")
        assert hash_male != hash_female

    def test_snapshot_serialized_as_json(self, store):
        calls, _ = store
        self._add(snapshot={"a": 1})
        raw = calls[-1][1][11]
        assert isinstance(raw, str)
        assert json.loads(raw) == {"a": 1}

    def test_empty_snapshot_becomes_empty_object(self, store):
        calls, _ = store
        self._add(snapshot=None)
        assert json.loads(calls[-1][1][11]) == {}

    @pytest.mark.parametrize("rating", [0, 6, -1, 100])
    def test_rejects_rating_out_of_range(self, store, rating):
        with pytest.raises(ValueError):
            self._add(rating=rating)

    def test_rejects_non_int_rating(self, store):
        """`True` 是 int 的子类，必须挡掉 —— 否则 bool 会被当成 1 星写进去。"""
        with pytest.raises(ValueError):
            self._add(rating=True)
        with pytest.raises(ValueError):
            self._add(rating="4")


class TestListKlineFeedback:
    def test_no_filter_lists_recent(self, store):
        calls, _ = store
        chart_store.list_kline_feedback(limit=10)
        sql, params = calls[-1]
        assert "FROM kline_feedback" in sql
        assert "WHERE 1 = 1" in sql
        assert params == [10]

    def test_filters_by_chart_hash_and_dimension(self, store):
        calls, _ = store
        chart_store.list_kline_feedback("1990-05-20 14:30", "男", "wealth", limit=5)
        sql, params = calls[-1]
        assert "chart_hash = %s" in sql
        assert "dimension = %s" in sql
        assert params == [chart_store._chart_hash("1990-05-20 14:30", "男"), "wealth", 5]

    def test_returns_empty_on_error(self, monkeypatch):
        class _Boom:
            def connection(self):
                raise RuntimeError("db down")

        monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)
        monkeypatch.setattr(chart_store, "get_pool", lambda: _Boom())
        assert chart_store.list_kline_feedback() == []


class TestKlineFeedbackStats:
    def test_computes_avg_and_rate_over_decided_only(self, store):
        """吻合率只对明确表过态的样本算：1 吻合 / (1 吻合 + 1 不吻合) = 0.5。"""
        calls, install = store
        install(
            row=(4, 3.5, 1, 1),
            rows=[("comprehensive", 3, 3.3), ("love", 1, 4.0)],
        )
        out = chart_store.kline_feedback_stats()
        assert out["total"] == 4
        assert out["avgRating"] == 3.5
        assert out["accurateYes"] == 1
        assert out["accurateNo"] == 1
        assert out["decided"] == 2
        assert out["accurateRate"] == 0.5
        assert out["byDimension"][0] == {"dimension": "comprehensive", "count": 3, "avgRating": 3.3}

    def test_rate_is_none_when_nobody_decided(self, store):
        """全都没表过态时不能报 0%（那会被读成"全不准"），要报 None。"""
        calls, install = store
        install(row=(2, 5.0, 0, 0), rows=[])
        out = chart_store.kline_feedback_stats()
        assert out["decided"] == 0
        assert out["accurateRate"] is None

    def test_empty_table_is_not_an_error(self, store):
        calls, install = store
        install(row=(0, None, 0, 0), rows=[])
        out = chart_store.kline_feedback_stats()
        assert out["total"] == 0
        assert out["avgRating"] is None

    def test_dimension_filter_is_passed(self, store):
        calls, install = store
        install(row=(0, None, 0, 0), rows=[])
        chart_store.kline_feedback_stats("wealth")
        sql, params = calls[-1]
        assert "dimension = %s" in sql
        assert params == ["wealth"]

    def test_returns_empty_dict_on_error(self, monkeypatch):
        class _Boom:
            def connection(self):
                raise RuntimeError("db down")

        monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)
        monkeypatch.setattr(chart_store, "get_pool", lambda: _Boom())
        assert chart_store.kline_feedback_stats() == {}


# ---------------- 接口契约 ----------------


def _fb_body(**overrides):
    kwargs = {
        "birth_time": "1990-05-20 14:30",
        "gender": "男",
        "dimension": FS.DIM_COMPREHENSIVE,
        "scope": "overview",
        "year": None,
        "anchor_year": 2026,
        "rating": 4,
        "accurate": True,
        "comment": "不错",
        "snapshot": {"x": 1},
    }
    kwargs.update(overrides)
    return xianzhi_kline.KlineFeedbackRequest(**kwargs)


def _submit(**overrides):
    return asyncio.run(xianzhi_kline.submit_kline_feedback(_fb_body(**overrides)))


class TestFeedbackEndpoint:
    @pytest.fixture(autouse=True)
    def _capture_repo(self, monkeypatch, _never_touch_real_db):
        """显式依赖模块级守卫，保证本桩在其**之后**安装（否则会被守卫覆盖回 stub-id）。"""
        self.saved: list = []

        async def _fake_add(birth_time, gender, dimension, scope, rating, **kw):
            self.saved.append(
                {"birth_time": birth_time, "gender": gender, "dimension": dimension, "scope": scope, "rating": rating, **kw}
            )
            return "fake-id"

        monkeypatch.setattr(xianzhi_kline.repo, "add_kline_feedback", _fake_add)

    def test_router_declares_feedback_paths(self):
        paths = {
            (r.path, m) for r in xianzhi_kline.router.routes for m in getattr(r, "methods", set())
        }
        assert ("/kline/feedback", "POST") in paths
        assert ("/kline/feedback", "GET") in paths
        assert ("/kline/feedback/stats", "GET") in paths

    def test_endpoints_are_mounted_on_app(self):
        try:
            from main import app
        except Exception as e:  # pragma: no cover
            pytest.skip(f"应用无法导入，跳过挂载校验：{e}")
        paths = set(app.openapi().get("paths", {}))
        assert "/api/ai/xianzhi/kline/feedback" in paths
        assert "/api/ai/xianzhi/kline/feedback/stats" in paths

    def test_happy_path_forwards_every_field(self):
        out = _submit()
        assert out == {"ok": True, "id": "fake-id"}
        assert self.saved[0]["rating"] == 4
        assert self.saved[0]["accurate"] is True
        assert self.saved[0]["anchor_year"] == 2026
        assert self.saved[0]["snapshot"] == {"x": 1}

    def test_year_scope_forwards_year(self):
        _submit(scope="year", year=2030)
        assert self.saved[0]["year"] == 2030

    def test_rejects_bad_dimension(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(dimension="nope")
        assert e.value.status_code == 400
        assert not self.saved

    def test_rejects_bad_scope(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(scope="nope")
        assert e.value.status_code == 400

    def test_rejects_year_scope_without_year(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(scope="year", year=None)
        assert e.value.status_code == 400

    @pytest.mark.parametrize("rating", [0, 6])
    def test_rejects_out_of_range_rating_at_model_level(self, rating):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _fb_body(rating=rating)

    def test_stats_endpoint_rejects_bad_dimension(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            asyncio.run(xianzhi_kline.kline_feedback_stats_endpoint("nope"))
        assert e.value.status_code == 400

    @pytest.mark.parametrize("limit", [0, -1, 501])
    def test_list_endpoint_rejects_bad_limit(self, limit):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            asyncio.run(xianzhi_kline.list_kline_feedback_endpoint(limit=limit))
        assert e.value.status_code == 400

    def test_list_endpoint_wraps_items(self, monkeypatch):
        async def _fake_list(birth_time, gender, dimension, limit):
            return [{"id": "1", "rating": 5}]

        monkeypatch.setattr(xianzhi_kline.repo, "list_kline_feedback", _fake_list)
        out = asyncio.run(xianzhi_kline.list_kline_feedback_endpoint())
        assert out["count"] == 1
        assert out["items"][0]["rating"] == 5


def test_data_access_exposes_feedback_wrappers():
    """接口层走 data_access 的异步包装，漏包装会在线上才炸。"""
    from app.api import data_access

    assert callable(data_access.add_kline_feedback)
    assert callable(data_access.list_kline_feedback)
    assert callable(data_access.kline_feedback_stats)


def test_feedback_does_not_touch_scoring(_never_touch_real_db):
    """反馈是**只写**通道：它不该以任何方式影响确定性评分。

    这条测试曾在模块级裸调 `_submit()` 而绕过类里的打桩，真往线上库写了 4 行；
    现在模块级 autouse 守卫兜底，下面同时断言"确实走了 repo 层（被 stub 接住）"。
    """
    from app.domain import fortune_score as FS2
    from tests import kline_resonance_golden as KG

    chart = KG.build_case_chart(KG.find_case("stem_ren"))
    before = FS2.build_kline(chart, max_age=30)
    _submit()
    assert [c[0] for c in _CALLS] == ["add"], "反馈未走 repo 层，或走了真实数据库"
    assert FS2.build_kline(chart, max_age=30) == before
