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


def test_app_context_refreshes_role_models_and_evicts_cached_agents(monkeypatch):
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
    ctx._agents["cached"] = object()
    monkeypatch.setattr(
        "app.core.config.kv.get_config",
        lambda key: {"models": {"decompose_model": "new"}} if key == MODEL_CONFIG_KEY else None,
    )

    ctx.refresh_configured_models()

    assert ctx.decompose_model is replacement
    assert ctx.role_model_names["decompose_model"] == "new"
    assert not ctx._agents
