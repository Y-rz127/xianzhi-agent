"""A small, dependency-free BaseAgent template for learning.

This module is intentionally not tied to LangChain or any model provider. It
shows the core shape of an agent:

1. receive user input
2. plan actions
3. call tools when needed
4. keep memory
5. return a final answer with an execution trace

When this structure is clear, replacing `plan()` or `compose_answer()` with an
LLM call becomes straightforward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


ActionType = Literal["think", "tool", "remember", "respond"]


@dataclass(frozen=True)
class AgentAction:
    """One planned action produced by an agent."""

    type: ActionType
    content: str
    tool_name: str | None = None
    tool_args: tuple[Any, ...] = field(default_factory=tuple)
    tool_kwargs: dict[str, Any] = field(default_factory=dict)
    memory_key: str | None = None


@dataclass
class AgentStep:
    """One executed step in the agent trace."""

    action_type: str
    content: str
    result: Any = None
    error: str | None = None


@dataclass
class ToolSpec:
    """Metadata and callable for a tool."""

    name: str
    description: str
    handler: Callable[..., Any]
    return_direct: bool = False


class AgentMemory:
    """Simple in-memory store for key-value data and chat messages."""

    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}
        self.messages: list[dict[str, str]] = []

    def remember(self, key: str, value: Any) -> None:
        self.kv[key] = value

    def recall(self, key: str, default: Any = None) -> Any:
        return self.kv.get(key, default)

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def recent_messages(self, limit: int = 6) -> list[dict[str, str]]:
        return self.messages[-limit:]


class BaseAgent:
    """Reusable base class for simple agents.

    Subclasses usually override `plan()` and optionally `compose_answer()`.
    """

    def __init__(
        self,
        name: str = "BaseAgent",
        description: str = "A minimal learning agent.",
        tools: list[ToolSpec] | None = None,
        memory: AgentMemory | None = None,
        max_steps: int = 8,
    ) -> None:
        self.name = name
        self.description = description
        self.memory = memory or AgentMemory()
        self.max_steps = max_steps
        self.tools: dict[str, ToolSpec] = {}
        self.trace: list[AgentStep] = []

        for tool in tools or []:
            self.register_tool(tool)

    def register_tool(self, tool: ToolSpec) -> None:
        if not tool.name:
            raise ValueError("Tool name cannot be empty.")
        self.tools[tool.name] = tool

    def add_tool(
        self,
        name: str,
        func: Callable[..., Any],
        description: str = "",
        return_direct: bool = False,
    ) -> None:
        self.register_tool(
            ToolSpec(
                name=name,
                description=description or func.__doc__ or "No description.",
                handler=func,
                return_direct=return_direct,
            )
        )

    def call_tool(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in self.tools:
            raise KeyError(f"Tool '{name}' not found.")
        return self.tools[name].handler(*args, **kwargs)

    def remember(self, key: str, value: Any) -> None:
        self.memory.remember(key, value)

    def recall(self, key: str, default: Any = None) -> Any:
        return self.memory.recall(key, default)

    def plan(self, user_input: str) -> list[AgentAction]:
        """Build an action plan.

        The base implementation only thinks and responds. A real agent can
        override this method with rule logic, an LLM planner, or LangGraph.
        """
        return [
            AgentAction(type="think", content=f"Analyze request: {user_input}"),
            AgentAction(type="respond", content=user_input),
        ]

    def compose_answer(self, user_input: str, observations: list[Any]) -> str:
        if not observations:
            return f"{self.name}: {user_input}"
        joined = "\n".join(str(item) for item in observations)
        return f"{self.name} completed the task.\n\nObservations:\n{joined}"

    def run(self, user_input: str) -> dict[str, Any]:
        """Run one agent turn and return answer plus trace."""
        self.trace = []
        observations: list[Any] = []
        final_answer: str | None = None

        self.memory.add_message("user", user_input)
        actions = self.plan(user_input)

        for index, action in enumerate(actions, start=1):
            if index > self.max_steps:
                self.trace.append(
                    AgentStep(
                        action_type="error",
                        content="Max steps exceeded.",
                        error=f"max_steps={self.max_steps}",
                    )
                )
                break

            if action.type == "think":
                self.trace.append(AgentStep("think", action.content))
                continue

            if action.type == "remember":
                if action.memory_key is None:
                    self.trace.append(
                        AgentStep("remember", action.content, error="memory_key is required")
                    )
                    continue
                self.remember(action.memory_key, action.content)
                self.trace.append(AgentStep("remember", action.content, result=action.memory_key))
                continue

            if action.type == "tool":
                if action.tool_name is None:
                    self.trace.append(
                        AgentStep("tool", action.content, error="tool_name is required")
                    )
                    continue
                try:
                    result = self.call_tool(
                        action.tool_name,
                        *action.tool_args,
                        **action.tool_kwargs,
                    )
                    observations.append(result)
                    self.trace.append(AgentStep("tool", action.content, result=result))
                    if self.tools[action.tool_name].return_direct:
                        final_answer = str(result)
                        break
                except Exception as exc:  # Keep demo agent resilient.
                    error = f"{type(exc).__name__}: {exc}"
                    self.trace.append(AgentStep("tool", action.content, error=error))
                continue

            if action.type == "respond":
                final_answer = self.compose_answer(user_input, observations)
                self.trace.append(AgentStep("respond", action.content, result=final_answer))
                break

        if final_answer is None:
            final_answer = self.compose_answer(user_input, observations)

        self.memory.add_message("assistant", final_answer)
        return {
            "agent": self.name,
            "input": user_input,
            "answer": final_answer,
            "observations": observations,
            "trace": [step.__dict__ for step in self.trace],
            "memory": {
                "kv": dict(self.memory.kv),
                "recent_messages": self.memory.recent_messages(),
            },
        }

