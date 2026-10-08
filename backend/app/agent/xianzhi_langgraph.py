"""Xianzhi 工作流的 LangGraph 编排实现（唯一编排后端）。

构建 StateGraph：分类→扩盘→检索→生成→校验→（条件路由）修复。
节点逻辑均委托 XianzhiWorkflow 的既有方法，本模块只负责图结构与状态流转。
langgraph 为硬依赖（requirements.txt）：导入失败会在 XianzhiWorkflow 构造期快速失败。
"""

from __future__ import annotations

from functools import partial
from typing import TypedDict

from langchain_core.messages import BaseMessage

from app.agent.workflow.fact_check import SHENSHA_NAMES, SHISHEN_NAMES
from app.agent.workflow.workflow_messages import (
    build_sui_section,
    compact_facts,
)
from app.agent.workflow.workflow_models import (
    DomainWorker,
    FactCheckResult,
    QuestionIntent,
    WorkflowChartContext,
)
from app.agent.workflow.workflow_support import classify_question
from app.agent.workflow.workflow_workers import WORKERS
from app.core.logger import log
from app.core.observability import record_error


class XianzhiGraphState(TypedDict, total=False):
    """LangGraph 工作流状态字典：各节点在 state 上读写，贯穿分类→扩盘→检索→生成→校验→修复。"""

    user_prompt: str
    chart_context: WorkflowChartContext
    history: list[BaseMessage]
    summary: str
    intent: QuestionIntent
    worker: DomainWorker
    knowledge: str
    raw_answer: str
    final_answer: str
    issues: list[str]


def _dropped_real_facts(before: str, after: str, facts_text: str) -> list[str]:
    """对比修复前后的十神/神煞提及，返回"原稿有、修复稿丢了、且排盘事实确实存在"的名字。

    只作观测用（日志 + /metrics 的 repair_dropped_facts），不构成 issue、不触发新一轮修复：
    修复器按 issues 重写整段时可能把正确信息一起删掉（实测恋爱轮修复稿删掉了正确的流年神煞
    "红艳煞"），此前无人可见。
    """
    if not before or not after or not facts_text:
        return []
    names = set(SHISHEN_NAMES) | set(SHENSHA_NAMES)
    return sorted(
        name for name in names
        if name != "日主" and name in before and name not in after and name in facts_text
    )


def _is_chitchat(intent) -> bool:
    return bool(intent and getattr(intent, "domain", "") == "chitchat")


def _intent_needs_chart(intent) -> bool:
    return bool(intent and getattr(intent, "needs_chart", True))


def _classify_node(workflow, state: XianzhiGraphState) -> XianzhiGraphState:
    """分类节点：优先复用 answer() 已拆解的 intent，否则关键词兜底；匹配对应 Worker。"""
    # 优先使用 answer() 入口已通过 LLM 拆解得到的 intent（含 queries/needs_chart），
    # 没有时才 fallback 到关键词分类
    intent = state.get("intent")
    if intent is None:
        intent = classify_question(state["user_prompt"])
    worker = WORKERS.get(intent.domain, WORKERS["general"])
    return {"intent": intent, "worker": worker}


def _chart_node(workflow, state: XianzhiGraphState) -> XianzhiGraphState:
    """扩盘节点：按需扩展命盘流年覆盖范围以覆盖目标年份。"""
    ctx = workflow._extend_chart_if_needed(state["chart_context"], state["intent"])
    return {"chart_context": ctx}


def _retrieve_node(workflow, state: XianzhiGraphState) -> XianzhiGraphState:
    """检索节点：闲聊意图短路跳过；否则检索命理知识库片段。"""
    # 闲聊场景短路：无需检索知识库
    intent = state.get("intent")
    if _is_chitchat(intent):
        log.info("[RAG] 闲聊意图，跳过知识检索")
        return {"knowledge": "（闲聊场景，无需命理知识检索）"}
    workflow._emit_progress("正在检索命理知识…")
    knowledge = workflow._retrieve_rules(
        state["intent"], state["chart_context"], state.get("worker"), state["user_prompt"]
    )
    log.info("[RAG] 检索完成，知识片段 {}字", len(knowledge))
    return {"knowledge": knowledge}


def _generate_node(workflow, state: XianzhiGraphState) -> XianzhiGraphState:
    """生成节点：组装 Worker 消息并调用 LLM 产出原始回答（含会话摘要透传）。"""
    worker = state.get("worker")
    workflow._emit_progress("正在推演生成…")
    messages = workflow._build_messages(
        state["user_prompt"],
        state["intent"],
        state["chart_context"],
        state.get("knowledge", ""),
        state.get("history", []),
        state.get("worker"),
        state.get("summary", ""),
    )
    raw = workflow._invoke(messages)
    log.info("[Worker] {} 生成回答 {}字", getattr(worker, "label", "?"), len(raw))
    return {"raw_answer": raw}


def _check_node(workflow, state: XianzhiGraphState) -> XianzhiGraphState:
    """校验节点：两层审核（正则快筛 + LLM 深审），通过则定稿，否则记录 issues。

    闲聊/题外话（intent.domain=chitchat）跳过 LLM 深审，仅依赖正则快筛，节省 1 次 LLM 调用。
    needs_chart=False（纯理论/术语解释）时十神/神煞校验仅检测归属断言，不误杀纯术语解释。
    """
    raw = state.get("raw_answer", "")
    worker = state.get("worker")
    intent = state.get("intent")
    is_chitchat = _is_chitchat(intent)
    needs_chart = _intent_needs_chart(intent)
    workflow._emit_progress("正在复核断语…")
    log.info("[Reviewer] 开始审核 {} Worker 产出 ({}字)...", getattr(worker, "label", "?"), len(raw))
    second_chart = getattr(intent, "second_chart", None)
    facts_text = compact_facts(state["chart_context"].chart, intent)
    review = workflow._reviewer.review(
        raw,
        state["chart_context"].chart,
        state.get("knowledge", ""),
        workflow.check_facts,
        second_chart.chart if second_chart else None,
        user_prompt=state["user_prompt"],
        ctx=state["chart_context"],
        skip_llm=is_chitchat,
        needs_chart=needs_chart,
        sui_text=build_sui_section(state["chart_context"].chart, intent),
        facts_text=facts_text,
    )
    if review.ok:
        log.info(
            "[Reviewer] {} Worker 产出通过审核 ✓ (source={})",
            getattr(worker, "label", "?"),
            review.source,
        )
    else:
        log.warning(
            "[Reviewer] {} Worker 产出未通过审核 ✗ (source={})",
            getattr(worker, "label", "?"),
            review.source,
        )
        for i, issue in enumerate(review.issues, 1):
            log.warning("[Reviewer]   issue[{}]: {}", i, issue)
        # 落被审原稿：此前只记字数，误判无法复盘（前端只显示修复稿，原稿会永久丢失）
        log.warning("[Reviewer] 被审原稿 ({}字):\n{}", len(raw), raw)
    return {"issues": review.issues, "final_answer": raw if review.ok else ""}


def _repair_node(workflow, state: XianzhiGraphState) -> XianzhiGraphState:
    """修复节点：基于 issues 重构消息让 LLM 反思修复，并二次校验；仍不过则附口径说明。

    闲聊场景无 issues 可修（check_node 已跳过 LLM 深审），无意义再走 repair。
    """
    intent = state.get("intent")
    is_chitchat = _is_chitchat(intent)
    needs_chart = _intent_needs_chart(intent)
    # 闲聊短路：check_node 已通过正则，repair 不会带来改善，直接返回原答案
    if is_chitchat:
        log.info("[Reflextion] 闲聊场景，跳过修复节点，直接返回原答案")
        return {"final_answer": state.get("raw_answer", ""), "issues": []}

    worker = state.get("worker")
    workflow._emit_progress("正在修订断语…")
    log.info("[Reflextion] {} Worker 开始修复...", getattr(worker, "label", "?"))
    checked = FactCheckResult(ok=False, issues=state.get("issues", []))
    messages = workflow._build_repair_messages(
        state.get("raw_answer", ""),
        checked,
        state["user_prompt"],
        state["intent"],
        state["chart_context"],
        state.get("knowledge", ""),
        state.get("worker"),
    )
    repaired = workflow._invoke(messages)
    log.info(
        "[Reflextion] {} Worker 修复完成 ({}字)，二次审核中...",
        getattr(worker, "label", "?"),
        len(repaired),
    )
    # 与 check_node 的「被审原稿」配对，便于复盘误判与改动效果
    log.info("[Reflextion] 修复稿 ({}字):\n{}", len(repaired), repaired)
    second_chart = getattr(intent, "second_chart", None)
    facts_text = compact_facts(state["chart_context"].chart, intent)
    # 修复稿 vs 原稿：记录"原稿提到、修复稿丢掉、且排盘事实确实存在"的十神/神煞。
    # 修复器按 issues 重写时可能把正确信息一并删掉（实测恋爱轮修复稿删掉了正确的流年神煞），
    # 这里只落日志 + 指标，不触发新一轮修复。
    dropped = _dropped_real_facts(state.get("raw_answer", ""), repaired, facts_text)
    if dropped:
        log.warning(
            "[Reflextion] {} 修复稿丢弃了排盘事实中确实存在的十神/神煞：{}",
            getattr(worker, "label", "?"),
            "、".join(dropped),
        )
        record_error("repair_dropped_facts")
    # 修复后先走 regex 快筛（零 LLM 调用）
    regex_issues = workflow._reviewer._regex_review(
        repaired,
        state["chart_context"].chart,
        state.get("knowledge", ""),
        workflow.check_facts,
        second_chart.chart if second_chart else None,
        needs_chart,
        facts_text,
    )
    if not regex_issues:
        # regex 通过 ≠ 修复稿没问题：再跑一次 LLM 深审复核。
        # 旧版此处"regex 过即定稿"，修复稿从未被 LLM 看过，改写质量问题无人发现。
        llm_ok = workflow._reviewer.review_llm_only(
            repaired,
            state["chart_context"].chart,
            state.get("knowledge", ""),
            user_prompt=state["user_prompt"],
            ctx=state["chart_context"],
            second_chart=second_chart.chart if second_chart else None,
            sui_text=build_sui_section(state["chart_context"].chart, intent),
        )
        if llm_ok.ok:
            log.info(
                "[Reflextion] {} Worker 修复后 regex + LLM 双通过 ✓ (source={})",
                getattr(worker, "label", "?"),
                llm_ok.source,
            )
            return {"final_answer": repaired, "issues": []}
        # LLM 判不通过但图是单轮修复（无二次修复循环）：仍按 repaired 定稿，问题仅记日志 + 指标
        log.warning(
            "[Reflextion] {} 修复后 regex 通过但 LLM 深审发现问题（{} 条）→ 单轮修复不重试，按 repaired 定稿",
            getattr(worker, "label", "?"),
            len(llm_ok.issues),
        )
        for i, issue in enumerate(llm_ok.issues, 1):
            log.warning("[Reflextion]   LLM 残留issue[{}]: {}", i, issue)
        record_error("reviewer_repair_llm_rejected")
        return {"final_answer": repaired, "issues": llm_ok.issues}
    # regex 仍发现问题 → 才跑 LLM 深审。
    # 注意：旧版这里调 `review()`，而 `review()` 会先跑一遍 regex 并在命中时立刻短路返回，
    # 所以 LLM 实际从未被调用（日志却写"触发 LLM 深审"，误导排查）。现改为 review_llm_only()。
    log.info(
        "[Reflextion] {} Worker 修复后 regex 发现 {} 条问题，跑 LLM 深审复核",
        getattr(worker, "label", "?"),
        len(regex_issues),
    )
    repaired_review = workflow._reviewer.review_llm_only(
        repaired,
        state["chart_context"].chart,
        state.get("knowledge", ""),
        user_prompt=state["user_prompt"],
        ctx=state["chart_context"],
        second_chart=second_chart.chart if second_chart else None,
        sui_text=build_sui_section(state["chart_context"].chart, intent),
    )
    if repaired_review.ok and repaired_review.source == "llm":
        # LLM 深审认为修复稿没问题 → 残留 issue 大概率是正则误报：仍按 repaired 定稿，
        # 但把"疑似误报"落日志 + 指标，避免正则误报长期静默（用户可见内容不受影响）
        log.warning(
            "[Reflextion] {} 修复稿 regex 仍报 {} 条问题，但 LLM 深审判通过 → regex 疑似误报，按 repaired 定稿",
            getattr(worker, "label", "?"),
            len(regex_issues),
        )
        for i, issue in enumerate(regex_issues, 1):
            log.warning("[Reflextion]   regex 残留issue[{}]: {}", i, issue)
        record_error("reviewer_regex_likely_false_positive")
        return {"final_answer": repaired, "issues": []}
    if repaired_review.ok:
        log.info(
            "[Reflextion] {} Worker 修复后 LLM 深审未生效（source={}），残留 issue 仅记日志",
            getattr(worker, "label", "?"),
            repaired_review.source,
        )
        return {"final_answer": repaired, "issues": regex_issues}
    # 修复后仍未通过：issues 仅写日志，不再硬拼到用户可见回复中（之前的「口径校验：...」调试信息会泄露给用户，已移除）
    log.warning(
        "[Reflextion] {} Worker 修复后仍未通过 ✗，降级返回 repaired (残留 {} 条 issue 仅记日志)",
        getattr(worker, "label", "?"),
        len(repaired_review.issues),
    )
    for i, issue in enumerate(repaired_review.issues, 1):
        log.warning("[Reflextion]   残留issue[{}]: {}", i, issue)
    return {"final_answer": repaired, "issues": repaired_review.issues}


def _route_after_check(state: XianzhiGraphState) -> str:
    """条件路由：有 issues 走 repair，否则结束。"""
    return "repair" if state.get("issues") else "end"


def create_xianzhi_graph(workflow):
    """构建编译后的 LangGraph 编排图；langgraph 未安装时直接抛 ImportError（硬依赖）。"""
    from langgraph.graph import END, StateGraph

    graph = StateGraph(XianzhiGraphState)
    graph.add_node("classify", partial(_classify_node, workflow))
    graph.add_node("chart", partial(_chart_node, workflow))
    graph.add_node("retrieve", partial(_retrieve_node, workflow))
    graph.add_node("generate", partial(_generate_node, workflow))
    graph.add_node("check", partial(_check_node, workflow))
    graph.add_node("repair", partial(_repair_node, workflow))
    graph.set_entry_point("classify")
    graph.add_edge("classify", "chart")
    graph.add_edge("chart", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "check")
    graph.add_conditional_edges("check", _route_after_check, {"repair": "repair", "end": END})
    graph.add_edge("repair", END)
    return graph.compile()
