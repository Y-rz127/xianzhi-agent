"""生成被输出上限截断时的自动续写回归测试（2026-09-15 引入）。

背景：`finish_reason=length` 表示模型撞到单次输出上限被硬停，正文是半截的。
审核侧被截断还能靠"抢救结论"兜住，**生成侧被截断就是用户收到半句话**，更严重。
现在 `workflow_messages.invoke()` 遇到 length 会自动续写一次并拼接：

① 续写正常 → 拼接（并去掉模型重写的重叠句子）；
② 续写仍被截断 → 按已有内容定稿 + 记 `workflow_output_truncated_twice`；
③ 续写调用抛错 → 按已有内容定稿 + 记 `workflow_continue_failed`；
④ finish_reason=stop 时不额外调用（不留隐形成本）。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.agent.workflow.workflow_messages import (
    _TRUNCATED_CONTINUE_HINT,
    _merge_continuation,
    invoke,
)


class _Resp:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self.content = content
        self.response_metadata = {"finish_reason": finish_reason}


class _ScriptedModel:
    """按脚本依次返回响应；记录每次收到的消息，便于断言续写提示。"""

    def __init__(self, script: list):
        self._script = list(script)
        self.calls: list[list] = []

    def bind(self, **kwargs):
        return self

    def invoke(self, messages):
        self.calls.append(list(messages))
        item = self._script.pop(0) if self._script else _Resp("", "stop")
        if isinstance(item, Exception):
            raise item
        return item


def _err_count(key: str) -> int:
    from app.core.observability import get_metrics

    return int(dict(get_metrics()["internal_errors"]).get(key, 0))


MSGS = [HumanMessage(content="用户问题")]


# ---------------- 续写拼接 ----------------
def test_truncated_answer_is_continued_and_merged():
    model = _ScriptedModel([_Resp("命主乙木生于酉月，金旺", "length"), _Resp("宜用水泄金、火暖局。", "stop")])

    out = invoke(model, MSGS)

    assert out == "命主乙木生于酉月，金旺宜用水泄金、火暖局。"
    assert len(model.calls) == 2, "被截断应触发一次续写"
    # 续写请求必须带上"接着写"的指令与半截正文，否则模型会从头重写
    followup = model.calls[1]
    assert followup[-1].content == _TRUNCATED_CONTINUE_HINT
    assert "金旺" in followup[-2].content


def test_merges_without_duplicating_rewritten_sentence():
    """模型常把最后一句重写一遍：要按最大重叠去重，不能出现重复句。"""
    head = "金旺为忌，宜以水泄金"
    tail = "宜以水泄金，兼用火暖局。"
    assert _merge_continuation(head, tail) == "金旺为忌，宜以水泄金，兼用火暖局。"


def test_merge_falls_back_to_plain_concat():
    assert _merge_continuation("前半句", "完全不同的后半句") == "前半句完全不同的后半句"
    assert _merge_continuation("", "只有尾巴") == "只有尾巴"
    assert _merge_continuation("只有头", "") == "只有头"


# ---------------- 异常与二次截断 ----------------
def test_second_truncation_keeps_what_we_have_and_records_metric():
    before = _err_count("workflow_output_truncated_twice")
    model = _ScriptedModel([_Resp("第一段", "length"), _Resp("第二段", "length")])

    out = invoke(model, MSGS)

    assert out == "第一段第二段"
    assert _err_count("workflow_output_truncated_twice") == before + 1


def test_continue_failure_keeps_partial_answer():
    before = _err_count("workflow_continue_failed")
    model = _ScriptedModel([_Resp("半截回答", "length"), RuntimeError("provider down")])

    out = invoke(model, MSGS)

    assert out == "半截回答"
    assert _err_count("workflow_continue_failed") == before + 1


def test_truncated_metric_recorded():
    before = _err_count("workflow_output_truncated")
    invoke(_ScriptedModel([_Resp("半截", "length"), _Resp("补齐", "stop")]), MSGS)
    assert _err_count("workflow_output_truncated") == before + 1


# ---------------- 正常路径不留隐形成本 ----------------
def test_normal_answer_does_not_call_twice():
    model = _ScriptedModel([_Resp("完整回答", "stop")])

    out = invoke(model, MSGS)

    assert out == "完整回答"
    assert len(model.calls) == 1


def test_empty_truncated_answer_uses_fallback_text_without_continuation():
    """空产出仍走既有兜底文案，不为空内容发起续写。"""
    before = _err_count("workflow_output_truncated")
    model = _ScriptedModel([_Resp("", "length")])

    out = invoke(model, MSGS)

    assert "没有生成有效解读" in out
    assert len(model.calls) == 1
    assert _err_count("workflow_output_truncated") == before + 1
