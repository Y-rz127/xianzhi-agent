"""Optional LangGraph wrapper for Xianzhi workflow.

The app can run without langgraph installed. When available, this module builds
a StateGraph that mirrors the deterministic workflow nodes.
"""
from __future__ import annotations

from typing import Any, TypedDict

from app.agent.xianzhi_workflow import QuestionIntent, WorkflowChartContext, classify_question


class XianzhiGraphState(TypedDict, total=False):
    user_prompt: str
    chart_context: WorkflowChartContext
    history: list[Any]
    intent: QuestionIntent
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
        return {"intent": classify_question(state["user_prompt"])}

    def chart_node(state: XianzhiGraphState) -> XianzhiGraphState:
        ctx = workflow._extend_chart_if_needed(state["chart_context"], state["intent"])
        return {"chart_context": ctx}

    def retrieve_node(state: XianzhiGraphState) -> XianzhiGraphState:
        return {"knowledge": workflow._retrieve_rules(state["intent"], state["chart_context"])}

    def generate_node(state: XianzhiGraphState) -> XianzhiGraphState:
        messages = workflow._build_messages(
            state["user_prompt"],
            state["intent"],
            state["chart_context"],
            state.get("knowledge", ""),
            state.get("history", []),
        )
        return {"raw_answer": workflow._invoke(messages)}

    def check_node(state: XianzhiGraphState) -> XianzhiGraphState:
        checked = workflow.check_facts(state.get("raw_answer", ""), state["chart_context"].chart)
        return {"issues": checked.issues, "final_answer": state.get("raw_answer", "") if checked.ok else ""}

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
        )
        repaired = workflow._invoke(messages)
        repaired_check = workflow.check_facts(repaired, state["chart_context"].chart)
        if repaired_check.ok:
            return {"final_answer": repaired, "issues": []}
        return {"final_answer": repaired.rstrip() + "\n\n口径校验：" + "；".join(repaired_check.issues), "issues": repaired_check.issues}

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

