"""ToolAgent example based on BaseAgent."""

from __future__ import annotations

import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from AI.templates import AgentAction, BaseAgent


class ToolAgent(BaseAgent):
    def plan(self, user_input: str) -> list[AgentAction]:
        if "calc" in user_input.lower() or "计算" in user_input:
            return [
                AgentAction("think", "User needs calculation."),
                AgentAction("tool", "Call add tool.", tool_name="add", tool_args=(2, 3)),
                AgentAction("respond", "Return calculation result."),
            ]
        return [AgentAction("respond", "No tool needed.")]


def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def main() -> None:
    agent = ToolAgent(name="ToolAgent")
    agent.add_tool("add", add, description="Add two integers.")
    result = agent.run("请计算 2 和 3 的和 calc")
    print(result["answer"])
    print(result["trace"])


if __name__ == "__main__":
    main()

