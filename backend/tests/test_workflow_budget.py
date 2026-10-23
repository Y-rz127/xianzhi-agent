"""整轮预算单测：阶段调用共享 deadline，预算耗尽时按约定降级。"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

import app.agent.workflow.workflow_messages as wm
import app.agent.xianzhi_langgraph as graph
from app.agent.core.base_agent import AgentState
from app.agent.workflow.workflow_budget import (
    MIN_CALL_SECONDS,
    TurnBudgetExceeded,
    budget_enough,
    budget_timeout,
    turn_budget,
)
from app.agent.workflow.workflow_models import FactCheckResult, QuestionIntent
from app.agent.xianzhi import _TURN_TIMEOUT_FLAG, _TURN_TIMEOUT_TEXT, Xianzhi


def test_budget_timeout_is_capped_by_remaining():
    with turn_budget(5):
        timeout = budget_timeout(100, fallback=180)
        assert 0 < timeout <= 5


def test_budget_timeout_without_budget_returns_fallback():
    assert budget_timeout(100, fallback=180) == 180
    assert budget_timeout(100, fallback=None) is None


def test_expired_budget_raises_and_reports_not_enough():
    with turn_budget(0.01):
        time.sleep(0.02)
        assert budget_enough(MIN_CALL_SECONDS) is False
        with pytest.raises(TurnBudgetExceeded):
            budget_timeout(10, fallback=180)


class _FakeModel:
    """记录 bind 进来的 timeout，返回固定回答。"""

    def __init__(self):
        self.timeout = None
        self.calls = 0

    def bind(self, **kwargs):
        self.timeout = kwargs.get("timeout")
        return self

    def invoke(self, messages):
        self.calls += 1
        return AIMessage(content="回答")


def test_invoke_binds_min_of_stage_cap_and_remaining():
    model = _FakeModel()
    with turn_budget(5):
        out = wm.invoke(model, [], timeout_cap=100)

    assert out == "回答"
    assert model.calls == 1
    assert model.timeout is not None and model.timeout <= 5


def test_invoke_raises_before_call_when_budget_exhausted():
    model = _FakeModel()
    with turn_budget(0.01):
        time.sleep(0.02)
        with pytest.raises(TurnBudgetExceeded):
            wm.invoke(model, [], timeout_cap=100)
    assert model.calls == 0


def test_repair_node_skips_when_budget_exhausted():
    state = {
        "intent": QuestionIntent(domain="career", label="事业工作"),
        "raw_answer": "已生成的回答",
        "issues": ["问题1"],
    }
    with turn_budget(0.01):
        time.sleep(0.02)
        out = graph._repair_node(object(), state)

    assert out["final_answer"] == "已生成的回答"
    assert out["issues"] == ["问题1"]


def test_check_node_skips_llm_review_when_budget_exhausted(monkeypatch):
    class _Reviewer:
        def __init__(self):
            self.skip_llm = None

        def review(self, *args, **kwargs):
            self.skip_llm = kwargs.get("skip_llm")
            return FactCheckResult(ok=True, source="regex")

    class _Workflow:
        def __init__(self):
            self._reviewer = _Reviewer()

        def _emit_progress(self, text):
            pass

        def check_facts(self, *args, **kwargs):
            return FactCheckResult(ok=True)

    monkeypatch.setattr(graph, "compact_facts", lambda *a, **k: "")
    monkeypatch.setattr(graph, "build_sui_section", lambda *a, **k: "")
    intent = QuestionIntent(domain="career", label="事业工作", needs_chart=True)
    state = {
        "user_prompt": "q",
        "chart_context": SimpleNamespace(chart=object()),
        "intent": intent,
        "raw_answer": "回答",
        "knowledge": "",
        "worker": SimpleNamespace(label="事业工作"),
    }
    workflow = _Workflow()
    with turn_budget(0.01):
        time.sleep(0.02)
        graph._check_node(workflow, state)

    assert workflow._reviewer.skip_llm is True


def _agent() -> Xianzhi:
    with patch("app.agent.xianzhi.create_chat_memory") as m:
        m.return_value = MagicMock()
        agent = Xianzhi(chat_model=MagicMock(), local_tools=[])
    agent.set_conversation_id("test-budget")
    return agent


def test_workflow_budget_exceeded_maps_to_friendly_text():
    agent = _agent()

    def _boom(*args, **kwargs):
        raise TurnBudgetExceeded("剩余 0.1s")

    agent._execute_workflow = _boom
    agent._get_session_summary = lambda: ""
    agent._persist_history = lambda: None

    chunks = list(agent._workflow_stream("问题"))

    assert chunks[-1] == _TURN_TIMEOUT_TEXT


def test_react_think_stops_after_budget(monkeypatch):
    agent = _agent()
    monkeypatch.setattr(agent, "_turn_started_at", time.monotonic() - 999)
    agent.chat_model.invoke = MagicMock()

    assert agent.think() is False
    assert agent.state == AgentState.ERROR
    assert agent._last_error == _TURN_TIMEOUT_FLAG
    agent.chat_model.invoke.assert_not_called()


def test_final_answer_or_error_returns_timeout_text():
    agent = _agent()
    agent._last_error = _TURN_TIMEOUT_FLAG
    assert agent._final_answer_or_error() == _TURN_TIMEOUT_TEXT
