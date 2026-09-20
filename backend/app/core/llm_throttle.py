"""LLM 调用背压与计量：全局并发信号量 + 连续失败熔断 + token 用量成本归因。

DashScope 按账号共享 QPS/TPM 配额，应用内多个模型实例（生成/拆解/审核/子应用）
的并发必须统一限制，否则请求洪峰直接触发上游限流，超配额请求重试也照常计费。
熔断用于上游持续故障（API Key 失效 / 5xx）时快速失败，避免每个请求空等重试。
所有模型的成功调用在此统一上报 token/耗时（按用途标签归因），供 /metrics 查成本。
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from app.core.config import settings
from app.core.llm_delegate import DelegatingRunnable
from app.core.logger import log


class LLMBusyError(RuntimeError):
    """排队超时或熔断打开时抛出，上层转换为友好文案。"""


# 用途标签（成本归因）：由调用方用 llm_tag() 包裹设置，ThrottledModel 上报时读取
llm_usage_tag: ContextVar[str] = ContextVar("llm_usage_tag", default="unknown")

# 合法标签清单（单一事实源）：新增调用路径必须在这里登记，否则成本页的"用途"列
# 会出现无法解释的行。前端 `Observability.vue` 的中文映射与此一一对应。
#   workflow 命理问答编排（拆解/生成/审核/修复整条链） | react ReAct 工具循环
#   chitchat 闲聊直答 | summary 会话摘要 | report 命理报告 | kline K线批注
#   probe 启动探活 | tarot/liuyao/ziwei/hehun 子应用解读
CANONICAL_TAGS: tuple[str, ...] = (
    "workflow",
    "react",
    "chitchat",
    "summary",
    "report",
    "kline",
    "probe",
    "tarot",
    "liuyao",
    "ziwei",
    "hehun",
)

# 未打标签的调用只警告一次（按模型）：成本页出现"用途 unknown"就是这里漏包 llm_tag
_untagged_warned: set[str] = set()
_untagged_lock = threading.Lock()


def _warn_untagged_once(model: str) -> None:
    with _untagged_lock:
        if model in _untagged_warned:
            return
        _untagged_warned.add(model)
    log.warning(
        "[llm] {} 的调用未打用途标签（成本页会记成 unknown）：调用方需用 llm_tag(...) 包裹",
        model,
    )


@contextmanager
def llm_tag(tag: str) -> Iterator[None]:
    """标记当前执行上下文的 LLM 用途（取值见 `CANONICAL_TAGS`）。"""
    token = llm_usage_tag.set(tag)
    try:
        yield
    finally:
        llm_usage_tag.reset(token)


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


# 进程内全局共享：并发额度全局统一；熔断按模型隔离
# （降级链场景下主模型故障不能误伤备选模型的调用）
_semaphore = threading.BoundedSemaphore(settings.llm_max_concurrency)
_circuits: dict[str, _CircuitBreaker] = {}
_circuits_lock = threading.Lock()


def _circuit_for(model: str) -> _CircuitBreaker:
    with _circuits_lock:
        circuit = _circuits.get(model)
        if circuit is None:
            circuit = _CircuitBreaker(settings.llm_circuit_failure_threshold, settings.llm_circuit_open_seconds)
            _circuits[model] = circuit
        return circuit


def _extract_usage(result: Any) -> tuple[int, int]:
    """从 LLM 响应提取 (prompt_tokens, completion_tokens)；来源缺失记 0。"""
    meta = getattr(result, "response_metadata", None)
    usage = meta.get("token_usage") if isinstance(meta, dict) else None
    if usage is None:
        usage = getattr(result, "usage_metadata", None)

    def _get(field: str) -> int:
        if hasattr(usage, field):
            try:
                return int(getattr(usage, field) or 0)
            except (TypeError, ValueError):
                return 0
        if isinstance(usage, dict):
            try:
                return int(usage.get(field) or 0)
            except (TypeError, ValueError):
                return 0
        return 0

    return _get("prompt_tokens"), _get("completion_tokens")


def _report_usage(wrapper: "ThrottledModel", result: Any, start: float, elapsed: float | None = None) -> None:
    """成功调用后上报 token/耗时（模型名经 __getattr__ 委托内层取）。"""
    from app.core.observability import record_llm_call

    if result is None:
        return
    prompt, completion = _extract_usage(result)
    if elapsed is None:
        elapsed = time.perf_counter() - start
    model = getattr(wrapper, "model_name", None) or "unknown"
    tag = llm_usage_tag.get()
    if tag == "unknown":
        # 漏包 llm_tag 是**成本归因的缺陷**，不是正常状态：留一条可 grep 的日志，
        # 免得只能在成本页看到一行无从排查的 unknown（2026-09-20 的探活/K线批注就是这种）。
        _warn_untagged_once(model)
    record_llm_call(model, tag, prompt, completion, elapsed * 1000)


class ThrottledModel(DelegatingRunnable):
    """包装 LangChain ChatModel：进入 invoke/stream 前获取全局信号量并过熔断。

    转发面（bind/bind_tools/with_config 派生 + 其余属性委托）由 ``DelegatingRunnable``
    提供，保证限流不旁路；本类只覆写 invoke/ainvoke/stream/astream 加入背压与计量。
    熔断按模型名隔离（降级链中主模型故障不影响备选模型）。
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._model_name = str(getattr(inner, "model_name", None) or "unknown")
        self._circuit = _circuit_for(self._model_name)

    # ---- DelegatingRunnable 钩子 ----
    @property
    def _target(self) -> Any:
        return self._inner

    def _derive(self, transform: Any) -> "ThrottledModel":
        """派生后仍是 ThrottledModel，保证限流/熔断不被 bind 旁路。"""
        return ThrottledModel(transform(self._inner))

    # ---- 背压入口 ----
    def _acquire(self) -> None:
        self._circuit.check()
        if not _semaphore.acquire(timeout=settings.llm_queue_timeout):
            raise LLMBusyError("当前咨询人数较多，请稍后再试")

    def _release(self) -> None:
        _semaphore.release()

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        self._acquire()
        start = time.perf_counter()
        try:
            result = self._inner.invoke(*args, **kwargs)
            self._circuit.record_success()
            _report_usage(self, result, start)
            return result
        except Exception:
            self._circuit.record_failure()
            raise
        finally:
            self._release()

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        # 放线程池执行同步 invoke，信号量/熔断/计量语义同同步路径
        return await asyncio.to_thread(self.invoke, *args, **kwargs)

    def stream(self, *args: Any, **kwargs: Any):
        self._acquire()
        start = time.perf_counter()
        last = None
        try:
            for chunk in self._inner.stream(*args, **kwargs):
                last = chunk
                yield chunk
            self._circuit.record_success()
            # OpenAI 兼容流式：usage 聚合在最后一个 chunk
            _report_usage(self, last, start)
        except Exception:
            self._circuit.record_failure()
            raise
        finally:
            self._release()

    async def astream(self, *args: Any, **kwargs: Any):
        await asyncio.to_thread(self._acquire)
        start = time.perf_counter()
        last = None
        try:
            async for chunk in self._inner.astream(*args, **kwargs):
                last = chunk
                yield chunk
            self._circuit.record_success()
            _report_usage(self, last, start)
        except Exception:
            self._circuit.record_failure()
            raise
        finally:
            self._release()
