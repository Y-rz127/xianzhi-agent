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
import uuid

import pytest
from fastapi.testclient import TestClient

from app.agent.context import get_app_context
from app.core.config import settings
from main import app

pytestmark = pytest.mark.integration

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


@pytest.fixture(scope="module")
def user_token(client: TestClient) -> str:
    """报告任务需要登录用户；注册一个随机测试账号。"""
    nickname = f"itest_{uuid.uuid4().hex[:10]}"
    r = client.post("/api/ai/auth/register", json={"nickname": nickname, "password": "itest-pass-123"})
    if r.status_code != 200:
        pytest.skip(f"测试用户创建失败: {r.status_code}")
    return r.json()["token"]


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


def test_health_live(client: TestClient) -> None:
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers.get("x-request-id")
    echoed = client.get("/api/health/live", headers={"X-Request-ID": "itest-rid-123"})
    assert echoed.headers["x-request-id"] == "itest-rid-123"


def test_health_ready_reports_dependencies(client: TestClient) -> None:
    response = client.get("/api/health/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "checks" in data
    assert data["ok"] is (response.status_code == 200)
    assert isinstance(data["checks"]["postgres"]["ok"], bool)
    assert isinstance(data["checks"]["redis"]["ok"], bool)


def test_metrics_requires_admin_when_auth_enabled(client: TestClient) -> None:
    if not AUTH_HEADERS:
        pytest.skip("未配置 API_KEYS，管理鉴权关闭")
    response = client.get("/api/ai/metrics")
    assert response.status_code == 401


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


def _wait_task(client: TestClient, task_id: str, token: str, timeout: float = 120.0) -> dict:
    """轮询任务状态直到 done/failed。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/ai/xianzhi/report/tasks/{task_id}", params={"token": token})
        assert r.status_code == 200
        data = r.json()
        if data["status"] in ("done", "failed"):
            return data
        time.sleep(1)
    raise AssertionError("任务等待超时")


@pytest.mark.integration
def test_report_pdf(client: TestClient, user_token: str) -> None:
    r = client.post(
        "/api/ai/xianzhi/report/tasks",
        params={"token": user_token},
        json={"kind": "basic_report", "birth_time": BIRTH_TIME, "gender": GENDER},
    )
    assert r.status_code == 200
    first_id = r.json()["task_id"]
    # 同参数重复提交必须复用同一任务（防重复生成/重复计费）
    repeat = client.post(
        "/api/ai/xianzhi/report/tasks",
        params={"token": user_token},
        json={"kind": "basic_report", "birth_time": BIRTH_TIME, "gender": GENDER},
    )
    assert repeat.status_code == 200
    assert repeat.json()["task_id"] == first_id
    task = _wait_task(client, first_id, user_token)
    assert task["status"] == "done", task.get("error")
    r = client.get(f"/api/ai/xianzhi/report/tasks/{task['task_id']}/result", params={"token": user_token})
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/pdf"
    assert len(r.content) > 0
    assert "attachment" in r.headers.get("content-disposition", "")


@pytest.mark.integration
def test_full_report(client: TestClient, user_token: str) -> None:
    try:
        chat_model = get_app_context().chat_model
    except RuntimeError:
        chat_model = None
    if chat_model is None:
        pytest.skip("chat_model 未初始化，跳过集成测试")
    r = client.post(
        "/api/ai/xianzhi/report/tasks",
        params={"token": user_token},
        json={"kind": "full_report", "birth_time": BIRTH_TIME, "gender": GENDER},
    )
    assert r.status_code == 200
    task = _wait_task(client, r.json()["task_id"], user_token, timeout=600)
    assert task["status"] == "done", task.get("error")
    assert "content" in task
