"""LLM 代理（decorator）共享基类：收敛 Runnable 接口的转发口径。

`FailoverModel` / `ThrottledModel` / `ThinkingRouter` 都是「包住内层模型、对外仍是
同款 Runnable」的装饰器。LangChain 的 Runnable 接口面较宽
（invoke / ainvoke / stream / astream / bind / bind_tools / with_config），
此前三个类各自手写一遍转发样板，带来两个问题：

1. **重复**：`__getattr__`、`bind_tools`、`with_config` 的样板三处各写一份；
2. **易漏**：接口面新增方法时容易漏转发。历史上 `ThinkingRouter` 漏了 `with_config`
   （经 `__getattr__` 落到内层，返回的模型**丢掉了开关语义**），
   而 `FailoverModel.with_config` 收到 `config` 后**丢弃了参数**、没有透传。

本基类把「转发」收敛到一处，子类只实现两个钩子并覆写需要拦截的方法：

- ``_target``：当前应转发到的内层模型。可以是 property，从而支持动态选择
  （如 ``ThinkingRouter`` 按开关在 ON/OFF 副本间切换）。
- ``_derive``：按变换函数构造**同类**新实例，供 bind / bind_tools / with_config 使用，
  保证派生后仍带着本层语义（限流 / 熔断 / 降级链 / 开关不旁路）。
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = ["DelegatingRunnable"]


class DelegatingRunnable:
    """Runnable 转发基类。

    子类需实现 ``_target`` 与 ``_derive``；`invoke` / `ainvoke` / `stream` / `astream`
    / `bind` / `bind_tools` / `with_config` / `__getattr__` 由本类提供，
    需要拦截（限流、降级链遍历、开关切换等）时在子类覆写。
    """

    # ---------------- 子类钩子 ----------------

    @property
    def _target(self) -> Any:
        """当前应转发到的内层模型。"""
        raise NotImplementedError

    def _derive(self, transform: Callable[[Any], Any]) -> "DelegatingRunnable":
        """用 ``transform`` 变换内层模型，并返回同类型的新实例。"""
        raise NotImplementedError

    # ---------------- 派生（返回值仍带本层包装） ----------------

    def bind(self, **kwargs: Any) -> "DelegatingRunnable":
        return self._derive(lambda model: model.bind(**kwargs))

    def bind_tools(self, tools: Any, **kwargs: Any) -> "DelegatingRunnable":
        return self._derive(lambda model: model.bind_tools(tools, **kwargs))

    def with_config(self, config: Any = None, **kwargs: Any) -> "DelegatingRunnable":
        return self._derive(lambda model: model.with_config(config, **kwargs))

    # ---------------- 执行 ----------------

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        return self._target.invoke(*args, **kwargs)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        return await self._target.ainvoke(*args, **kwargs)

    def stream(self, *args: Any, **kwargs: Any):
        yield from self._target.stream(*args, **kwargs)

    async def astream(self, *args: Any, **kwargs: Any):
        async for chunk in self._target.astream(*args, **kwargs):
            yield chunk

    # ---------------- 其余属性委托 ----------------

    def __getattr__(self, name: str) -> Any:
        """把 model_name / get_input_schema 等其余属性委托给内层模型。

        ``__getattr__`` 仅在常规属性查找失败时触发。对下划线开头的名字直接拒绝：
        子类内部属性（``_inner`` / ``_on`` / ``_primary`` 等）若尚未赋值，
        转发会去读 ``_target`` 再触发自身查找，形成无限递归。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._target, name)
