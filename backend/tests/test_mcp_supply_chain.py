"""MCP 供应链加固：固定包版本、子进程环境变量最小化。"""
from __future__ import annotations

import os

from app.tools import mcp_client


def test_mcp_child_env_excludes_application_secrets(monkeypatch) -> None:
    monkeypatch.setattr(mcp_client.settings, "amap_maps_api_key", "amap-key", raising=False)
    monkeypatch.setenv("AMAP_MAPS_API_KEY", "env-should-not-be-used")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-secret")
    monkeypatch.setenv("API_KEYS", "admin-secret")
    monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "postgresql://secret")
    monkeypatch.setenv("LANGSMITH_API_KEY", "langsmith-secret")

    env = mcp_client._mcp_child_env(os.path.join("C:\\", "nodejs"))

    assert env["AMAP_MAPS_API_KEY"] == "amap-key"
    for key in ("DASHSCOPE_API_KEY", "API_KEYS", "POSTGRES_CONNECTION_STRING", "LANGSMITH_API_KEY"):
        assert key not in env
    path_key = next(k for k in env if k.upper() == "PATH")
    assert "nodejs" in env[path_key]
    assert "npm_config_cache" in env


def test_mcp_package_is_pinned_and_version_is_sanitized(monkeypatch) -> None:
    monkeypatch.setattr(mcp_client.settings, "amap_mcp_version", "0.0.8", raising=False)
    assert mcp_client._pinned_amap_package() == "@amap/amap-maps-mcp-server@0.0.8"

    monkeypatch.setattr(mcp_client.settings, "amap_mcp_version", "latest --evil", raising=False)
    assert mcp_client._pinned_amap_package() == "@amap/amap-maps-mcp-server@0.0.8"
