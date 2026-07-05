"""RetrievalAgent example based on BaseAgent."""

from __future__ import annotations

import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from AI.templates import AgentAction, BaseAgent


class RetrievalAgent(BaseAgent):
    def __init__(self, retriever, **kwargs):
        super().__init__(**kwargs)
        self.retriever = retriever

    def plan(self, user_input: str) -> list[AgentAction]:
        docs = self.retriever(user_input)
        self.remember("last_retrieved_docs", docs)
        return [
            AgentAction("think", f"Retrieved {len(docs)} local documents."),
            AgentAction("respond", "Answer with retrieved snippets."),
        ]

    def compose_answer(self, user_input: str, observations: list[object]) -> str:
        docs = self.recall("last_retrieved_docs", [])
        return "检索到的资料：\n" + "\n".join(f"- {doc}" for doc in docs)


def dummy_retriever(query: str) -> list[str]:
    return [f"Doc snippet matching '{query}' - #{i + 1}" for i in range(3)]


def main() -> None:
    agent = RetrievalAgent(retriever=dummy_retriever, name="RetrievalAgent")
    output = agent.run("查找关于向量检索的最佳实践")
    print(output["answer"])


if __name__ == "__main__":
    main()

