"""文本清洗工具：LLM 输出后处理。

- 移除 thinking... response 推理过程标签（Qwen3 等推理模型）
- 处理未闭合的 thinking 标签（流式中断场景）
- 检测并移除完全重复的内容（think 块泄漏兜底）
"""
from __future__ import annotations

import re

from app.core.logger import log

# 编译正则，避免每次调用重新编译
_THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>[\s\S]*$", re.IGNORECASE)


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
