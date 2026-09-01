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


class TestRecordErrorMetric:
    """内部错误埋点：降级路径也必须可观测。"""

    def test_record_error_increments_counter(self):
        from app.core.observability import get_metrics, record_error

        before = get_metrics()["internal_errors"].get("unit_test.category", 0)
        record_error("unit_test.category")
        record_error("unit_test.category")
        after = get_metrics()["internal_errors"]["unit_test.category"]
        assert after == before + 2
