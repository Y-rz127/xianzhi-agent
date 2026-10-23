"""检索内容与工具输出的提示注入防护（确定性、可单测）。

威胁模型：联网搜索摘要、抓取网页、知识库片段都可能被第三方写入“忽略之前的指令”
一类文本。模型若把它当指令执行，会出现回答劫持、越权调工具、系统提示泄露。
防护分两层：
1) 中和高风险指令行（整行替换，不做模糊改写，避免残留半句仍可被利用）；
2) 用 DATA_BEGIN/DATA_END 把内容标成“资料”，配合系统提示中的隔离规则。

只处理进入 prompt 的数据，不触碰排盘/规则引擎产生的结构化事实。
"""
from __future__ import annotations

import re

from app.core.logger import log
from app.core.observability import record_error

DATA_BEGIN = "<<<DATA_BEGIN"
DATA_END = "<<<DATA_END>>>"

# 外部内容里伪造的边界标记一律先抹掉，避免提前闭合数据块或冒充用户输入
_DATA_MARKER_RE = re.compile(r"<<<\s*/?\s*DATA_(?:BEGIN|END)[^>]*>>>", re.IGNORECASE)
_USER_BOUNDARY_RE = re.compile(r"---\s*USER\s+INPUT\s+(?:BEGIN|END)\s*---", re.IGNORECASE)
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")

# 逐行匹配的高风险指令；命中即整行中和。宁可少滤，也不误删正常命理文本。
_INJECTION_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # 英文：忽略/覆盖既有指令
        r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|all)\b.{0,30}\b(instructions?|prompts?|rules?|directives?)\b",
        r"\b(ignore|disregard|forget)\b.{0,20}\b(instructions?|prompts?|rules?)\b",
        # 英文：身份切换 / 新指令 / 提示词泄露
        r"\byou\s+are\s+now\b",
        r"\b(new|updated|system|developer)\s+(instructions?|prompt)\b",
        r"\b(reveal|print|output|show|repeat|leak|expose)\b.{0,30}\b(system\s+)?(prompt|instructions?|rules?)\b",
        r"\b(jailbreak|developer\s+mode|DAN\s+mode)\b",
        # 对话模板/角色标记
        r"<\|im_start\|>|<<SYS>>|\[/?INST\]|<\|(?:system|assistant|user)\|>",
        r"^\s*(system|assistant|developer|tool)\s*[:：]",
        r"^\s*#{2,}\s*(system|assistant|instruction)",
        # 中文：忽略/覆盖既有规则
        r"(忽略|无视|忘记|抛弃|跳过).{0,6}(之前|以上|前面|先前|所有|全部)?.{0,4}(指令|提示词|提示|规则|要求|设定)",
        # 中文：身份切换 / 提示词泄露 / 新指令 / 诱导弹工具
        r"(你|您)(现在|从现在起|接下来|必须|要)(是|扮演|作为|执行|服从)",
        r"(输出|显示|打印|告诉我|复述|泄露|透露|展示).{0,8}(系统)?(提示词|提示|指令|规则)",
        r"(新|新的|更新后的)(的)?(指令|提示词|规则|要求)",
        r"(以下|下面)(的)?(指令|提示词)",
        r"(调用|执行|使用).{0,16}(工具|函数|接口)",
        r"^\s*(系统|助手|用户|开发者)\s*[:：]",
        # 伪造本系统内部段落标题
        r"^\s*【(?:系统排盘事实|命理规则检索|用户问题|待审核回答|正确排盘事实|最近对话摘要|合婚基础数据)】",
    )
)

# 系统内确定性工具的输出可直接作为事实使用；其余（联网/抓取/MCP/知识库）按资料隔离
_TRUSTED_TOOL_PREFIXES = ("bazi_", "huangli_", "ziwei_")
_TRUSTED_TOOLS = frozenset({"lunar_to_solar", "do_terminate"})


def is_trusted_tool(tool_name: str) -> bool:
    """该工具的输出是否由本系统确定性生成（可信事实）。"""
    name = (tool_name or "").strip()
    return name in _TRUSTED_TOOLS or name.startswith(_TRUSTED_TOOL_PREFIXES)


def _source_label(source: str) -> str:
    label = re.sub(r"[\s<>\"'`]+", "_", (source or "").strip())
    return label[:40] or "unknown"


def neutralize_instructions(text: str) -> tuple[str, int]:
    """逐行中和可疑指令，返回 (清洗后文本, 命中行数)。

    先抹掉伪造的边界标记，再按行匹配；命中的整行替换为占位符，
    保留其余资料内容（引用、事实、规则）不受影响。
    """
    raw = _DATA_MARKER_RE.sub("", text or "")
    raw = _USER_BOUNDARY_RE.sub("", raw)
    lines: list[str] = []
    hits = 0
    for line in raw.splitlines():
        probe = _INVISIBLE_RE.sub("", line)
        if any(p.search(probe) for p in _INJECTION_PATTERNS):
            hits += 1
            lines.append("[已移除可疑指令]")
        else:
            lines.append(line)
    return "\n".join(lines), hits


def sanitize_untrusted(text: str, source: str = "", max_chars: int | None = None) -> str:
    """把外部内容中和后包进数据隔离标记，供模型作为资料引用。"""
    raw = text or ""
    if max_chars and len(raw) > max_chars:
        raw = raw[:max_chars] + "…"
    cleaned, hits = neutralize_instructions(raw)
    label = _source_label(source)
    if hits:
        log.warning("[prompt-safety] {} 中发现 {} 行可疑指令，已中和", label, hits)
        record_error("prompt_injection_suspected")
    if not cleaned.strip():
        cleaned = "（无可引用内容）"
    return '{} source="{}">>>\n{}\n{}'.format(DATA_BEGIN, label, cleaned, DATA_END)


def guard_tool_output(tool_name: str, content: str) -> str:
    """工具输出进入模型前的统一防线：可信工具原样返回，其余按资料隔离。"""
    if not content or is_trusted_tool(tool_name):
        return content
    return sanitize_untrusted(content, source=tool_name)
