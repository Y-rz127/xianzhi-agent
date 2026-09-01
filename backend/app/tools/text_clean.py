"""文本清洗工具：LLM 输出后处理。

- 移除 thinking... response 推理过程标签（Qwen3 等推理模型）
- 处理未闭合的 thinking 标签（流式中断场景）
- 检测并移除完全重复的内容（think 块泄漏兜底）
- 剥离模型回显的用户输入边界标记（`--- USER INPUT BEGIN/END ---`）
"""
from __future__ import annotations

import re

from app.core.logger import log

# 编译正则，避免每次调用重新编译
_THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>[\s\S]*$", re.IGNORECASE)

# 防御：剥离模型回显的用户输入边界标记（防止 LLM 把 "--- USER INPUT BEGIN/END ---" 原样当作回答输出）
_USER_INPUT_BOUNDARY_RE = re.compile(
    r"---\s*USER\s+INPUT\s+BEGIN\s*---[\s\S]*?---\s*USER\s+INPUT\s+END\s*---"
)


def clean_think_tags(content: str) -> str:
    """移除 LLM 输出中的 thinking 推理过程标签（含未闭合的流式中断场景）。"""
    if not content:
        return content
    content = _THINK_BLOCK_RE.sub("", content)
    content = _THINK_OPEN_RE.sub("", content)
    return content.strip()


def dedupe_content(content: str) -> str:
    """检测内容前后完全重复（推理模型 think 块泄漏），只保留前半部分。"""
    content = content.strip()
    if len(content) < 100:
        return content
    mid = len(content) // 2
    first_half = content[:mid].strip()
    second_half = content[mid:].strip()
    if first_half == second_half and len(first_half) > 50:
        log.warning("检测到 LLM 输出内容重复，已去重（长度 {}）", len(first_half))
        return first_half
    return content


def strip_user_input_boundary(content: str) -> str:
    """移除 LLM 回答里回显的 ```--- USER INPUT BEGIN/END ---``` 边界块及其包裹的复述内容。

    用户输入被 `_wrap_user_input` 包上边界标记以防指令注入；若模型把整段标记连同
    用户原话一并当回答输出，这里一次性剥掉，保证用户永远看不到内部标记。
    所有生成路径（Workflow / 闲聊短路）都应调用，统一防护、避免各自为政漏剥。
    """
    if not content:
        return content
    cleaned = _USER_INPUT_BOUNDARY_RE.sub("", content)
    # 清理剥离后可能残留的多余空行
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned
