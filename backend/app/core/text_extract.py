"""从异构载荷中提取可展示文本（LLM 流式 chunk 与 WebSocket 消息共用一套归一化口径）。

背景：部分模型/传输层会把 `content` 给成 `str`、`list[dict]` 或 `dict`，
直接下发给前端会表现为"只显示标题、没有正文"。本模块把这类载荷扁平化为纯文本。

原先该逻辑在 hehun / liuyao / ziwei 三个子应用里各复制了一份（逐字节相同，共 6 份），
任一处修 bug 都不会同步到其余处，故收敛到此处作为单一事实源。

注意：`app/sub_app/tarot/` 另有一套**行为不同**的同类实现（递归拼接、不做 strip、
阈值 10/20 与 join 方式均不同），本模块不覆盖它——统一它需要产品决策与回归基线，
且 tarot 当前无对应测试，贸然合并会改变线上流式表现。
"""

from __future__ import annotations

from typing import Any

__all__ = ["normalize_chunk_text", "normalize_ws_payload_text"]


def normalize_chunk_text(raw_content: Any) -> str:
    """归一化 LLM 流式返回的 chunk 文本（兼容 None / str / list / dict / 其他对象）。"""
    if raw_content is None:
        return ""
    if isinstance(raw_content, str):
        text = raw_content.strip()
        return text if text else ""
    if isinstance(raw_content, list):
        texts = []
        for item in raw_content:
            if isinstance(item, dict) and item.get("text"):
                texts.append(item["text"])
            elif isinstance(item, str):
                texts.append(item)
        text = " ".join(texts).strip()
        return text if text else ""
    if isinstance(raw_content, dict):
        for key in ("text", "content", "delta", "result"):
            val = raw_content.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        for val in raw_content.values():
            if isinstance(val, str) and len(val) > 20 and not val.startswith("<"):
                return val.strip()
        return ""
    text = str(raw_content)
    if len(text) > 200 or "<__" in text or "object at 0x" in text:
        return ""
    return text.strip()


def normalize_ws_payload_text(data: Any) -> str:
    """归一化 WebSocket 消息中的文本字段（兼容 None / str / dict / 其他对象）。

    相比 `normalize_chunk_text`，本函数额外识别 OpenAI 风格的
    `{"choices": [{"delta": {"content": ...}}]}` 结构。
    """
    if data is None:
        return ""
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        for key in ("text", "content", "delta", "result"):
            val = data.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        if "choices" in data and isinstance(data["choices"], list):
            choice = data["choices"][0] if data["choices"] else {}
            delta = choice.get("delta", {})
            if isinstance(delta, dict) and delta.get("content"):
                return str(delta["content"]).strip()
        for val in data.values():
            if (
                isinstance(val, str)
                and len(val) > 20
                and not val.startswith("<")
                and "object at 0x" not in val
            ):
                return val.strip()
        return ""
    text = str(data)
    if len(text) > 200 or "<__" in text or "object at 0x" in text:
        return ""
    return text.strip()
