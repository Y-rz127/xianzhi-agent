"""子应用共享骨架：LLM 流式解读的统一循环。

hehun / liuyao / ziwei 三个 *_app.py 的流式解读都是同构的
「构造 msgs → llm_tag 包裹的 astream → 归一化 chunk → 空片段/异常回退」，
故下沉本模块去重；各子应用只保留自身业务细节（prompt 构造、回退文本）。

tarot 因是类封装且带结构化牌义 fallback，模式不同，不归入本骨架。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from langchain_core.messages import BaseMessage

from app.agent.context import get_sub_app_model
from app.core.llm_throttle import llm_tag
from app.core.logger import log
from app.core.text_extract import normalize_chunk_text


async def llm_interpret_stream(
    msgs: list[BaseMessage],
    *,
    tag: str,
    name: str,
    empty_text: str,
    error_text: str = "\n\n[AI 解读暂不可用：{error}]\n\n",
) -> AsyncGenerator[str, None]:
    """LLM 流式解读公共骨架：空片段/异常时回退为给定文本。

    empty_text：空片段回退（如规则结果或"暂不可用"）；
    error_text：异常回退，可选含 {error} 占位符替换为异常类型名。
    """
    had_chunk = False
    try:
        with llm_tag(tag):
            async for chunk in get_sub_app_model().astream(msgs):
                text = normalize_chunk_text(getattr(chunk, "content", None))
                if text:
                    had_chunk = True
                    yield text
        if not had_chunk:
            log.warning("{} LLM 返回空片段", name)
            yield empty_text
    except Exception as exc:
        log.exception("{} LLM 解读失败", name)
        yield error_text.replace("{error}", type(exc).__name__)
