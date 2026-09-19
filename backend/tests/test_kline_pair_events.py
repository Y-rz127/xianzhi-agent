"""合盘关系事件的存储层 SQL + 接口契约 + 合盘回测端点。

为什么要与单盘事件完全分开一套（表、存取层、接口、测试都分开）：
单盘事件校准的是「这个人这年过得好不好」，共振分的权重只能由「这两人这年顺不顺」
校准。两者的主键与可切分维度都不同 —— 单盘是「盘 × 年 × 领域」，关系事件没有
领域切片（同一年两人可以一个升职一个生病，但"我们俩这一年"只有一个答案）。

同 `test_kline_events`：不连真实 PostgreSQL，用 FakePool 验 SQL 与参数；
模块级 autouse 守卫把 repo 掐断，任何用例都不可能真写库。
"""

from __future__ import annotations

import asyncio
import datetime

import pytest

from app.api import data_access as _REAL_REPO, xianzhi_kline
from app.db import chart_store

# 导入期抓取原始函数（在任何 monkeypatch 之前），供守卫自检比对。
_ORIGINAL_REPO = {
    name: getattr(_REAL_REPO, name)
    for name in (
        "add_kline_pair_event",
        "list_kline_pair_events",
        "delete_kline_pair_event",
        "kline_pair_event_stats",
    )
}

_CHART_A = "1990-05-20 14:30"
_CHART_B = "1992-08-08 09:00"


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
    """返回 (calls, install)：calls 收集 SQL，install 可在用例内换返回行。"""
    calls: list = []
    monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)

    def install(row=None, rows=None):
        pool = _FakePool(calls, row, rows)
        monkeypatch.setattr(chart_store, "get_pool", lambda: pool)
        return pool

    install()
    return calls, install


# 本文件任何测试都不许碰真实 PostgreSQL。
_CALLS: list = []


@pytest.fixture(autouse=True)
def _never_touch_real_db(monkeypatch):
    async def _add(*a, **kw):
        _CALLS.append(("add", a, kw))
        return "stub-id"

    async def _list(*a, **kw):
        _CALLS.append(("list", a, kw))
        return []

    async def _delete(*a, **kw):
        _CALLS.append(("delete", a, kw))
        return True

    async def _stats(*a, **kw):
        _CALLS.append(("stats", a, kw))
        return {}

    monkeypatch.setattr(xianzhi_kline.repo, "add_kline_pair_event", _add)
    monkeypatch.setattr(xianzhi_kline.repo, "list_kline_pair_events", _list)
    monkeypatch.setattr(xianzhi_kline.repo, "delete_kline_pair_event", _delete)
    monkeypatch.setattr(xianzhi_kline.repo, "kline_pair_event_stats", _stats)
    # 建盘 0.35s/次，接口用例不需要真盘
    monkeypatch.setattr(xianzhi_kline, "_build_chart", lambda *a, **kw: "chart-stub")
    _CALLS.clear()
    yield


def test_module_guard_blocks_real_db_writes(_never_touch_real_db):
    """守卫自检：repo 四个入口必须都已被换成 stub（`xianzhi_kline.repo` 与 data_access
    是同一对象，两者互比是假测试，故与导入期抓取的原始函数比）。"""
    names = (
        "add_kline_pair_event",
        "list_kline_pair_events",
        "delete_kline_pair_event",
        "kline_pair_event_stats",
    )
    for name in names:
        assert getattr(xianzhi_kline.repo, name) is not _ORIGINAL_REPO[name], f"{name} 没被守卫换掉"
    assert asyncio.run(xianzhi_kline.repo.add_kline_pair_event("a", "男", "b", "女", 2026, 1)) == "stub-id"
    assert _CALLS[-1][0] == "add"


# ---------------- 配对键 ----------------


class TestPairKey:
    def test_is_symmetric(self):
        """关系是对称的（共振分交换甲乙逐字相同），谁填在甲不该影响分组。"""
        forward = chart_store.kline_pair_key(_CHART_A, "男", _CHART_B, "女")
        backward = chart_store.kline_pair_key(_CHART_B, "女", _CHART_A, "男")
        assert forward == backward

    def test_differs_across_pairs(self):
        assert chart_store.kline_pair_key(_CHART_A, "男", _CHART_B, "女") != chart_store.kline_pair_key(
            _CHART_A, "男", _CHART_B, "男"
        )

    def test_changes_with_gender_only(self):
        a = chart_store.kline_pair_key(_CHART_A, "男", _CHART_B, "女")
        b = chart_store.kline_pair_key(_CHART_A, "女", _CHART_B, "女")
        assert a != b


# ---------------- 存储层 ----------------


def _add(**overrides):
    kwargs = {
        "birth_time_a": _CHART_A,
        "gender_a": "男",
        "birth_time_b": _CHART_B,
        "gender_b": "女",
        "ganzhi_year": 2016,
        "polarity": 1,
        "sect": 2,
        "yun_sect": 1,
        "longitude_a": None,
        "longitude_b": None,
        "event_date": "2016-06-18",
        "relation": "夫妻",
        "source": "自述",
        "note": "结婚",
    }
    kwargs.update(overrides)
    return chart_store.add_kline_pair_event(**kwargs)


class TestAddKlinePairEvent:
    def test_inserts_with_expected_columns_and_params(self, store):
        calls, _ = store
        eid = _add()
        assert isinstance(eid, str) and len(eid) == 36
        sql, params = calls[-1]
        assert "INSERT INTO kline_pair_events" in sql
        for col in (
            "pair_key",
            "birth_time_a",
            "gender_a",
            "birth_time_b",
            "gender_b",
            "sect",
            "yun_sect",
            "longitude_a",
            "longitude_b",
            "ganzhi_year",
            "event_date",
            "polarity",
            "relation",
            "source",
            "note",
        ):
            assert col in sql, f"INSERT 缺少列 {col}"
        assert params[0] == eid
        assert params[2] == _CHART_A
        assert params[3] == "男"
        assert params[4] == _CHART_B
        assert params[5] == "女"
        assert params[10] == 2016
        assert params[11] == datetime.date(2016, 6, 18)
        assert params[12] == 1
        assert params[13] == "夫妻"

    def test_pair_key_is_the_sorted_hash_join(self, store):
        calls, _ = store
        _add()
        assert calls[-1][1][1] == chart_store.kline_pair_key(_CHART_A, "男", _CHART_B, "女")

    def test_swapped_sides_yield_the_same_pair_key(self, store):
        calls, _ = store
        _add(birth_time_a=_CHART_A, gender_a="男", birth_time_b=_CHART_B, gender_b="女")
        first = calls[-1][1][1]
        _add(birth_time_a=_CHART_B, gender_a="女", birth_time_b=_CHART_A, gender_b="男")
        assert calls[-1][1][1] == first

    def test_rejects_same_chart_on_both_sides(self, store):
        """同一张盘不构成合盘：两侧同盘时共振分退化成"自己跟自己"，没有校准意义。"""
        with pytest.raises(ValueError, match="同一张盘"):
            _add(birth_time_b=_CHART_A, gender_b="男")

    def test_accepts_date_object_and_blank_event_date(self, store):
        calls, _ = store
        _add(event_date=datetime.date(2016, 6, 18))
        assert calls[-1][1][11] == datetime.date(2016, 6, 18)
        _add(event_date="")
        assert calls[-1][1][11] is None

    @pytest.mark.parametrize("polarity", [2, -2, 5])
    def test_rejects_out_of_range_polarity(self, polarity):
        with pytest.raises(ValueError):
            _add(polarity=polarity)

    def test_rejects_bool_and_str_polarity(self):
        """`True` 是 int 子类，不单独挡就会被当成 1（顺）写进去。"""
        with pytest.raises(ValueError):
            _add(polarity=True)
        with pytest.raises(ValueError):
            _add(polarity="1")

    def test_zero_polarity_is_valid(self, store):
        """0（平）是合法标注："那几年没大事"本身就是可验证的断言。"""
        calls, _ = store
        _add(polarity=0)
        assert calls[-1][1][12] == 0

    @pytest.mark.parametrize("year", [0, 20260918, 999, 3001])
    def test_rejects_implausible_ganzhi_year(self, year):
        with pytest.raises(ValueError):
            _add(ganzhi_year=year)

    def test_rejects_bool_ganzhi_year(self):
        with pytest.raises(ValueError):
            _add(ganzhi_year=True)

    def test_relation_is_stored_verbatim(self, store):
        """存储层不管关系类型的合法值 —— 语义归接口层，这里只保证不被改写。"""
        calls, _ = store
        _add(relation="自由文本")
        assert calls[-1][1][13] == "自由文本"


class TestListKlinePairEvents:
    def test_no_filter_lists_recent(self, store):
        calls, _ = store
        chart_store.list_kline_pair_events(limit=10)
        sql, params = calls[-1]
        assert "FROM kline_pair_events" in sql
        assert "WHERE 1 = 1" in sql
        assert params == [10]

    def test_filters_by_pair_when_all_four_sides_given(self, store):
        calls, _ = store
        chart_store.list_kline_pair_events(_CHART_A, "男", _CHART_B, "女", 2016, limit=5)
        sql, params = calls[-1]
        assert "pair_key = %s" in sql
        assert "ganzhi_year = %s" in sql
        assert params == [chart_store.kline_pair_key(_CHART_A, "男", _CHART_B, "女"), 2016, 5]

    def test_partial_identity_does_not_filter_by_pair(self, store):
        """只给一侧不是"这一对"，退回列最近的 —— 否则会把一半人漏掉。"""
        calls, _ = store
        chart_store.list_kline_pair_events(_CHART_A, "男")
        assert "pair_key = %s" not in calls[-1][0]

    def test_returns_rebuild_params_for_both_sides(self, store):
        """回测要原样重建**两张**盘，故列表必须带两侧的 sect/yun_sect/longitude。"""
        calls, install = store
        install(
            rows=[
                (
                    "id-1",
                    _CHART_A,
                    "男",
                    _CHART_B,
                    "女",
                    1,
                    2,
                    116.4,
                    121.5,
                    2016,
                    datetime.date(2016, 6, 18),
                    1,
                    "夫妻",
                    "自述",
                    "结婚",
                    None,
                ),
            ]
        )
        item = chart_store.list_kline_pair_events()[0]
        assert item["birthTimeA"] == _CHART_A
        assert item["genderA"] == "男"
        assert item["birthTimeB"] == _CHART_B
        assert item["genderB"] == "女"
        assert item["sect"] == 1
        assert item["yunSect"] == 2
        assert item["longitudeA"] == 116.4
        assert item["longitudeB"] == 121.5
        assert item["ganzhiYear"] == 2016
        assert item["eventDate"] == "2016-06-18"
        assert item["relation"] == "夫妻"

    def test_empty_date_and_created_at_are_blank(self, store):
        calls, install = store
        install(
            rows=[
                ("id-1", "a", "男", "b", "女", None, None, None, None, 2020, None, -1, "", "", "", None)
            ]
        )
        item = chart_store.list_kline_pair_events()[0]
        assert item["eventDate"] == ""
        assert item["createdAt"] is None
        assert item["sect"] == 2 and item["yunSect"] == 1  # 空值回落默认流派
        assert item["relation"] == ""

    def test_returns_empty_on_error(self, monkeypatch):
        class _Boom:
            def connection(self):
                raise RuntimeError("db down")

        monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)
        monkeypatch.setattr(chart_store, "get_pool", lambda: _Boom())
        assert chart_store.list_kline_pair_events() == []


class TestDeleteKlinePairEvent:
    def test_deletes_and_reports_true(self, store):
        calls, _ = store
        assert chart_store.delete_kline_pair_event("id-1") is True
        sql, params = calls[-1]
        assert "DELETE FROM kline_pair_events" in sql
        assert params == ("id-1",)

    def test_reports_false_when_nothing_deleted(self, monkeypatch):
        class _Cursor:
            rowcount = 0

            def execute(self, sql, params=None):
                return self

        class _Conn(_Cursor):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class _Pool:
            def connection(self):
                return _Conn()

        monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)
        monkeypatch.setattr(chart_store, "get_pool", lambda: _Pool())
        assert chart_store.delete_kline_pair_event("nope") is False


class TestKlinePairEventStats:
    def test_maps_every_aggregate(self, monkeypatch):
        """统计有 5 次查询，必须按 SQL 分派返回行 —— 共用一批行会串味。"""
        calls: list = []
        rows_by_sql = {
            "GROUP BY polarity": [(1, 6), (-1, 4), (0, 2)],
            "GROUP BY relation": [("夫妻", 8), ("同事", 3)],
            "GROUP BY birth_time_a": [(_CHART_A, "男", _CHART_B, "女", 7, 2005, 2026)],
        }
        scalars = {
            "COUNT(DISTINCT pair_key)": (12, 2, 8),
            "MIN(ganzhi_year)": (2005, 2026),
        }

        class _Cursor:
            def __init__(self, row, rows):
                self._row, self._rows = row, rows

            def execute(self, sql, params=None):
                calls.append((sql, params))
                return self

            def fetchone(self):
                return self._row

            def fetchall(self):
                return self._rows

        class _Pool:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                for key, rows in rows_by_sql.items():
                    if key in sql:
                        return _Cursor(None, rows)
                for key, row in scalars.items():
                    if key in sql:
                        return _Cursor(row, [])
                raise AssertionError(f"未预期的查询：{sql}")

            def connection(self):
                return self

        monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)
        monkeypatch.setattr(chart_store, "get_pool", lambda: _Pool())
        out = chart_store.kline_pair_event_stats()
        assert out["total"] == 12
        assert out["pairs"] == 2
        assert out["yearCount"] == 8
        assert out["yearFrom"] == 2005 and out["yearTo"] == 2026
        assert out["byPolarity"][0] == {"polarity": 1, "count": 6}
        assert out["byRelation"] == [{"relation": "夫妻", "count": 8}, {"relation": "同事", "count": 3}]
        assert out["byPair"][0] == {
            "birthTimeA": _CHART_A,
            "genderA": "男",
            "birthTimeB": _CHART_B,
            "genderB": "女",
            "count": 7,
            "yearFrom": 2005,
            "yearTo": 2026,
        }

    def test_blank_relation_shows_as_unlabelled(self, monkeypatch):
        """空 relation 在分组里不能显示成空字符串，否则前端看不出"这组是没标注"。"""
        class _Cursor:
            def __init__(self, row, rows):
                self._row, self._rows = row, rows

            def execute(self, sql, params=None):
                return self

            def fetchone(self):
                return self._row

            def fetchall(self):
                return self._rows

        class _Pool:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                if "GROUP BY relation" in sql:
                    return _Cursor(None, [("", 4)])
                if "GROUP BY polarity" in sql:
                    return _Cursor(None, [(1, 4)])
                if "GROUP BY birth_time_a" in sql:
                    return _Cursor(None, [])
                if "COUNT(DISTINCT pair_key)" in sql:
                    return _Cursor((4, 1, 1), [])
                return _Cursor((2016, 2016), [])

            def connection(self):
                return self

        monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)
        monkeypatch.setattr(chart_store, "get_pool", lambda: _Pool())
        out = chart_store.kline_pair_event_stats()
        assert out["byRelation"] == [{"relation": "未标注", "count": 4}]

    def test_returns_empty_dict_on_error(self, monkeypatch):
        class _Boom:
            def connection(self):
                raise RuntimeError("db down")

        monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)
        monkeypatch.setattr(chart_store, "get_pool", lambda: _Boom())
        assert chart_store.kline_pair_event_stats() == {}


# ---------------- 接口契约 ----------------


def _pair_body(**overrides):
    kwargs = {
        "birth_time_a": _CHART_A,
        "gender_a": "男",
        "birth_time_b": _CHART_B,
        "gender_b": "女",
        "sect": 2,
        "yun_sect": 1,
        "longitude_a": None,
        "longitude_b": None,
        "ganzhi_year": 2016,
        "event_date": "",
        "polarity": 1,
        "relation": "夫妻",
        "source": "自述",
        "note": "结婚",
    }
    kwargs.update(overrides)
    return xianzhi_kline.KlinePairEventRequest(**kwargs)


def _submit(**overrides):
    return asyncio.run(xianzhi_kline.submit_kline_pair_event(_pair_body(**overrides)))


class TestPairEventEndpoint:
    @pytest.fixture(autouse=True)
    def _capture_repo(self, monkeypatch, _never_touch_real_db):
        """显式依赖模块级守卫，保证本桩装在其后（否则会被覆盖回 stub-id）。"""
        self.saved: list = []
        self.ids: list = []
        self.built: list = []

        async def _fake_add(birth_time_a, gender_a, birth_time_b, gender_b, ganzhi_year, polarity, **kw):
            self.saved.append(
                {
                    "birth_time_a": birth_time_a,
                    "gender_a": gender_a,
                    "birth_time_b": birth_time_b,
                    "gender_b": gender_b,
                    "ganzhi_year": ganzhi_year,
                    "polarity": polarity,
                    **kw,
                }
            )
            return "fake-id"

        async def _fake_delete(event_id):
            self.ids.append(event_id)
            return event_id != "missing"

        def _fake_build(birth_time, gender, sect, yun_sect, longitude):
            self.built.append((birth_time, gender, sect, yun_sect, longitude))
            return f"chart::{birth_time}"

        monkeypatch.setattr(xianzhi_kline.repo, "add_kline_pair_event", _fake_add)
        monkeypatch.setattr(xianzhi_kline.repo, "delete_kline_pair_event", _fake_delete)
        monkeypatch.setattr(xianzhi_kline, "_build_chart", _fake_build)

    def test_router_declares_pair_paths(self):
        paths = {(r.path, m) for r in xianzhi_kline.router.routes for m in getattr(r, "methods", set())}
        assert ("/kline/pair-events", "POST") in paths
        assert ("/kline/pair-events", "GET") in paths
        assert ("/kline/pair-events/stats", "GET") in paths
        assert ("/kline/pair-events/{event_id}", "DELETE") in paths
        assert ("/kline/pair-backtest", "GET") in paths

    def test_endpoints_are_mounted_on_app(self):
        try:
            from main import app
        except Exception as e:  # pragma: no cover
            pytest.skip(f"应用无法导入，跳过挂载校验：{e}")
        paths = set(app.openapi().get("paths", {}))
        for p in (
            "/api/ai/xianzhi/kline/pair-events",
            "/api/ai/xianzhi/kline/pair-events/stats",
            "/api/ai/xianzhi/kline/pair-events/{event_id}",
            "/api/ai/xianzhi/kline/pair-backtest",
        ):
            assert p in paths

    def test_happy_path_forwards_every_field(self):
        out = _submit()
        assert out == {"ok": True, "id": "fake-id", "ganzhiYear": 2016}
        row = self.saved[0]
        assert row["polarity"] == 1
        assert row["relation"] == "夫妻"
        assert row["source"] == "自述"
        assert row["note"] == "结婚"
        assert row["sect"] == 2
        assert row["longitude_a"] is None and row["longitude_b"] is None

    def test_builds_both_sides(self):
        """两侧都要起盘校验：任一侧出生信息非法，这一对就没法回测。"""
        _submit()
        assert [b[0] for b in self.built] == [_CHART_A, _CHART_B]

    def test_second_side_invalid_becomes_400(self, monkeypatch):
        from fastapi import HTTPException

        def _boom(birth_time, gender, sect, yun_sect, longitude):
            if birth_time == _CHART_B:
                raise ValueError("出生时间格式不正确")
            return "chart-stub"

        monkeypatch.setattr(xianzhi_kline, "_build_chart", _boom)
        with pytest.raises(HTTPException) as e:
            _submit()
        assert e.value.status_code == 400
        assert not self.saved

    def test_derives_ganzhi_year_from_event_date(self):
        """只给日期时按立春换岁推命理年：2016-01-20 属 2015。"""
        out = _submit(ganzhi_year=None, event_date="2016-01-20")
        assert out["ganzhiYear"] == 2015
        assert self.saved[0]["ganzhi_year"] == 2015

    def test_rejects_mismatched_year_and_date(self):
        """1-2 月的日期按公历年填是最常见的录入错误，必须报错而不是静默改写。"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(ganzhi_year=2016, event_date="2016-01-20")
        assert e.value.status_code == 400
        assert "立春换岁" in e.value.detail
        assert not self.saved

    def test_requires_year_or_date(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(ganzhi_year=None, event_date="")
        assert e.value.status_code == 400

    def test_rejects_unparsable_event_date(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(ganzhi_year=None, event_date="去年双十一")
        assert e.value.status_code == 400
        assert "YYYY-MM-DD" in e.value.detail
        assert not self.saved

    @pytest.mark.parametrize("polarity", [2, -2])
    def test_rejects_bad_polarity(self, polarity):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(polarity=polarity)
        assert e.value.status_code == 400
        assert not self.saved

    def test_rejects_bad_relation(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(relation="夫妻俩")
        assert e.value.status_code == 400

    def test_blank_relation_is_allowed(self):
        """关系类型是可选的复盘切片，不该逼着人先选一个。"""
        out = _submit(relation="")
        assert out["ok"] is True
        assert self.saved[0]["relation"] == ""

    def test_rejects_bad_sect(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(sect=3)
        assert e.value.status_code == 400

    def test_rejects_implausible_year(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(ganzhi_year=20260918)
        assert e.value.status_code == 400

    def test_delete_returns_404_when_missing(self):
        from fastapi import HTTPException

        assert asyncio.run(xianzhi_kline.delete_kline_pair_event_endpoint("id-1")) == {"ok": True}
        with pytest.raises(HTTPException) as e:
            asyncio.run(xianzhi_kline.delete_kline_pair_event_endpoint("missing"))
        assert e.value.status_code == 404
        assert self.ids == ["id-1", "missing"]

    def test_list_endpoint_wraps_items(self, monkeypatch):
        async def _fake_list(a, ga, b, gb, year, limit):
            return [{"id": "1", "ganzhiYear": 2016}]

        monkeypatch.setattr(xianzhi_kline.repo, "list_kline_pair_events", _fake_list)
        out = asyncio.run(xianzhi_kline.list_kline_pair_events_endpoint())
        assert out["count"] == 1
        assert out["items"][0]["ganzhiYear"] == 2016

    def test_list_endpoint_rejects_bad_limit(self):
        from fastapi import HTTPException

        for limit in (0, -1, xianzhi_kline.MAX_BACKTEST_EVENTS + 1):
            with pytest.raises(HTTPException):
                asyncio.run(xianzhi_kline.list_kline_pair_events_endpoint(limit=limit))

    def test_stats_endpoint_forwards(self):
        assert asyncio.run(xianzhi_kline.kline_pair_event_stats_endpoint()) == {}


# ---------------- 合盘回测端点 ----------------


class TestPairBacktestEndpoint:
    @pytest.fixture(autouse=True)
    def _capture_backtest(self, monkeypatch, _never_touch_real_db):
        self.events: list[dict] = []
        self.built: list[tuple] = []
        self.calls: list[dict] = []

        async def _fake_list(a, ga, b, gb, ganzhi_year, limit):
            return list(self.events)

        def _fake_build(birth_time, gender, sect, yun_sect, longitude):
            self.built.append((birth_time, gender, sect, yun_sect, longitude))
            return f"chart::{birth_time}"

        def _fake_run(pairs, *, dimension, min_samples):
            self.calls.append({"pairs": pairs, "dimension": dimension, "min_samples": min_samples})
            return {"summary": {"samples": 0, "ok": False, "hitRate": None}, "warnings": []}

        monkeypatch.setattr(xianzhi_kline.repo, "list_kline_pair_events", _fake_list)
        monkeypatch.setattr(xianzhi_kline, "_build_chart", _fake_build)
        monkeypatch.setattr(xianzhi_kline.kline_backtest, "run_pair_backtest", _fake_run)

    def _event(self, birth_time_b=_CHART_B, **kw):
        row = {
            "birthTimeA": _CHART_A,
            "genderA": "男",
            "birthTimeB": birth_time_b,
            "genderB": "女",
            "sect": 2,
            "yunSect": 1,
            "longitudeA": None,
            "longitudeB": None,
            "ganzhiYear": 2016,
            "polarity": 1,
            "relation": "夫妻",
        }
        row.update(kw)
        return row

    def _run(self, **kw):
        return asyncio.run(xianzhi_kline.run_kline_pair_backtest_endpoint(**kw))

    def test_empty_library_does_not_build_any_chart(self):
        out = self._run()
        assert out["events"]["total"] == 0
        assert out["summary"]["ok"] is False
        assert self.built == []
        assert self.calls == []
        assert any("关系事件库为空" in w for w in out["warnings"])

    def test_groups_events_by_pair(self):
        self.events = [
            self._event(),
            self._event(ganzhiYear=2017),
            self._event(birth_time_b="1988-03-03 06:00", genderB="男"),
        ]
        self._run()
        assert [len(p[2]) for p in self.calls[0]["pairs"]] == [2, 1]
        assert len(self.built) == 4  # 两对各两张盘

    def test_swapped_sides_land_in_one_group(self):
        """录入时谁填在甲是随手的事，同一条关系倒过来录不该变成两组样本。"""
        self.events = [
            self._event(),
            {
                "birthTimeA": _CHART_B,
                "genderA": "女",
                "birthTimeB": _CHART_A,
                "genderB": "男",
                "sect": 2,
                "yunSect": 1,
                "longitudeA": None,
                "longitudeB": None,
                "ganzhiYear": 2017,
                "polarity": 1,
                "relation": "夫妻",
            },
        ]
        self._run()
        assert len(self.calls[0]["pairs"]) == 1
        assert len(self.calls[0]["pairs"][0][2]) == 2

    def test_pair_build_order_is_deterministic(self):
        """同一对每次都要建出同样顺序的两张盘 —— 共振分对称，但要可复现。"""
        forward = self._event()
        backward = {
            "birthTimeA": _CHART_B,
            "genderA": "女",
            "birthTimeB": _CHART_A,
            "genderB": "男",
            "sect": 2,
            "yunSect": 1,
            "longitudeA": None,
            "longitudeB": None,
            "ganzhiYear": 2017,
            "polarity": 1,
            "relation": "夫妻",
        }
        self.events = [forward]
        self._run()
        first = [b[0] for b in self.built]
        self.built.clear()
        self.events = [backward]
        self._run()
        assert [b[0] for b in self.built] == first

    def test_different_sect_is_a_different_pair(self):
        """同两个人换流派就是另一套盘：混在一起会让"预测"与"标注"对不上号。"""
        self.events = [self._event(), self._event(sect=1)]
        self._run()
        assert len(self.calls[0]["pairs"]) == 2

    def test_forwards_options(self):
        self.events = [self._event()]
        self._run(dimension="love", min_samples=5)
        assert self.calls[0]["dimension"] == "love"
        assert self.calls[0]["min_samples"] == 5

    def test_truncates_when_too_many_pairs(self):
        self.events = [self._event(birth_time_b=f"19{80 + i}-01-01 08:00", genderB="女") for i in range(14)]
        out = self._run()
        assert len(self.calls[0]["pairs"]) == xianzhi_kline.MAX_BACKTEST_PAIRS
        assert any("配对过多" in w for w in out["warnings"])

    @pytest.mark.parametrize(
        "kw",
        [
            {"dimension": "nope"},
            {"dimension": "auto"},
            {"min_samples": 0},
            {"min_samples": xianzhi_kline.MAX_BACKTEST_EVENTS + 1},
        ],
    )
    def test_rejects_bad_options(self, kw):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            self._run(**kw)
        assert e.value.status_code == 400

    def test_engine_value_error_becomes_400(self, monkeypatch):
        from fastapi import HTTPException

        def _boom(*a, **kw):
            raise ValueError("dimension 需为 综合/... 之一")

        monkeypatch.setattr(xianzhi_kline.kline_backtest, "run_pair_backtest", _boom)
        self.events = [self._event()]
        with pytest.raises(HTTPException) as e:
            self._run()
        assert e.value.status_code == 400


def test_data_access_exposes_pair_wrappers():
    from app.api import data_access

    for name in (
        "add_kline_pair_event",
        "list_kline_pair_events",
        "delete_kline_pair_event",
        "kline_pair_event_stats",
    ):
        assert callable(getattr(data_access, name)), f"{name} 未包装"


def test_pair_events_do_not_touch_scoring(_never_touch_real_db):
    """关系事件也是只写通道，不得影响确定性评分（单盘或合盘都不许）。"""
    from app.domain import fortune_score as FS, kline_resonance as KR
    from tests.test_kline_backtest import chart_of

    chart_a, chart_b = chart_of("stem_ren"), chart_of("stem_jia")
    before_single = FS.build_kline(chart_a, max_age=30)
    before_pair = KR.build_resonance(chart_a, chart_b, max_age=30)
    _submit()
    assert [c[0] for c in _CALLS] == ["add"], "关系事件未走 repo 层，或走了真实数据库"
    assert FS.build_kline(chart_a, max_age=30) == before_single
    assert KR.build_resonance(chart_a, chart_b, max_age=30) == before_pair
