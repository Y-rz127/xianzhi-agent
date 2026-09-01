"""工作流支撑工具：容错 JSON 解析、命理信号正则、意图分类、命盘上下文构建。

R9 拆分自 xianzhi_workflow.py。"""

from __future__ import annotations

import datetime as _dt
import json
import re
from typing import Any

from app.agent.workflow.workflow_models import (
    DOMAIN_LABELS,
    QuestionIntent,
    WorkflowChartContext,
)
from app.domain.bazi_engine import build_bazi_chart, format_fact_context
from app.rag.retrieval import DOMAIN_KEYWORDS
from app.tools.text_clean import dedupe_content as _dedupe_content_impl


def _parse_json(text: str) -> Any:
    """容错 JSON 解析：处理 LLM 输出的各种格式问题。"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试提取第一个 {...} 块
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _dedupe_content(content: str) -> str:
    """检测并移除完全重复的内容（推理模型 think 块泄漏的兜底）。
    委托给 app.tools.text_clean.dedupe_content 统一实现。
    """
    return _dedupe_content_impl(content)


GANZHI_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")


YEAR_GANZHI_RE = re.compile(
    r"(?P<year>\d{4})年[^。；;，,、\n]{0,6}(?P<ganzhi>[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])"
)


_ALL_BAZI_SIGNALS = (
    "八字",
    "命理",
    "算命",
    "排盘",
    "命盘",
    "运势",
    "大运",
    "流年",
    "甲",
    "乙",
    "丙",
    "丁",
    "戊",
    "己",
    "庚",
    "辛",
    "壬",
    "癸",
    "子",
    "丑",
    "寅",
    "卯",
    "辰",
    "巳",
    "午",
    "未",
    "申",
    "酉",
    "戌",
    "亥",
    "五行",
    "十神",
    "用神",
    "忌神",
    "格局",
    "神煞",
    "财星",
    "官星",
    "印星",
    "食伤",
    "事业",
    "财运",
    "感情",
    "婚姻",
    "健康",
    "考试",
    "六亲",
    "子女",
    "性格",
    "合婚",
    "起名",
    "择日",
    "方位",
)


def _looks_off_topic(text: str) -> bool:
    """前置判断：用户输入是否大概率与命理无关。

    条件（同时满足）：
    1. 文本长度 > 100 字（长文本）
    2. 不含任何命理信号词（_ALL_BAZI_SIGNALS）

    命中则跳过 LLM 拆解，直接走闲聊兜底，节省 token。
    """
    if len(text) <= 100:
        return False
    return not any(sig in text for sig in _ALL_BAZI_SIGNALS)


_OTHER_BIRTH_RE1 = re.compile(
    r"(?P<gender>男|女)(?:(?!男|女)[^\d])*?(?P<year>\d{4})[-年/](?P<month>\d{1,2})[-月/](?P<day>\d{1,2})"
    r"(?:[日\s]*(?P<hour>\d{1,2})[:：]?(?P<minute>\d{1,2})?)?"
)


_OTHER_BIRTH_RE2 = re.compile(
    r"(?P<year>\d{4})[-年/](?P<month>\d{1,2})[-月/](?P<day>\d{1,2})"
    r"(?:[日\s]*(?P<hour>\d{1,2})[:：]?(?P<minute>\d{1,2})?)?[^\d]*?(?P<gender>男|女)"
)


def classify_question(text: str, today: _dt.date | None = None) -> QuestionIntent:
    """基于关键词/年份/闲聊信号的轻量意图分类（LLM 拆解的兜底）。

    Args:
        text: 用户问题
        today: 基准日期（默认今天，用于"今年/明年"年份推算）
    Returns:
        含 domain/label/target_years 等的 QuestionIntent
    """
    today = today or _dt.date.today()
    years = sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", text)})
    if "今年" in text:
        years.append(today.year)
    if "明年" in text:
        years.append(today.year + 1)
    years = sorted(set(years))

    best_domain = "general"
    best_score = 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_domain = domain
            best_score = score

    # 闲聊场景优先级提升：含强闲聊信号词时，直接判定为 chitchat，避免被 liunian 的"最近"等词抢走
    CHITCHAT_STRONG = (
        "哈哈",
        "你好",
        "在吗",
        "谢谢",
        "辛苦",
        "早上好",
        "晚上好",
        "晚安",
        "吃饭了吗",
        "在干嘛",
        "生日快乐",
        "新年好",
    )
    if any(w in text for w in CHITCHAT_STRONG) and not years:
        best_domain = "chitchat"

    # 工具型通用查询（天气、搜索资料、实时信息等）不应被闲聊短路；
    # 否则会直接跳过 ReAct / MCP / online-search 路径。
    WEATHER_HINTS = (
        "天气",
        "气温",
        "降雨",
        "晴天",
        "阴天",
        "雨天",
        "风力",
        "风向",
        "空气质量",
        "湿度",
        "雷阵雨",
        "暴雨",
        "天气预报",
    )
    SEARCH_HINTS = (
        "查一下",
        "搜索",
        "搜一下",
        "搜一搜",
        "查询",
        "资讯",
        "新闻",
        "最新",
        "网上",
        "网络",
        "资料",
        "百科",
        "百度",
        "谷歌",
        "网页",
        "在线",
        "实时",
        "信息",
    )
    tool_query = any(w in text for w in WEATHER_HINTS + SEARCH_HINTS)
    if tool_query and not years:
        best_domain = "general"

    # 零命理信号 + 无年份 → 闲聊（如"为什么这么多人执着西藏"）
    # 但天气/搜索/信息查询必须保留在 general，避免被直接短路掉 ReAct。
    if best_score == 0 and not years and best_domain == "general" and not tool_query:
        best_domain = "chitchat"

    if years and best_domain == "general":
        best_domain = "liunian"

    wants_report = any(word in text for word in ("完整报告", "详细报告", "全面分析", "完整分析", "从头到尾"))
    confidence = min(0.95, 0.45 + best_score * 0.18 + (0.15 if years else 0))
    return QuestionIntent(
        domain=best_domain,
        label=DOMAIN_LABELS.get(best_domain, "综合咨询"),
        target_years=years,
        wants_report=wants_report,
        confidence=round(confidence, 2),
    )


def build_chart_context(
    birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1, user_id: str = "", longitude: float = 0.0
) -> WorkflowChartContext:
    """根据出生时间/性别/流派构造 WorkflowChartContext（大运 10 柱、流年 8 年）。

    Args:
        birth_time: 出生时间（公历/农历/时辰/节日格式均可）
        gender: 性别（男/女）
        sect: 日柱计算流派（默认 2）
        yun_sect: 大运计算流派（默认 1）
        user_id: 用户 ID，用于从命盘画像加载历史断事知识
        longitude: 出生地东经度数（0=未提供）。传入后做真太阳时校正（基准 120°E，每度差 4 分钟），
            保证聊天路径与 /chart API 的排盘结果一致
    Returns:
        已排盘完成的 WorkflowChartContext
    """
    chart = build_bazi_chart(
        birth_time,
        gender,
        sect=sect,
        yun_sect=yun_sect,
        dayun_count=10,
        liunian_years=8,
        longitude=longitude or None,
    )
    return WorkflowChartContext(
        birth_time=birth_time,
        gender=gender,
        sect=sect,
        yun_sect=yun_sect,
        chart=chart,
        user_id=user_id,
        longitude=longitude,
    )


def render_full_fact_context(ctx: WorkflowChartContext) -> str:
    return format_fact_context(ctx.chart)
