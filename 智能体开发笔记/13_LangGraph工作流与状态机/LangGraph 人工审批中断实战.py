"""LangGraph 人工审批中断示例。

当工作流遇到高风险动作时，用 interrupt 暂停，等待人类通过 Command(resume=...)
继续执行。
"""

from __future__ import annotations

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class State(TypedDict):
    action: str
    approved: bool
    result: str


def approval_gate(state: State) -> dict[str, bool]:
    decision = interrupt(
        {
            "reason": "高风险操作需要人工审批",
            "action": state["action"],
            "options": ["approve", "reject"],
        }
    )
    return {"approved": decision == "approve"}


def execute_action(state: State) -> dict[str, str]:
    if not state["approved"]:
        return {"result": f"已拒绝执行：{state['action']}"}
    return {"result": f"已执行：{state['action']}"}


builder = StateGraph(State)
builder.add_node("approval_gate", approval_gate)
builder.add_node("execute_action", execute_action)
builder.add_edge(START, "approval_gate")
builder.add_edge("approval_gate", "execute_action")
builder.add_edge("execute_action", END)

graph = builder.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "approval-demo-001"}}
    paused = graph.invoke(
        {"action": "删除生产数据库中的测试表", "approved": False, "result": ""},
        config=config,
    )
    print("paused:", paused)

    resumed = graph.invoke(Command(resume="approve"), config=config)
    print("resumed:", resumed["result"])

