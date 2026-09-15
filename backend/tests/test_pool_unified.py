"""连接池归属单测：全仓单一池在后，指纹持久化必须走它。

背景：`app/rag/fingerprint.py` 曾用同一 DSN 自建第二个 ConnectionPool，
既多占空闲连接，又让关停要分别关两处。阶段 2-12 后统一到 `app.db.pool`。

注意 `_save_pg` / `_load_pg` 都会吞掉全部异常（仅打日志），所以断言必须落在
"是否真的从共享池借出了连接"上 —— 只断言返回值会让写错的 stub 也能通过。
"""

from __future__ import annotations

import json

from app.db import pool as db_pool
from app.rag import fingerprint


class _FakeCursor:
    def __init__(self, row) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConn:
    """最小连接桩：记录执行过的 SQL 与入参。"""

    def __init__(self, store: dict, row=None) -> None:
        self.store = store
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.store.setdefault("sql", []).append(" ".join(sql.split()))
        if params is not None:
            # _save_pg 用具名参数 dict；_ensure_table 无参数
            self.store["written"] = params["data"] if isinstance(params, dict) else params[0]
        return _FakeCursor(self._row)


class _FakePool:
    """提供 psycopg_pool.ConnectionPool 的 .connection() 契约。"""

    def __init__(self, store: dict, row=None) -> None:
        self.store = store
        self.row = row
        self.borrowed = 0

    def connection(self):
        self.borrowed += 1
        return _FakeConn(self.store, self.row)


def test_fingerprint_pg_write_goes_through_shared_pool(monkeypatch):
    fake = _FakePool({})
    monkeypatch.setattr(fingerprint, "get_pool", lambda: fake)

    fingerprint._save_pg({"docs_hash": "abc", "meta_version": 2})

    assert fake.borrowed == 1, "未从共享池借出连接（说明仍在用自有池或压根没连）"
    assert json.loads(fake.store["written"])["docs_hash"] == "abc"
    assert any("rag_fingerprint" in sql for sql in fake.store["sql"]), "未落到指纹表"


def test_fingerprint_pg_read_goes_through_shared_pool(monkeypatch):
    payload = {"docs_hash": "abc", "meta_version": 2}
    fake = _FakePool({}, row=(json.dumps(payload),))
    monkeypatch.setattr(fingerprint, "get_pool", lambda: fake)

    assert fingerprint._load_pg() == payload
    assert fake.borrowed == 1


def test_fingerprint_pg_read_accepts_native_dict_row(monkeypatch):
    """jsonb 列由 psycopg 反序列化成 dict 时也能直接返回。"""
    payload = {"docs_hash": "native"}
    fake = _FakePool({}, row=(payload,))
    monkeypatch.setattr(fingerprint, "get_pool", lambda: fake)

    assert fingerprint._load_pg() == payload


def test_fingerprint_pg_failure_degrades_to_none(monkeypatch):
    """共享池不可用时必须吞异常返回 None，让上层回退本地文件。"""

    def _broken():
        raise RuntimeError("pool closed")

    monkeypatch.setattr(fingerprint, "get_pool", _broken)
    assert fingerprint._load_pg() is None


def test_fingerprint_get_pool_is_shared_pool():
    """指纹模块绑定的 get_pool 就是 app.db.pool.get_pool 本体。"""
    assert fingerprint.get_pool is db_pool.get_pool


def test_fingerprint_has_no_own_pool_state():
    """指纹模块不得再残留自有池/锁/关闭函数。"""
    for attr in ("_fp_pool", "_fp_lock", "_fp_pool_get", "close_pool"):
        assert not hasattr(fingerprint, attr), f"{attr} 应已随池统一删除"


def test_memory_layer_reuses_shared_pool():
    """记忆层同样只用共享池，且不再暴露自己的关闭函数。"""
    from app.memory import postgres_memory

    assert postgres_memory._get_pool is db_pool.get_pool
    assert not hasattr(postgres_memory, "close_global_conn"), "关停应统一走 db.pool"


def test_close_pool_is_idempotent(monkeypatch):
    """重复关闭不得报错（关停顺序变化时会重复调用）。"""
    closed: list[bool] = []

    class _Closable:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(db_pool, "pg_pool", _Closable())
    db_pool.close_pool()
    assert closed == [True]
    assert db_pool.pg_pool is None

    db_pool.close_pool()  # 已是 None，再关一次应静默
    assert closed == [True]
