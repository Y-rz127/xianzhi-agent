"""DelegatingRunnable 基类与三个 LLM 代理类的转发契约测试。

这三个类（FailoverModel / ThrottledModel / ThinkingRouter）存在的意义是
「派生后语义不旁路」： bind / bind_tools / with_config 之后拿到的必须仍是同类包装器，
否则限流、熔断、降级链、思考开关会在派生处静默失效。

回归背景（本次重构修掉的两处）：
- `ThinkingRouter` 原先没有 `with_config`，经 `__getattr__` 落到内层模型，
  返回的是裸模型——**开关语义直接丢失**；
- `FailoverModel.with_config` 收到 `config` 后没有透传，**参数被丢弃**。
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from app.core.llm_delegate import DelegatingRunnable
from app.core.llm_failover import FailoverModel
from app.core.llm_throttle import ThrottledModel
from app.core.thinking_router import ThinkingRouter


class _Spy:
    """最小假模型：记录每一次调用，便于断言转发是否真的发生。"""

    def __init__(self, name: str = "spy", extra_body: dict | None = None):
        self.name = name
        self.extra_body = dict(extra_body or {})
        self.calls: list[tuple] = []

    # ---- 派生 ----
    def model_copy(self, *, update):
        new = _Spy(self.name, self.extra_body)
        if "extra_body" in update:
            new.extra_body = dict(update["extra_body"])
        return new

    def bind(self, **kwargs):
        self.calls.append(("bind", kwargs))
        return self

    def bind_tools(self, tools, **kwargs):
        self.calls.append(("bind_tools", tools, kwargs))
        return self

    def with_config(self, config=None, **kwargs):
        self.calls.append(("with_config", config, kwargs))
        return self

    # ---- 执行 ----
    def invoke(self, *args, **kwargs):
        self.calls.append(("invoke", args, kwargs))
        return f"invoke:{self.name}"

    async def ainvoke(self, *args, **kwargs):
        return f"ainvoke:{self.name}"

    def stream(self, *args, **kwargs):
        yield "s1"
        yield "s2"

    async def astream(self, *args, **kwargs):
        yield "a1"
        yield "a2"


def _failover(**kwargs) -> FailoverModel:
    return FailoverModel(_Spy("primary"), lambda name: _Spy(name), **kwargs)


def _router(**kwargs) -> ThinkingRouter:
    return ThinkingRouter(_Spy("base", {"enable_thinking": True}), default_thinking=True, **kwargs)


# ---------------- 派生后语义不旁路 ----------------


@pytest.mark.parametrize(
    "make, arg_name",
    [
        (_failover, "failover"),
        (lambda: ThrottledModel(_Spy()), "throttled"),
        (_router, "router"),
    ],
)
def test_derived_instances_keep_same_wrapper(make, arg_name) -> None:
    """bind / bind_tools / with_config 之后必须仍是同类包装器。"""
    wrapper = make()
    for produced in (wrapper.bind(a=1), wrapper.bind_tools([], b=2), wrapper.with_config({"tags": ["t"]})):
        assert isinstance(produced, type(wrapper)), (
            f"{arg_name} 派生后类型变成了 {type(produced).__name__}，本层语义会旁路"
        )


def test_thinking_router_derives_bind_both_copies() -> None:
    """RoutingRouter 的派生必须同时作用于 ON / OFF 两份副本，否则工具只在一条路径生效。"""
    router = _router()
    bound = router.bind_tools([{"name": "bazi_full"}])
    assert bound._on.calls[-1][0] == "bind_tools"
    assert bound._off.calls[-1][0] == "bind_tools"
    assert bound._default == router._default


def test_thinking_router_with_config_returns_router() -> None:
    """回归：with_config 必须返回 ThinkingRouter，而不是经 __getattr__ 漏出裸模型。"""
    router = _router()
    out = router.with_config({"tags": ["x"]})

    assert isinstance(out, ThinkingRouter), "with_config 漏出了裸模型，思考开关会失效"
    for copy in (out._on, out._off):
        assert ("with_config", {"tags": ["x"]}, {}) in copy.calls


def test_failover_with_config_passes_config_through() -> None:
    """回归：FailoverModel.with_config 必须把 config 透传给主模型，不能丢弃参数。"""
    primary = _Spy("primary")
    fm = FailoverModel(primary, lambda name: _Spy(name))

    fm.with_config({"tags": ["trace"]})

    assert ("with_config", {"tags": ["trace"]}, {}) in primary.calls, "config 被丢弃"


def test_failover_bind_accumulates_instead_of_binding_primary() -> None:
    """FailoverModel.bind 语义特殊：累积绑定参数，在 invoke 时投给链上每个模型。"""
    primary = _Spy("primary")
    fm = FailoverModel(primary, lambda name: _Spy(name)).bind(temperature=0.5)

    assert fm._bound == {"temperature": 0.5}
    assert primary.calls == [], "bind 不应立即 bind 主模型（那样降级到备选模型时参数会丢）"


# ---------------- 属性委托 ----------------


@pytest.mark.parametrize(
    "make, expected_name",
    [
        (_failover, "primary"),
        (lambda: ThrottledModel(_Spy("spy")), "spy"),
        (_router, "base"),
    ],
)
def test_unknown_attribute_delegates_to_inner(make, expected_name) -> None:
    """model_name / get_input_schema 等未定义属性应落到内层模型。"""
    assert make().name == expected_name


@pytest.mark.parametrize("make", [_failover, lambda: ThrottledModel(_Spy()), _router])
def test_underscore_attribute_is_not_forwarded(make) -> None:
    """下划线名字不转发：否则子类属性未就绪时会无限递归。"""
    with pytest.raises(AttributeError):
        make()._definitely_not_defined


# ---------------- 执行转发 ----------------


def test_thinking_router_forwards_invoke_and_astream() -> None:
    router = _router()
    assert router.invoke("hi").startswith("invoke:")
    assert list(router.stream("hi")) == ["s1", "s2"]
    assert asyncio.run(_collect(router.astream("hi"))) == ["a1", "a2"]


def test_throttled_model_forwards_invoke() -> None:
    inner = _Spy()
    assert ThrottledModel(inner).invoke("hi") == "invoke:spy"


async def _collect(agen) -> list:
    return [item async for item in agen]


def test_base_class_declares_expected_surface() -> None:
    """接口面清单化：LangChain 侧新增需转发的方法时，这里会提醒同步补齐。"""
    for name in ("invoke", "ainvoke", "stream", "astream", "bind", "bind_tools", "with_config"):
        assert hasattr(DelegatingRunnable, name), f"基类缺少 {name}"
    assert inspect.isasyncgenfunction(DelegatingRunnable.astream)
