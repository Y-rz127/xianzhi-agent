"""`/sessions/{id}/birth-info` 三级取数顺序回归测试（不联网、不依赖真实 PG）。

背景（2026-09-15）：会话恢复命盘上下文时只查了两处——agent 内存 + 从 message_store
的 tool_calls 里翻。正则直接挂的盘（"2005年9月28日18:00 男命"）不产生 tool_calls，
于是后端一重启、或换会话/换端，就出现"消息都在、出生信息空了"。

修好后顺序为：① agent 内存（最新）→ ② PG session_birth_info（挂盘即落库，权威兜底）
→ ③ 历史工具调用参数（兼容旧会话）。
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.api import xianzhi as api_mod


class _FakeAppCtx:
    def __init__(self, agent=None):
        self._agent = agent

    def get_xianzhi(self, conversation_id):
        if self._agent is None:
            raise RuntimeError("not initialized")
        return self._agent, MagicMock()


def _agent_with(time: str | None, gender: str | None):
    agent = MagicMock()
    agent._last_birth_info = {"time": time, "gender": gender} if time and gender else None
    return agent


def _run(monkeypatch, *, memory, stored, legacy):
    async def _noop_access(session_id, token):
        return None

    async def _stored(session_id):
        return stored

    async def _legacy(session_id):
        return legacy

    monkeypatch.setattr(api_mod, "_check_session_access", _noop_access)
    monkeypatch.setattr(api_mod.repo, "get_session_birth_info", _stored)
    monkeypatch.setattr(api_mod.repo, "get_birth_info_from_session", _legacy)
    return asyncio.run(
        api_mod.get_xianzhi_session_birth_info("s1", token=None, app_ctx=_FakeAppCtx(memory))
    )


def test_memory_wins_when_available(monkeypatch):
    out = _run(
        monkeypatch,
        memory=_agent_with("2005-09-28 18:00", "男"),
        stored={"time": "1990-05-20 14:30", "gender": "男"},
        legacy={"time": "1980-01-01 00:00", "gender": "女"},
    )
    assert out == {"time": "2005-09-28 18:00", "gender": "男"}


def test_db_used_when_memory_empty(monkeypatch):
    """重启后内存为空：必须靠落库的 session_birth_info 恢复（旧实现这里是空的）。"""
    out = _run(
        monkeypatch,
        memory=_agent_with(None, None),
        stored={"time": "2005-09-28 18:00", "gender": "男"},
        legacy=None,
    )
    assert out == {"time": "2005-09-28 18:00", "gender": "男"}


def test_db_preferred_over_legacy_tool_calls(monkeypatch):
    out = _run(
        monkeypatch,
        memory=_agent_with(None, None),
        stored={"time": "2005-09-28 18:00", "gender": "男"},
        legacy={"time": "2001-02-03 04:05", "gender": "女"},
    )
    assert out["time"] == "2005-09-28 18:00"


def test_legacy_tool_calls_still_used_for_old_sessions(monkeypatch):
    """落库表上线前的老会话：仍能从工具调用参数里恢复。"""
    out = _run(
        monkeypatch,
        memory=_agent_with(None, None),
        stored=None,
        legacy={"time": "2004-06-22 08:00", "gender": "男"},
    )
    assert out == {"time": "2004-06-22 08:00", "gender": "男"}


def test_all_empty_returns_nulls(monkeypatch):
    out = _run(monkeypatch, memory=_agent_with(None, None), stored=None, legacy=None)
    assert out == {"time": None, "gender": None}


def test_agent_lookup_failure_does_not_break_fallback(monkeypatch):
    """会话池里没有该 agent（未初始化）时不能 500，继续走落库。"""
    out = _run(
        monkeypatch,
        memory=None,  # get_xianzhi 抛 RuntimeError
        stored={"time": "2005-09-28 18:00", "gender": "男"},
        legacy=None,
    )
    assert out == {"time": "2005-09-28 18:00", "gender": "男"}


def test_partial_memory_falls_through(monkeypatch):
    """内存里只有 half（缺 gender）时不得直接返回半截数据。"""
    agent = MagicMock()
    agent._last_birth_info = {"time": "2005-09-28 18:00"}  # 缺 gender
    out = _run(
        monkeypatch,
        memory=agent,
        stored={"time": "1990-05-20 14:30", "gender": "女"},
        legacy=None,
    )
    assert out == {"time": "1990-05-20 14:30", "gender": "女"}


@pytest.mark.parametrize("stored", [None, {}, {"time": None, "gender": None}])
def test_stored_empty_shapes_fall_through(monkeypatch, stored):
    out = _run(
        monkeypatch,
        memory=_agent_with(None, None),
        stored=stored,
        legacy={"time": "2004-06-22 08:00", "gender": "男"},
    )
    assert out == {"time": "2004-06-22 08:00", "gender": "男"}
