"""ThinkingRouter 中间件单测（不依赖 langchain，用 fake base 验证路由逻辑）。

验证点：
1. contextvar 解析：显式 False→关、显式 True→开、未设置→回落 default。
2. ThinkingRouter 在构造期派生 ON/OFF 两份副本，各自 extra_body.enable_thinking 正确。
3. invoke / bind_tools 后 invoke 都按当前开关挑选对应副本（闲聊走 OFF、其它走 ON）。
"""

from __future__ import annotations

from contextlib import contextmanager
import asyncio

from app.core.thinking_router import (
    ThinkingRouter,
    thinking_override,
    use_thinking,
)


class _FakeModel:
    """最小可用假模型：记录 extra_body，invoke 返回带标记的对象。"""

    def __init__(self, name: str, extra_body: dict | None = None):
        self.name = name
        self.extra_body = extra_body or {}
        self.bound_tools = None

    def model_copy(self, *, update):
        # 仅支持更新 extra_body（与 ChatOpenAI 行为一致）
        new = _FakeModel(self.name, dict(self.extra_body))
        if "extra_body" in update:
            new.extra_body = dict(update["extra_body"])
        return new

    def bind_tools(self, tools, **kwargs):
        bound = _FakeModel(self.name + "[tools]", dict(self.extra_body))
        bound.bound_tools = tools
        return bound

    def invoke(self, messages, config=None, **kwargs):
        return {"content": f"{self.name}:thinking={self.extra_body.get('enable_thinking')}"}

    def astream(self, messages, config=None, **kwargs):
        async def chunks():
            yield "first"
            yield "second"

        return chunks()


@contextmanager
def _no_override():
    token = thinking_override.set(None)
    try:
        yield
    finally:
        thinking_override.reset(token)


def test_contextvar_resolution():
    # 未设置 → 回落 default
    with _no_override():
        r = ThinkingRouter(_FakeModel("m"), default_thinking=True)
        assert r.pick().extra_body["enable_thinking"] is True
        r2 = ThinkingRouter(_FakeModel("m"), default_thinking=False)
        assert r2.pick().extra_body["enable_thinking"] is False
    # 显式 False
    with use_thinking(False):
        r = ThinkingRouter(_FakeModel("m"), default_thinking=True)
        assert r.pick().extra_body["enable_thinking"] is False
    # 显式 True
    with use_thinking(True):
        r = ThinkingRouter(_FakeModel("m"), default_thinking=False)
        assert r.pick().extra_body["enable_thinking"] is True


def test_derived_copies_have_correct_flag():
    r = ThinkingRouter(_FakeModel("m", extra_body={"enable_thinking": True}), default_thinking=True)
    assert r._on.extra_body["enable_thinking"] is True
    assert r._off.extra_body["enable_thinking"] is False
    # 原 base 的其它 extra_body 键应保留
    r2 = ThinkingRouter(_FakeModel("m", extra_body={"foo": 1}), default_thinking=True)
    assert r2._on.extra_body.get("foo") == 1
    assert r2._off.extra_body.get("foo") == 1


def test_invoke_respects_switch():
    r = ThinkingRouter(_FakeModel("m"), default_thinking=True)
    with use_thinking(False):  # 闲聊
        out = r.invoke([{"role": "user", "content": "你好"}])
        assert out["content"].endswith("thinking=False")
    with use_thinking(True):  # 其它
        out = r.invoke([{"role": "user", "content": "我今年事业运如何"}])
        assert out["content"].endswith("thinking=True")


def test_bind_tools_respects_switch():
    r = ThinkingRouter(_FakeModel("m"), default_thinking=True)
    bound = r.bind_tools([{"name": "bazi_full"}])
    assert isinstance(bound, ThinkingRouter)
    with use_thinking(False):  # 闲聊 + 工具（理论上闲聊不会走工具，这里仅验证开关生效）
        out = bound.invoke([{"role": "user", "content": "hi"}])
        assert out["content"].endswith("thinking=False")
        assert out["content"].startswith("m[tools]")
    with use_thinking(True):
        out = bound.invoke([{"role": "user", "content": "hi"}])
        assert out["content"].endswith("thinking=True")


def test_switch_does_not_leak():
    r = ThinkingRouter(_FakeModel("m"), default_thinking=True)
    with use_thinking(False):
        assert r.pick().extra_body["enable_thinking"] is False
    # 退出上下文后回到 default
    with _no_override():
        assert r.pick().extra_body["enable_thinking"] is True


def test_astream_forwards_async_chunks():
    async def collect():
        router = ThinkingRouter(_FakeModel("m"))
        return [chunk async for chunk in router.astream([])]

    assert asyncio.run(collect()) == ["first", "second"]
