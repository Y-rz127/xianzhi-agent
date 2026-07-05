"""LangGraph store 长期记忆示例。

store 保存跨 thread 的应用数据，适合用户偏好、事实和共享知识。
"""

from __future__ import annotations

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore


class State(TypedDict):
    user_id: str
    preference: str
    answer: str


store = InMemoryStore()


def save_preference(state: State) -> dict[str, str]:
    namespace = ("users", state["user_id"], "preferences")
    store.put(namespace, "language", {"value": state["preference"]})
    return {"answer": "偏好已保存。"}


def load_preference(user_id: str) -> str:
    item = store.get(("users", user_id, "preferences"), "language")
    if item is None:
        return "未设置"
    return item.value["value"]


builder = StateGraph(State)
builder.add_node("save_preference", save_preference)
builder.add_edge(START, "save_preference")
builder.add_edge("save_preference", END)
graph = builder.compile(store=store)


if __name__ == "__main__":
    graph.invoke({"user_id": "u-001", "preference": "中文回答，步骤清晰", "answer": ""})
    print(load_preference("u-001"))

