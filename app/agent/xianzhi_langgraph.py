"""Xianzhi 工作流的 LangGraph 编排实现（唯一编排后端）。

构建 StateGraph：分类→扩盘→检索→生成→校验→（条件路由）修复。
节点逻辑均委托 XianzhiWorkflow 的既有方法，本模块只负责图结构与状态流转。
langgraph 为硬依赖（requirements.txt）：导入失败会在 XianzhiWorkflow 构造期快速失败。
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.agent.workflow.xianzhi_workflow import (
    WORKERS,
    DomainWorker,
    FactCheckResult,
    QuestionIntent,
    WorkflowChartContext,
    classify_question,
)
from app.core.logger import log


class XianzhiGraphState(TypedDict, total=False):
    """LangGraph 工作流状态字典：各节点在 state 上读写，贯穿分类→扩盘→检索→生成→校验→修复。"""

    user_prompt: str
    chart_context: WorkflowChartContext
    history: list[Any]
    summary: str
    intent: QuestionIntent
    worker: DomainWorker
    knowledge: str
    raw_answer: str
    final_answer: str
    issues: list[str]


def create_xianzhi_graph(workflow):
    """构建编译后的 LangGraph 编排图；langgraph 未安装时直接抛 ImportError（硬依赖）。"""
    from langgraph.graph import END, StateGraph

    def _is_chitchat(intent) -> bool:
        return bool(intent and getattr(intent, "domain", "") == "chitchat")

    def _intent_needs_chart(intent) -> bool:
        return bool(intent and getattr(intent, "needs_chart", True))

    def classify_node(state: XianzhiGraphState) -> XianzhiGraphState:
        """分类节点：优先复用 answer() 已拆解的 intent，否则关键词兜底；匹配对应 Worker。"""
        # 优先使用 answer() 入口已通过 LLM 拆解得到的 intent（含 queries/needs_chart），
        # 没有时才 fallback 到关键词分类
        intent = state.get("intent")
        if intent is None:
            intent = classify_question(state["user_prompt"])
        worker = WORKERS.get(intent.domain, WORKERS["general"])
        return {"intent": intent, "worker": worker}

    def chart_node(state: XianzhiGraphState) -> XianzhiGraphState:
        """扩盘节点：按需扩展命盘流年覆盖范围以覆盖目标年份。"""
        ctx = workflow._extend_chart_if_needed(state["chart_context"], state["intent"])
        return {"chart_context": ctx}

    def retrieve_node(state: XianzhiGraphState) -> XianzhiGraphState:
        """检索节点：闲聊意图短路跳过；否则检索命理知识库片段。"""
        # 闲聊场景短路：无需检索知识库
        intent = state.get("intent")
        if _is_chitchat(intent):
            log.info("[RAG] 闲聊意图，跳过知识检索")
            return {"knowledge": "（闲聊场景，无需命理知识检索）"}
        knowledge = workflow._retrieve_rules(
            state["intent"], state["chart_context"], state.get("worker"), state["user_prompt"]
        )
        log.info("[RAG] 检索完成，知识片段 {}字", len(knowledge))
        return {"knowledge": knowledge}

    def generate_node(state: XianzhiGraphState) -> XianzhiGraphState:
        """生成节点：组装 Worker 消息并调用 LLM 产出原始回答（含会话摘要透传）。"""
        worker = state.get("worker")
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

    def check_node(state: XianzhiGraphState) -> XianzhiGraphState:
        """校验节点：两层审核（正则快筛 + LLM 深审），通过则定稿，否则记录 issues。

        闲聊/题外话（intent.domain=chitchat）跳过 LLM 深审，仅依赖正则快筛，节省 1 次 LLM 调用。
        needs_chart=False（纯理论/术语解释）时十神/神煞校验仅检测归属断言，不误杀纯术语解释。
        """
        raw = state.get("raw_answer", "")
        worker = state.get("worker")
        intent = state.get("intent")
        is_chitchat = _is_chitchat(intent)
        needs_chart = _intent_needs_chart(intent)
        log.info("[Reviewer] 开始审核 {} Worker 产出 ({}字)...", getattr(worker, "label", "?"), len(raw))
        second_chart = getattr(intent, "second_chart", None)
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
        return {"issues": review.issues, "final_answer": raw if review.ok else ""}

    def repair_node(state: XianzhiGraphState) -> XianzhiGraphState:
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
        second_chart = getattr(intent, "second_chart", None)
        # 修复后先走 regex 快筛（零 LLM 调用），通过则信任修复，不再全量 LLM 重审
        regex_issues = workflow._reviewer._regex_review(
            repaired,
            state["chart_context"].chart,
            state.get("knowledge", ""),
            workflow.check_facts,
            second_chart.chart if second_chart else None,
            needs_chart,
        )
        if not regex_issues:
            log.info(
                "[Reflextion] {} Worker 修复后 regex 快筛通过 ✓（跳过 LLM 重审）",
                getattr(worker, "label", "?"),
            )
            return {"final_answer": repaired, "issues": []}
        # regex 仍发现问题 → 才触发 LLM 深审
        log.info(
            "[Reflextion] {} Worker 修复后 regex 发现 {} 条问题，触发 LLM 深审",
            getattr(worker, "label", "?"),
            len(regex_issues),
        )
        repaired_review = workflow._reviewer.review(
            repaired,
            state["chart_context"].chart,
            state.get("knowledge", ""),
            workflow.check_facts,
            second_chart.chart if second_chart else None,
            user_prompt=state["user_prompt"],
            ctx=state["chart_context"],
            needs_chart=needs_chart,
        )
        if repaired_review.ok:
            log.info("[Reflextion] {} Worker 修复后通过校验 ✓", getattr(worker, "label", "?"))
            return {"final_answer": repaired, "issues": []}
        # 修复后仍未通过：issues 仅写日志，不再硬拼到用户可见回复中（之前的「口径校验：...」调试信息会泄露给用户，已移除）
        log.warning(
            "[Reflextion] {} Worker 修复后仍未通过 ✗，降级返回 repaired (残留 {} 条 issue 仅记日志)",
            getattr(worker, "label", "?"),
            len(repaired_review.issues),
        )
        for i, issue in enumerate(repaired_review.issues, 1):
            log.warning("[Reflextion]   残留issue[{}]: {}", i, issue)
        return {"final_answer": repaired, "issues": repaired_review.issues}

    def route_after_check(state: XianzhiGraphState) -> str:
        """条件路由：有 issues 走 repair，否则结束。"""
        return "repair" if state.get("issues") else "end"

    graph = StateGraph(XianzhiGraphState)
    graph.add_node("classify", classify_node)
    graph.add_node("chart", chart_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("check", check_node)
    graph.add_node("repair", repair_node)
    graph.set_entry_point("classify")
    graph.add_edge("classify", "chart")
    graph.add_edge("chart", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "check")
    graph.add_conditional_edges("check", route_after_check, {"repair": "repair", "end": END})
    graph.add_edge("repair", END)
    return graph.compile()
