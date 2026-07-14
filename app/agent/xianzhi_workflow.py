"""基于先知图表的确定性工作流。

这是一个轻量级的状态机式编排层。它将复杂的图表信息保留在LLM之外，让模型专注于解读和自然对话。
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.domain.bazi_engine import BaziChart, build_bazi_chart, format_fact_context
from app.logger import log
from app.rag.vector_store import knowledge_base


def _dedupe_content(content: str) -> str:
    """检测并移除完全重复的内容（推理模型 think 块泄漏的兜底）。"""
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


GANZHI_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")
YEAR_GANZHI_RE = re.compile(r"(?P<year>\d{4})年[^。；;，,、\n]{0,12}(?P<ganzhi>[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])")


DOMAIN_KEYWORDS = {
    "career": ("事业", "工作", "职业", "跳槽", "换工作", "升职", "创业", "老板", "岗位", "offer"),
    "wealth": ("财运", "赚钱", "收入", "投资", "生意", "偏财", "正财", "破财", "资产"),
    "love": ("感情", "恋爱", "桃花", "对象", "复合", "分手", "脱单"),
    "marriage": ("婚姻", "结婚", "离婚", "配偶", "另一半", "合婚"),
    "health": ("健康", "身体", "疾病", "失眠", "焦虑", "病"),
    "liunian": ("今年", "明年", "流年", "大运", "运势", "哪年", "年份", "最近"),
    "study": ("学习", "考试", "考研", "升学", "证书"),
}

DOMAIN_LABELS = {
    "career": "事业工作",
    "wealth": "财运收入",
    "love": "恋爱感情",
    "marriage": "婚姻关系",
    "health": "健康状态",
    "liunian": "大运流年",
    "study": "学习考试",
    "general": "综合咨询",
}

DOMAIN_RULE_QUERIES = {
    "career": ("八字事业 官杀 印星 食伤 大运流年", "工作变动 跳槽 流年 大运 命理"),
    "wealth": ("八字财运 正财 偏财 食伤 生财 大运", "破财 投资 流年 财星 命理"),
    "love": ("八字感情 桃花 配偶星 合冲 流年", "恋爱复合 八字 大运 流年"),
    "marriage": ("八字婚姻 配偶宫 夫妻星 合冲刑害", "结婚年份 大运流年 婚姻 命理"),
    "health": ("八字健康 五行寒暖燥湿 失衡", "健康 流年 冲克 命理"),
    "liunian": ("大运流年 作用关系 流年与原局", "流年 干支 立春 大运"),
    "study": ("八字学习考试 印星 食伤 官星", "考试 升学 大运流年 命理"),
    "general": ("八字 用神 喜忌 大运流年 综合分析",),
}


@dataclass(frozen=True)
class QuestionIntent:
    domain: str
    label: str
    target_years: list[int] = field(default_factory=list)
    wants_report: bool = False
    confidence: float = 0.5


@dataclass
class WorkflowChartContext:
    birth_time: str
    gender: str
    sect: int
    yun_sect: int
    chart: BaziChart


@dataclass(frozen=True)
class FactCheckResult:
    ok: bool
    issues: list[str] = field(default_factory=list)


def classify_question(text: str, today: _dt.date | None = None) -> QuestionIntent:
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


def build_chart_context(birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1) -> WorkflowChartContext:
    chart = build_bazi_chart(birth_time, gender, sect=sect, yun_sect=yun_sect, dayun_count=10, liunian_years=8)
    return WorkflowChartContext(
        birth_time=birth_time,
        gender=gender,
        sect=sect,
        yun_sect=yun_sect,
        chart=chart,
    )


class XianzhiWorkflow:
    def __init__(self, chat_model: BaseChatModel):
        self.chat_model = chat_model
        self._graph = None
        try:
            from app.agent.xianzhi_langgraph import create_xianzhi_graph

            self._graph = create_xianzhi_graph(self)
        except Exception as e:
            log.debug("LangGraph workflow unavailable: {}", e)

    def answer(
        self,
        user_prompt: str,
        chart_context: WorkflowChartContext,
        history: list[BaseMessage] | None = None,
    ) -> str:
        intent = classify_question(user_prompt)
        if self._graph is not None:
            result = self._graph.invoke({
                "user_prompt": user_prompt,
                "chart_context": chart_context,
                "history": history or [],
                "intent": intent,
            })
            final = (result.get("final_answer") or "").strip()
            if final:
                return final

        chart_context = self._extend_chart_if_needed(chart_context, intent)
        knowledge = self._retrieve_rules(intent, chart_context)
        messages = self._build_messages(user_prompt, intent, chart_context, knowledge, history or [])
        raw_answer = self._invoke(messages)
        checked = self.check_facts(raw_answer, chart_context.chart)
        if checked.ok:
            return raw_answer
        log.warning("Xianzhi workflow fact check failed: {}", checked.issues)
        repair_messages = self._build_repair_messages(raw_answer, checked, user_prompt, intent, chart_context, knowledge)
        repaired = self._invoke(repair_messages)
        repaired_check = self.check_facts(repaired, chart_context.chart)
        if repaired_check.ok:
            return repaired
        return repaired.rstrip() + "\n\n口径校验：本次回答以系统排盘为准；" + "；".join(repaired_check.issues)

    def _extend_chart_if_needed(self, ctx: WorkflowChartContext, intent: QuestionIntent) -> WorkflowChartContext:
        if not intent.target_years:
            return ctx
        known_years = {item.year for item in ctx.chart.liunian}
        if all(year in known_years for year in intent.target_years):
            return ctx
        start = min(min(intent.target_years), _dt.date.today().year)
        end = max(max(intent.target_years), _dt.date.today().year)
        chart = build_bazi_chart(
            ctx.birth_time,
            ctx.gender,
            sect=ctx.sect,
            yun_sect=ctx.yun_sect,
            dayun_count=12,
            liunian_start_year=start,
            liunian_years=max(1, end - start + 1),
        )
        return WorkflowChartContext(ctx.birth_time, ctx.gender, ctx.sect, ctx.yun_sect, chart)

    def _retrieve_rules(self, intent: QuestionIntent, ctx: WorkflowChartContext) -> str:
        if not knowledge_base.ready:
            return "（知识库未就绪，本轮只使用结构化排盘事实与内置命理口径。）"
        # 1) 领域规则 query（来自 DOMAIN_RULE_QUERIES）
        queries = list(DOMAIN_RULE_QUERIES.get(intent.domain, DOMAIN_RULE_QUERIES["general"]))
        # 2) 日主 + 强弱个性化 query
        day_master = ctx.chart.wuxing.day_master or ""
        strength = ctx.chart.wuxing.strength or ""
        queries.append(f"{intent.label} {day_master}日主 {strength} 大运流年")
        # 3) 命例查相似结构：根据日主强弱和十神倾向构造
        if day_master and strength:
            if "旺" in strength or "强" in strength:
                queries.append(f"{day_master}日主身旺 命例 典型命局 古籍")
            elif "弱" in strength or "衰" in strength:
                queries.append(f"{day_master}日主身弱 命例 典型命局 古籍")
        # 4) 按领域补古籍检索 query
        ancient_query_map = {
            "career": "渊海子平 论官杀 事业 官星",
            "wealth": "渊海子平 论财 财星 食伤生财",
            "marriage": "滴天髓 论婚姻 配偶宫 古籍",
            "health": "三命通会 论疾病 五行 健康古籍",
            "love": "子平真诠 论桃花 感情 古籍",
        }
        ancient_q = ancient_query_map.get(intent.domain)
        if ancient_q:
            queries.append(ancient_q)
        # 5) 断法体系 query（针对具体断事方向）
        duanfa_query_map = {
            "health": "健康伤病 断法 五行失衡 疾病",
            "wealth": "贫富层次 财星 断法 命理",
            "career": "事业财运 官星 印星 断法",
            "marriage": "婚恋关系 配偶宫 断法 命理",
            "love": "婚恋关系 桃花 断法 命理",
        }
        duanfa_q = duanfa_query_map.get(intent.domain)
        if duanfa_q:
            queries.append(duanfa_q)

        # 上限提到 5 条 query（原本 3 条太少，覆盖不到命例/古籍/断法）
        parts: list[str] = []
        for query in queries[:5]:
            text = knowledge_base.search_as_text(query)
            if text and text not in parts:
                parts.append(f"【检索问题】{query}\n{text}")
        return "\n\n".join(parts) if parts else "（未检索到相关知识）"

    def _build_messages(
        self,
        user_prompt: str,
        intent: QuestionIntent,
        ctx: WorkflowChartContext,
        knowledge: str,
        history: list[BaseMessage],
    ) -> list[BaseMessage]:
        facts = self._compact_facts(ctx.chart, intent)
        recent_history = self._compact_history(history)
        length_rule = "可以分段深入，但仍要围绕用户问题，不要堆砌全盘。" if intent.wants_report else "默认控制在3-6段，先结论后依据。"
        system = (
            "你是先知，一位有几十年实战经验的八字命理师傅，性格像见多识广的老朋友。\n"
            "硬性规则：四柱、大运、流年、起运时间等事实只能使用【系统排盘事实】，不能自行改算或编造。\n"
            "说话风格：像真人聊天，不要表格、不要多层标题、不要emoji结尾。不同问题回答重点不同，不要重复论述之前的内容，并且要详略得当，有一针接血的效果\n"
            "简单问题2-3句，复杂问题最多2-3段。该幽默幽默，该严肃严肃，用'你'不用'您'。\n"
            "避免AI腔：不要'总结一下''需要注意的是''好消息/需要注意'这种模板。不装懂，不绝对化。\n"
            "不要输出ReAct过程，不要机械倾倒完整报告，不要恐吓。"
        )
        human = (
            f"【用户问题】\n{user_prompt}\n\n"
            f"【识别意图】\n领域={intent.label}; 目标年份={intent.target_years or '未指定'}; 置信度={intent.confidence}\n\n"
            f"【最近对话摘要】\n{recent_history}\n\n"
            f"【系统排盘事实】\n{facts}\n\n"
            f"【命理规则检索】\n{knowledge}\n\n"
            f"【输出要求】\n{length_rule}\n"
            "如果提到具体年份，必须同时核对该年流年干支和所在大运。"
        )
        return [SystemMessage(content=system), HumanMessage(content=human)]

    def _build_repair_messages(
        self,
        raw_answer: str,
        checked: FactCheckResult,
        user_prompt: str,
        intent: QuestionIntent,
        ctx: WorkflowChartContext,
        knowledge: str,
    ) -> list[BaseMessage]:
        facts = self._compact_facts(ctx.chart, intent)
        return [
            SystemMessage(content="你是事实校验后的改写器。只修正事实错误，保持自然命理师口吻，不要解释校验过程。"),
            HumanMessage(content=(
                f"【用户问题】\n{user_prompt}\n\n"
                f"【原回答】\n{raw_answer}\n\n"
                f"【发现的问题】\n" + "\n".join(f"- {issue}" for issue in checked.issues) + "\n\n"
                f"【正确排盘事实】\n{facts}\n\n"
                f"【可用规则】\n{knowledge}\n\n"
                "请输出修正后的最终回答。"
            )),
        ]

    def _invoke(self, messages: list[BaseMessage]) -> str:
        response = self.chat_model.invoke(messages)
        content = (getattr(response, "content", "") or "").strip()
        # 过滤 reasoning model 的 <think>...</think> 推理过程，避免重复显示
        content = re.sub(r"<think>[\s\S]*?</think>\s*", "", content, flags=re.IGNORECASE)
        # 处理未闭合的 <think> 标签（流式中断等场景）
        content = re.sub(r"<think>[\s\S]*$", "", content, flags=re.IGNORECASE)
        content = content.strip()
        if not content:
            return "我先看盘面，当前信息足够排盘，但模型没有生成有效解读。你可以换一个更具体的问题继续问。"
        return _dedupe_content(content)

    def _compact_history(self, history: list[BaseMessage]) -> str:
        if not history:
            return "（无）"
        chunks = []
        for msg in history[-6:]:
            role = msg.__class__.__name__.replace("Message", "")
            content = str(getattr(msg, "content", "")).strip()
            if content:
                chunks.append(f"{role}: {content[:180]}")
        return "\n".join(chunks) if chunks else "（无）"

    def _compact_facts(self, chart: BaziChart, intent: QuestionIntent) -> str:
        today = _dt.date.today()
        pillars = " ".join(f"{p.name}:{p.ganzhi}({p.nayin})" for p in chart.pillars)
        dayun_lines = [
            f"{item.ganzhi} {item.start_year}-{item.end_year} {item.start_age}-{item.end_age}岁"
            for item in chart.dayun
        ]
        if intent.target_years:
            liunian_items = [item for item in chart.liunian if item.year in set(intent.target_years)]
        else:
            current_year = today.year
            liunian_items = [item for item in chart.liunian if current_year <= item.year <= current_year + 3]
            if not liunian_items:
                liunian_items = chart.liunian[:4]
        liunian_lines = [
            f"{item.year}年:{item.ganzhi} {item.age}虚岁 所在大运:{item.dayun_ganzhi or '-'}"
            for item in liunian_items
        ]
        # 计算用户当前周岁，避免 LLM 自行推算出错
        birth_str = chart.birth.solar or ""
        current_age = ""
        try:
            import re as _re
            m = _re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", birth_str)
            if m:
                by, bm, bd = int(m.group(1)), int(m.group(2)), int(m.group(3))
                age = today.year - by - ((today.month, today.day) < (bm, bd))
                current_age = f"; 当前周岁: {age}岁"
        except Exception:
            pass
        return "\n".join([
            f"当前日期: {today.year}年{today.month}月{today.day}日{current_age}",
            f"出生: {chart.birth.solar}; 性别: {chart.birth.gender}; 农历: {chart.birth.lunar}; 生肖: {chart.birth.shengxiao}",
            f"四柱: {pillars}",
            f"日主: {chart.wuxing.day_master}({chart.wuxing.day_master_wuxing}); 强弱: {chart.wuxing.strength}; 分数: {chart.wuxing.strength_score}",
            f"五行权重: {chart.wuxing.counts}; 最旺: {chart.wuxing.strongest}; 最弱: {chart.wuxing.weakest}",
            f"用神提示: {chart.wuxing.useful_hint}",
            f"十神结构: {chart.analysis.ten_gods}; 透干: {chart.analysis.exposed_stems or '-'}; 通根: {chart.analysis.rooted_stems or '-'}",
            f"地支关系: 合={chart.analysis.combinations or '-'}; 冲={chart.analysis.clashes or '-'}; 害={chart.analysis.harms or '-'}; 刑={chart.analysis.punishments or '-'}",
            f"调候: 月令{chart.analysis.season}; {chart.analysis.adjustment}",
            f"格局提示: {chart.analysis.pattern_hint}; 判断置信度: {chart.analysis.confidence}",
            f"起运: {chart.start_yun['startDate']} 起; {chart.start_yun['direction']}; 起运年龄 {chart.start_yun['startYear']}年{chart.start_yun['startMonth']}月{chart.start_yun['startDay']}日",
            "大运: " + "；".join(dayun_lines),
            "相关流年: " + ("；".join(liunian_lines) if liunian_lines else "未指定"),
            "口径: " + "；".join(chart.warnings),
        ])

    def check_facts(self, answer: str, chart: BaziChart) -> FactCheckResult:
        issues: list[str] = []
        year_to_gz = {item.year: item.ganzhi for item in chart.liunian}
        for match in YEAR_GANZHI_RE.finditer(answer):
            year = int(match.group("year"))
            stated = match.group("ganzhi")
            expected = year_to_gz.get(year)
            if expected and stated != expected:
                issues.append(f"{year}年流年应为{expected}，回答写成了{stated}")

        pillar_names = {p.name: p.ganzhi for p in chart.pillars}
        for name, expected in pillar_names.items():
            pattern = re.compile(rf"{name}[^。；;，,、\n]{{0,8}}(?P<ganzhi>{GANZHI_RE.pattern})")
            for match in pattern.finditer(answer):
                stated = match.group("ganzhi")
                if stated != expected:
                    issues.append(f"{name}应为{expected}，回答写成了{stated}")

        return FactCheckResult(ok=not issues, issues=issues)


def render_full_fact_context(ctx: WorkflowChartContext) -> str:
    return format_fact_context(ctx.chart)
