"""core 配置层单测：KV 注册表语义 + BACKEND_ROOT 路径锚点守卫。

两部分都是「静默出错」高发区：
- KV 未注册时若静默吞掉写入，管理端改了配置却查不到原因；
- BACKEND_ROOT 一旦指错层（本模块曾从 `core/config.py` 移到
  `core/config/settings.py`，硬编码的 `parents[N]` 就会指向 app/），
  .env 与 data/ 会整体漂移且不报任何错 —— 故用断言钉死。
"""

from __future__ import annotations

import importlib

import pytest

from app.core.config import BACKEND_ROOT, kv


class _MemoryStore:
    def __init__(self) -> None:
        self.data: dict = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value


class _BrokenStore:
    def get(self, key, default=None):
        raise RuntimeError("pg unreachable")

    def set(self, key, value) -> None:  # pragma: no cover - 用例不写
        raise RuntimeError("pg unreachable")


# ---------------- BACKEND_ROOT 锚点 ----------------


def test_backend_root_points_at_backend_dir():
    """必须锚在 backend/：指到 app/ 或仓库根都会让 .env 与 data/ 静默错位。"""
    assert BACKEND_ROOT.name == "backend"
    assert (BACKEND_ROOT / "pyproject.toml").is_file()
    assert (BACKEND_ROOT / "app").is_dir()


def test_settings_paths_anchored_under_backend_root():
    """相对路径类配置在 model_validator 里被锚定到 BACKEND_ROOT 下。"""
    from app.core.config import settings

    for name in ("data_dir", "memory_dir", "vector_db_dir"):
        path = getattr(settings, name)
        assert path.is_absolute(), f"{name} 未按绝对路径锚定"
        assert BACKEND_ROOT in path.parents, f"{name} 未落在 backend/ 下：{path}"


def test_env_file_resolves_next_to_backend_root():
    from app.core.config import settings

    assert str(settings.model_config["env_file"]).startswith(str(BACKEND_ROOT))


# ---------------- KV 注册表语义 ----------------


def test_get_config_returns_default_when_store_unregistered(monkeypatch):
    monkeypatch.setattr(kv, "_store", None)
    assert kv.get_config("any_key") is None
    assert kv.get_config("any_key", "fallback") == "fallback"


def test_set_config_raises_when_store_unregistered(monkeypatch):
    """写入静默丢失比报错更难排查 —— 未注册必须抛。"""
    monkeypatch.setattr(kv, "_store", None)
    with pytest.raises(RuntimeError, match="KV 存储未注册"):
        kv.set_config("k", {"v": 1})


def test_registered_store_round_trip(monkeypatch):
    store = _MemoryStore()
    monkeypatch.setattr(kv, "_store", store)

    kv.set_config("chain", {"models": ["m1"]})

    assert store.data["chain"] == {"models": ["m1"]}
    assert kv.get_config("chain") == {"models": ["m1"]}


def test_get_config_swallows_store_errors(monkeypatch):
    """存储抛错（连接池拿不到连接等）必须回退默认值，不得向上冒泡成 500。"""
    monkeypatch.setattr(kv, "_store", _BrokenStore())
    assert kv.get_config("chain") is None
    assert kv.get_config("chain", "default") == "default"


def test_get_config_returns_default_for_missing_key(monkeypatch):
    monkeypatch.setattr(kv, "_store", _MemoryStore())
    assert kv.get_config("absent") is None
    assert kv.get_config("absent", 0) == 0


def test_register_kv_store_is_replaceable(monkeypatch):
    """重复注册为替换语义（幂等），不叠加、不报错。"""
    monkeypatch.setattr(kv, "_store", kv.get_kv_store())  # 用例结束后复原全局注册
    store_a, store_b = _MemoryStore(), _MemoryStore()
    kv.register_kv_store(store_a)
    assert kv.get_kv_store() is store_a
    kv.register_kv_store(store_b)
    assert kv.get_kv_store() is store_b


def test_postgres_kv_store_satisfies_protocol():
    from app.db.kv_store import PostgresKVStore

    assert isinstance(PostgresKVStore(), kv.KVStore)


def test_kv_store_module_registers_on_import(monkeypatch):
    """kv_store 模块体在导入时完成注册（reload 复现导入副作用）。"""
    from app.db import kv_store as kv_store_mod

    monkeypatch.setattr(kv, "_store", None)
    # reload 会重建类对象，须用 reload 后模块里的类做 isinstance，
    # 否则旧引用与新实例的类不是同一个对象，断言恒假。
    reloaded = importlib.reload(kv_store_mod)

    assert isinstance(kv.get_kv_store(), reloaded.PostgresKVStore)
