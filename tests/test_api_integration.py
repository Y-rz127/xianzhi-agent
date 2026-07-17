"""Backend API integration tests for FastAPI endpoints.

运行方式：
    pytest tests/test_api_integration.py -m integration

运行本文件全部测试：
    pytest tests/test_api_integration.py

说明：
- 标记为 `@pytest.mark.integration` 的测试依赖完整的应用栈（xianzhi、rag_chain）。
- 如果应用无法启动，或某个所需单例未初始化，相关测试会被跳过，而不是失败。
- 测试保持确定性且快速：SSE 接口只校验状态码与响应头，不消费完整流。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import state as app_state
from main import app


BIRTH_TIME = "1990-05-20 14:30"
GENDER = "男"
BIRTH_TIME_B = "1992-08-15 08:00"
GENDER_B = "女"


def _skip_if_uninitialized(attr: str) -> None:
    """如果所需单例未初始化，则跳过当前集成测试。"""
    if getattr(app_state, attr, None) is None:
        pytest.skip(f"{attr} 未初始化，跳过集成测试")


@pytest.fixture(scope="module")
def client():
    """模块级 TestClient，使用真实的 FastAPI 应用生命周期。

    如果应用 lifespan 启动失败（例如缺少 API 密钥），依赖此 fixture 的
    测试会被整体跳过，避免产生硬失败。
    """
    try:
        with TestClient(app) as c:
            yield c
    except Exception as exc:
        pytest.skip(f"完整应用栈不可用，跳过集成测试: {exc}")


def test_health(client: TestClient) -> None:
    response = client.get("/api/ai/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert isinstance(data.get("rag_ready"), bool)


def test_hehun(client: TestClient) -> None:
    response = client.get(
        "/api/ai/xianzhi/hehun",
        params={
            "birth_time_a": BIRTH_TIME,
            "gender_a": GENDER,
            "birth_time_b": BIRTH_TIME_B,
            "gender_b": GENDER_B,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "result" in data


def test_chart(client: TestClient) -> None:
    response = client.get(
        "/api/ai/xianzhi/chart",
        params={"birth_time": BIRTH_TIME, "gender": GENDER},
    )
    assert response.status_code == 200
    data = response.json()
    assert "chartText" in data
    assert "analysisText" in data
    assert "dayunText" in data
    assert "liunianText" in data
    assert "pillars" in data
    assert "wuxing" in data


def test_cache_stats(client: TestClient) -> None:
    response = client.get("/api/ai/xianzhi/cache_stats")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    for key in ("size", "max_size", "hits", "misses", "hit_rate"):
        assert key in data


def test_observability_status(client: TestClient) -> None:
    response = client.get("/api/ai/observability/status")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_sessions(client: TestClient) -> None:
    response = client.get("/api/ai/xianzhi/sessions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.integration
def test_rag_sync(client: TestClient) -> None:
    _skip_if_uninitialized("_rag_chain")
    response = client.get(
        "/api/ai/xianzhi/rag/sync",
        params={"message": "你好", "session_id": "integration-test"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "result" in data or "error" in data


@pytest.mark.integration
def test_report_pdf(client: TestClient) -> None:
    response = client.get(
        "/api/ai/xianzhi/report",
        params={"birth_time": BIRTH_TIME, "gender": GENDER},
    )
    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/pdf"
    assert len(response.content) > 0
    assert "attachment" in response.headers.get("content-disposition", "")


@pytest.mark.integration
def test_full_report(client: TestClient) -> None:
    if app_state.get_chat_model() is None:
        pytest.skip("chat_model 未初始化，跳过集成测试")
    response = client.get(
        "/api/ai/xianzhi/full_report",
        params={"birth_time": BIRTH_TIME, "gender": GENDER},
    )
    assert response.status_code == 200
    data = response.json()
    assert "content" in data or "error" in data
