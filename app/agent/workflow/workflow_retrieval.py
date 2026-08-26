"""工作流检索逻辑（命中命理知识库、构造领域检索 query、合婚对方盘解析）。

纯函数模块：供 XianzhiWorkflow Supervisor 委托调用，不持有实例状态。
从 app/agent/xianzhi_workflow.py 抽离（解耦：把"知识检索"这一单一职责独立成模块），
行为与原内联实现完全一致。
"""
from __future__ import annotations

import datetime as _dt

from app.agent.workflow.workflow_models import (
    DomainWorker,
    QuestionIntent,
    WorkflowChartContext,
)
from app.agent.workflow.workflow_support import (
    _OTHER_BIRTH_RE1,
    _OTHER_BIRTH_RE2,
)
from app.core.logger import log
from app.domain.bazi_engine import build_bazi_chart
from app.rag.retrieval import (
    DOMAIN_RULE_QUERIES,
    detect_theory_topic,
    retrieve_for_context,
)
from app.rag.vector_store import get_knowledge_base

# 单 query 检索结果最大字符数（与 chunk_size 对齐，top-1 chunk 截断兜底）
_MAX_TEXT_PER_QUERY = 600

# 断事领域 → 古籍检索 query（命中对应古籍，增强断法依据）
_ANCIENT_QUERY_MAP = {
    "career": "渊海子平 官杀 事业 官星",
    "wealth": "渊海子平 财星 食伤生财",
    "marriage": "滴天髓 婚姻 配偶宫",
    "health": "三命通会 疾病 五行 健康",
    "love": "渊海子平 桃花 感情",
    "personality": "滴天髓 性情 日主 十神",
    "migration": "三命通会 驿马 方位 迁移",
    "naming": "渊海子平 起名 用神",
    "auspicious": "三命通会 择日 择吉",
    "match": "三命通会 合婚 夫妻宫",
    "children": "三命通会 子息 子女 食伤",
}

# 断事领域 → 断法体系检索 query
_DUANFA_QUERY_MAP = {
    "health": "健康伤病 断法 五行失衡 疾病",
    "wealth": "贫富层次 财星 判断",
    "career": "事业工作 官星 印星 断法",
    "marriage": "婚恋关系 规则卡 配偶宫",
    "love": "婚恋关系 规则卡 桃花",
    "personality": "性格心性 详断 十神 日主",
    "migration": "方位迁移 断法 驿马 用神",
    "naming": "起名改名 规则 喜用神 五行",
    "auspicious": "择吉择日 断法 黄道 用事",
    "match": "合婚配对 断法 夫妻宫 刑冲",
    "children": "子女子嗣 断法 食伤 子女宫",
}


def retrieve_rules(
    intent: QuestionIntent,
    ctx: WorkflowChartContext,
    worker: DomainWorker | None = None,
    user_text: str = "",
) -> str:
    """按问题意图检索命理知识库规则，返回拼接好的知识文本。

    闲聊直接短路返回提示；知识库未就绪则返回「仅用结构化事实」提示。
    否则根据 intent.domain 选择对应 Worker 的检索维度，结合日主/月支构造查询词，
    调 vector_store 检索并拼回文本。
    """
    # 闲聊场景：最优先短路，不依赖知识库，让 LLM 自然回应
    if intent.domain == "chitchat":
        return "（闲聊场景，无需命理知识检索）"
    if not get_knowledge_base().ready:
        return "（知识库未就绪，本轮只使用结构化排盘事实与内置命理口径。）"

    day_master = ctx.chart.wuxing.day_master or ""
    strength = ctx.chart.wuxing.strength or ""

    # ===== LLM 拆解的 queries 优先（精准、自适应） =====
    if intent.queries:
        # LLM 拆解的 query 可能过短（如"学业 命盘分析"），2-gram 区分度低，
        # 拼接领域核心术语前缀增强检索相关性
        domain_kw = DOMAIN_RULE_QUERIES.get(intent.domain, ("",))[0].split()[0] if intent.domain else ""
        queries = [
            f"{domain_kw} {q}" if domain_kw and len(q) < 8 else q
            for q in intent.queries
        ]
        # 不追加 extra_queries / DOMAIN_RULE_QUERIES：固定领域检索词对同领域任何问题
        # 都命中同样片段（与具体问题无关），只会挤占 query 名额并引入噪音；
        # 检索质量交给 LLM 拆解的自适应 query（theory 领域同理，见 build_theory_queries）
        queries = queries[:4]
        log.info("[workflow检索] LLM拆解路径 queries={} (共{}条)",
                 queries, len(queries))
    elif intent.domain == "theory":
        queries, log_meta = build_theory_queries(user_text)
        log.info("[workflow检索] 理论路径 meta={} 构造query数={}", log_meta, len(queries))
    else:
        queries, log_meta = build_duxing_queries(intent, ctx, worker, user_text)
        log.info("[workflow检索] 断事路径 meta={} 构造query数={}", log_meta, len(queries))

    log.info("[workflow检索] 领域={} 命主={}{} 构造query数={}",
             intent.domain, day_master, strength, len(queries))

    # 检索执行统一走 app.rag.retrieval.retrieve_for_context（与 ReAct 工具路径同一入口/口径）
    hit_docs = retrieve_for_context(
        queries,
        max_docs=len(queries),
        max_chars_per_chunk=_MAX_TEXT_PER_QUERY,
        verbose=True,
    )
    if not hit_docs:
        log.info("[workflow检索] 全部query无匹配结果")
        return "（未检索到相关知识）"
    parts: list[str] = []
    for i, (_q, doc) in enumerate(hit_docs, 1):
        parts.append("[片段{}] (来源:{}):\n{}".format(
            i, doc.metadata.get("source", "未知"), doc.page_content))
    return "\n\n".join(parts)


def build_theory_queries(user_text: str) -> tuple[list[str], str]:
    """理论问题 query 构造：精准单概念，规避泛化检索。

    1) 命中具体术语 → 单条精准 query
    2) 未命中 → 走兜底 query
    3) 严格限制 1-2 条 query，不叠加个性化/命例/古籍/断法
    """
    match = detect_theory_topic(user_text)
    if match:
        topic, query = match
        # 用户原句放首条：语义最自然，对 embedding 检索最友好
        queries = [user_text, query] if user_text and user_text.strip() else [query]
        return queries, f"topic={topic}"
    # fallback 仅保留用户原句，不再追加"术语白话 对照表..."这类泛化 query
    # （该 query 总会命中术语白话对照表 chunk，对综合性理论回答引入噪音）
    if user_text and user_text.strip():
        return [user_text.strip()], "fallback"
    return [], "fallback"


def build_duxing_queries(
    intent: QuestionIntent,
    ctx: WorkflowChartContext,
    worker: DomainWorker | None,
    user_text: str = "",
) -> tuple[list[str], str]:
    """断事问题 query 构造：用户原句 + 个性化 + 领域规则 + Worker 专属 + 古籍 + 断法。"""
    # 用户原句放首条：语义最自然，对 embedding 检索最友好
    queries: list[str] = []
    if user_text and user_text.strip():
        queries.append(user_text.strip())
    day_master = ctx.chart.wuxing.day_master or ""
    strength = ctx.chart.wuxing.strength or ""
    # 个性化 query 紧随：绑定命盘日主+强弱，对检索精度最关键，优先于通用堆砌词
    queries.append(f"{intent.label} {day_master}日主 {strength} 大运流年")
    # 领域通用规则 query（合并为1条，抽象术语）
    domain_rules = DOMAIN_RULE_QUERIES.get(intent.domain, DOMAIN_RULE_QUERIES["general"])
    if domain_rules:
        queries.append(domain_rules[0])
    # 1) Worker 专属检索 query（合并为1条，具体场景词）
    if worker and worker.extra_queries:
        queries.append(worker.extra_queries[0])
    # 2) 按领域补古籍检索
    ancient_q = _ANCIENT_QUERY_MAP.get(intent.domain)
    if ancient_q:
        queries.append(ancient_q)
    # 3) 断法体系 query
    duanfa_q = _DUANFA_QUERY_MAP.get(intent.domain)
    if duanfa_q:
        queries.append(duanfa_q)
    # 上限 4 条（用户原句 + 个性化 + 领域规则 + worker专属）
    return queries[:4], "duxing"


def extend_chart_if_needed(ctx: WorkflowChartContext, intent: QuestionIntent) -> WorkflowChartContext:
    """按需扩展命盘流年覆盖范围以覆盖 intent.target_years（合婚/跨年流年查询用）。"""
    if not intent.target_years:
        return ctx
    known_years = {item.year for item in ctx.chart.liunian}
    if all(year in known_years for year in intent.target_years):
        log.debug("[扩盘] 目标年份 {} 已在流年范围内，无需扩盘", intent.target_years)
        return ctx
    start = min(min(intent.target_years), _dt.date.today().year)
    end = max(max(intent.target_years), _dt.date.today().year)
    log.info("[扩盘] 流年范围不足，扩展至 {}~{} (目标年份={})", start, end, intent.target_years)
    chart = build_bazi_chart(
        ctx.birth_time,
        ctx.gender,
        sect=ctx.sect,
        yun_sect=ctx.yun_sect,
        dayun_count=12,
        liunian_start_year=start,
        liunian_years=max(1, end - start + 1),
    )
    return WorkflowChartContext(ctx.birth_time, ctx.gender, ctx.sect, ctx.yun_sect, chart, user_id=ctx.user_id)


def parse_other_birth(text: str) -> tuple[str, str]:
    """从用户问题中正则抽取「对方」出生信息（合婚兜底）。

    返回 (birth_time, gender)，无匹配返回 ("", "")。
    birth_time 标准化为 YYYY-MM-DD HH:MM（时分缺省补 00:00）。
    """
    for pattern in (_OTHER_BIRTH_RE1, _OTHER_BIRTH_RE2):
        m = pattern.search(text)
        if m:
            d = m.groupdict()
            year, month, day = int(d["year"]), int(d["month"]), int(d["day"])
            hour = int(d["hour"]) if d.get("hour") else 0
            minute = int(d["minute"]) if d.get("minute") else 0
            birth_time = "{}-{:02d}-{:02d} {:02d}:{:02d}".format(year, month, day, hour, minute)
            return birth_time, d["gender"]
    return "", ""


def build_match_basis(self_ctx: WorkflowChartContext, other_ctx: WorkflowChartContext) -> str:
    """复用规则合婚工具 bazi_hehun，生成双盘基础数据，作为 LLM 综合判断的锚点。"""
    try:
        from app.tools.bazi import bazi_hehun
        # bazi_hehun 是 @tool 装饰的 StructuredTool，需用 .func 取底层函数直接调用
        base = bazi_hehun.func(
            self_ctx.birth_time, self_ctx.gender,
            other_ctx.birth_time, other_ctx.gender,
            self_ctx.sect,
        )
        if base and not base.startswith("合婚分析失败"):
            return base
    except Exception as e:
        log.warning("[match] 规则合婚基础数据生成失败: {}", e)
    return ""
