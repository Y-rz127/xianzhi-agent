"""管理端候选模型清单接口单测（不联网、不依赖 PG）。

背景：候选模型原先是 `llm_chain.py` 里的硬编码常量，管理端只能点不能删；
现改为落库 `app_config.llm_candidates`，管理端可增删（删掉某个候选只是去掉快捷提示，
不影响降级链）。本模块钉死以下几件事：

1. `_clean_models` 的规范化与校验（去空/去重/保持顺序/非法名报 400/非数组报 400）；
2. 回退语义：从未配置 → 内置默认候选；配置过空清单 → 就是空（不回弹默认）；
3. `PUT /candidates` 落库键名与返回体，且不碰 `llm_failover_chain`（删候选不得影响降级链）；
4. 候选数量上限。
5. GET /chain 带 `default_candidates`，管理端「恢复默认」据此回填。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api import llm_chain
from app.core.config import kv as kv_config


class _MemoryKVStore:
    """内存 KV 存储：替代 PG 版，供接口单测使用。"""

    def __init__(self, data: dict | None = None) -> None:
        self.data: dict = data if data is not None else {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value


def _patch_config(monkeypatch, store: dict) -> _MemoryKVStore:
    """把 KV 读写换成内存字典。

    走真实注册表（替换 ``kv_config._store``）而非打桩 ``get_config`` ——
    这样 ``get_config`` 的异常兜底与 ``set_config`` 的未注册校验也在覆盖范围内。
    """
    mem = _MemoryKVStore(store)
    monkeypatch.setattr(kv_config, "_store", mem)
    return mem


# ---------------- 1. _clean_models ----------------
def test_clean_models_trims_and_dedupes_keeping_order():
    assert llm_chain._clean_models([" b ", "a", "", "  ", "b", "c"]) == ["b", "a", "c"]


def test_clean_models_rejects_non_list():
    with pytest.raises(HTTPException) as ei:
        llm_chain._clean_models("qwen3.8-27b")
    assert ei.value.status_code == 400


@pytest.mark.parametrize("bad", ["has space", "has\ttab", "x" * 65])
def test_clean_models_rejects_bad_name(bad):
    with pytest.raises(HTTPException) as ei:
        llm_chain._clean_models([bad])
    assert ei.value.status_code == 400


# ---------------- 2. 回退语义 ----------------
def test_candidates_unconfigured_falls_back_to_defaults(monkeypatch):
    """从未配置过（PG 无该 key）→ 内置默认候选。"""
    for stored in (None, {}):
        _patch_config(monkeypatch, stored)
        assert llm_chain.get_candidates() == llm_chain.DEFAULT_CANDIDATE_MODELS


def test_candidates_prefer_stored(monkeypatch):
    _patch_config(monkeypatch, {"llm_candidates": {"models": ["my-model", "other"]}})
    assert llm_chain.get_candidates() == ["my-model", "other"]


def test_candidates_stored_empty_stays_empty(monkeypatch):
    """配置过空清单 → 就是空（不能把管理端删掉的模型又"回退"出来）。"""
    _patch_config(monkeypatch, {"llm_candidates": {"models": []}})
    assert llm_chain.get_candidates() == []


def test_candidates_config_read_error_falls_back(monkeypatch):
    """PG 不可达（get_config 抛错）时不得 500，回退默认候选。"""

    def boom(key, default=None):
        raise RuntimeError("pg down")

    monkeypatch.setattr(kv_config, "get_config", boom)
    assert llm_chain.get_candidates() == llm_chain.DEFAULT_CANDIDATE_MODELS


def test_candidates_store_query_error_falls_back(monkeypatch):
    """存储内部抛错（如连接池拿不到连接）同样回退默认候选 —— 真实 PG 不可达即走此路径。"""

    class _BrokenStore:
        def get(self, key, default=None):
            raise RuntimeError("connection refused")

        def set(self, key, value) -> None:  # pragma: no cover - 本用例不写
            raise RuntimeError("connection refused")

    monkeypatch.setattr(kv_config, "_store", _BrokenStore())
    assert llm_chain.get_candidates() == llm_chain.DEFAULT_CANDIDATE_MODELS


# ---------------- 3. 增删落库，且不动降级链 ----------------
def test_update_candidates_persists_and_returns_list(monkeypatch):
    store: dict = {}
    _patch_config(monkeypatch, store)

    out = asyncio.run(llm_chain.update_candidates({"models": ["qwen3.8-max-0902", "kimi-k3"]}))

    assert out == {"candidates": ["qwen3.8-max-0902", "kimi-k3"]}
    assert store["llm_candidates"] == {"models": ["qwen3.8-max-0902", "kimi-k3"]}
    # 删候选不得顺手写降级链
    assert "llm_failover_chain" not in store


def test_remove_candidate_keeps_others_and_chain_untouched(monkeypatch):
    """模拟界面点 × 删掉一个候选：只改 llm_candidates。"""
    store: dict = {
        "llm_candidates": {"models": ["qwen3.8-max-0902", "qwen3.8-2.4t-a95b", "kimi-k3"]},
        "llm_failover_chain": {"models": ["qwen3.8-max-0902", "qwen3.8-27b"]},
    }
    _patch_config(monkeypatch, store)
    remaining = [c for c in llm_chain.get_candidates() if c != "qwen3.8-2.4t-a95b"]

    out = asyncio.run(llm_chain.update_candidates({"models": remaining}))

    assert out == {"candidates": ["qwen3.8-max-0902", "kimi-k3"]}
    assert store["llm_failover_chain"] == {"models": ["qwen3.8-max-0902", "qwen3.8-27b"]}


def test_clear_candidates_stays_empty(monkeypatch):
    """删光候选 → 存空清单，读回来就是空（不回弹默认）。"""
    store: dict = {"llm_candidates": {"models": ["only-one"]}}
    _patch_config(monkeypatch, store)

    out = asyncio.run(llm_chain.update_candidates({"models": []}))

    assert out == {"candidates": []}
    assert store["llm_candidates"] == {"models": []}


# ---------------- 5. 管理端读到的结构 ----------------
def test_get_chain_exposes_defaults_for_restore(monkeypatch):
    """GET /chain 要带上 default_candidates，管理端「恢复默认」才有数据可用。"""
    _patch_config(monkeypatch, {"llm_candidates": {"models": ["only-one"]}})
    monkeypatch.setattr(llm_chain, "get_active_chain", lambda: ["only-one"])
    out = asyncio.run(llm_chain.get_chain())
    assert out["models"] == ["only-one"]
    assert out["candidates"] == ["only-one"]
    assert out["default_candidates"] == llm_chain.DEFAULT_CANDIDATE_MODELS


def test_restore_defaults_round_trip(monkeypatch):
    """点「恢复默认」= 把 default_candidates 存回去。"""
    store: dict = {"llm_candidates": {"models": []}}
    _patch_config(monkeypatch, store)
    out = asyncio.run(llm_chain.update_candidates({"models": llm_chain.DEFAULT_CANDIDATE_MODELS}))
    assert out["candidates"] == llm_chain.DEFAULT_CANDIDATE_MODELS


# ---------------- 4. 上限 ----------------
def test_update_candidates_rejects_too_many(monkeypatch):
    _patch_config(monkeypatch, {})
    too_many = [f"m{i}" for i in range(llm_chain._MAX_CANDIDATE_LEN + 1)]
    with pytest.raises(HTTPException) as ei:
        asyncio.run(llm_chain.update_candidates({"models": too_many}))
    assert ei.value.status_code == 400
