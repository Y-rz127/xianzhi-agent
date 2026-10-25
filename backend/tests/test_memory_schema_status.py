"""记忆层建表失败的两类区分（回归，不需要真实 PG）。

背景：2026-10-25 本机 Windows 智能应用控制拦住 `sqlalchemy/sql/_util_cy.pyd`，
`langchain_postgres` 导不进来，`_ensure_schema` 把 ImportError 也当成"数据库暂不可达，
将重试"，于是：

- 日志说"将重试"，其实重试一万次也不会好（依赖层坏了）；
- 服务"启动成功"，但一句对话都存不下（PG 探测走裸 psycopg，还是绿的）。

所以这里把两类失败钉开：
① ImportError → `fatal` 非空、进程内不再重试、日志走 ERROR；
② 连接失败 → 只记 WARNING，保留重试（DB 晚点起来还能自愈）。
"""

from __future__ import annotations

import pytest

from app.memory import postgres_memory as pg


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return self


class _Pool:
    def __init__(self, exc: Exception | None = None, calls: list | None = None):
        self._exc = exc
        self.calls = calls if calls is not None else []

    def connection(self):
        self.calls.append(1)
        if self._exc is not None:
            raise self._exc
        return _Conn()


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """每个用例从"未初始化"状态开始。"""
    monkeypatch.setattr(pg, "_schema_ready", False)
    monkeypatch.setattr(pg, "_schema_fatal", "")


def _patch_schema_sql(monkeypatch):
    """用假模块顶掉 langchain_postgres，只保留我们自己那几条建表 SQL 的执行。

    注意不能真去 import 它：这组用例的起因就是它导不进来（原生扩展被策略拦），
    真 import 会让测试在本机上直接挂掉。
    """
    import sys
    import types

    module = types.ModuleType("langchain_postgres")

    class _History:
        @staticmethod
        def create_tables(conn, table_name):
            return None

    module.PostgresChatMessageHistory = _History
    monkeypatch.setitem(sys.modules, "langchain_postgres", module)


def test_import_error_is_fatal_and_not_retried(monkeypatch):
    calls: list = []
    # 模拟"原生扩展被策略拦"：真正抛错的是 import，但异常类型是关键
    monkeypatch.setattr(
        pg, "_get_pool", lambda: _Pool(ImportError("DLL load failed while importing _util_cy"), calls)
    )

    pg._ensure_schema()
    status = pg.memory_schema_status()

    assert status["ready"] is False
    assert "_util_cy" in status["fatal"]

    # 进程内不再重试：第二次调用不该再碰连接池（否则日志会被刷爆）
    pg._ensure_schema()
    assert len(calls) == 1


def test_connection_error_stays_retryable(monkeypatch):
    calls: list = []
    pool = _Pool(RuntimeError("connection refused"), calls)
    monkeypatch.setattr(pg, "_get_pool", lambda: pool)

    pg._ensure_schema()
    status = pg.memory_schema_status()

    assert status["ready"] is False
    assert status["fatal"] == ""  # 可自愈：不标记为 fatal

    # 数据库恢复后能自愈：把连接错误去掉，再调一次应建表成功
    pool._exc = None
    _patch_schema_sql(monkeypatch)
    pg._ensure_schema()

    status = pg.memory_schema_status()
    assert status["ready"] is True
    assert status["fatal"] == ""
    assert len(calls) == 2


def test_status_shape_for_health_endpoint():
    status = pg.memory_schema_status()
    assert set(status) == {"ready", "fatal"}
