"""文本形式工具调用的解析、剥离与参数名对齐。

事故锚点：2026-10-08 小程序现场 —— 用户问「你综合分析下这个八字：癸巳甲子丁酉甲辰」，
回复里直接吐出 `<｜DSML｜ calls>…` / `<tool_calls>…` 协议标记。根因是降级链首位
deepseek-v4.1-flash bind_tools 后不走 tool_calls 通道，把调用写进 content，
ReAct 判「无工具」即结束，把协议原文当最终回答发给用户。
"""
import sys

sys.path.insert(0, r"c:\MyProjects\xianzhi-agent")

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from app.agent.core.tool_call_agent import ToolCallAgent
from app.tools.dsml import (
    has_text_tool_calls,
    parse_text_tool_calls,
    strip_text_tool_calls,
)

# 现场格式一：DSML（两个并行调用）
SCENE_DSML = """<｜DSML｜ calls>
<｜DSML｜ invoke name="bazi_infer_dates">
<｜DSML｜ parameter name="pillars" string="true">癸巳 甲子 丁酉 甲辰</｜DSML｜ parameter>
<｜DSML｜ parameter name="gender" string="true">男</｜DSML｜ parameter>
</｜DSML｜ invoke>
<｜DSML｜ invoke name="search_knowledge">
<｜DSML｜ parameter name="query" string="true">丁火生于子月 调候用神 格局取用</｜DSML｜ parameter>
</｜DSML｜ invoke>
</｜DSML｜ calls>"""

# 现场格式二：裸 tool_call（含零宽字符，且参数名漂移 four_pillars）
SCENE_RAW = """<tool_calls>
<tool_call name="bazi_infer_dates">
<parameter name="four_pillars">癸巳 甲子 丁酉 甲辰</parameter>
<parameter name="gender">男</parameter>
</tool_call>
</tool_calls>"""


def test_parse_dsml_scene():
    """现场格式一：两个调用都要还原出来。"""
    calls, remaining = parse_text_tool_calls(SCENE_DSML)
    assert len(calls) == 2, f"应还原出 2 个调用，实际 {len(calls)}"
    assert calls[0]["name"] == "bazi_infer_dates"
    assert calls[0]["args"]["pillars"] == "癸巳 甲子 丁酉 甲辰"
    assert calls[0]["args"]["gender"] == "男"
    assert calls[1]["name"] == "search_knowledge"
    assert calls[1]["args"]["query"] == "丁火生于子月 调候用神 格局取用"
    assert remaining == "", f"剩余正文应为空，实际 {remaining!r}"
    for c in calls:
        assert c["type"] == "tool_call" and c["id"]


def test_parse_raw_scene_with_zerowidth():
    """现场格式二：裸格式 + 零宽字符 + 参数名漂移，都要能还原。"""
    calls, remaining = parse_text_tool_calls(SCENE_RAW)
    assert len(calls) == 1, f"应还原出 1 个调用，实际 {len(calls)}"
    assert calls[0]["name"] == "bazi_infer_dates"
    assert calls[0]["args"]["gender"] == "男"
    assert calls[0]["args"]["four_pillars"] == "癸巳 甲子 丁酉 甲辰"
    assert remaining == ""
    assert "tool_call" not in remaining


def test_no_marker_passthrough():
    """无协议标记时原样返回，不得误伤正常文本。"""
    calls, remaining = parse_text_tool_calls("你日主丁火生于子月，调候用神为甲木。")
    assert calls == []
    assert remaining == "你日主丁火生于子月，调候用神为甲木。"
    assert has_text_tool_calls("正常回答") is False


def test_text_around_markers_preserved():
    """协议标记前后夹带正文时，正文必须保留（不能整段吞掉）。"""
    mixed = "我先反推日期。\n" + SCENE_DSML + "\n稍等我排盘。"
    calls, remaining = parse_text_tool_calls(mixed)
    assert len(calls) == 2
    assert "我先反推日期。" in remaining
    assert "稍等我排盘。" in remaining
    assert "DSML" not in remaining


def test_truncated_block_still_parsed():
    """流式截断（缺尾部闭合标签）也要能还原。"""
    truncated = (
        '<｜DSML｜ calls>\n<｜DSML｜ invoke name="bazi_infer_dates">\n'
        '<｜DSML｜ parameter name="pillars" string="true">癸巳甲子丁酉甲辰</｜DSML｜ parameter>'
    )
    calls, remaining = parse_text_tool_calls(truncated)
    assert len(calls) == 1
    assert calls[0]["args"]["pillars"] == "癸巳甲子丁酉甲辰"
    assert "DSML" not in remaining


def test_type_coercion():
    """类型标注属性不影响取值；数字转 int，四柱必须留字符串。"""
    content = (
        '<｜DSML｜ calls>\n<｜DSML｜ invoke name="t">\n'
        '<｜DSML｜ parameter name="n" number="true">3</｜DSML｜ parameter>\n'
        '<｜DSML｜ parameter name="s" string="true">甲申</｜DSML｜ parameter>\n'
        '<｜DSML｜ parameter name="b" boolean="true">true</｜DSML｜ parameter>\n'
        "</｜DSML｜ invoke>\n</｜DSML｜ calls>"
    )
    calls, _ = parse_text_tool_calls(content)
    assert calls[0]["args"] == {"n": 3, "s": "甲申", "b": True}


def test_strip_fallback():
    """兜底：两种格式都要剥干净。"""
    assert "DSML" not in strip_text_tool_calls(SCENE_DSML)
    assert "tool_call" not in strip_text_tool_calls(SCENE_RAW)
    assert strip_text_tool_calls("正常回答") == "正常回答"
    assert strip_text_tool_calls("") == ""


def _make_agent(tools=None) -> ToolCallAgent:
    """构造一个只用于参数对齐/think 测试的 Agent（chat_model 只需能 bind_tools）。"""

    class _Noop:
        def bind_tools(self, tools, **kw):
            return self

    return ToolCallAgent(name="T", chat_model=_Noop(), tools=tools or [])


def test_align_args_four_pillars_to_pillars():
    """参数名漂移要对齐：four_pillars → pillars，否则工具报缺参。"""

    @tool
    def bazi_infer_dates(pillars: str, gender: str, top_n: int = 3) -> str:
        """反推出生日期。"""
        return "{}|{}".format(pillars, gender)

    agent = _make_agent([bazi_infer_dates])
    aligned = agent._align_args(bazi_infer_dates, {"four_pillars": "癸巳甲子丁酉甲辰", "gender": "男"})
    assert aligned == {"pillars": "癸巳甲子丁酉甲辰", "gender": "男"}


def test_align_args_keeps_valid_names():
    """参数名已正确时原样返回，不做任何改写。"""

    @tool
    def t(a: str) -> str:
        """测试。"""
        return a

    agent = _make_agent([t])
    assert agent._align_args(t, {"a": "x"}) == {"a": "x"}
    # 部分命中也算对齐成功，未命中的键原样保留（交由工具自己报错，信息更明确）
    assert agent._align_args(t, {"a": "x", "zzz": 1}) == {"a": "x", "zzz": 1}


def test_think_restores_text_calls():
    """端到端（Agent.think）：文本调用必须变成 tool_calls 并继续 act，而不是收尾。"""

    class _Model:
        def __init__(self, content):
            self._c = content

        def bind_tools(self, tools, **kw):
            return self

        def invoke(self, messages):
            return AIMessage(content=self._c)

    for scene, expect_n in ((SCENE_DSML, 2), (SCENE_RAW, 1)):
        agent = _make_agent()
        agent._llm_with_tools = _Model(scene)
        assert agent.think() is True, f"应判定为「有工具调用」：{scene[:40]}"
        last = agent.message_list[-1]
        assert len(last.tool_calls) == expect_n
        assert last.tool_calls[0]["name"] == "bazi_infer_dates"
        assert agent.final_answer == "", f"final_answer 不应含协议标记，实际 {agent.final_answer!r}"
        assert "DSML" not in last.content and "tool_call" not in last.content


def test_think_real_tool_calls_unaffected():
    """正常 tool_calls 通道的模型行为不得被改动影响。"""
    real = AIMessage(
        content="我先反推一下。",
        tool_calls=[{"name": "bazi_infer_dates", "args": {"pillars": "甲申", "gender": "女"}, "id": "c1"}],
    )

    class _Model:
        def bind_tools(self, tools, **kw):
            return self

        def invoke(self, messages):
            return real

    agent = _make_agent()
    agent._llm_with_tools = _Model()
    assert agent.think() is True
    assert len(agent.message_list[-1].tool_calls) == 1
    assert agent.final_answer == "我先反推一下。"


if __name__ == "__main__":
    for fn in (
        test_parse_dsml_scene,
        test_parse_raw_scene_with_zerowidth,
        test_no_marker_passthrough,
        test_text_around_markers_preserved,
        test_truncated_block_still_parsed,
        test_type_coercion,
        test_strip_fallback,
        test_align_args_four_pillars_to_pillars,
        test_align_args_keeps_valid_names,
        test_think_restores_text_calls,
        test_think_real_tool_calls_unaffected,
    ):
        fn()
        print(f"  ok  {fn.__name__}")
    print("\n全部通过")
