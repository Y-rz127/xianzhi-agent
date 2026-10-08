"""事件标注的存储层 SQL + 接口契约 + 回测端点。

同 `test_kline_feedback`：不连真实 PostgreSQL，用 FakePool 验 SQL 与参数；
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
    for name in ("add_kline_event", "list_kline_events", "delete_kline_event", "kline_event_stats")
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
    """返回 (calls, install)：calls 收集 SQL，install 可在用例内换返回行。"""
    calls: list = []
    monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)

    def install(row=None, rows=None):
        pool = _FakePool(calls, row, rows)
        monkeypatch.setattr(chart_store, "get_pool", lambda: pool)
        return pool

    install()
    return calls, install


# 本文件任何测试都不许碰真实 PostgreSQL（同 feedback 的教训：类级 autouse 管不到模块级用例）。
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

    monkeypatch.setattr(xianzhi_kline.repo, "add_kline_event", _add)
    monkeypatch.setattr(xianzhi_kline.repo, "list_kline_events", _list)
    monkeypatch.setattr(xianzhi_kline.repo, "delete_kline_event", _delete)
    monkeypatch.setattr(xianzhi_kline.repo, "kline_event_stats", _stats)
    # 建盘 0.35s/次，接口用例不需要真盘
    monkeypatch.setattr(xianzhi_kline, "_build_chart", lambda *a, **kw: "chart-stub")
    _CALLS.clear()
    yield


def test_module_guard_blocks_real_db_writes(_never_touch_real_db):
    """守卫自检：repo 四个入口必须都已被换成 stub（`xianzhi_kline.repo` 与 data_access 同一对象，
    两者互比是假测试，故与导入期抓取的原始函数比）。"""
    for name in ("add_kline_event", "list_kline_events", "delete_kline_event", "kline_event_stats"):
        assert getattr(xianzhi_kline.repo, name) is not _ORIGINAL_REPO[name], f"{name} 没被守卫换掉"
    assert asyncio.run(xianzhi_kline.repo.add_kline_event("x", "男", 2026, 1)) == "stub-id"
    assert _CALLS[-1][0] == "add"


# ---------------- 存储层 ----------------


class TestAddKlineEvent:
    def _add(self, **overrides):
        kwargs = {
            "birth_time": "1990-05-20 14:30",
            "gender": "男",
            "ganzhi_year": 2016,
            "polarity": 1,
            "sect": 2,
            "yun_sect": 1,
            "longitude": None,
            "event_date": "2016-06-18",
            "domain": "career",
            "source": "自述",
            "note": "晋升",
            "case_id": "case-1",
        }
        kwargs.update(overrides)
        return chart_store.add_kline_event(**kwargs)

    def test_inserts_with_expected_columns_and_params(self, store):
        calls, _ = store
        eid = self._add()
        assert isinstance(eid, str) and len(eid) == 36
        sql, params = calls[-1]
        assert "INSERT INTO kline_events" in sql
        for col in (
            "chart_hash",
            "birth_time",
            "gender",
            "sect",
            "yun_sect",
            "longitude",
            "ganzhi_year",
            "event_date",
            "polarity",
            "domain",
            "source",
            "note",
            "case_id",
        ):
            assert col in sql, f"INSERT 缺少列 {col}"
        assert params[0] == eid
        assert params[2] == "1990-05-20 14:30"
        assert params[3] == "男"
        assert params[7] == 2016
        assert params[8] == datetime.date(2016, 6, 18)
        assert params[9] == 1
        assert params[10] == "career"

    def test_chart_hash_covers_birth_and_gender(self, store):
        calls, _ = store
        self._add()
        assert calls[-1][1][1] == chart_store._chart_hash("1990-05-20 14:30", "男")
        self._add(gender="女")
        assert calls[-1][1][1] != chart_store._chart_hash("1990-05-20 14:30", "男")

    def test_event_date_accepts_date_object_and_blank(self, store):
        calls, _ = store
        self._add(event_date=datetime.date(2016, 6, 18))
        assert calls[-1][1][8] == datetime.date(2016, 6, 18)
        self._add(event_date="")
        assert calls[-1][1][8] is None

    @pytest.mark.parametrize("polarity", [2, -2, 5])
    def test_rejects_out_of_range_polarity(self, store, polarity):
        with pytest.raises(ValueError):
            self._add(polarity=polarity)

    def test_rejects_bool_and_str_polarity(self, store):
        """`True` 是 int 子类，不单独挡就会被当成 1（吉）写进去。"""
        with pytest.raises(ValueError):
            self._add(polarity=True)
        with pytest.raises(ValueError):
            self._add(polarity="1")

    def test_zero_polarity_is_valid(self, store):
        """0（平）是合法标注："那年没大事"本身就是一种可验证的断言。"""
        calls, _ = store
        self._add(polarity=0)
        assert calls[-1][1][9] == 0

    @pytest.mark.parametrize("year", [0, 20260918, 999, 3001])
    def test_rejects_implausible_ganzhi_year(self, store, year):
        with pytest.raises(ValueError):
            self._add(ganzhi_year=year)

    def test_rejects_bool_ganzhi_year(self, store):
        with pytest.raises(ValueError):
            self._add(ganzhi_year=True)


class TestListKlineEvents:
    def test_no_filter_lists_recent(self, store):
        calls, _ = store
        chart_store.list_kline_events(limit=10)
        sql, params = calls[-1]
        assert "FROM kline_events" in sql
        assert "WHERE 1 = 1" in sql
        assert params == [10]

    def test_filters_by_chart_year_and_domain(self, store):
        calls, _ = store
        chart_store.list_kline_events("1990-05-20 14:30", "男", 2016, "career", limit=5)
        sql, params = calls[-1]
        assert "chart_hash = %s" in sql
        assert "ganzhi_year = %s" in sql
        assert "domain = %s" in sql
        assert params == [chart_store._chart_hash("1990-05-20 14:30", "男"), 2016, "career", 5]

    def test_returns_rebuild_params(self, store):
        """回测要原样重建命盘，故列表必须带 sect/yun_sect/longitude。"""
        calls, install = store
        install(
            rows=[
                (
                    "id-1",
                    "1990-05-20 14:30",
                    "男",
                    1,
                    2,
                    116.4,
                    2016,
                    datetime.date(2016, 6, 18),
                    1,
                    "career",
                    "自述",
                    "晋升",
                    "",
                    None,
                ),
            ]
        )
        item = chart_store.list_kline_events()[0]
        assert item["sect"] == 1
        assert item["yun_sect"] == 2
        assert item["longitude"] == 116.4
        assert item["ganzhiYear"] == 2016
        assert item["eventDate"] == "2016-06-18"

    def test_empty_date_and_created_at_are_blank(self, store):
        calls, install = store
        install(rows=[("id-1", "b", "男", None, None, None, 2020, None, -1, "", "", "", "", None)])
        item = chart_store.list_kline_events()[0]
        assert item["eventDate"] == ""
        assert item["createdAt"] is None
        assert item["sect"] == 2 and item["yun_sect"] == 1  # 空值回落默认流派

    def test_returns_empty_on_error(self, monkeypatch):
        class _Boom:
            def connection(self):
                raise RuntimeError("db down")

        monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)
        monkeypatch.setattr(chart_store, "get_pool", lambda: _Boom())
        assert chart_store.list_kline_events() == []


class TestDeleteKlineEvent:
    def test_deletes_and_reports_true(self, store):
        calls, _ = store
        assert chart_store.delete_kline_event("id-1") is True
        sql, params = calls[-1]
        assert "DELETE FROM kline_events" in sql
        assert params == ("id-1",)

    def test_reports_false_when_nothing_deleted(self, monkeypatch):
        calls: list = []

        class _Cursor:
            rowcount = 0

            def execute(self, sql, params=None):
                calls.append((sql, params))
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
        assert chart_store.delete_kline_event("nope") is False


class TestKlineEventStats:
    def test_maps_every_aggregate(self, monkeypatch):
        """统计函数有 5 次查询，必须按 SQL 分派返回行 —— 共用一批行会串味。"""
        calls: list = []
        rows_by_sql = {
            "GROUP BY polarity": [(1, 7), (-1, 5), (0, 2)],
            "GROUP BY domain": [("career", 9), ("health", 3)],
            "GROUP BY birth_time": [("1990-05-20 14:30", "男", 8, 2001, 2026)],
        }
        scalars = {
            "COUNT(DISTINCT chart_hash)": (14, 3, 9),
            "MIN(ganzhi_year)": (2001, 2026),
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
        out = chart_store.kline_event_stats()
        assert out["total"] == 14
        assert out["charts"] == 3
        assert out["yearCount"] == 9
        assert out["yearFrom"] == 2001 and out["yearTo"] == 2026
        assert out["byPolarity"][0] == {"polarity": 1, "count": 7}
        assert out["byDomain"] == [{"domain": "career", "count": 9}, {"domain": "health", "count": 3}]
        assert out["byChart"][0] == {
            "birthTime": "1990-05-20 14:30",
            "gender": "男",
            "count": 8,
            "yearFrom": 2001,
            "yearTo": 2026,
        }

    def test_returns_empty_dict_on_error(self, monkeypatch):
        class _Boom:
            def connection(self):
                raise RuntimeError("db down")

        monkeypatch.setattr(chart_store, "_ensure_tables", lambda: None)
        monkeypatch.setattr(chart_store, "get_pool", lambda: _Boom())
        assert chart_store.kline_event_stats() == {}


# ---------------- 接口契约 ----------------


def _event_body(**overrides):
    kwargs = {
        "birth_time": "1990-05-20 14:30",
        "gender": "男",
        "sect": 2,
        "yun_sect": 1,
        "longitude": None,
        "ganzhi_year": 2016,
        "event_date": "",
        "polarity": 1,
        "domain": "career",
        "source": "自述",
        "note": "晋升",
        "case_id": "",
    }
    kwargs.update(overrides)
    return xianzhi_kline.KlineEventRequest(**kwargs)


def _submit(**overrides):
    return asyncio.run(xianzhi_kline.submit_kline_event(_event_body(**overrides)))


class TestEventEndpoint:
    @pytest.fixture(autouse=True)
    def _capture_repo(self, monkeypatch, _never_touch_real_db):
        """显式依赖模块级守卫，保证本桩装在其后（否则会被覆盖回 stub-id）。"""
        self.saved: list = []
        self.ids: list = []

        async def _fake_add(birth_time, gender, ganzhi_year, polarity, **kw):
            self.saved.append(
                {
                    "birth_time": birth_time,
                    "gender": gender,
                    "ganzhi_year": ganzhi_year,
                    "polarity": polarity,
                    **kw,
                }
            )
            return "fake-id"

        async def _fake_delete(event_id):
            self.ids.append(event_id)
            return event_id != "missing"

        monkeypatch.setattr(xianzhi_kline.repo, "add_kline_event", _fake_add)
        monkeypatch.setattr(xianzhi_kline.repo, "delete_kline_event", _fake_delete)

    def test_router_declares_event_paths(self):
        paths = {(r.path, m) for r in xianzhi_kline.router.routes for m in getattr(r, "methods", set())}
        assert ("/kline/events", "POST") in paths
        assert ("/kline/events", "GET") in paths
        assert ("/kline/events/stats", "GET") in paths
        assert ("/kline/events/{event_id}", "DELETE") in paths
        assert ("/kline/backtest", "GET") in paths

    def test_endpoints_are_mounted_on_app(self):
        try:
            from main import app
        except Exception as e:  # pragma: no cover
            pytest.skip(f"应用无法导入，跳过挂载校验：{e}")
        paths = set(app.openapi().get("paths", {}))
        for p in (
            "/api/ai/xianzhi/kline/events",
            "/api/ai/xianzhi/kline/events/stats",
            "/api/ai/xianzhi/kline/events/{event_id}",
            "/api/ai/xianzhi/kline/backtest",
        ):
            assert p in paths

    def test_happy_path_forwards_every_field(self):
        out = _submit()
        assert out == {"ok": True, "id": "fake-id", "ganzhiYear": 2016}
        assert self.saved[0]["polarity"] == 1
        assert self.saved[0]["domain"] == "career"
        assert self.saved[0]["source"] == "自述"
        assert self.saved[0]["note"] == "晋升"
        assert self.saved[0]["sect"] == 2

    def test_derives_ganzhi_year_from_event_date(self):
        """只给日期时按立春换岁推命理年：2016-01-20 属 2015。"""
        out = _submit(ganzhi_year=None, event_date="2016-01-20")
        assert out["ganzhiYear"] == 2015
        assert self.saved[0]["ganzhi_year"] == 2015

    def test_rejects_mismatched_year_and_date(self):
        """1-2 月的事件按公历年填是最常见的录入错误，必须报错而不是静默改写。"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(ganzhi_year=2016, event_date="2016-01-20")
        assert e.value.status_code == 400
        assert "立春换岁" in e.value.detail
        assert not self.saved

    def test_accepts_matching_year_and_date(self):
        out = _submit(ganzhi_year=2015, event_date="2016-01-20")
        assert out["ganzhiYear"] == 2015

    def test_requires_year_or_date(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(ganzhi_year=None, event_date="")
        assert e.value.status_code == 400

    def test_rejects_unparsable_event_date(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(ganzhi_year=None, event_date="二〇一六年")
        assert e.value.status_code == 400
        # 报错要说"该填什么格式"，不要把标准库的 `Invalid isoformat string` 透出去
        assert "YYYY-MM-DD" in e.value.detail
        assert "isoformat" not in e.value.detail

    @pytest.mark.parametrize("polarity", [2, -2])
    def test_rejects_bad_polarity(self, polarity):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(polarity=polarity)
        assert e.value.status_code == 400
        assert not self.saved

    def test_rejects_bad_domain(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(domain="nope")
        assert e.value.status_code == 400

    def test_rejects_bad_sect(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(sect=3)
        assert e.value.status_code == 400

    def test_rejects_implausible_year_range(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _submit(ganzhi_year=20260918)
        assert e.value.status_code == 400

    def test_invalid_birth_info_becomes_400(self, monkeypatch):
        """录一条回测不了的标注没有意义，故建盘失败要拦在写库之前。"""
        from fastapi import HTTPException

        def _boom(*a, **kw):
            raise ValueError("出生时间格式不正确")

        monkeypatch.setattr(xianzhi_kline, "_build_chart", _boom)
        with pytest.raises(HTTPException) as e:
            _submit()
        assert e.value.status_code == 400
        assert not self.saved

    def test_delete_returns_404_when_missing(self):
        from fastapi import HTTPException

        assert asyncio.run(xianzhi_kline.delete_kline_event_endpoint("id-1")) == {"ok": True}
        with pytest.raises(HTTPException) as e:
            asyncio.run(xianzhi_kline.delete_kline_event_endpoint("missing"))
        assert e.value.status_code == 404
        assert self.ids == ["id-1", "missing"]

    def test_list_endpoint_wraps_items(self, monkeypatch):
        async def _fake_list(birth_time, gender, ganzhi_year, domain, limit):
            return [{"id": "1", "ganzhiYear": 2016}]

        monkeypatch.setattr(xianzhi_kline.repo, "list_kline_events", _fake_list)
        out = asyncio.run(xianzhi_kline.list_kline_events_endpoint())
        assert out["count"] == 1
        assert out["items"][0]["ganzhiYear"] == 2016

    def test_list_endpoint_rejects_bad_filters(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            asyncio.run(xianzhi_kline.list_kline_events_endpoint(domain="nope"))
        for limit in (0, -1, xianzhi_kline.MAX_BACKTEST_EVENTS + 1):
            with pytest.raises(HTTPException):
                asyncio.run(xianzhi_kline.list_kline_events_endpoint(limit=limit))

    def test_stats_endpoint_forwards(self):
        assert asyncio.run(xianzhi_kline.kline_event_stats_endpoint()) == {}


# ---------------- 回测端点 ----------------


class TestBacktestEndpoint:
    @pytest.fixture(autouse=True)
    def _capture_backtest(self, monkeypatch, _never_touch_real_db):
        self.events: list[dict] = []
        self.built: list[tuple] = []
        self.calls: list[dict] = []

        async def _fake_list(birth_time, gender, ganzhi_year, domain, limit):
            return list(self.events)

        def _fake_build(birth_time, gender, sect, yun_sect, longitude):
            self.built.append((birth_time, gender, sect, yun_sect, longitude))
            return f"chart::{birth_time}"

        def _fake_run(pairs, *, dimension, predictor, min_samples):
            self.calls.append(
                {
                    "pairs": pairs,
                    "dimension": dimension,
                    "predictor": predictor,
                    "min_samples": min_samples,
                }
            )
            return {"summary": {"samples": 0, "ok": False, "hitRate": None}, "warnings": []}

        monkeypatch.setattr(xianzhi_kline.repo, "list_kline_events", _fake_list)
        monkeypatch.setattr(xianzhi_kline, "_build_chart", _fake_build)
        monkeypatch.setattr(xianzhi_kline.kline_backtest, "run_backtest", _fake_run)

    def _event(self, birth_time="1990-05-20 14:30", **kw):
        row = {
            "birth_time": birth_time,
            "gender": "男",
            "sect": 2,
            "yun_sect": 1,
            "longitude": None,
            "ganzhiYear": 2016,
            "polarity": 1,
            "domain": "general",
        }
        row.update(kw)
        return row

    def _run(self, **kw):
        return asyncio.run(xianzhi_kline.run_kline_backtest_endpoint(**kw))

    def test_empty_library_does_not_build_any_chart(self):
        out = self._run()
        assert out["events"]["total"] == 0
        assert out["summary"]["ok"] is False
        assert self.built == []
        assert self.calls == []
        assert any("事件库为空" in w for w in out["warnings"])

    def test_groups_events_by_chart_identity(self):
        self.events = [self._event(), self._event(ganzhiYear=2017), self._event(birth_time="1985-01-01 08:00")]
        self._run()
        assert len(self.built) == 2
        assert [len(p[1]) for p in self.calls[0]["pairs"]] == [2, 1]

    def test_different_sect_is_a_different_chart(self):
        """同一个人换流派就是另一张盘：混在一起会让"预测"与"标注"对不上号。"""
        self.events = [self._event(), self._event(sect=1)]
        self._run()
        assert len(self.built) == 2

    def test_forwards_options(self):
        self.events = [self._event()]
        self._run(dimension="wealth", predictor="mean", min_samples=5)
        assert self.calls[0]["dimension"] == "wealth"
        assert self.calls[0]["predictor"] == "mean"
        assert self.calls[0]["min_samples"] == 5

    def test_truncates_when_too_many_charts(self):
        self.events = [self._event(birth_time=f"19{80 + i}-01-01 08:00") for i in range(25)]
        self.events[0]["domain"] = "career"
        self.events[1]["domain"] = "wealth"
        self.events[0]["ganzhiYear"] = 2016
        self.events[1]["ganzhiYear"] = 2017
        out = self._run()
        assert len(self.built) == xianzhi_kline.MAX_BACKTEST_CHARTS
        assert any("命盘过多" in w for w in out["warnings"])

    @pytest.mark.parametrize(
        "kw",
        [
            {"dimension": "nope"},
            {"predictor": "nope"},
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
            raise ValueError("dimension 需为 auto/... 之一")

        monkeypatch.setattr(xianzhi_kline.kline_backtest, "run_backtest", _boom)
        self.events = [self._event()]
        with pytest.raises(HTTPException) as e:
            self._run()
        assert e.value.status_code == 400


def test_data_access_exposes_event_wrappers():
    from app.api import data_access

    for name in ("add_kline_event", "list_kline_events", "delete_kline_event", "kline_event_stats"):
        assert callable(getattr(data_access, name)), f"{name} 未包装"


def test_events_do_not_touch_scoring(_never_touch_real_db):
    """事件标注是只写通道，不得影响确定性评分。"""
    from app.domain import fortune_score as FS
    from tests.test_kline_backtest import chart_of

    chart = chart_of("stem_ren")
    before = FS.build_kline(chart, max_age=30)
    _submit()
    assert [c[0] for c in _CALLS] == ["add"], "事件未走 repo 层，或走了真实数据库"
    assert FS.build_kline(chart, max_age=30) == before
