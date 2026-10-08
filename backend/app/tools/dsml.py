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

import json
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


# ---- 格式三：JSON 载荷 ----
# <tool_call>{"name": "x", "arguments": {...}}</tool_call>（也可能是 [{...},{...}] 数组）
# 实测于 2026-10-08 12:xx：模型把 OpenAI 风格的 function-call JSON 塞进 tool_call 标签，
# 且四柱被拆成数组 ["己丑","癸酉","甲子","壬申"]（需要拼回字符串）。
_JSON_BLOCK_RE = re.compile(
    r"<\s*[\u200b\ufeff]*\s*tool_calls?\s*>(.*?)<\s*/\s*[\u200b\ufeff]*\s*tool_calls?\s*>",
    re.DOTALL | re.IGNORECASE,
)
# JSON 里 name 与参数容器常见的几种键名（OpenAI 风格 arguments 为主）
_JSON_NAME_KEYS = ("name", "tool", "tool_name", "function")
_JSON_ARG_KEYS = ("arguments", "args", "parameters", "params", "input")


def _extract_json_spans(body: str):
    """按大括号/中括号平衡切出 body 里可解析的 JSON 片段（容忍前后夹带的杂字）。"""
    n = len(body)
    i = 0
    while i < n:
        if body[i] not in "{[":
            i += 1
            continue
        open_ch = body[i]
        close_ch = "}" if open_ch == "{" else "]"
        depth = 0
        in_str = False
        esc = False
        for j in range(i, n):
            ch = body[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    yield body[i : j + 1]
                    i = j + 1
                    break
        else:
            # 内层循环自然结束（无 break）⇒ 括号不平衡（多为流式截断），放弃后续扫描
            return


def _normalize_json_value(value: Any) -> Any:
    """JSON 参数值归一：字符串数组拼成空格分隔的字符串。

    模型常把四柱拆成 ``["己丑","癸酉","甲子","壬申"]``，而工具签名要的是字符串；
    下游（``_parse_pillars`` / ``_PILLARS_RE``）本身就容忍空格，拼上即可对上。
    **只处理「全字符串」的数组**，其余类型原样返回（让 schema 校验去报错）。
    """
    if isinstance(value, list) and value and all(isinstance(x, str) for x in value):
        return " ".join(x.strip() for x in value)
    return value


def _call_from_json_obj(obj: Any) -> dict | None:
    """从解析出的 JSON 对象里取 (name, args)；不符合工具调用形状时返回 None。"""
    if not isinstance(obj, dict):
        return None
    name = ""
    for key in _JSON_NAME_KEYS:
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            name = v.strip()
            break
    if not name:
        return None
    raw_args: Any = {}
    for key in _JSON_ARG_KEYS:
        if key in obj:
            raw_args = obj[key]
            break
    if isinstance(raw_args, str):
        # 双编码的字符串参数体：尽力再解一层
        try:
            raw_args = json.loads(raw_args)
        except Exception:
            raw_args = {}
    if not isinstance(raw_args, dict):
        raw_args = {}
    args = {k: _normalize_json_value(v) for k, v in raw_args.items()}
    return {"name": name, "args": args}


def _parse_json_payload(content: str) -> tuple[list[dict], str]:
    """JSON 载荷式：``<tool_call>{"name": "x", "arguments": {...}}</tool_call>``。

    注意：属性式（``name="x"``）的块必须**让给 _parse_raw**——若在这里被当成
    "没提取到就跳过"，后面的 _parse_raw 仍能处理；但若这里误提取（参数值里恰好
    有 name 键的 JSON），整块会被移除、真调用丢失。故先排除属性式的块。
    """
    calls: list[dict] = []
    remaining = content
    for block in _JSON_BLOCK_RE.finditer(content):
        body = block.group(1)
        if _RAW_INNER_RE.search(body):
            continue  # 属性式，交给 _parse_raw
        found_here = []
        for span in _extract_json_spans(body):
            try:
                obj = json.loads(span)
            except Exception:
                continue
            candidates = obj if isinstance(obj, list) else [obj]
            for item in candidates:
                call = _call_from_json_obj(item)
                if call:
                    found_here.append(call)
        if found_here:
            calls.extend(found_here)
            # 只在真的提取到调用时才移除（否则留给残片清理判断）
            remaining = remaining.replace(block.group(0), "")
    return calls, remaining


def _parse_raw(content: str) -> tuple[list[dict], str]:
    """属性式：``<tool_call name="x"><parameter name="p">v</parameter></tool_call>``。

    直接扫描 ``<tool_call name="...">`` 块，**不要求外面套 ``<tool_calls>`` 壳**
    （实测模型时套时不套）。只移除真正提取到调用的块——旧版依赖外层壳且无条件移除，
    会把「块内没有 name 属性」的 JSON 载荷块提前吃光，后面的 JSON 解析器再也看不到原文。
    外层壳残留由 ``_RESIDUE_RES`` 统一清理。
    """
    calls: list[dict] = []
    remaining = content
    for seq, m in enumerate(_RAW_INNER_RE.finditer(content), 1):
        name, body = m.group(1), m.group(2)
        args = {k: _coerce(v) for k, v in _RAW_PARAM_RE.findall(body)}
        calls.append(_build(name, args, seq))
        remaining = remaining.replace(m.group(0), "")
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
    # 三种格式依次尝试；各自只移除自己成功提取的块，互不干扰
    for parser in (_parse_dsml, _parse_raw, _parse_json_payload):
        found, remaining = parser(remaining)
        calls.extend(found)

    # id 全局重排：各解析器内部从 1 计数，混用时可能撞车（ToolMessage 靠 id 关联）
    for seq, call in enumerate(calls, 1):
        call["id"] = "call_txt_{}_{}".format(seq, call["name"])

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
