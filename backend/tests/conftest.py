"""测试全局夹具：默认关闭付费配额/外部网络，并隔离进程级全局状态。

集成测试必须显式配置 TEST_POSTGRES_CONNECTION_STRING（独立测试库）才会运行，
避免启动应用 lifespan 时对开发库执行保留期清理等写操作。
"""
from __future__ import annotations

import os
import socket

import pytest

from app.core.config import settings

_TEST_DSN = (os.environ.get("TEST_POSTGRES_CONNECTION_STRING") or "").strip()
_TEST_REDIS = (os.environ.get("TEST_REDIS_URL") or "").strip()

# conftest 先于测试模块导入：这里覆盖后，main.py 的 lifespan 才会连测试库
if _TEST_DSN:
    settings.postgres_connection_string = _TEST_DSN
if _TEST_REDIS:
    settings.redis_url = _TEST_REDIS


@pytest.fixture(autouse=True)
def _isolate_runtime(monkeypatch):
    """关闭计费/外部初始化，并重置进程级可变状态，避免用例互相污染。"""
    monkeypatch.setattr(settings, "llm_chain_probe_enabled", False)
    monkeypatch.setattr(settings, "message_retention_days", 0)
    monkeypatch.setattr(settings, "rag_init_enabled", False)
    monkeypatch.setattr(settings, "checkpoint_enabled", False)
    # 单测不启动 MCP 子进程、不初始化 LangSmith（避免 npx/网络拖慢与副作用）
    monkeypatch.setattr(settings, "amap_maps_api_key", "")
    monkeypatch.setattr(settings, "langsmith_tracing", False)
    for name in (
        "paid_quota_report_daily",
        "paid_quota_asr_daily",
        "paid_quota_tts_daily",
        "paid_quota_interpret_daily",
        "paid_quota_guest_daily",
    ):
        monkeypatch.setattr(settings, name, 0)

    from app.core import observability, turn_idempotency

    with observability._metrics_lock:
        observability._metrics["endpoints"].clear()
        observability._metrics["recent_errors"].clear()
        observability._metrics["internal_errors"].clear()
        observability._metrics["llm"].clear()
        observability._metrics["status_codes"].update({"2xx": 0, "4xx": 0, "5xx": 0})
    turn_idempotency._local.clear()
    yield
    turn_idempotency._local.clear()


@pytest.fixture(autouse=True)
def _block_external_network(request, monkeypatch):
    """非集成用例禁止访问 external 网络：防止误调真实 LLM/SerpAPI 产生费用。"""
    if "integration" in request.node.keywords:
        return
    original_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host in ("127.0.0.1", "::1", "localhost"):
            return original_connect(self, address)
        raise RuntimeError(f"测试禁止访问外部网络: {address}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


def pytest_collection_modifyitems(config, items):
    """未配置独立测试库时跳过集成测试，防止误连开发库。"""
    if _TEST_DSN:
        return
    skip = pytest.mark.skip(reason="未配置 TEST_POSTGRES_CONNECTION_STRING，集成测试跳过")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
