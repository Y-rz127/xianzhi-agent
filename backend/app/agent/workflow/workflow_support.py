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
from app.core.config import settings as _settings
from app.domain.chart_builder import build_bazi_chart
from app.domain.chart_format import format_fact_context
from app.rag.retrieval import DOMAIN_KEYWORDS
from app.tools.text_clean import clean_think_tags, dedupe_content as _dedupe_content_impl


def _iter_json_candidates(text: str):
    """按大括号平衡扫描，逐个 yield 能解析成 JSON 的片段（含字符串转义/引号内大括号处理）。"""
    for start, ch in enumerate(text):
        if ch != "{":
            continue
        depth = 0
        in_str = False
        esc = False
        for pos in range(start, len(text)):
            c = text[pos]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        yield json.loads(text[start : pos + 1])
                    except json.JSONDecodeError:
                        pass
                    break


def _parse_json(text: str) -> Any:
    """容错 JSON 解析：处理 LLM 输出的各种格式问题。

    旧实现失败后用贪婪正则 ``\\{[\\s\\S]*\\}`` 取"第一个 { 到最后一个 }"，只要思考文字里出现
    任何大括号就会整体解析失败（审核路径因此被静默降级为"通过"）。现改为整体解析 →
    逐个大括号起点做平衡扫描，逐个尝试；审核类 JSON 以 ``pass`` 字段为标志，优先取最后一个
    含 ``pass`` 的对象（结论通常在思考之后），否则取最后一个可解析对象。
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    candidates = list(_iter_json_candidates(text))
    if not candidates:
        return None
    verdicts = [c for c in candidates if isinstance(c, dict) and "pass" in c]
    return verdicts[-1] if verdicts else candidates[-1]


def invoke_review(chat_model: Any, messages: list[Any]) -> str:
    """审核（Reviewer）专用 LLM 调用。

    与 `workflow_messages.invoke` 一致地放宽超时并清理思考标签（旧版审核直接
    `chat_model.invoke`，既没有超时 bind 也不清理 think 块，思考模型的输出会让 JSON 解析失败），
    但不做"空产出兜底文案"——审核拿不到 JSON 时必须显式降级，而不是把兜底文案当审核结论解析。
    """
    response = chat_model.bind(timeout=_settings.workflow_llm_timeout).invoke(messages)
    content = (getattr(response, "content", "") or "").strip()
    return clean_think_tags(content)


def _dedupe_content(content: str) -> str:
    """检测并移除完全重复的内容（推理模型 think 块泄漏的兜底）。
    委托给 app.tools.text_clean.dedupe_content 统一实现。
    """
    return _dedupe_content_impl(content)


GANZHI_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")


YEAR_GANZHI_RE = re.compile(
    r"(?P<year>\d{4})年(?P<gap>[^。；;，,、\n]{0,6})(?P<ganzhi>[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])"
)


# 大运指认兜底识别（LLM 拆解失败时用，只识别显式表达，不猜）
_DAYUN_SEQ_RE = re.compile(r"第\s*([一二三四五六七八九十]+|\d{1,2})\s*[步運运]")
_DAYUN_AGE_RE = re.compile(r"(\d{1,2})\s*[-~到至]\s*(\d{1,2})\s*岁")
_DAYUN_GANZHI_RE = re.compile(r"([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])\s*(?:大)?运")

# 短年份（2 位 NN 年）：限定 NN ≥ 10 且距今年 ≤ 50 年，避免「5年」「6岁」等量词误识别
_SHORT_YEAR_RE = re.compile(r"(?<![\d年月日时])(\d{2})\s*年(?!月|日)")

# 年龄指认：NN 岁那年/时/当时/前后 之类的相对时间。NN ∈ [0, 120]
# 捕获：组1=年龄数字，组2=连接词（"那年"/"时"/"那年"），无组2（如"35岁运势"）也接受
_AGE_RE = re.compile(r"(?<![\d年大小高])\s*(\d{1,3})\s*岁(?:那年|那年时|那时|当时|时候|前|后|左右)?")

_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _extract_target_years(text: str, today: _dt.date | None = None) -> list[int]:
    """抽取用户问题中的目标年份：4 位年份 + "NN 年" 简写 → 20NN；"今年/明年" 兜底。

    与 _detect_target_dayun（解析大运指认）配合：拿到 target_years 后可触发扩盘与岁运关系注入。
    """
    today = today or _dt.date.today()
    years: set[int] = set()
    # 4 位年份（1900-2099）
    for y in re.findall(r"(?:19|20)\d{2}", text):
        years.add(int(y))
    # 2 位简写年份（23年 → 2023）：候选 20NN/19NN，挑距 today 近且 ≤ 50 年的
    for m in _SHORT_YEAR_RE.finditer(text):
        nn = int(m.group(1))
        if nn < 10:
            continue
        cand = [base + nn for base in (2000, 1900) if abs(base + nn - today.year) <= 50]
        if cand:
            years.add(min(cand, key=lambda y: abs(y - today.year)))
    # "今年"/"明年" 兜底
    if "今年" in text:
        years.add(today.year)
    if "明年" in text:
        years.add(today.year + 1)
    return sorted(years)


def _age_to_years(text: str, birth_time: str, today: _dt.date | None = None) -> list[int]:
    """把「NN 岁那年/时/当时」等年龄指认换算成具体年份；其余文本中的纯年龄不识别。

    口径：周岁 = today.year - birth_year - (today 是否过生日)；
    虚岁 = 周岁 + 1（传统命理以虚岁为主，LLM 上下文注入的也是虚岁）。
    命中多条「NN 岁」时全部换算、按年份去重返回。

    Args:
        text: 用户问题
        birth_time: 用户出生时间（公历，"YYYY-MM-DD HH:MM"）
        today: 基准日期（默认今天）

    Returns:
        换算后的目标年份列表（去重、按升序）；无年龄指认时返回空列表
    """
    today = today or _dt.date.today()
    # 解析出生年/月/日（容错 "1990-05-20"/"1990-05-20 14:30" 等）
    m = re.search(r"(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})", birth_time or "")
    if not m:
        return []
    by = int(m.group(1))
    # 虚岁约定：今年虚岁 = today.year - by + 1
    # 已知虚岁 → 公历出生年 = today.year - 已知虚岁 + 1
    out: set[int] = set()
    for am in _AGE_RE.finditer(text):
        age = int(am.group(1))
        if age < 1 or age > 120:
            continue
        solar_year = today.year - age + 1
        # 边界 sanity：与出生年差不能 < 0（用户在出生前"几岁"无意义）
        if solar_year < by:
            continue
        out.add(solar_year)
    return sorted(out)


def _normalize_seq(raw: str) -> str:
    """中文/阿拉伯大运序号 → 阿拉伯数字串（'三'→'3'、'十二'→'12'）。"""
    raw = raw.strip()
    if raw.isdigit():
        return str(int(raw))
    if raw == "十":
        return "10"
    if raw.startswith("十"):
        return str(10 + _CN_DIGITS.get(raw[1:], 0))
    if "十" in raw:
        a, b = raw.split("十", 1)
        return str(_CN_DIGITS.get(a, 0) * 10 + _CN_DIGITS.get(b, 0))
    return str(_CN_DIGITS.get(raw, 0))


def _detect_target_dayun(text: str) -> str:
    """从文本提取大运指认 spec（'' 未指定），规则与 yun_relations._resolve_spec 对齐。"""
    m = _DAYUN_SEQ_RE.search(text)
    if m:
        return _normalize_seq(m.group(1))
    m = _DAYUN_AGE_RE.search(text)
    if m:
        return f"{int(m.group(1))}-{int(m.group(2))}"
    m = _DAYUN_GANZHI_RE.search(text)
    if m:
        return m.group(1)
    return ""


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
    years = _extract_target_years(text, today)

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
        target_dayun=_detect_target_dayun(text),
    )


def build_chart_context(
    birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1, user_id: str = "", longitude: float = 0.0
) -> WorkflowChartContext:
    """根据出生时间/性别/流派构造 WorkflowChartContext（大运 12 柱、流年 8 年）。

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
        dayun_count=12,
        liunian_years=10,
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
