"""主模型降级链（FailoverModel）。

- 链配置存 PG app_config（llm_failover_chain），管理后台 Web 端可热改，30s TTL 缓存
- 主模型调用失败（限流/超时/5xx/熔断打开/模型不存在）时按链序自动切换下一模型
- 客户端参数类错误（400 参数非法、鉴权失败）不降级，直接抛出
- 每链位模型独立熔断（per-model circuit），失败主模型不会连累备选
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from app.core.config import settings
from app.core.llm_throttle import LLMBusyError
from app.core.logger import log

_CHAIN_KEY = "llm_failover_chain"
_CHAIN_TTL_SECONDS = 30.0


class ModelUnavailableError(RuntimeError):
    """链上所有模型都失败时抛出，上层转友好文案。"""


def _retryable(exc: Exception) -> bool:
    """判断异常是否值得切换模型重试。"""
    name = f"{exc.__class__.__module__}.{exc.__class__.__name__}"
    if isinstance(exc, LLMBusyError):
        # 熔断打开/排队超时：本模型不健康，换下一个
        return True
    if "RateLimitError" in name or "APITimeoutError" in name or "APIConnectionError" in name:
        return True
    if "InternalServerError" in name:
        return True
    if "BadRequestError" in name or "NotFoundError" in name:
        # 模型不存在/无权限属可降级错误；其余 400/404 是请求本身的问题，换模型也会一样失败
        msg = str(exc).lower()
        return "model" in msg and ("not exist" in msg or "not found" in msg or "does not exist" in msg or "no access" in msg)
    if "ReadTimeout" in name or "ConnectError" in name or "RemoteProtocolError" in name:
        return True
    return False


_active_chain: list[str] = []
_active_chain_at: float = 0.0
_chain_lock = threading.Lock()


def get_active_chain() -> list[str]:
    """当前降级链（30s TTL 缓存；PG 不可用/未配置时回退 [主模型] 单元素链）。"""
    global _active_chain, _active_chain_at
    now = time.monotonic()
    with _chain_lock:
        if now - _active_chain_at < _CHAIN_TTL_SECONDS:
            return list(_active_chain)
        try:
            from app.db.app_config import get_config

            stored = get_config(_CHAIN_KEY)
            models = [str(m).strip() for m in (stored or {}).get("models", []) if str(m).strip()]
            _active_chain = models or [settings.dashscope_model]
        except Exception as e:
            log.warning("降级链配置读取失败，回退为主模型单元素链: {}", e)
            _active_chain = [settings.dashscope_model]
        _active_chain_at = now
        return list(_active_chain)


def invalidate_chain_cache() -> None:
    """管理后台修改链配置后立即生效。"""
    global _active_chain_at
    with _chain_lock:
        _active_chain_at = 0.0


class FailoverModel:
    """按降级链执行的主模型包装器（最外层）。

    链首为主模型实例（primary，由 main.py 传入）；其余链位按模型名懒建实例。
    bind/with_config 等派生返回携带绑定参数的新包装器，保持限流/计量不旁路。
    """

    def __init__(
        self,
        primary: Any,
        factory: Callable[[str], Any],
        *,
        bound: dict | None = None,
    ) -> None:
        self._primary = primary
        self._factory = factory
        self._bound = dict(bound or {})
        self._instances: dict[str, Any] = {settings.dashscope_model: primary}
        self._instances_lock = threading.Lock()

    # ---- 派生方法 ----
    def bind(self, **kwargs: Any) -> "FailoverModel":
        return FailoverModel(self._primary, self._factory, bound={**self._bound, **kwargs})

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FailoverModel":
        # ReAct 路径绑定工具：只对主模型绑定（bind_tools 与降级链合并的复杂度不值得引入）
        return FailoverModel(self._primary.bind_tools(tools, **kwargs), self._factory, bound=dict(self._bound))

    def with_config(self, config: Any = None, **kwargs: Any) -> "FailoverModel":
        return FailoverModel(self._primary, self._factory, bound=dict(self._bound))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._primary, name)

    # ---- 链解析 ----
    def _resolve_model(self, name: str) -> Any:
        with self._instances_lock:
            instance = self._instances.get(name)
            if instance is None:
                instance = self._factory(name)
                self._instances[name] = instance
            return instance

    def _chain_models(self) -> list[Any]:
        return [self._resolve_model(name) for name in get_active_chain()]

    def _merged_kwargs(self, kwargs: dict) -> dict:
        return {**self._bound, **kwargs}

    # ---- 执行入口 ----
    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        merged = self._merged_kwargs(kwargs)
        last_error: Exception | None = None
        for idx, model in enumerate(self._chain_models()):
            try:
                return model.invoke(*args, **merged)
            except Exception as exc:
                if not _retryable(exc):
                    raise
                log.warning("[failover] 链路第 {} 个模型 {} 失败: {}", idx + 1, getattr(model, "model_name", "?"), exc)
                last_error = exc
        raise ModelUnavailableError(f"降级链全部模型均不可用: {last_error}")

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        import asyncio

        return await asyncio.to_thread(self.invoke, *args, **kwargs)

    def stream(self, *args: Any, **kwargs: Any):
        merged = self._merged_kwargs(kwargs)
        last_error: Exception | None = None
        for idx, model in enumerate(self._chain_models()):
            try:
                yield from model.stream(*args, **merged)
                return
            except Exception as exc:
                if not _retryable(exc):
                    raise
                log.warning("[failover] 链路第 {} 个模型 {} 流式失败: {}", idx + 1, getattr(model, "model_name", "?"), exc)
                last_error = exc
        raise ModelUnavailableError(f"降级链全部模型均不可用: {last_error}")

    async def astream(self, *args: Any, **kwargs: Any):
        merged = self._merged_kwargs(kwargs)
        last_error: Exception | None = None
        for idx, model in enumerate(self._chain_models()):
            try:
                async for chunk in model.astream(*args, **merged):
                    yield chunk
                return
            except Exception as exc:
                if not _retryable(exc):
                    raise
                log.warning("[failover] 链路第 {} 个模型 {} 流式失败: {}", idx + 1, getattr(model, "model_name", "?"), exc)
                last_error = exc
        raise ModelUnavailableError(f"降级链全部模型均不可用: {last_error}")