"""metrics 中间件记账口径守卫：路由模板而非原始 URL。

回归背景：中间件曾用 request.url.path（原始 URL）作 _metrics["endpoints"] 的 key，
带路径参数的路由（如 /api/ai/xianzhi/cases/{case_id}）每个不同 id 都会常驻一个
defaultdict key、只增不减——用户量上来后缓慢涨内存，且拖慢 get_metrics 全量遍历。
现统一记路由模板；404 未匹配路由归并 "(unmatched)"，原始路径仍可从 recent_errors 观测。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.observability import get_metrics
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _endpoint_keys() -> set[str]:
    return {f"{ep['method']} {ep['path']}" for ep in get_metrics()["endpoints"]}


def test_metrics_key_uses_route_template(client: TestClient) -> None:
    """带路径参数的请求按路由模板记账，原始 id 不落 key。"""
    client.get("/api/ai/xianzhi/cases/guard-case-id-xyz")
    keys = _endpoint_keys()
    assert "GET /api/ai/xianzhi/cases/{case_id}" in keys
    assert not any("guard-case-id-xyz" in k for k in keys)


def test_metrics_key_unmatched_fallback(client: TestClient) -> None:
    """未匹配路由（404）归并 "(unmatched)"，原始路径不落 key。"""
    client.get("/api/ai/guard-no-such-route-xyz")
    keys = _endpoint_keys()
    assert "GET (unmatched)" in keys
    assert not any("guard-no-such-route-xyz" in k for k in keys)
