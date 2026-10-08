"""运行时 KV 配置访问（core 层，零业务依赖）。

具体存储由 infra 层在**导入时注册**（见 `app/db/kv_store.py` 的 ``PostgresKVStore``）：
本模块只认 ``KVStore`` 协议，不 import 任何存储实现 ——
这是「core 不得反向依赖 db」铁律的落点（原实现 core 函数内 import db.app_config）。

未注册存储、key 不存在或存储抛错时，``get_config`` 一律返回 default，
与原先「PG 不可达即回退默认值」的行为一致。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class KVStore(Protocol):
    """键值配置存储协议。实现方须自行保证线程安全与异常隔离。"""

    def get(self, key: str, default: Any = None) -> Any: ...

    def set(self, key: str, value: Any) -> None: ...


_store: KVStore | None = None


def register_kv_store(store: KVStore) -> None:
    """注册（替换）全局 KV 存储。由 infra 层在模块导入时调用，幂等。"""
    global _store
    _store = store


def get_kv_store() -> KVStore | None:
    """当前已注册的存储；未注册返回 None（供诊断/测试断言用）。"""
    return _store


def reset_kv_store() -> None:
    """清空注册（仅测试用）。"""
    global _store
    _store = None


def get_config(key: str, default=None):
    """读取配置；存储未注册、key 不存在或读取失败均返回 default。"""
    store = _store
    if store is None:
        return default
    try:
        return store.get(key, default)
    except Exception:
        return default


def set_config(key: str, value) -> None:
    """写入（UPSERT）配置。

    存储未注册时抛 RuntimeError —— 配置写入静默丢失比报错更难排查。
    """
    store = _store
    if store is None:
        raise RuntimeError("KV 存储未注册：请确认 infra 层 app.db.kv_store 已被导入")
    store.set(key, value)
