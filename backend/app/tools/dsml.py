"""文本形式的工具调用：解析与剥离。

背景
----
DeepSeek 系模型（降级链上的 ``deepseek-v4.1-flash``）在 ``bind_tools`` 后**不走**
OpenAI 的 ``tool_calls`` 通道，而是把工具调用以**文本**形式写进 ``content``。
同一模型不同版本吐过的格式有两种（2026-10-08 实测都撞上了）：

1. **DSML 格式**::

       <｜DSML｜ calls>
       <｜DSML｜ invoke name="bazi_infer_dates">
       <｜DSML｜ parameter name="pillars" string="true">癸巳甲子丁酉甲辰</｜DSML｜ parameter>
       </｜DSML｜ invoke>
       </｜DSML｜ calls>

2. **裸 tool_call 格式**（部分版本 / 无类型标注时）::

       <tool_calls>
       <tool_call name="bazi_infer_dates">
       <parameter name="pillars">癸巳甲子丁酉甲辰</parameter>
       </tool_call>
       </tool_calls>

langchain 只认 ``message.tool_calls``，因此这类响应的 ``tool_calls`` 为空、
``finish_reason="stop"``，ReAct 的 ``think()`` 会判定「无工具调用」而直接结束，
**工具调用原文被当成最终回答发给用户**（2026-10-08 小程序现场）。

本模块把这段文本还原成标准 tool_calls，并给出「解析不出来也要剥干净」的兜底。
两道防线都在 ``app.agent.core.tool_call_agent.think`` 调用，另有
``app.agent.xianzhi._final_answer_or_error`` 收口兜底。
"""
from __future__ import annotations

import re
from typing import Any

from app.core.logger import log

# ---- 格式一：DSML ----
_DSML_CALLS_RE = re.compile(r"<｜DSML｜\s*calls?>(.*?)(?:</｜DSML｜\s*calls?>|$)", re.DOTALL)
_DSML_INVOKE_RE = re.compile(
    r'<｜DSML｜\s*invoke\s+name="([^"]+)"[^>]*>(.*?)(?:</｜DSML｜\s*invoke>|$)',
    re.DOTALL,
)
_DSML_PARAM_RE = re.compile(
    r'<｜DSML｜\s*parameter\s+name="([^"]+)"(?:\s+[a-z_]+="[^"]*")*\s*>'
    r"(.*?)(?:</｜DSML｜\s*parameter>|$)",
    re.DOTALL,
)

# ---- 格式二：裸 tool_call ----
# 闭合标签里可能混入零宽字符（U+200B），用[\s\u200b\ufeff]* 兜一下
_RAW_CALL_RE = re.compile(
    r"<tool_calls?>(.*?)(?:</\s*[\u200b\ufeff]*\s*tool_calls?>|$)",
    re.DOTALL | re.IGNORECASE,
)
_RAW_INNER_RE = re.compile(
    r"<\s*[\u200b\ufeff]*\s*tool_call\s+name\s*=\s*\"([^\"]+)\"[^>]*>(.*?)"
    r"(?:<\s*/\s*[\u200b\ufeff]*\s*tool_call\s*>|$)",
    re.DOTALL | re.IGNORECASE,
)
_RAW_PARAM_RE = re.compile(
    r"<\s*[\u200b\ufeff]*\s*parameter\s+name\s*=\s*\"([^\"]+)\"[^>]*>(.*?)"
    r"(?:<\s*/\s*[\u200b\ufeff]*\s*parameter\s*>|$)",
    re.DOTALL | re.IGNORECASE,
)

# 兜底：任何残留的协议标签（含未闭合片段）
_RESIDUE_RES = (
    re.compile(r"<｜DSML｜[\s\S]*?(?:</｜DSML｜\s*(?:calls?|invoke|parameter)>|$)"),
    re.compile(
        r"<\s*[\u200b\ufeff]*\s*/?\s*(?:tool_calls?|tool_call|parameter)\b[^>]*>"
        r"[\s\S]*?(?:<\s*/\s*[\u200b\ufeff]*\s*(?:tool_calls?|tool_call|parameter)\s*>|$)",
        re.IGNORECASE,
    ),
)

_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")

# 快速筛：只有出现这些标记才值得跑解析（正常命理回答不会命中，避免每轮都付正则代价）
_MAY_CONTAIN_RE = re.compile(r"DSML|<tool_call", re.IGNORECASE)


def _coerce(value: str) -> Any:
    """把参数字符串转成合适的 Python 类型。

    类型标注（``string="true"``）只是提示、不保证准确，这里按值本身推断：
    数字→int/float，true/false→bool，其余原样留字符串
    （八字四柱 "癸巳甲子丁酉甲辰" 必须是 str，绝不能被误转成别的东西）。
    """
    v = value.strip().strip("\u200b\ufeff")
    if v == "":
        return ""
    low = v.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT_RE.match(v):
        try:
            return int(v)
        except ValueError:
            return v
    if _FLOAT_RE.match(v):
        try:
            return float(v)
        except ValueError:
            return v
    return v


def _build(name: str, args: dict, seq: int) -> dict:
    return {
        "name": name.strip().strip("\u200b\ufeff"),
        "args": args,
        "id": "call_txt_{}_{}".format(seq, name.strip()),
        "type": "tool_call",
    }


def _parse_dsml(content: str) -> tuple[list[dict], str]:
    calls: list[dict] = []
    remaining = content
    for block in _DSML_CALLS_RE.finditer(content):
        for seq, (name, body) in enumerate(_DSML_INVOKE_RE.findall(block.group(1)), 1):
            args = {k: _coerce(v) for k, v in _DSML_PARAM_RE.findall(body)}
            calls.append(_build(name, args, seq))
        remaining = remaining.replace(block.group(0), "")
    return calls, remaining


def _parse_raw(content: str) -> tuple[list[dict], str]:
    calls: list[dict] = []
    remaining = content
    for block in _RAW_CALL_RE.finditer(content):
        for seq, (name, body) in enumerate(_RAW_INNER_RE.findall(block.group(1)), 1):
            args = {k: _coerce(v) for k, v in _RAW_PARAM_RE.findall(body)}
            calls.append(_build(name, args, seq))
        remaining = remaining.replace(block.group(0), "")
    return calls, remaining


def parse_text_tool_calls(content: str) -> tuple[list[dict], str]:
    """从模型输出里提取文本形式的工具调用。

    Returns:
        ``(tool_calls, remaining_text)`` —— 工具调用列表（无则空列表）
        与剥掉协议标记后的剩余正文（无正文则空串）。
    """
    if not content or not _MAY_CONTAIN_RE.search(content):
        return [], content or ""

    calls: list[dict] = []
    remaining = content
    for parser in (_parse_dsml, _parse_raw):
        found, remaining = parser(remaining)
        calls.extend(found)

    # 未闭合的残片（invoke/parameter 标签单独漏出）也要剥干净，别让用户看见
    for residue in _RESIDUE_RES:
        remaining = residue.sub("", remaining)
    remaining = re.sub(r"\n{3,}", "\n\n", remaining).strip()

    if calls:
        log.warning(
            "[text_tool_calls] 模型未走 tool_calls 通道，从 content 还原出 {} 个调用: {}",
            len(calls),
            [c["name"] for c in calls],
        )
    return calls, remaining


def strip_text_tool_calls(content: str) -> str:
    """只剥离协议标记，不解析（解析不出调用时的兜底防线）。

    两类正则都要跑：DSML 专用块（``_DSML_CALLS_RE``）与裸格式（``_RAW_CALL_RE``），
    再用通用 residue 收掉未闭合的残片——少跑一个都会漏（裸格式剥净了 DSML 仍残留）。
    """
    if not content or not _MAY_CONTAIN_RE.search(content):
        return content or ""
    cleaned = _DSML_CALLS_RE.sub("", content)
    cleaned = _RAW_CALL_RE.sub("", cleaned)
    for residue in _RESIDUE_RES:
        cleaned = residue.sub("", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def has_text_tool_calls(content: str) -> bool:
    """content 是否含文本形式的工具调用标记（用于决定是否走还原逻辑）。"""
    return bool(content) and bool(_MAY_CONTAIN_RE.search(content))
