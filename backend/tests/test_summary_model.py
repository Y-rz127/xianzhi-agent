"""会话摘要模型的独立配置（SUMMARY_MODEL）。

背景：摘要每 6 轮跑一次，任务是"压缩最近对话"，与命盘问答（长上下文 + 推理）
诉求不同。此前摘要直接复用主模型（kimi-k3），两边的成本/时延被绑死 —— 想给摘要
换个便宜快模型就得连问答一起换。

这里锁住三件事：
1. summary_model 是独立角色，可在管理端热改（/api/admin/models）；
2. 摘要真的走 summary_model，而不是主模型；
3. 装配期注入的实例可能被启动探活替换 ⇒ 摘要必须按轮重取，不能抓死引用。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def test_summary_model_is_a_configurable_role():
    from app.core.model_config import LLM_MODEL_ROLES, default_model_config

    assert "summary_model" in LLM_MODEL_ROLES
    defaults = default_model_config()
    assert "summary_model" in defaults
    # 默认值：轻量模型即可，不占用主模型预算
    from app.core.config import settings

    assert settings.summary_model == "deepseek-v4.1-flash-1017"


def test_app_context_exposes_summary_model_and_hot_swaps_it():
    from app.agent.context import AppContext

    new_summary = object()
    ctx = AppContext(
        chat_model=object(),
        local_tools=[],
        memory=None,
        role_model_names={
            "decompose_model": "d",
            "reviewer_model": "r",
            "sub_app_model": "s",
            "summary_model": "old",
        },
        role_model_factory=lambda role, _name: new_summary if role == "summary_model" else None,
    )

    ctx.refresh_configured_models(
        {
            "decompose_model": "d",
            "reviewer_model": "r",
            "sub_app_model": "s",
            "summary_model": "new",
        }
    )

    assert ctx.summary_model is new_summary
    assert ctx.role_model_names["summary_model"] == "new"


def test_summary_model_change_keeps_same_agent_and_lock():
    """换摘要模型不能重建会话 Agent（否则同会话两轮可能并发跑）。"""
    from app.agent.context import AppContext

    ctx = AppContext(
        chat_model=object(),
        local_tools=[],
        memory=None,
        role_model_names={
            "decompose_model": "d",
            "reviewer_model": "r",
            "sub_app_model": "s",
            "summary_model": "old",
        },
        role_model_factory=lambda _role, _name: object(),
    )
    agent1, _ = ctx.get_xianzhi("conv-summary")

    ctx.refresh_configured_models(
        {
            "decompose_model": "d",
            "reviewer_model": "r",
            "sub_app_model": "s",
            "summary_model": "new",
        }
    )
    agent2, _ = ctx.get_xianzhi("conv-summary")

    assert agent1 is agent2
    assert agent1.lock is agent2.lock


def test_summary_model_propagates_into_existing_agents():
    """已存在的 Agent 也要用上新的摘要模型（否则老会话仍用旧模型）。"""
    from app.agent.context import AppContext

    new_summary = object()
    ctx = AppContext(
        chat_model=object(),
        local_tools=[],
        memory=None,
        role_model_names={
            "decompose_model": "d",
            "reviewer_model": "r",
            "sub_app_model": "s",
            "summary_model": "old",
        },
        role_model_factory=lambda role, _name: new_summary if role == "summary_model" else None,
    )
    agent, _ = ctx.get_xianzhi("conv-summary")

    ctx.refresh_configured_models(
        {
            "decompose_model": "d",
            "reviewer_model": "r",
            "sub_app_model": "s",
            "summary_model": "new",
        }
    )

    assert agent._summary_model is new_summary


def test_summary_model_of_falls_back_to_chat_model():
    """未配置摘要模型时回落主模型（与其它角色一致）。"""
    from app.agent.context import summary_model_of

    chat = object()
    ctx = SimpleNamespace(chat_model=chat, summary_model=None)
    assert summary_model_of(ctx) is chat

    summary = object()
    ctx2 = SimpleNamespace(chat_model=chat, summary_model=summary)
    assert summary_model_of(ctx2) is summary


def test_agent_persist_history_uses_summary_model_not_chat_model():
    """回归：摘要必须走摘要模型，而不是主模型。

    做法：直接断言「传给 maybe_summarize 的第二个参数」就是摘要模型 ——
    靠 mock 的 call_args 精确核对，不做「如果被调用了才断言」的条件式弱验证。
    """
    from app.agent.xianzhi import Xianzhi

    agent = Xianzhi.__new__(Xianzhi)
    agent._memory = MagicMock()
    agent._conversation_id = "conv-1"
    agent.message_list = [SimpleNamespace(content="hi", __class__=type("HumanMessage", (), {}))]
    agent._user_id = ""
    agent.chat_model = MagicMock(name="chat_model")
    summary_model = MagicMock(name="summary_model")
    agent._summary_model = summary_model
    agent._history_len = 0
    agent._pending_question_id = None
    agent._persisted_question = ""

    with patch("app.memory.summarizer.maybe_summarize") as spy:
        agent._persist_history()

    spy.assert_called_once()
    args = spy.call_args[0]
    assert args[1] is summary_model, "摘要模型未生效：仍传入了非 summary_model 的实例"
    assert args[1] is not agent.chat_model


def test_summary_model_is_resolved_at_call_time_not_captured_at_init():
    """回归：探活替换模型实例后，摘要必须用新的那个。

    装配期注入的引用会被探活整体替换 ⇒ 抓死旧引用会让「只接受思考模式」的
    自动纠正对摘要失效（同 get_sub_app_model 的考量）。
    """
    from app.agent.xianzhi import Xianzhi

    agent = Xianzhi.__new__(Xianzhi)
    agent._memory = MagicMock()
    agent._conversation_id = "conv-1"
    agent.message_list = [SimpleNamespace(content="hi", __class__=type("HumanMessage", (), {}))]
    agent._user_id = ""
    agent.chat_model = MagicMock(name="chat_model")
    agent._summary_model = MagicMock(name="stale_at_init")
    agent._history_len = 0
    agent._pending_question_id = None
    agent._persisted_question = ""

    # 探活纠正后的新实例
    fresh = MagicMock(name="fresh_after_probe")
    with patch("app.agent.context.get_summary_model", return_value=fresh):
        with patch("app.memory.summarizer.maybe_summarize") as spy:
            agent._persist_history()

    spy.assert_called_once()
    assert spy.call_args[0][1] is fresh, "摘要仍抓着装配期的旧实例，探活纠正对它无效"


def test_resolve_summary_model_falls_back_when_app_context_missing():
    """AppContext 未初始化时（测试/独立脚本）回落装配期实例，再退到主模型。"""
    from app.agent.xianzhi import Xianzhi

    agent = Xianzhi.__new__(Xianzhi)
    summary = object()
    agent._summary_model = summary
    agent.chat_model = object()

    with patch("app.agent.context.get_summary_model", side_effect=RuntimeError("no ctx")):
        assert agent._resolve_summary_model() is summary

    agent._summary_model = None
    with patch("app.agent.context.get_summary_model", side_effect=RuntimeError("no ctx")):
        assert agent._resolve_summary_model() is agent.chat_model


def test_probe_spec_covers_summary_role():
    """摘要模型要纳入启动探活（只接受思考模式的模型靠它自愈）。"""
    import ast
    import pathlib

    src = pathlib.Path("main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    labels = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "SubModelSpec":
            for kw in node.keywords:
                if kw.arg == "label" and isinstance(kw.value, ast.Constant):
                    labels.append(kw.value.value)
    assert "会话摘要" in labels, f"摘要模型未纳入探活规格：{labels}"


def test_admin_models_api_accepts_summary_model():
    """管理端保存模型配置要接受 summary_model 字段。"""
    from app.api.model_config import _validate_models
    from app.core.model_config import default_model_config

    # 以真实默认值为基底（asr/tts 等非 LLM 角色不允许为空）
    payload = default_model_config()
    payload["summary_model"] = "deepseek-v4.1-flash-1017"

    cleaned = _validate_models(payload)

    assert cleaned["summary_model"] == "deepseek-v4.1-flash-1017"


def test_admin_models_api_rejects_unknown_key():
    from fastapi import HTTPException

    from app.api.model_config import _validate_models
    from app.core.model_config import default_model_config

    payload = default_model_config()
    payload["summary_model"] = "x"
    payload["bogus"] = "y"

    with pytest.raises(HTTPException) as exc:
        _validate_models(payload)
    assert exc.value.status_code == 400
