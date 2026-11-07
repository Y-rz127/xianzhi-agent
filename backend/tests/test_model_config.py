from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_model_config_uses_environment_defaults(monkeypatch):
    from app.core import model_config

    monkeypatch.setattr(model_config.settings, "decompose_model", "env-decompose")
    monkeypatch.setattr(model_config.settings, "tts_voice", "env-voice")
    monkeypatch.setattr(model_config, "get_config", lambda _key: None)

    result = model_config.get_model_config()

    assert result["decompose_model"] == "env-decompose"
    assert result["tts_voice"] == "env-voice"


def test_model_config_stored_blank_llm_model_preserves_fallback(monkeypatch):
    from app.core import model_config

    monkeypatch.setattr(
        model_config,
        "get_config",
        lambda _key: {"models": {"decompose_model": "", "tts_voice": "custom-voice"}},
    )

    result = model_config.get_model_config()

    assert result["decompose_model"] == ""
    assert result["reviewer_model"] == model_config.settings.reviewer_model
    assert result["tts_voice"] == "custom-voice"


def test_model_config_validation_rejects_whitespace_model_names():
    from app.api.model_config import _validate_models
    from app.core.model_config import default_model_config

    models = default_model_config()
    models["asr_model"] = "bad model"

    with pytest.raises(HTTPException) as exc_info:
        _validate_models(models)

    assert exc_info.value.status_code == 400


def test_model_config_validation_requires_nonempty_speech_models():
    from app.api.model_config import _validate_models
    from app.core.model_config import default_model_config

    models = default_model_config()
    models["tts_model"] = ""

    with pytest.raises(HTTPException) as exc_info:
        _validate_models(models)

    assert exc_info.value.status_code == 400


def test_app_context_refreshes_role_models_in_place(monkeypatch):
    """模型配置变更应原地换模型，**不重建会话 Agent**。

    每个 Agent 自带会话锁（agent.lock），清空会话池会让同一 conversation_id
    下次拿到另一个 Agent、另一把锁 → 同会话两轮可能并发跑、互相覆盖会话内存。
    """
    from app.agent.context import AppContext
    from app.core.model_config import MODEL_CONFIG_KEY

    main = object()
    replacement = object()
    ctx = AppContext(
        chat_model=main,
        local_tools=[],
        memory=None,
        role_model_names={"decompose_model": "old", "reviewer_model": "", "sub_app_model": ""},
        role_model_factory=lambda _role, name: replacement if name == "new" else None,
    )
    monkeypatch.setattr(
        "app.core.config.kv.get_config",
        lambda key: {"models": {"decompose_model": "new"}} if key == MODEL_CONFIG_KEY else None,
    )

    ctx.refresh_configured_models()

    assert ctx.decompose_model is replacement
    assert ctx.role_model_names["decompose_model"] == "new"


def test_model_change_keeps_same_agent_and_session_lock():
    """回归：改模型配置后，同一会话必须仍是同一个 Agent、同一把会话锁。"""
    from app.agent.context import AppContext

    ctx = AppContext(
        chat_model=object(),
        local_tools=[],
        memory=None,
        role_model_names={"decompose_model": "old", "reviewer_model": "", "sub_app_model": ""},
        role_model_factory=lambda _role, _name: object(),
    )
    agent1, _lock1 = ctx.get_xianzhi("conv-1")

    ctx.refresh_configured_models({"decompose_model": "new", "reviewer_model": "", "sub_app_model": ""})
    agent2, _lock2 = ctx.get_xianzhi("conv-1")

    assert agent1 is agent2, "改模型配置不应重建会话 Agent"
    assert agent1.lock is agent2.lock, "同一会话的进程内锁必须保持一致"
    assert ctx.decompose_model is not ctx.chat_model


def test_model_change_syncs_models_into_existing_agent():
    """已存在的 Agent 的 workflow 也要换成新模型（否则老会话继续用旧模型）。"""
    from app.agent.context import AppContext

    new_decompose = object()
    new_reviewer = object()
    ctx = AppContext(
        chat_model=object(),
        local_tools=[],
        memory=None,
        role_model_names={"decompose_model": "old", "reviewer_model": "old2", "sub_app_model": ""},
        role_model_factory=lambda role, _name: {
            "decompose_model": new_decompose,
            "reviewer_model": new_reviewer,
        }.get(role),
    )
    agent, _lock = ctx.get_xianzhi("conv-1")

    ctx.refresh_configured_models(
        {"decompose_model": "new", "reviewer_model": "new2", "sub_app_model": ""}
    )

    assert agent._workflow._decompose_model is new_decompose
    assert agent._workflow._reviewer._chat_model is new_reviewer
