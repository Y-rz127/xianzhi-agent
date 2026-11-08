"""会话摘要的触发阈值配置（SUMMARY_TRIGGER_ROUNDS，按轮）。

背景：摘要触发阈值原先硬编码 12 条消息（约 6 轮），改不了 —— 想让摘要更频繁
（短会话也要有上下文）或更稀疏（省 token）都做不到。现在按「轮」暴露配置项
（一问一答=1轮，与用户感知一致），在 .env 里配。

锁住：
1. 默认 6 轮 ⇒ 12 条消息，与历史行为逐字对齐（不改变现有部署的行为）；
2. 轮数 → 消息条数的换算（一问一答各一条 ⇒ 轮数×2）；
3. 轮数 ≤ 0 ⇒ 不触发；
4. 达到阈值才真的发起摘要调用，未达到时不调模型（不白花钱）。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def rounds(monkeypatch):
    """设置摘要触发轮数，测试结束自动还原（monkeypatch 负责）。

    settings 是模块级单例，直接赋值会污染后续用例 —— 必须用 monkeypatch。
    """
    from app.core.config import settings

    def _set(value: int):
        monkeypatch.setattr(settings, "summary_trigger_rounds", value)
        return value

    return _set


def test_default_rounds_match_legacy_message_threshold():
    """默认 6 轮 = 12 条消息，与改动前的硬编码完全一致（不改变现有行为）。"""
    from app.core.config import settings
    from app.memory.summarizer import _trigger_messages

    assert settings.summary_trigger_rounds == 6
    assert _trigger_messages() == 12


def test_rounds_convert_to_message_count(rounds):
    """一问一答各一条消息 ⇒ 轮数 × 2 = 消息条数。"""
    from app.memory.summarizer import _trigger_messages

    for expected_rounds, expected in ((1, 2), (3, 6), (10, 20)):
        rounds(expected_rounds)
        assert _trigger_messages() == expected


def test_zero_rounds_disables_summarizing(rounds):
    """轮数 ≤ 0 ⇒ 视为不触发（阈值设成极大值）。"""
    from app.memory.summarizer import _trigger_messages

    rounds(0)
    assert _trigger_messages() > 10**5


def test_summary_not_triggered_below_threshold(rounds):
    """未达阈值时**不调模型**（不白花钱）。"""
    from app.memory import summarizer

    rounds(6)
    memory = MagicMock()
    memory.get_message_count.return_value = 8  # 8 条 < 12 条阈值
    memory.get_last_summary_count.return_value = 0
    model = MagicMock()

    summarizer.maybe_summarize(memory, model, "conv-1", [])
    model.invoke.assert_not_called()
    memory.save_summary.assert_not_called()


def test_summary_triggered_at_threshold(rounds):
    """达到阈值时应发起摘要调用，并把最近若干条消息送进模型。"""
    from app.memory import summarizer

    rounds(6)
    msgs = [
        SimpleNamespace(content=f"第{i}条", __class__=type("HumanMessage", (), {}))
        for i in range(12)
    ]
    memory = MagicMock()
    memory.get_message_count.return_value = 12
    memory.get_last_summary_count.return_value = 0
    memory.get_summary.return_value = ""
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(content="新摘要内容，足够长，超过十个字")

    summarizer.maybe_summarize(memory, model, "conv-1", msgs)

    # 摘要在后台线程里跑，等它完成
    for _ in range(50):
        if memory.save_summary.called:
            break
        import time

        time.sleep(0.02)

    assert model.invoke.called, "达到阈值却没调用摘要模型"
    memory.save_summary.assert_called_once()


def test_trigger_uses_configured_rounds_not_hardcoded(rounds):
    """把轮数调小 ⇒ 阈值随之下降（配置真的生效）。"""
    from app.memory import summarizer

    rounds(2)  # 2 轮 = 4 条消息
    memory = MagicMock()
    memory.get_message_count.return_value = 4
    memory.get_last_summary_count.return_value = 0
    memory.get_summary.return_value = ""
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(content="新摘要内容，足够长，超过十个字")

    summarizer.maybe_summarize(memory, model, "conv-1", [])

    for _ in range(50):
        if model.invoke.called:
            break
        import time

        time.sleep(0.02)

    assert model.invoke.called, "轮数调小后阈值应下降并触发摘要"
