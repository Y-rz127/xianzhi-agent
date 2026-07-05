"""Runnable BaseAgent demo.

Run from `PythonProject`:

    python -m AI.examples.base_agent_demo

Or run this file directly:

    python AI/examples/base_agent_demo.py
"""

from __future__ import annotations

import os
import re
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from AI.templates import AgentAction, BaseAgent, ToolSpec


def calculator(expression: str) -> str:
    """Calculate a safe arithmetic expression."""
    if not re.fullmatch(r"[0-9+\-*/().\s]+", expression):
        raise ValueError("Only arithmetic characters are allowed.")
    return str(eval(expression, {"__builtins__": {}}, {}))


def knowledge_search(query: str) -> list[str]:
    """Search a tiny local knowledge base."""
    docs = {
        "agent": "Agent = model + tools + memory + planning loop.",
        "rag": "RAG = retrieval augmented generation, useful for document QA.",
        "tool": "Tool should have a clear name, schema, description and error policy.",
    }
    query_lower = query.lower()
    return [text for key, text in docs.items() if key in query_lower] or ["No local document matched."]


class LearningAgent(BaseAgent):
    """A simple rule-based agent built on BaseAgent."""

    def plan(self, user_input: str) -> list[AgentAction]:
        actions = [
            AgentAction("think", "Classify intent and decide whether tools are needed."),
            AgentAction("remember", user_input, memory_key="last_user_input"),
        ]

        expression = self._extract_expression(user_input)
        if expression:
            actions.append(
                AgentAction(
                    "tool",
                    "Calculate arithmetic expression.",
                    tool_name="calculator",
                    tool_args=(expression,),
                )
            )

        if any(keyword in user_input.lower() for keyword in ["agent", "rag", "tool"]):
            actions.append(
                AgentAction(
                    "tool",
                    "Search local knowledge snippets.",
                    tool_name="knowledge_search",
                    tool_args=(user_input,),
                )
            )

        actions.append(AgentAction("respond", "Summarize observations and answer user."))
        return actions

    def compose_answer(self, user_input: str, observations: list[object]) -> str:
        if not observations:
            return "我已经记录了你的问题，但当前没有需要调用工具的步骤。"

        lines = ["BaseAgent 示例执行完成："]
        for index, item in enumerate(observations, start=1):
            lines.append(f"{index}. {item}")
        lines.append(f"已写入记忆 last_user_input = {self.recall('last_user_input')}")
        return "\n".join(lines)

    @staticmethod
    def _extract_expression(text: str) -> str | None:
        match = re.search(r"计算[:：]?\s*([0-9+\-*/().\s]+)", text)
        if match:
            return match.group(1).strip()
        return None


def build_agent() -> LearningAgent:
    return LearningAgent(
        name="LearningAgent",
        description="A rule-based learning agent powered by BaseAgent.",
        tools=[
            ToolSpec("calculator", "Calculate arithmetic expressions.", calculator),
            ToolSpec("knowledge_search", "Search local Agent learning notes.", knowledge_search),
        ],
    )


def main() -> None:
    agent = build_agent()
    result = agent.run("请介绍 Agent 和 tool，并计算: 12 * (3 + 4)")

    print(result["answer"])
    print("\n执行轨迹：")
    for step in result["trace"]:
        print(step)


if __name__ == "__main__":
    main()

