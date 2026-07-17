"""文本清洗工具：LLM 输出后处理。

集中管理 LLM 响应的清洗逻辑，避免多处重复：
- 移除 <think>...</think> 推理过程标签（Qwen3 等推理模型）
- 处理未闭合的 <think> 标签（流式中断场景）
- 检测并移除完全重复的内容（think 块泄漏兜底）
"""
from __future__ import annotations

import re

from app.logger import log


# 编译正则，避免每次调用重新编译
_THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>[\s\S]*$", re.IGNORECASE)


def clean_think_tags(content: str) -> str:
    """移除 LLM 输出中的 <think> 推理过程标签。

    处理两种情况：
    1. 完整的 <think>...</think> 块（正常推理输出）
    2. 未闭合的 <think> 标签（流式中断、超时等异常场景）

    Args:
        content: LLM 原始输出

    Returns:
        清洗后的内容（已 strip）
    """
    if not content:
        return content
    content = _THINK_BLOCK_RE.sub("", content)
    content = _THINK_OPEN_RE.sub("", content)
    return content.strip()


def dedupe_content(content: str) -> str:
    """检测并移除完全重复的内容（推理模型 think 块泄漏的兜底）。

    某些推理模型偶尔会把 think 块内容重复输出到正文。
    本函数检测内容是否前后完全重复，若是则只保留前半部分。

    Args:
        content: 待检测内容

    Returns:
        去重后的内容
    """
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


def clean_llm_output(content: str) -> str:
    """LLM 输出完整清洗流水线：移除 think 标签 + 去重。

    Args:
        content: LLM 原始输出

    Returns:
        清洗后的内容
    """
    if not content:
        return content
    content = clean_think_tags(content)
    content = dedupe_content(content)
    return content
