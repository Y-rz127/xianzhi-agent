"""LangGraph 最小状态机示例。

LangGraph 的核心是 StateGraph：节点读取 state，返回要合并进 state 的增量。
"""

from __future__ import annotations

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    topic: str
    outline: str


def make_outline(state: State) -> dict[str, str]:
    topic = state["topic"]
    return {"outline": f"1. 什么是{topic}\n2. 核心概念\n3. 最小实战"}


builder = StateGraph(State)
builder.add_node("make_outline", make_outline)
builder.add_edge(START, "make_outline")
builder.add_edge("make_outline", END)

graph = builder.compile()


if __name__ == "__main__":
    result = graph.invoke({"topic": "LangGraph", "outline": ""})
    print(result["outline"])

