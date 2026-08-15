"""分节命理报告生成器。

根据出生时间与性别，调用八字工具获取盘面信息，再由 LLM 生成结构化 Markdown 报告。
"""
from __future__ import annotations

import hashlib
import threading
import time

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.prompts import REPORT_PROMPT_TEMPLATE, REPORT_SYSTEM_PROMPT
from app.tools.bazi import bazi_analysis, bazi_chart, bazi_dayun

SECTIONS = {
    "overview": "命盘总览",
    "career": "事业分析",
    "wealth": "财运分析",
    "love": "感情婚姻",
    "health": "健康提示",
    "dayun": "大运流年",
}

DEFAULT_SECTIONS = list(SECTIONS.keys())

# 报告缓存：避免"展示"和"导出PDF"两次调用产生不同内容（LLM temperature≠0 时不稳定）
# 以 (birth_time, gender, sections) 为 key，TTL 1 小时
_REPORT_CACHE_TTL = 3600
_REPORT_CACHE_MAX = 50
_report_cache: dict[str, tuple[float, str]] = {}
_report_cache_lock = threading.Lock()

_SYSTEM_PROMPT = REPORT_SYSTEM_PROMPT

_REPORT_PROMPT = REPORT_PROMPT_TEMPLATE


def _report_cache_key(birth_time: str, gender: str, sections: list[str]) -> str:
    raw = f"{birth_time}|{gender}|{','.join(sorted(sections))}"
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached_report(birth_time: str, gender: str, sections: list[str]) -> str | None:
    key = _report_cache_key(birth_time, gender, sections)
    with _report_cache_lock:
        entry = _report_cache.get(key)
        if not entry:
            return None
        ts, content = entry
        if time.time() - ts > _REPORT_CACHE_TTL:
            _report_cache.pop(key, None)
            return None
        return content


def _set_cached_report(birth_time: str, gender: str, sections: list[str], content: str) -> None:
    key = _report_cache_key(birth_time, gender, sections)
    with _report_cache_lock:
        # LRU 淘汰：超过上限时移除最旧的
        while len(_report_cache) >= _REPORT_CACHE_MAX:
            oldest_key = min(_report_cache, key=lambda k: _report_cache[k][0])
            _report_cache.pop(oldest_key, None)
        _report_cache[key] = (time.time(), content)


def generate_full_report(
    chat_model: BaseChatModel,
    birth_time: str,
    gender: str,
    sections: list[str] | None = None,
) -> str:
    """生成完整分节命理报告（Markdown）。

    Args:
        chat_model: 用于生成报告的大模型
        birth_time: 出生时间，格式 YYYY-MM-DD HH:MM
        gender: 性别，男 / 女
        sections: 要生成的章节 key 列表，默认全部

    Returns:
        Markdown 格式的命理报告
    """
    sections = sections or DEFAULT_SECTIONS
    selected = [s for s in sections if s in SECTIONS]
    if not selected:
        selected = DEFAULT_SECTIONS

    # 命中缓存直接返回（保证"展示"和"导出PDF"内容一致）
    cached = _get_cached_report(birth_time, gender, selected)
    if cached is not None:
        return cached

    chart_text = bazi_chart.invoke({"birth_time": birth_time, "gender": gender})
    analysis_text = bazi_analysis.invoke({"birth_time": birth_time, "gender": gender, "question": "整体命盘"})
    dayun_text = bazi_dayun.invoke({"birth_time": birth_time, "gender": gender, "count": 8})

    sections_text = "\n".join([f"- {SECTIONS[s]}" for s in selected])

    prompt = _REPORT_PROMPT.format(
        birth_time=birth_time,
        gender=gender,
        chart_text=chart_text,
        analysis_text=analysis_text,
        dayun_text=dayun_text,
        sections_text=sections_text,
    )

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    response = chat_model.invoke(messages)
    content = response.content or ""

    # 写入缓存
    _set_cached_report(birth_time, gender, selected, content)
    return content
