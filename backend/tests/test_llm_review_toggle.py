"""LLM 审核开关（WORKFLOW_LLM_REVIEW_ENABLED）双模式回归测试。

背景：用户要求「审核开关」配置项——开启时走现状（正则+LLM 审核+修复，审完整段再发）；
关闭时改成纯流式：审核/修复与逐 token 下发天然互斥，check/repair 节点整体跳过，
生成阶段逐 token 直出。流式下「生成完整后再 clean_think_tags」失效，故发送侧加
ThinkStreamGuard 挡思考块泄漏。

验证点：
1. ThinkStreamGuard：思考块过滤、滞后窗口、跨 chunk 断裂、flush；
2. invoke_stream：token 转发、思考过滤、空产出兜底也转发；
3. 图路由：节点固定注册以支持不同用户的逐轮开关，关闭审核时 generate 直通 END；
4. _generate_node：按开关分流 invoke / invoke_stream，流式模式写 final_answer；
5. _workflow_stream：按开关选择「整段一次」还是「token 逐块」。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessageChunk

import app.agent.workflow.workflow_messages as wm
import app.agent.xianzhi_langgraph as graph
from app.agent.xianzhi import Xianzhi
from app.tools.text_clean import ThinkStreamGuard

# ---------------- 1. ThinkStreamGuard ----------------

def test_guard_passes_through_plain_text():
    g = ThinkStreamGuard(lag=8)
    out = g.feed("你好，")
    assert out == ""
    out = g.feed("这是正常文本。")
    assert out == "你好"  # 超出滞后窗口的部分才放行
    assert g.flush() == "，这是正常文本。"


def test_guard_suppresses_think_block():
    g = ThinkStreamGuard(lag=8)
    assert g.feed("前面正文，" + "[思考]") == "前面正文，"
    assert g.feed("这段不该出去") == ""
    assert g.feed("[/思考]后面正文") == ""
    assert g.flush() == "后面正文"


def test_guard_suppresses_xml_think_split_across_chunks():
    g = ThinkStreamGuard(lag=8)
    assert g.feed('前文<thi') == ''
    assert g.feed('nking>内部推理') == '前文'
    assert g.feed('还有推理') == ''
    assert g.feed('</th') == ''
    assert g.feed('inking>') == ''
    assert g.feed('后文') == ''  # 仍在滞后窗口内，flush 才放行
    tail = g.flush()
    assert '后文' in tail and '内部' not in tail


def test_guard_flush_drops_unclosed_think_tail():
    g = ThinkStreamGuard(lag=8)
    assert g.feed("正文[" + "思考]" + "没写完") == "正文"
    assert g.flush() == ""  # 未闭合的抑制残余丢弃


# ---------------- 2. invoke_stream ----------------

class _StreamModel:
    """按脚本吐 chunk 的假模型：bind 返回自身，stream 逐个产出。"""

    def __init__(self, chunks):
        self._chunks = chunks
        self.timeout = None
        self.calls = 0

    def bind(self, **kwargs):
        self.timeout = kwargs.get("timeout")
        return self

    def stream(self, messages):
        self.calls += 1
        for c in self._chunks:
            yield c


def _tok(text, finish=None):
    return AIMessageChunk(
        content=text,
        response_metadata={"finish_reason": finish} if finish else {},
    )


def test_invoke_stream_forwards_tokens_and_returns_full_text():
    model = _StreamModel([_tok("第一"), _tok("段，"), _tok("第二段", finish="stop")])
    sent: list[str] = []
    out = wm.invoke_stream(model, [], sent.append)
    assert out == "第一段，第二段"
    assert "".join(sent) == "第一段，第二段"


def test_invoke_stream_filters_think_at_send_side():
    model = _StreamModel([_tok("正文" + "[思考]"), _tok("内部推理"), _tok("[/思考]收尾", finish="stop")])
    sent: list[str] = []
    out = wm.invoke_stream(model, [], sent.append)
    assert "内部推理" not in "".join(sent)
    assert out == "正文收尾"


def test_invoke_stream_empty_output_sends_fallback():
    model = _StreamModel([])
    sent: list[str] = []
    out = wm.invoke_stream(model, [], sent.append)
    assert "模型没有生成有效解读" in out
    assert "".join(sent) == out  # 空产出时兜底文案也要让用户看到


# ---------------- 3. 图拓扑 ----------------

class _FakeWorkflow:
    pass


def test_graph_skips_check_repair_when_review_disabled(monkeypatch):
    monkeypatch.setattr(graph.settings, "workflow_llm_review_enabled", False)
    compiled = graph.create_xianzhi_graph(_FakeWorkflow())
    nodes = set(compiled.get_graph().nodes.keys())
    # 同一进程内不同用户可有不同设置，因此节点固定注册，按每轮 state 动态路由。
    assert {"classify", "chart", "retrieve", "generate", "check", "repair"} <= nodes
    assert graph._route_after_generate({"review_enabled": False}) == "end"
    assert graph._route_after_generate({"review_enabled": True}) == "check"


def test_graph_keeps_check_repair_when_review_enabled(monkeypatch):
    monkeypatch.setattr(graph.settings, "workflow_llm_review_enabled", True)
    compiled = graph.create_xianzhi_graph(_FakeWorkflow())
    nodes = set(compiled.get_graph().nodes.keys())
    assert {"check", "repair"} <= nodes


# ---------------- 4. _generate_node 分流 ----------------

def _gen_state():
    intent = SimpleNamespace(domain="career")
    return {
        "user_prompt": "问事业",
        "intent": intent,
        "chart_context": MagicMock(),
        "worker": _FakeWorkflow(),
        "knowledge": "",
        "history": [],
        "summary": "",
    }


def test_generate_node_uses_stream_when_review_disabled(monkeypatch):
    monkeypatch.setattr(graph.settings, "workflow_llm_review_enabled", False)
    wf = MagicMock()
    wf._emit_progress = MagicMock()
    wf._build_messages.return_value = []
    wf._invoke_stream.return_value = "流式全文"

    out = graph._generate_node(wf, _gen_state())

    wf._invoke_stream.assert_called_once()
    wf._invoke.assert_not_called()
    assert out["final_answer"] == "流式全文"  # 图中无 check/repair，答案必须由 generate 自己定稿


def test_generate_node_uses_invoke_when_review_enabled(monkeypatch):
    monkeypatch.setattr(graph.settings, "workflow_llm_review_enabled", True)
    wf = MagicMock()
    wf._emit_progress = MagicMock()
    wf._build_messages.return_value = []
    wf._invoke.return_value = "待审全文"

    out = graph._generate_node(wf, _gen_state())

    wf._invoke.assert_called_once()
    wf._invoke_stream.assert_not_called()
    assert out["raw_answer"] == "待审全文"
    assert "final_answer" not in out  # 定稿留给 check/repair


# ---------------- 5. _workflow_stream 双模式 ----------------

def _make_agent():
    with patch("app.agent.xianzhi.create_chat_memory") as m:
        m.return_value = MagicMock()
        agent = Xianzhi(chat_model=MagicMock(), local_tools=[])
    agent._get_session_summary = lambda: ""
    agent._persist_history = lambda: None
    agent._history_len = 0
    return agent


def test_workflow_stream_review_mode_yields_single_full_answer(monkeypatch):
    monkeypatch.setattr("app.agent.xianzhi.settings.workflow_llm_review_enabled", True)
    agent = _make_agent()
    agent._execute_workflow = lambda *a, **k: "完整回答"

    chunks = list(agent._workflow_stream("问题"))
    assert chunks == ["完整回答"]


def test_workflow_stream_streaming_mode_yields_tokens_only(monkeypatch):
    monkeypatch.setattr("app.agent.xianzhi.settings.workflow_llm_review_enabled", False)
    agent = _make_agent()

    def _fake_execute(prompt, history, summary):
        # 模拟工作流回调 token（与 _invoke_stream 的 on_token 链同路径）
        agent._workflow.on_token("第一段，")
        agent._workflow.on_token("第二段。")
        return "第一段，第二段。"

    agent._execute_workflow = _fake_execute

    chunks = list(agent._workflow_stream("问题"))
    assert chunks == ["第一段，", "第二段。"]  # token 逐块；完整答案不再重复 yield
    assert agent._workflow.on_token is None  # 收尾必须解绑，避免串到下一轮


def test_workflow_stream_streaming_mode_error_yields_friendly_text(monkeypatch):
    monkeypatch.setattr("app.agent.xianzhi.settings.workflow_llm_review_enabled", False)
    agent = _make_agent()

    def _boom(*a, **k):
        raise ModelUnavailableErrorForTest("降级链全部模型均不可用")

    agent._execute_workflow = _boom

    chunks = list(agent._workflow_stream("问题"))
    assert "".join(chunks) == "分析过程遇到错误，请稍后重试。"
    assert agent._workflow.on_token is None


class ModelUnavailableErrorForTest(Exception):
    pass


def test_sync_streaming_emits_first_token_before_turn_finishes(monkeypatch):
    import threading

    monkeypatch.setattr("app.agent.xianzhi.settings.workflow_llm_review_enabled", False)
    agent = _make_agent()
    release = threading.Event()
    finished = threading.Event()

    def _fake_execute(prompt, history, summary):
        agent._workflow.on_token("首块")
        assert release.wait(timeout=2)
        agent._workflow.on_token("后续")
        finished.set()
        return "首块后续"

    agent._execute_workflow = _fake_execute
    stream = agent._workflow_stream("问题")
    timer = threading.Timer(1.0, release.set)
    timer.start()
    try:
        assert next(stream) == "首块"
        assert not finished.is_set()  # 首块不能等整轮完成后才出现
        release.set()
        assert list(stream) == ["后续"]
    finally:
        release.set()
        timer.cancel()


# ---------------- asyncio 路径 ----------------

async def _collect(agen):
    out = []
    async for c in agen:
        out.append(c)
    return out


def test_aworkflow_stream_streaming_mode_bridges_tokens(monkeypatch):
    import asyncio

    monkeypatch.setattr("app.agent.xianzhi.settings.workflow_llm_review_enabled", False)
    agent = _make_agent()

    def _fake_execute(prompt, history, summary):
        agent._workflow.on_token("甲")
        agent._workflow.on_token("乙丙")
        return "甲乙丙"

    agent._execute_workflow = _fake_execute

    async def _run():
        return await _collect(agent._aworkflow_stream("问题"))

    chunks = asyncio.run(_run())
    assert chunks == ["甲", "乙丙"]
    assert agent._workflow.on_token is None


def test_aworkflow_stream_review_mode_unchanged(monkeypatch):
    import asyncio

    monkeypatch.setattr("app.agent.xianzhi.settings.workflow_llm_review_enabled", True)
    agent = _make_agent()
    agent._execute_workflow = lambda *a, **k: "整段回答"

    async def _run():
        return await _collect(agent._aworkflow_stream("问题"))

    assert asyncio.run(_run()) == ["整段回答"]
