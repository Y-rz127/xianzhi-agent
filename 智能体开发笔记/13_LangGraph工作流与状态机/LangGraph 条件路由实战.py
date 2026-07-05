"""LangGraph 条件路由示例。

根据用户问题类型选择不同节点：RAG、工具调用或普通聊天。
"""

from __future__ import annotations

from typing import Literal
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    question: str
    route: str
    answer: str


def router(state: State) -> dict[str, str]:
    question = state["question"]
    if "文档" in question or "知识库" in question:
        return {"route": "rag"}
    if "计算" in question or any(op in question for op in ["+", "-", "*", "/"]):
        return {"route": "tool"}
    return {"route": "chat"}


def choose_next(state: State) -> Literal["rag_answer", "tool_answer", "chat_answer"]:
    return {
        "rag": "rag_answer",
        "tool": "tool_answer",
        "chat": "chat_answer",
    }[state["route"]]


def rag_answer(state: State) -> dict[str, str]:
    return {"answer": f"走 RAG 检索流程回答：{state['question']}"}


def tool_answer(state: State) -> dict[str, str]:
    return {"answer": f"走工具调用流程回答：{state['question']}"}


def chat_answer(state: State) -> dict[str, str]:
    return {"answer": f"走普通聊天流程回答：{state['question']}"}


builder = StateGraph(State)
builder.add_node("router", router)
builder.add_node("rag_answer", rag_answer)
builder.add_node("tool_answer", tool_answer)
builder.add_node("chat_answer", chat_answer)

builder.add_edge(START, "router")
builder.add_conditional_edges("router", choose_next)
builder.add_edge("rag_answer", END)
builder.add_edge("tool_answer", END)
builder.add_edge("chat_answer", END)

graph = builder.compile()


if __name__ == "__main__":
    print(graph.invoke({"question": "请从知识库回答 Milvus 是什么", "route": "", "answer": ""})["answer"])

