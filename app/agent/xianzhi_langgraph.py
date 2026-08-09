"""可选的LangGraph封装，用于Xianzhi工作流。

该应用无需安装langgraph即可运行。如果可用，此模块会构建一个StateGraph，以反映确定性的工作流节点。
本模块接入多 Agent 协作架构：节点从 state 取 worker 配置，与 XianzhiWorkflow.answer() 新架构保持一致。
"""
from __future__ import annotations

from typing import Any, TypedDict

from app.agent.xianzhi_workflow import DomainWorker, WORKERS, QuestionIntent, WorkflowChartContext, classify_question
from app.logger import log


class XianzhiGraphState(TypedDict, total=False):
    """LangGraph 工作流状态字典：各节点在 state 上读写，贯穿分类→扩盘→检索→生成→校验→修复。"""
    user_prompt: str
    chart_context: WorkflowChartContext
    history: list[Any]
    intent: QuestionIntent
    worker: DomainWorker
    knowledge: str
    raw_answer: str
    final_answer: str
    issues: list[str]


def create_xianzhi_graph(workflow):
    """Create a compiled LangGraph app if langgraph is installed."""
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return None

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
        if intent and getattr(intent, "domain", "") == "chitchat":
            log.info("[RAG] 闲聊意图，跳过知识检索")
            return {"knowledge": "（闲聊场景，无需命理知识检索）"}
        knowledge = workflow._retrieve_rules(state["intent"], state["chart_context"], state.get("worker"), state["user_prompt"])
        log.info("[RAG] 检索完成，知识片段 {}字", len(knowledge))
        return {"knowledge": knowledge}

    def generate_node(state: XianzhiGraphState) -> XianzhiGraphState:
        """生成节点：组装 Worker 消息并调用 LLM 产出原始回答。"""
        worker = state.get("worker")
        messages = workflow._build_messages(
            state["user_prompt"],
            state["intent"],
            state["chart_context"],
            state.get("knowledge", ""),
            state.get("history", []),
            state.get("worker"),
        )
        raw = workflow._invoke(messages)
        log.info("[Worker] {} 生成回答 {}字", getattr(worker, "label", "?"), len(raw))
        return {"raw_answer": raw}

    def check_node(state: XianzhiGraphState) -> XianzhiGraphState:
        """校验节点：两层审核（正则快筛 + LLM 深审），通过则定稿，否则记录 issues。

        闲聊/题外话（intent.domain=chitchat）跳过 LLM 深审，仅依赖正则快筛，节省 1 次 LLM 调用。
        """
        raw = state.get("raw_answer", "")
        worker = state.get("worker")
        intent = state.get("intent")
        is_chitchat = bool(intent and getattr(intent, "domain", "") == "chitchat")
        log.info("[Reviewer] 开始审核 {} Worker 产出 ({}字){}...",
                 getattr(worker, "label", "?"), len(raw),
                 " [闲聊短路: 跳过LLM深审]" if is_chitchat else "")
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
        )
        if review.ok:
            log.info("[Reviewer] {} Worker 产出通过审核 ✓ (source={})", getattr(worker, "label", "?"), review.source)
        else:
            log.warning("[Reviewer] {} Worker 产出未通过审核 ✗ (source={})", getattr(worker, "label", "?"), review.source)
            for i, issue in enumerate(review.issues, 1):
                log.warning("[Reviewer]   issue[{}]: {}", i, issue)
        return {"issues": review.issues, "final_answer": raw if review.ok else ""}

    def repair_node(state: XianzhiGraphState) -> XianzhiGraphState:
        """修复节点：基于 issues 重构消息让 LLM 反思修复，并二次校验；仍不过则附口径说明。

        闲聊场景无 issues 可修（check_node 已跳过 LLM 深审），无意义再走 repair。
        """
        from app.agent.xianzhi_workflow import FactCheckResult

        intent = state.get("intent")
        is_chitchat = bool(intent and getattr(intent, "domain", "") == "chitchat")
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
        log.info("[Reflextion] {} Worker 修复完成 ({}字)，二次审核中...",
                 getattr(worker, "label", "?"), len(repaired))
        second_chart = getattr(state.get("intent"), "second_chart", None)
        repaired_review = workflow._reviewer.review(
            repaired,
            state["chart_context"].chart,
            state.get("knowledge", ""),
            workflow.check_facts,
            second_chart.chart if second_chart else None,
            user_prompt=state["user_prompt"],
            ctx=state["chart_context"],
        )
        if repaired_review.ok:
            log.info("[Reflextion] {} Worker 修复后通过校验 ✓", getattr(worker, "label", "?"))
            return {"final_answer": repaired, "issues": []}
        # 修复后仍未通过：issues 仅写日志，不再硬拼到用户可见回复中（之前的「口径校验：...」调试信息会泄露给用户，已移除）
        log.warning("[Reflextion] {} Worker 修复后仍未通过 ✗，降级返回 repaired (残留 {} 条 issue 仅记日志)",
                    getattr(worker, "label", "?"), len(repaired_review.issues))
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

