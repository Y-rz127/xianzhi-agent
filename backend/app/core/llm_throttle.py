"""LLM 调用背压：全局并发信号量 + 连续失败熔断。

DashScope 按账号共享 QPS/TPM 配额，应用内多个模型实例（生成/拆解/审核/子应用）
的并发必须统一限制，否则请求洪峰直接触发上游限流，超配额请求重试也照常计费。
熔断用于上游持续故障（API Key 失效 / 5xx）时快速失败，避免每个请求空等重试。
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from app.core.config import settings


class LLMBusyError(RuntimeError):
    """排队超时或熔断打开时抛出，上层转换为友好文案。"""


class _CircuitBreaker:
    def __init__(self, threshold: int, open_seconds: float) -> None:
        self._threshold = threshold
        self._open_seconds = open_seconds
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at = 0.0

    def check(self) -> None:
        with self._lock:
            if self._opened_at:
                if time.monotonic() - self._opened_at < self._open_seconds:
                    raise LLMBusyError("服务暂时不可用，请稍后再试")
                # 冷却结束，放行一个请求试探（半开）
                self._opened_at = 0.0
                self._failures = 0

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = 0.0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                self._opened_at = time.monotonic()


# 进程内全局共享：并发额度与熔断状态对全部模型实例统一计量
_semaphore = threading.BoundedSemaphore(settings.llm_max_concurrency)
_circuit = _CircuitBreaker(settings.llm_circuit_failure_threshold, settings.llm_circuit_open_seconds)


class ThrottledModel:
    """包装 LangChain ChatModel：进入 invoke/stream 前获取全局信号量并过熔断。

    bind/bind_tools/with_config 派生方法仍返回 ThrottledModel，保证限流不旁路；
    其余属性委托给内层模型（model_name / get_input_schema 等）。
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    # ---- 派生方法保持包装 ----
    def bind(self, **kwargs: Any) -> "ThrottledModel":
        return ThrottledModel(self._inner.bind(**kwargs))

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ThrottledModel":
        return ThrottledModel(self._inner.bind_tools(tools, **kwargs))

    def with_config(self, config: Any = None, **kwargs: Any) -> "ThrottledModel":
        return ThrottledModel(self._inner.with_config(config, **kwargs))

    # ---- 背压入口 ----
    @staticmethod
    def _acquire() -> None:
        _circuit.check()
        if not _semaphore.acquire(timeout=settings.llm_queue_timeout):
            raise LLMBusyError("当前咨询人数较多，请稍后再试")

    @staticmethod
    def _release() -> None:
        _semaphore.release()

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        self._acquire()
        try:
            result = self._inner.invoke(*args, **kwargs)
            _circuit.record_success()
            return result
        except Exception:
            _circuit.record_failure()
            raise
        finally:
            self._release()

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        # 放线程池执行同步 invoke，信号量与熔断语义同同步路径
        return await asyncio.to_thread(self.invoke, *args, **kwargs)

    def stream(self, *args: Any, **kwargs: Any):
        self._acquire()
        try:
            for chunk in self._inner.stream(*args, **kwargs):
                yield chunk
            _circuit.record_success()
        except Exception:
            _circuit.record_failure()
            raise
        finally:
            self._release()

    async def astream(self, *args: Any, **kwargs: Any):
        await asyncio.to_thread(self._acquire)
        try:
            async for chunk in self._inner.astream(*args, **kwargs):
                yield chunk
            _circuit.record_success()
        except Exception:
            _circuit.record_failure()
            raise
        finally:
            self._release()

    # ---- 其余属性/方法委托内层 ----
    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)