"""LangChain create_agent 新版 Agent 示例。

当前 LangChain 推荐用 create_agent 作为标准 Agent 入口：
- model: 模型标识或模型实例
- tools: Python 函数、LangChain Tool 或工具字典
- system_prompt: 系统提示词
- response_format: 可选，要求 Agent 返回结构化结果
- checkpointer: 可选，按 thread_id 保存会话状态
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver


class AgentAnswer(BaseModel):
    summary: str = Field(description="最终回答摘要")
    confidence: float = Field(ge=0, le=1, description="回答置信度")


@tool
def calculator(expression: str) -> str:
    """Calculate a simple arithmetic expression, such as '12 * 8 + 3'."""
    allowed = set("0123456789+-*/(). ")
    if any(ch not in allowed for ch in expression):
        return "只允许基础四则运算表达式。"
    return str(eval(expression, {"__builtins__": {}}, {}))


agent = create_agent(
    model="openai:gpt-4.1-mini",
    tools=[calculator],
    system_prompt="你是一个严谨的学习助手。需要计算时先调用 calculator 工具。",
    response_format=AgentAnswer,
    checkpointer=InMemorySaver(),
)


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "demo-thread-001"}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "帮我计算 12 * 8 + 3，并解释结果。"}]},
        config=config,
    )
    print(result["structured_response"])

