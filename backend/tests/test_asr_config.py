"""语音识别（ASR）模型配置：.env 入口 + 空值回落。

背景（2026-10-22 用户要求"在 .env 给个配置入口"）：
- ASR_MODEL 字段早就有，但 .env / .env.example 里没有入口，只能改代码默认值。
- pydantic-settings **不把空串当"未设置"**：`ASR_MODEL=` 会直接把 default 覆盖成
  ""，请求体带 model="" → 上游直接报参数错。所以空值必须显式回落。
"""

from __future__ import annotations


def test_asr_model_reads_env(monkeypatch):
    """ASR_MODEL 环境变量可覆盖（.env 入口生效的前提）。"""
    from app.core.config.settings import Settings

    monkeypatch.setenv("ASR_MODEL", "qwen-audio-turbo")
    assert Settings().asr_model == "qwen-audio-turbo"


def test_asr_model_blank_falls_back_to_default(monkeypatch):
    """ASR_MODEL 留空 → 回落到默认模型名，不能是空串。"""
    from app.core.config.settings import Settings

    monkeypatch.setenv("ASR_MODEL", "")
    assert Settings().asr_model == "qwen-audio-3.1-asr-flash"

    monkeypatch.setenv("ASR_MODEL", "   ")
    assert Settings().asr_model == "qwen-audio-3.1-asr-flash"


def test_asr_api_uses_configured_model(monkeypatch):
    """转写接口用的模型必须来自配置（换模型只改 .env，不改代码）。"""
    from app.api import asr

    monkeypatch.setattr(asr.settings, "asr_model", "qwen-audio-turbo", raising=False)
    assert asr.settings.asr_model == "qwen-audio-turbo"
