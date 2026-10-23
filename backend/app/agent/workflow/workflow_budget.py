"""单轮对话总时限：拆解/生成/审核/修复共享同一个 deadline。

背景：各阶段各自绑定 180s 超时，串行叠加后整轮可达 427s 甚至更久。
这里用一个 ContextVar 保存整轮剩余预算，每次 LLM 调用取
`min(阶段上限, 剩余时间)`，避免"每段都没超时、整轮却超时"。
"""
from __future__ import annotations

import contextvars
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

# 低于该值不再发起 LLM 调用：请求发出去也来不及返回
MIN_CALL_SECONDS = 3.0


class TurnBudgetExceeded(RuntimeError):
    """本轮剩余时间不足，无法继续调用 LLM。"""


@dataclass(frozen=True)
class TurnBudget:
    total: float
    started_at: float

    def remaining(self) -> float:
        return max(0.0, self.total - (time.monotonic() - self.started_at))

    def enough(self, minimum: float = MIN_CALL_SECONDS) -> bool:
        return self.remaining() >= max(0.0, minimum)

    def call_timeout(self, cap: float) -> float:
        remaining = self.remaining()
        if remaining < MIN_CALL_SECONDS:
            raise TurnBudgetExceeded(f"本轮剩余时间不足（{remaining:.1f}s）")
        return min(cap, remaining)


_budget: contextvars.ContextVar[TurnBudget | None] = contextvars.ContextVar(
    "turn_budget", default=None
)


@contextmanager
def turn_budget(total: float) -> Iterator[None]:
    """开启一轮预算；退出时恢复外层上下文（测试可嵌套）。"""
    token = _budget.set(TurnBudget(total=max(1.0, float(total)), started_at=time.monotonic()))
    try:
        yield
    finally:
        _budget.reset(token)


def current_budget() -> TurnBudget | None:
    return _budget.get()


def budget_remaining() -> float | None:
    """剩余秒数；未开启预算时返回 None。"""
    budget = _budget.get()
    return None if budget is None else budget.remaining()


def budget_enough(minimum: float = MIN_CALL_SECONDS) -> bool:
    budget = _budget.get()
    return True if budget is None else budget.enough(minimum)


def budget_timeout(cap: float, fallback: float | None = None) -> float | None:
    """预算内返回 min(cap, 剩余)；未开启预算时返回 fallback。"""
    budget = _budget.get()
    if budget is None:
        return fallback
    return budget.call_timeout(cap)
