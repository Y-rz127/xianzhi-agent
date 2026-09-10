"""八字合婚应用：规则排盘基础数据 + LLM 综合解读（无状态，模块函数）。

从 app.api.tools 抽出：合婚规则计算复用 bazi_hehun 工具，LLM 解读独立成服务，
路由层只做参数校验与并发调度。
"""

from __future__ import annotations

from typing import Any, Generator

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.prompts import HEHUN_SYSTEM_PROMPT
from app.api.context import get_app_context
from app.core.llm_throttle import llm_tag
from app.core.logger import log
from app.tools.text_clean import clean_think_tags


def rule_basis(
    birth_time_a: str,
    gender_a: str,
    birth_time_b: str,
    gender_b: str,
    sect: int = 2,
    longitude_a: float | None = None,
    longitude_b: float | None = None,
) -> str:
    """调规则合婚工具（bazi_hehun）生成双盘基础数据；参数非法时以"合婚失败"开头。"""
    from app.tools.bazi import bazi_hehun

    return bazi_hehun.invoke(
        {
            "birth_time_a": birth_time_a,
            "gender_a": gender_a,
            "birth_time_b": birth_time_b,
            "gender_b": gender_b,
            "sect": sect,
            "longitude_a": longitude_a,
            "longitude_b": longitude_b,
        }
    )


def analyze(
    birth_time_a: str,
    gender_a: str,
    birth_time_b: str,
    gender_b: str,
    sect: int = 2,
    longitude_a: float | None = None,
    longitude_b: float | None = None,
    chat_model=None,
) -> str:
    """合婚分析：先拿规则基础数据，再由 LLM 做综合解读。

    chat_model 为 None（如未初始化）或解读失败时回退规则结果。
    """
    base_result = rule_basis(
        birth_time_a,
        gender_a,
        birth_time_b,
        gender_b,
        sect=sect,
        longitude_a=longitude_a,
        longitude_b=longitude_b,
    )
    if not base_result or base_result.startswith("合婚失败") or chat_model is None:
        return base_result

    messages = [
        SystemMessage(content=HEHUN_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "以下是系统根据双方出生时间自动排盘生成的合婚基础数据，"
                "请基于这些事实进行综合解读，给出缘分分析和合婚建议：\n\n"
                f"{base_result}"
            )
        ),
    ]
    try:
        with llm_tag("hehun"):
            resp = chat_model.invoke(messages)
        content = clean_think_tags((getattr(resp, "content", "") or "").strip())
        return content or base_result
    except Exception as e:
        log.warning("合婚 LLM 解读失败，返回规则结果: {}", e)
        return base_result


def _normalize_chunk_text(raw_content: Any) -> str:
    """归一化 LLM 流式返回的 chunk 文本（兼容多种格式）。"""
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


async def analyze_stream(
    birth_time_a: str,
    gender_a: str,
    birth_time_b: str,
    gender_b: str,
    sect: int = 2,
    longitude_a: float | None = None,
    longitude_b: float | None = None,
) -> Generator[str, None, None]:
    """流式合婚分析：先拿规则基础数据，再由 LLM 流式返回综合解读。"""
    base_result = rule_basis(
        birth_time_a,
        gender_a,
        birth_time_b,
        gender_b,
        sect=sect,
        longitude_a=longitude_a,
        longitude_b=longitude_b,
    )
    if not base_result or base_result.startswith("合婚失败"):
        yield base_result
        return

    messages = [
        SystemMessage(content=HEHUN_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "以下是系统根据双方出生时间自动排盘生成的合婚基础数据，"
                "请基于这些事实进行综合解读，给出缘分分析和合婚建议：\n\n"
                f"{base_result}"
            )
        ),
    ]
    try:
        has_any_chunk = False
        with llm_tag("hehun"):
            async for chunk in get_app_context().chat_model.astream(messages):
                text = _normalize_chunk_text(getattr(chunk, "content", None))
                if text:
                    has_any_chunk = True
                    yield clean_think_tags(text)
        if not has_any_chunk:
            log.warning("合婚 LLM 返回空片段")
            yield base_result
    except Exception as e:
        log.exception("合婚 LLM 流式解读失败，返回规则结果")
        yield base_result
