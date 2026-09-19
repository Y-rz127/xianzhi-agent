"""子应用解读模型（`SUB_APP_MODEL`）与「先知问答」主模型分离的回归测试。

背景
----
塔罗 / 紫微 / 六爻 / 合婚的解读原先一律取 `get_app_context().chat_model`，与问答主模型
共用一个实例 ⇒ 想给子应用换个便宜快模型就得连问答一起换（反之亦然）。现在统一走
`get_sub_app_model()`：配了 `SUB_APP_MODEL` 就用独立实例，留空则回落主模型（旧行为不变）。

这组测试锁两件事：
1. 四个子应用的解读入口**确实**走子应用模型（逐个入口验证，别只看一处）；
2. 它是**按请求解析**的 —— 启动探活可能整体替换模型实例，装配期抓住引用会让纠正失效。
"""

from __future__ import annotations

import asyncio
import pathlib
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from app.agent.context import AppContext, get_sub_app_model, set_app_context, sub_app_model_of
from app.sub_app import _base as sub_app_base
from app.sub_app.tarot.tarot_app import TarotApp


class _FakeModel:
    """记录被调用次数的假模型：区分一次性调用（六爻/紫微）与流式（塔罗/共享骨架）。"""

    def __init__(self, text: str = "解读内容") -> None:
        self.text = text
        self.invocations = 0
        self.streams = 0

    async def ainvoke(self, messages, **kwargs):
        self.invocations += 1
        return AIMessage(content=self.text)

    async def astream(self, messages, **kwargs):
        self.streams += 1
        yield AIMessageChunk(content=self.text)

    def bind(self, **kwargs):
        return self

    def invoke(self, messages, **kwargs):
        self.invocations += 1
        return AIMessage(content=self.text)


@pytest.fixture
def ctx_pair():
    """装一个「主模型 ≠ 子应用模型」的上下文替身，用完恢复成未初始化。"""
    main, sub = _FakeModel("来自主模型"), _FakeModel("来自子应用模型")
    ctx = SimpleNamespace(chat_model=main, sub_app_model=sub)
    set_app_context(ctx)
    try:
        yield SimpleNamespace(main=main, sub=sub)
    finally:
        set_app_context(None)


async def _collect(agen) -> str:
    return "".join([chunk async for chunk in agen])


# ============================================================
# 1. 解析规则
# ============================================================

def test_app_context_defaults_sub_app_model_to_chat_model():
    """留空即复用主模型：旧部署（.env 里没有 SUB_APP_MODEL）行为必须一字不变。"""
    main = _FakeModel()
    ctx = AppContext(chat_model=main, local_tools=[], memory=None)
    assert ctx.sub_app_model is main


def test_app_context_keeps_dedicated_sub_app_model():
    main, sub = _FakeModel(), _FakeModel()
    ctx = AppContext(chat_model=main, local_tools=[], memory=None, sub_app_model=sub)
    assert ctx.sub_app_model is sub and ctx.chat_model is main


def test_get_sub_app_model_raises_when_uninitialized():
    """没有上下文时与 get_app_context 同口径报错（不静默回落到 None 去调 LLM）。"""
    with pytest.raises(RuntimeError, match="AppContext not initialized"):
        get_sub_app_model()


def test_get_sub_app_model_tolerates_context_without_field():
    """测试替身可能只塞了 chat_model：按字段缺失回落主模型，而不是 AttributeError。"""
    main = _FakeModel()
    set_app_context(SimpleNamespace(chat_model=main))  # type: ignore[arg-type]
    try:
        assert get_sub_app_model() is main
    finally:
        set_app_context(None)


def test_get_sub_app_model_prefers_dedicated(ctx_pair):
    assert get_sub_app_model() is ctx_pair.sub


def test_sub_app_model_of_works_with_injected_or_stub_context():
    """按 ctx 取（而不是模块级）是给"注入式"调用点用的：K 线批注端点拿到的是 app_ctx 参数。"""
    main, sub = _FakeModel(), _FakeModel()
    assert sub_app_model_of(SimpleNamespace(chat_model=main, sub_app_model=sub)) is sub
    assert sub_app_model_of(SimpleNamespace(chat_model=main)) is main, "替身缺字段 ⇒ 回落主模型"
    assert sub_app_model_of(SimpleNamespace()) is None, "两者都没有 ⇒ None（调用方自己判 503）"


# ============================================================
# 2. 四个子应用入口逐个验证（只看一处会漏）
# ============================================================

def test_ziwei_interpret_uses_sub_app_model(ctx_pair):
    from app.sub_app.ziwei import routes as ziwei_routes

    out = asyncio.run(ziwei_routes.ziwei_interpret({"date": "1990-05-20", "time_index": 4, "gender": "男"}))

    assert out["text"] == "来自子应用模型"
    assert ctx_pair.sub.invocations == 1
    assert ctx_pair.main.invocations == 0, "紫微解读不能再打主问答模型"


def test_liuyao_interpret_uses_sub_app_model(ctx_pair):
    from app.sub_app.liuyao import routes as liuyao_routes

    result = asyncio.run(liuyao_routes.cast_liuyao({"method": "numbers", "numbers": [7, 8]}))
    out = asyncio.run(liuyao_routes.interpret_liuyao({"question": "这次面试如何？", "result": result}))

    assert out["interpretation"] == "来自子应用模型"
    assert ctx_pair.sub.invocations == 1
    assert ctx_pair.main.invocations == 0


def test_tarot_stream_uses_sub_app_model(ctx_pair):
    app = TarotApp()  # 生产装配不注入模型
    cards = app.draw_cards("daily")

    text = asyncio.run(_collect(app.divine_stream("今天运势如何", "daily", cards)))

    assert text == "来自子应用模型"
    assert ctx_pair.sub.streams == 1
    assert ctx_pair.main.streams == 0


def test_tarot_explicit_injection_still_wins(ctx_pair):
    """显式注入优先（既有测试与特殊装配都这么用），注入后不再看上下文。"""
    injected = _FakeModel("注入的模型")
    app = TarotApp(chat_model=injected)

    text = asyncio.run(_collect(app.divine_stream("今天运势如何", "daily", app.draw_cards("daily"))))

    assert text == "注入的模型"
    assert injected.streams == 1
    assert ctx_pair.sub.streams == 0


def test_shared_stream_skeleton_uses_sub_app_model(ctx_pair):
    """`_base.llm_interpret_stream` 是合婚/六爻/紫微 `*_app.py` 的公共流式骨架，同样要吃到配置。"""
    text = asyncio.run(
        _collect(
            sub_app_base.llm_interpret_stream(
                [HumanMessage(content="解读一下")],
                tag="test",
                name="测试子应用",
                empty_text="回退文本",
            )
        )
    )

    assert text == "来自子应用模型"
    assert ctx_pair.sub.streams == 1
    assert ctx_pair.main.streams == 0


def test_shared_stream_skeleton_keeps_fallback_on_error():
    """回归：骨架的异常回退文案不能因为换模型解析而丢掉。"""
    class _Boom(_FakeModel):
        async def astream(self, messages, **kwargs):
            raise RuntimeError("上游炸了")
            yield  # pragma: no cover —— 让它是 async generator

    set_app_context(SimpleNamespace(chat_model=_Boom(), sub_app_model=_Boom()))  # type: ignore[arg-type]
    try:
        text = asyncio.run(
            _collect(
                sub_app_base.llm_interpret_stream(
                    [HumanMessage(content="解读一下")],
                    tag="test",
                    name="测试子应用",
                    empty_text="回退文本",
                )
            )
        )
    finally:
        set_app_context(None)

    assert "AI 解读暂不可用" in text and "RuntimeError" in text


# ============================================================
# 3. 命理报告 / K 线批注：也算子应用解读（2026-09-19 纳入）
# ============================================================

def test_report_worker_resolves_sub_app_model_per_task(ctx_pair):
    """报告任务（命理报告）按需取子应用解读模型，而不是把实例抓在 worker 循环外。

    抓死引用会让启动探活对子模型的纠正失效（见 resolve_report_model docstring）。
    """
    from app.tasks.worker import resolve_report_model

    assert resolve_report_model() is ctx_pair.sub, "不传实例 ⇒ 取子应用解读模型"
    assert resolve_report_model(None) is ctx_pair.sub
    assert resolve_report_model(ctx_pair.main) is ctx_pair.main, "显式传入优先（测试/特殊装配）"


def test_report_generation_uses_the_model_it_is_given(ctx_pair):
    """报告生成只吃传入的模型（装配层给谁就用谁）——它是 resolve_report_model 的下游契约。"""
    from app.tools.report_tasks import run_task

    out = run_task(ctx_pair.sub, "full_report", {"birth_time": "1990-05-20 14:30", "gender": "男"})
    assert isinstance(out, bytes) and out
    assert ctx_pair.sub.invocations >= 1, "报告必须真的调用了传入模型"
    assert ctx_pair.main.invocations == 0, "不能顺手打主问答模型"


def test_kline_annotation_uses_sub_app_model():
    """K 线 AI 批注走注入的 app_ctx ⇒ 也取子应用解读模型（未配置才回落主模型）。"""
    from app.api import xianzhi_kline
    from app.tools.cache import bazi_cache

    bazi_cache.clear()  # 批注结果有缓存，命中缓存就不会调模型（否则本用例会假绿/假红）
    main, sub = _FakeModel("来自主模型"), _FakeModel("K 线批注正文")
    body = xianzhi_kline.KlineAnnotationRequest(birth_time="1988-03-03 09:00", gender="男")
    try:
        asyncio.run(xianzhi_kline.annotate_kline(body, app_ctx=SimpleNamespace(chat_model=main, sub_app_model=sub)))
    except Exception:
        # 批注内容会被事实校验，可能返回 ok=False 或抛错 —— 本用例只关心"用了哪个模型"
        pass

    assert sub.invocations >= 1, "批注必须打子应用解读模型"
    assert main.invocations == 0, "批注不该再打主问答模型"


# ============================================================
# 4. 守卫：别再退回"直取主模型"
# ============================================================

def test_no_sub_app_module_reads_main_chat_model():
    """`app/sub_app/**` 里不许再出现 `get_app_context().chat_model`。

    出现即绕开 SUB_APP_MODEL（子应用模型配置静默失效），这类"配置看着生效其实没生效"
    正是本轮要消灭的故障类型。报告与 K 线批注不在 `app/sub_app/` 下，由下面两条守卫覆盖。
    """
    import app.sub_app as sub_app_pkg

    root = pathlib.Path(sub_app_pkg.__file__).parent
    offenders = [
        f"{p.relative_to(root)}:{lineno}"
        for p in sorted(root.rglob("*.py"))
        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if "get_app_context().chat_model" in line
    ]
    assert not offenders, f"子应用解读应走 get_sub_app_model()，直接取主模型的位置：{offenders}"


def test_report_and_kline_chains_resolve_sub_app_model_not_main():
    """守卫：报告 worker 与 K 线批注端点必须走子应用模型解析。

    这两处曾是 `app_ctx.chat_model` / `worker_loop(app_ctx.chat_model)` 直取主模型；
    名字写死在源码里，故用文本守卫钉死（行为侧由上面两条用例覆盖）。
    """
    import app.api.xianzhi_kline as kline_api
    import app.tasks.worker as report_worker
    import main as app_main

    kline_src = pathlib.Path(kline_api.__file__).read_text(encoding="utf-8")
    assert "sub_app_model_of(app_ctx)" in kline_src, "K 线批注端点必须按 app_ctx 取子应用解读模型"
    assert "getattr(app_ctx, \"chat_model\"" not in kline_src, "别再退回直取主模型"

    worker_src = pathlib.Path(report_worker.__file__).read_text(encoding="utf-8")
    assert "get_sub_app_model()" in worker_src, "报告 worker 必须按任务取子应用解读模型"

    main_src = pathlib.Path(app_main.__file__).read_text(encoding="utf-8")
    assert "worker_loop(None, report_stop)" in main_src, (
        "main 不应把模型实例注入报告 worker（探活替换后纠正会失效）"
    )
