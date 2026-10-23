"""P1-10 隐私与数据治理：日志脱敏、生产禁用 LangSmith、保留期清理。"""
from __future__ import annotations

import os

import pytest

import app.core.observability as obs
import app.db.retention as retention
from app.core.config import settings
from app.core.privacy import safe_birth_time, safe_id, safe_text

pytestmark = pytest.mark.security


def test_safe_text_hides_content_by_default(monkeypatch):
    monkeypatch.setattr(settings, "log_llm_content", False)
    text = "我的生日是2004年6月22日"
    assert safe_text(text, 80) == f"<{len(text)} chars>"


def test_safe_text_shows_content_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "log_llm_content", True)
    assert safe_text("我的生日是2004年6月22日", 5) == "我的生日是"


def test_safe_birth_time_is_hashed_by_default(monkeypatch):
    monkeypatch.setattr(settings, "log_llm_content", False)
    masked = safe_birth_time("2004-06-22 08:00")
    assert masked.startswith("birth#")
    assert "2004" not in masked
    assert safe_birth_time("") == "-"


def test_safe_birth_time_shows_raw_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "log_llm_content", True)
    assert safe_birth_time("2004-06-22 08:00") == "2004-06-22 08:00"


def test_safe_id_is_hashed():
    masked = safe_id("user-123")
    assert masked.startswith("id#")
    assert "user-123" not in masked


def test_langsmith_forced_off_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "langsmith_tracing", True)
    monkeypatch.setattr(settings, "langsmith_api_key", "ls-test-key")
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    before = obs.get_metrics()["internal_errors"].get("langsmith_disabled_in_production", 0)

    assert obs.init_observability() is False

    assert os.environ.get("LANGCHAIN_TRACING_V2") != "true"
    after = obs.get_metrics()["internal_errors"].get("langsmith_disabled_in_production", 0)
    assert after == before + 1


class _Tx:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Cur:
    rowcount = 1


class _Conn:
    def __init__(self):
        self.sqls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def transaction(self):
        return _Tx()

    def execute(self, sql, params):
        self.sqls.append(" ".join(sql.split()))
        return _Cur()


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def connection(self):
        return self.conn


def test_purge_expired_zero_days_is_noop():
    assert retention.purge_expired(0) == {}


def test_purge_expired_covers_conversation_and_chart_tables(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(retention, "get_pool", lambda: _Pool(conn))

    stats = retention.purge_expired(90)

    assert set(stats) == {
        "messages",
        "session_birth_info",
        "sessions",
        "chart_profiles",
        "answer_feedback",
        "ai_interpretation_records",
        "feedback",
    }
    joined = "\n".join(conn.sqls)
    for table in ("message_store", "session_birth_info", "session_metadata", "chart_profiles", "answer_feedback"):
        assert table in joined
    assert "make_interval(days => %s)" in joined
