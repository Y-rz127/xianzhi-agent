"""R2 异常收紧专项单测。

覆盖点：
- _validate_api_key 失败关闭（网络异常/非预期状态码 → 视为无效，不再放行）
- PostgresChatMemory.add 写失败重抛（不静默吞掉对话轮次）
- record_error 内部错误埋点计数

运行方式：
    pytest tests/test_exception_tightening.py
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest


class TestValidateApiKeyFailClosed:
    """LangSmith Key 校验：无法确认有效时一律返回 False（失败关闭）。"""

    def test_network_error_returns_false(self, monkeypatch):
        from app.core.observability import _validate_api_key

        def _raise(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", _raise)
        assert _validate_api_key("fake-key") is False

    def test_http_403_returns_false(self, monkeypatch):
        from app.core.observability import _validate_api_key

        def _raise(*args, **kwargs):
            raise urllib.error.HTTPError(
                url="https://api.smith.langchain.com/info",
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=None,
            )

        monkeypatch.setattr(urllib.request, "urlopen", _raise)
        assert _validate_api_key("fake-key") is False

    def test_unexpected_status_returns_false(self, monkeypatch):
        from app.core.observability import _validate_api_key

        class _Resp:
            status = 500

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
        assert _validate_api_key("fake-key") is False


class TestMemoryWriteReraise:
    """PG 记忆写入失败必须重抛，不允许静默丢对话轮次。"""

    @pytest.fixture()
    def broken_memory(self, monkeypatch):
        from app.memory import postgres_memory

        # 跳过构造期建表，直接让运行期连接池故障
        monkeypatch.setattr(postgres_memory, "_schema_ready", True)

        def _broken_pool():
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(postgres_memory, "_get_pool", _broken_pool)
        return postgres_memory.PostgresChatMemory()

    def test_add_raises_when_pool_unavailable(self, broken_memory):
        with pytest.raises(RuntimeError):
            broken_memory.add("unit-test-conv", [])

    def test_save_summary_raises_when_pool_unavailable(self, broken_memory):
        with pytest.raises(RuntimeError):
            broken_memory.save_summary("unit-test-conv", "summary", 10)

    def test_get_degrades_to_empty_on_failure(self, broken_memory):
        """读路径保持降级语义：失败返回空列表而不是抛出。"""
        assert broken_memory.get("unit-test-conv") == []


class TestLegacyTarotRecordRouteRemoval:
    """旧塔罗记录表专用路由必须从共享 API 栈中剥离，统一走通用 AI 解读记录表。

    注：本项目所用 FastAPI 版本把 include_router 的结果包在 _IncludedRouter 中
    （该对象没有 .path 属性），直接遍历 router.routes 会全部取到空串、使断言恒真。
    这里改用 app.openapi() 暴露的真实路径表做校验。
    """

    def test_tarot_records_route_is_not_registered(self):
        from main import app

        paths = app.openapi()["paths"]
        assert paths, "openapi 路径表为空，该断言将失去意义"
        leaked = [p for p in paths if "tarot_records" in p]
        assert not leaked, f"旧的塔罗记录路由应已剥离，实际仍注册: {leaked}"


class TestDeleteSessionSummaryCleanup:
    """会话删除时必须把摘要状态元数据也一起碎片化清理，避免历史摘要残留。"""

    def test_delete_session_clears_summary_metadata_before_row_delete(self, monkeypatch):
        from app.memory import postgres_memory

        monkeypatch.setattr(postgres_memory, "_schema_ready", True)
        monkeypatch.setattr(
            postgres_memory,
            "_resolve_session_uuid",
            lambda session_id: "11111111-1111-1111-1111-111111111111",
        )

        calls = []

        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                calls.append((sql, params))

        class FakePool:
            def connection(self):
                return FakeConn()

        monkeypatch.setattr(postgres_memory, "_get_pool", lambda: FakePool())

        postgres_memory.delete_session("unit-test-conv")

        assert any("UPDATE session_metadata" in sql and "summary" in sql for sql, _ in calls)
        assert any("DELETE FROM session_metadata" in sql for sql, _ in calls)


class TestDeleteAnswerFeedback:
    """回答反馈记录删除必须落到 answer_feedback 表的一条标准删除语句。"""

    def test_delete_answer_feedback_runs_sql(self, monkeypatch):
        from app.db import user_records

        calls = []

        class FakeCursor:
            rowcount = 1

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                calls.append((sql, params))
                return self

        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                calls.append((sql, params))
                return FakeCursor()

        class FakePool:
            def connection(self):
                return FakeConn()

        monkeypatch.setattr(user_records, "_ensure_tables", lambda: None)
        monkeypatch.setattr(user_records, "get_pool", lambda: FakePool())

        assert user_records.delete_answer_feedback("unit-test-fid") is True
        assert any("DELETE FROM answer_feedback" in sql and "WHERE id = %s" in sql for sql, _ in calls)


class TestAiInterpretationRecords:
    """通用 AI 解读记录必须落到用户私有记录表的一条标准写入语句。"""

    def test_add_ai_interpretation_record_runs_sql(self, monkeypatch):
        from app.db import user_records

        calls = []

        class FakeCursor:
            rowcount = 1

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                calls.append((sql, params))
                return self

        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                calls.append((sql, params))
                return FakeCursor()

        class FakePool:
            def connection(self):
                return FakeConn()

        monkeypatch.setattr(user_records, "_ensure_tables", lambda: None)
        monkeypatch.setattr(user_records, "get_pool", lambda: FakePool())

        user_records.add_ai_interpretation_record(
            "unit-test-user",
            "liuyao",
            "这次工作变动应当如何准备？",
            {"source": "liuyao"},
            "解读文案",
        )
        assert any("INSERT INTO ai_interpretation_records" in sql for sql, _ in calls)


class TestTarotStreamChunkNormalization:
    """塔罗流式解读必须把模型产出的文本片段标准化为纯字符串片段，避免 WS 端收到结构化 list/对象并且页面只看到标题。"""

    def test_tarot_divine_stream_flattens_content_blocks(self):
        import asyncio

        from app.sub_app.tarot.tarot_app import TarotApp

        class FakeChunk:
            content = [
                {"type": "text", "text": "先看到"},
                {"type": "text", "text": "未来"},
            ]

        class FakeModel:
            async def astream(self, msgs):
                yield FakeChunk()

        async def _collect():
            app = TarotApp(chat_model=FakeModel())
            out = []
            async for piece in app.divine_stream(
                "问卜",
                "daily",
                [
                    {
                        "name": "愚者",
                        "nameEn": "The Fool",
                        "emblem": "☆",
                        "arcana": "major",
                        "suit": "major",
                        "meaning": "启程",
                        "isReversed": False,
                    }
                ],
            ):
                out.append(piece)
            return out

        result = asyncio.run(_collect())
        assert result == ["先看到未来"]


class TestRecordErrorMetric:
    """内部错误埋点：降级路径也必须可观测。"""

    def test_record_error_increments_counter(self):
        from app.core.observability import get_metrics, record_error

        before = get_metrics()["internal_errors"].get("unit_test.category", 0)
        record_error("unit_test.category")
        record_error("unit_test.category")
        after = get_metrics()["internal_errors"]["unit_test.category"]
        assert after == before + 2
