"""可选的LangGraph封装，用于Xianzhi工作流。

该应用无需安装langgraph即可运行。如果可用，此模块会构建一个StateGraph，以反映确定性的工作流节点。
本模块接入多 Agent 协作架构：节点从 state 取 worker 配置，与 XianzhiWorkflow.answer() 新架构保持一致。
"""
from __future__ import annotations

from typing import Any, TypedDict

from app.agent.xianzhi_workflow import DomainWorker, WORKERS, QuestionIntent, WorkflowChartContext, classify_question


class XianzhiGraphState(TypedDict, total=False):
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
        intent = classify_question(state["user_prompt"])
        worker = WORKERS.get(intent.domain, WORKERS["general"])
        return {"intent": intent, "worker": worker}

    def chart_node(state: XianzhiGraphState) -> XianzhiGraphState:
        ctx = workflow._extend_chart_if_needed(state["chart_context"], state["intent"])
        return {"chart_context": ctx}

    def retrieve_node(state: XianzhiGraphState) -> XianzhiGraphState:
        return {"knowledge": workflow._retrieve_rules(state["intent"], state["chart_context"], state.get("worker"))}

    def generate_node(state: XianzhiGraphState) -> XianzhiGraphState:
        messages = workflow._build_messages(
            state["user_prompt"],
            state["intent"],
            state["chart_context"],
            state.get("knowledge", ""),
            state.get("history", []),
            state.get("worker"),
        )
        return {"raw_answer": workflow._invoke(messages)}

    def check_node(state: XianzhiGraphState) -> XianzhiGraphState:
        # 新架构：用 ReviewerWorker 做三重校验（事实+古籍真实性+合规），替代旧的 check_facts
        review = workflow._reviewer.review(
            state.get("raw_answer", ""),
            state["chart_context"].chart,
            state.get("knowledge", ""),
            workflow.check_facts,
        )
        return {"issues": review.issues, "final_answer": state.get("raw_answer", "") if review.ok else ""}

    def repair_node(state: XianzhiGraphState) -> XianzhiGraphState:
        from app.agent.xianzhi_workflow import FactCheckResult

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
        repaired_review = workflow._reviewer.review(
            repaired,
            state["chart_context"].chart,
            state.get("knowledge", ""),
            workflow.check_facts,
        )
        if repaired_review.ok:
            return {"final_answer": repaired, "issues": []}
        return {"final_answer": repaired.rstrip() + "\n\n口径校验：" + "；".join(repaired_review.issues), "issues": repaired_review.issues}

    def route_after_check(state: XianzhiGraphState) -> str:
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

