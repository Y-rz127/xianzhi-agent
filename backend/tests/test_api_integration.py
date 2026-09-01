"""Backend API integration tests for FastAPI endpoints.

运行方式：
    pytest tests/test_api_integration.py -m integration

运行本文件全部测试：
    pytest tests/test_api_integration.py

说明：
- 标记为 `@pytest.mark.integration` 的测试依赖完整的应用栈（xianzhi、知识库）。
- 如果应用无法启动，或某个所需单例未初始化，相关测试会被跳过，而不是失败。
- 测试保持确定性且快速：SSE 接口只校验状态码与响应头，不消费完整流。
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.api import state as app_state
from app.core.config import settings
from main import app

# 本地/CI 环境若配置了 API_KEYS，管理类端点（observability/rag/sessions）需携带 Key，
# 否则中间件/require_admin 返回 401；未配置时为空 dict，行为不变。
_FIRST_KEY = next((k.strip() for k in settings.api_keys.split(",") if k.strip()), "")
AUTH_HEADERS = {"X-API-Key": _FIRST_KEY} if _FIRST_KEY else {}


BIRTH_TIME = "1990-05-20 14:30"
GENDER = "男"
BIRTH_TIME_B = "1992-08-15 08:00"
GENDER_B = "女"


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
    response = client.get("/api/ai/observability/status", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_sessions(client: TestClient) -> None:
    response = client.get("/api/ai/xianzhi/sessions", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_rag_status(client: TestClient) -> None:
    """知识库状态端点：问答已并入先知对话流，此处只校验知识库本身可用。"""
    response = client.get("/api/ai/rag/status", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data.get("ready"), bool)
    assert isinstance(data.get("count"), int)


def _wait_task(client: TestClient, task_id: str, timeout: float = 120.0) -> dict:
    """轮询任务状态直到 done/failed。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/ai/xianzhi/report/tasks/{task_id}")
        assert r.status_code == 200
        data = r.json()
        if data["status"] in ("done", "failed"):
            return data
        time.sleep(1)
    raise AssertionError("任务等待超时")


@pytest.mark.integration
def test_report_pdf(client: TestClient) -> None:
    r = client.post(
        "/api/ai/xianzhi/report/tasks",
        json={"kind": "basic_report", "birth_time": BIRTH_TIME, "gender": GENDER},
    )
    assert r.status_code == 200
    task = _wait_task(client, r.json()["task_id"])
    assert task["status"] == "done", task.get("error")
    r = client.get(f"/api/ai/xianzhi/report/tasks/{task['task_id']}/result")
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/pdf"
    assert len(r.content) > 0
    assert "attachment" in r.headers.get("content-disposition", "")


@pytest.mark.integration
def test_full_report(client: TestClient) -> None:
    if app_state.get_chat_model() is None:
        pytest.skip("chat_model 未初始化，跳过集成测试")
    r = client.post(
        "/api/ai/xianzhi/report/tasks",
        json={"kind": "full_report", "birth_time": BIRTH_TIME, "gender": GENDER},
    )
    assert r.status_code == 200
    task = _wait_task(client, r.json()["task_id"], timeout=600)
    assert task["status"] == "done", task.get("error")
    assert "content" in task
