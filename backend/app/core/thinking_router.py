"""思考模式中间件（ThinkingRouter）。

背景
----
主模型 `enable_thinking` 在 langchain ``ChatOpenAI`` 上是构造期写死的（``extra_body``），
无法按请求切换。本项目希望「闲聊关思考、其他开思考」，而闲聊判定在两条路径里都已经现成
（ReAct 路径 ``Xianzhi._is_chitchat``、Workflow 路径 ``detect_domain``/``classify_question``）。

设计
----
``ThinkingRouter`` 包住底层 ``ChatOpenAI``，对外仍是同款 Runnable（``invoke``/``ainvoke``/
``stream``/``astream``/``bind_tools``/``bind`` 全部可用），调用方零感知。

- 构造期派生出 ``_on`` / ``_off`` 两个底层模型副本（各自把 ``enable_thinking`` 烤进 ``extra_body``），
  避免运行时对 ``RunnableBinding`` 做 ``model_copy`` 注入 ``extra_body`` 的不确定性。
- 每次调用前读取 ``contextvars`` 里的开关（由调用方在 ``answer()`` 入口用 ``use_thinking`` 设置），
  挑 ``_on`` 或 ``_off`` 委托。未设置时回落到 ``default_thinking``。
- ``bind_tools`` / ``bind`` 返回新的 ``ThinkingRouter``，其内部已把工具绑定到 ON/OFF 两个副本上，
  因此工具调用同样受开关控制。

线程/协程安全：contextvar 天然按请求任务隔离，无需额外锁。
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional

# None = 未显式设置，回落到 default_thinking
thinking_override: ContextVar[Optional[bool]] = ContextVar("thinking_override", default=None)


@contextmanager
def use_thinking(on: bool) -> Iterator[None]:
    """上下文管理器：进入时关/开思考，退出时复位，避免开关泄漏到后续调用。

    用法::

        with use_thinking(False):   # 闲聊
            return self._chitchat_reply(user_prompt)
    """
    token = thinking_override.set(on)
    try:
        yield
    finally:
        thinking_override.reset(token)


class ThinkingRouter:
    """按 contextvar 透明切换 ``enable_thinking`` 的模型中间件。

    Args:
        base: 底层 ``ChatOpenAI`` 实例（仅在直接构造时需要）。
        on/off: 已派生好的 ON/OFF 副本（``bind_tools``/``bind`` 复用，避免重复派生）。
        default_thinking: 未显式设置开关时的回落值，默认 True（即「其他开思考」）。
    """

    def __init__(
        self,
        base: Any = None,
        *,
        on: Any = None,
        off: Any = None,
        default_thinking: bool = True,
    ) -> None:
        if base is not None:
            extra = dict(getattr(base, "extra_body", None) or {})
            self._on = base.model_copy(update={"extra_body": {**extra, "enable_thinking": True}})
            self._off = base.model_copy(update={"extra_body": {**extra, "enable_thinking": False}})
        else:
            self._on = on
            self._off = off
        self._default = default_thinking

    # ---- 开关解析 ----
    def pick(self) -> Any:
        v = thinking_override.get()
        on = self._default if v is None else v
        return self._on if on else self._off

    # ---- Runnable 接口转发 ----
    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        return self.pick().invoke(input, config=config, **kwargs)

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        return await self.pick().ainvoke(input, config=config, **kwargs)

    def stream(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        return self.pick().stream(input, config=config, **kwargs)

    async def astream(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        async for chunk in self.pick().astream(input, config=config, **kwargs):
            yield chunk

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ThinkingRouter":
        return ThinkingRouter(
            on=self._on.bind_tools(tools, **kwargs),
            off=self._off.bind_tools(tools, **kwargs),
            default_thinking=self._default,
        )

    def bind(self, **kwargs: Any) -> "ThinkingRouter":
        return ThinkingRouter(
            on=self._on.bind(**kwargs),
            off=self._off.bind(**kwargs),
            default_thinking=self._default,
        )

    # ---- 其余属性/方法委托给 ON 副本（model_name / model / model_dump 等）----
    def __getattr__(self, name: str) -> Any:
        # 仅当实例上找不到属性时才走到这里（_on/_off/_default 均为实例属性，不会触发）
        return getattr(self._on, name)
