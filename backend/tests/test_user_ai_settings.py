from __future__ import annotations

import base64
import socket
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from app.agent.workflow.orchestrator import XianzhiWorkflow
from app.agent.xianzhi import Xianzhi
from app.api import user_ai
from app.api.deps import get_current_user
from app.core import crypto_util, user_llm
from app.db import user_ai_settings as store, user_llm as db_llm


@pytest.fixture(autouse=True)
def _configured_secret(monkeypatch):
    monkeypatch.setattr(crypto_util.settings, "user_llm_key_secret", "test-user-llm-secret")
    monkeypatch.setattr(crypto_util.settings, "admin_session_secret", "")


def test_secret_roundtrip_hides_plaintext_and_rejects_tampering():
    token = crypto_util.encrypt_secret("sk-private-value")

    assert "sk-private-value" not in token
    assert crypto_util.decrypt_secret(token) == "sk-private-value"
    raw = bytearray(base64.b64decode(token.removeprefix("v1.")))
    raw[-1] ^= 1
    tampered = "v1." + base64.b64encode(raw).decode("ascii")
    with pytest.raises(crypto_util.SecretDecryptError):
        crypto_util.decrypt_secret(tampered)


def test_secret_rejects_wrong_key_and_missing_server_secret(monkeypatch):
    token = crypto_util.encrypt_secret("sk-private-value")
    monkeypatch.setattr(crypto_util.settings, "user_llm_key_secret", "another-secret")
    with pytest.raises(crypto_util.SecretDecryptError):
        crypto_util.decrypt_secret(token)

    monkeypatch.setattr(crypto_util.settings, "user_llm_key_secret", "")
    with pytest.raises(crypto_util.SecretConfigError):
        crypto_util.encrypt_secret("new-key")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434/v1",
        "http://localhost:11434/v1",
        "http://10.0.0.8/v1",
        "http://192.168.1.8/v1",
        "http://169.254.169.254/v1",
        "http://[::ffff:127.0.0.1]/v1",
        "ftp://example.com/v1",
        "https://user:pass@example.com/v1",
        "https://example.com/v1?key=secret",
    ],
)
def test_model_url_rejects_non_public_or_ambiguous_targets(url, monkeypatch):
    monkeypatch.setattr(
        user_llm.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    with pytest.raises(user_llm.InvalidBaseURLError):
        user_llm.validate_llm_base_url(url)


def test_model_url_rejects_domain_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(
        user_llm.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))],
    )
    with pytest.raises(user_llm.InvalidBaseURLError):
        user_llm.validate_llm_base_url("https://api.example.com/v1")


def test_model_url_allows_public_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setattr(
        user_llm.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    assert user_llm.validate_llm_base_url("https://api.example.com/v1/") == "https://api.example.com/v1"


def test_unset_review_preference_exposes_actual_env_default(monkeypatch):
    monkeypatch.setattr(store.settings, "workflow_llm_review_enabled", False)

    result = store._row_to_settings((None, "", "", "", None))

    assert result["review_enabled"] is False
    assert result["review_set"] is False


def test_public_settings_never_returns_plaintext_or_ciphertext(monkeypatch):
    monkeypatch.setattr(
        store,
        "get_user_ai_settings",
        lambda _uid: {
            "review_enabled": True,
            "review_set": True,
            "llm_base_url": "https://api.example.com/v1",
            "llm_api_key": "sk-plaintext",
            "llm_api_key_enc": "ciphertext",
            "llm_model": "demo",
            "has_key": True,
            "updated_at": "",
        },
    )

    result = store.public_settings("user-a")

    assert result["has_key"] is True
    assert "llm_api_key" not in result
    assert "llm_api_key_enc" not in result


@pytest.fixture
def user_ai_client(monkeypatch):
    """只挂用户 AI 路由的轻量 FastAPI，避免完整 app lifespan。"""
    states = {
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": {
            "review_enabled": True,
            "review_set": False,
            "llm_base_url": "",
            "llm_model": "",
            "llm_api_key": "",
            "has_key": False,
            "updated_at": "",
        },
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": {
            "review_enabled": True,
            "review_set": False,
            "llm_base_url": "",
            "llm_model": "",
            "llm_api_key": "",
            "has_key": False,
            "updated_at": "",
        },
    }

    def _get(uid):
        return dict(states[uid])

    def _save(uid, **payload):
        current = states[uid]
        if payload.get("clear_model"):
            current.update(llm_base_url="", llm_model="", llm_api_key="", has_key=False)
        else:
            for field in ("llm_base_url", "llm_model", "llm_api_key"):
                if field in payload:
                    current[field] = payload[field]
            if payload.get("llm_api_key"):
                current["has_key"] = True
            if current["llm_api_key"]:
                current["has_key"] = True
        if "review_enabled" in payload:
            current["review_enabled"] = payload["review_enabled"]
            current["review_set"] = True
        return store.public_settings(uid)

    monkeypatch.setattr(store, "get_user_ai_settings", _get)
    monkeypatch.setattr(store, "save_user_ai_settings", _save)

    app = FastAPI()
    app.include_router(user_ai.router, prefix="/api/ai")

    def _current_user(x_test_user: str = Header(...)) -> dict:
        return {"id": x_test_user}

    app.dependency_overrides[get_current_user] = _current_user
    with TestClient(app) as client:
        yield client, states


def test_http_settings_are_isolated_by_authenticated_user(user_ai_client):
    client, states = user_ai_client
    user_a = {"X-Test-User": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
    user_b = {"X-Test-User": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}

    response = client.put("/api/ai/user/ai-settings", headers=user_a, json={"review_enabled": False})
    assert response.status_code == 200
    assert response.json()["review_enabled"] is False
    assert response.json()["review_set"] is True

    response = client.put(
        "/api/ai/user/ai-settings",
        headers=user_a,
        json={
            "llm_base_url": "https://8.8.8.8/v1",
            "llm_model": "user-a-model",
            "llm_api_key": "sk-user-a-secret",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_key"] is True
    assert "sk-user-a-secret" not in str(body)
    assert "llm_api_key" not in body

    response_b = client.get("/api/ai/user/ai-settings", headers=user_b)
    assert response_b.status_code == 200
    assert response_b.json()["review_enabled"] is True
    assert response_b.json()["review_set"] is False
    assert response_b.json()["has_key"] is False
    assert response_b.json()["llm_model"] == ""
    assert states["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]["llm_model"] == "user-a-model"


def test_http_settings_reject_invalid_types_and_oversize_fields(user_ai_client):
    client, _ = user_ai_client
    headers = {"X-Test-User": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}

    assert client.put(
        "/api/ai/user/ai-settings", headers=headers, json={"review_enabled": "false"}
    ).status_code == 400
    assert client.put(
        "/api/ai/user/ai-settings", headers=headers, json={"llm_api_key": "x" * 301}
    ).status_code == 400
    assert client.put(
        "/api/ai/user/ai-settings", headers=headers, json={"llm_base_url": "http://127.0.0.1/v1"}
    ).status_code == 400


def test_saving_invalidates_settings_and_model_caches(monkeypatch):
    store._cache["user-a"] = (9999999999.0, {"old": True})
    db_llm._cache["user-a"] = {"model": object(), "at": 9999999999.0}

    store.invalidate_user_cache("user-a")

    assert "user-a" not in store._cache
    assert "user-a" not in db_llm._cache


def test_user_model_cache_is_isolated_and_rebuilt_after_invalidation(monkeypatch):
    db_llm._cache.clear()
    configs = {
        "user-a": {"llm_base_url": "https://a.example.com/v1", "llm_model": "model-a", "llm_api_key": "key-a"},
        "user-b": {"llm_base_url": "https://b.example.com/v1", "llm_model": "model-b", "llm_api_key": "key-b"},
    }
    monkeypatch.setattr(db_llm, "get_user_ai_settings", lambda uid: configs[uid])
    monkeypatch.setattr(db_llm, "validate_llm_base_url", lambda url: url)
    monkeypatch.setattr(db_llm, "build_user_model", lambda cfg: SimpleNamespace(name=cfg["llm_model"]))

    model_a = db_llm.get_user_model("user-a")
    model_b = db_llm.get_user_model("user-b")
    assert model_a.name == "model-a"
    assert model_b.name == "model-b"

    configs["user-a"]["llm_model"] = "model-a-new"
    assert db_llm.get_user_model("user-a") is model_a  # 未保存前仍可命中短 TTL 缓存
    db_llm.invalidate_user_model_cache("user-a")
    assert db_llm.get_user_model("user-a").name == "model-a-new"
    assert db_llm.get_user_model("user-b") is model_b


def test_agent_applies_overrides_per_user_without_cross_talk(monkeypatch):
    settings_by_user = {
        "user-a": {"review_set": True, "review_enabled": False, "llm_model": "model-a"},
        "user-b": {"review_set": True, "review_enabled": True, "llm_model": "model-b"},
    }
    models = {"user-a": object(), "user-b": object()}
    monkeypatch.setattr("app.db.user_ai_settings.get_user_ai_settings", lambda uid: settings_by_user[uid])
    monkeypatch.setattr("app.db.user_llm.get_user_model", lambda uid: models[uid])

    agents = []
    for uid in ("user-a", "user-b"):
        agent = Xianzhi.__new__(Xianzhi)
        agent._user_id = uid
        agent._workflow = SimpleNamespace(overlay_model=None, review_enabled=None)
        agent._prepare_user_overrides()
        agents.append(agent)

    assert agents[0]._workflow.review_enabled is False
    assert agents[0]._workflow.overlay_model is models["user-a"]
    assert agents[1]._workflow.review_enabled is True
    assert agents[1]._workflow.overlay_model is models["user-b"]

    # 同一实例切到游客：必须立刻清掉上一账号的模型与审核偏好。
    agents[0]._user_id = ""
    agents[0]._prepare_user_overrides()
    assert agents[0]._workflow.review_enabled is None
    assert agents[0]._workflow.overlay_model is None


def _stream_workflow() -> XianzhiWorkflow:
    workflow = XianzhiWorkflow.__new__(XianzhiWorkflow)
    workflow.chat_model = object()
    workflow.overlay_model = object()
    workflow.on_token = None
    return workflow


def test_user_stream_failure_before_output_falls_back_to_server_stream(monkeypatch):
    workflow = _stream_workflow()
    sent = []
    workflow.on_token = sent.append

    def _fake_invoke_stream(model, messages, on_token, timeout_cap):
        if model is workflow.overlay_model:
            raise RuntimeError("user model unavailable")
        on_token("服务端回答")
        return "服务端回答"

    monkeypatch.setattr("app.agent.workflow.orchestrator.invoke_stream", _fake_invoke_stream)

    assert workflow._invoke_stream([]) == "服务端回答"
    assert sent == ["服务端回答"]


def test_user_stream_failure_after_output_does_not_append_second_answer(monkeypatch):
    workflow = _stream_workflow()
    sent = []
    workflow.on_token = sent.append

    def _fake_invoke_stream(model, messages, on_token, timeout_cap):
        if model is workflow.overlay_model:
            on_token("用户模型的半截回答")
            raise RuntimeError("connection lost")
        raise AssertionError("已发出正文后不得再回退拼接另一篇回答")

    monkeypatch.setattr("app.agent.workflow.orchestrator.invoke_stream", _fake_invoke_stream)

    result = workflow._invoke_stream([])

    assert result.startswith("用户模型的半截回答")
    assert "连接中断" in result
    assert "".join(sent) == result
