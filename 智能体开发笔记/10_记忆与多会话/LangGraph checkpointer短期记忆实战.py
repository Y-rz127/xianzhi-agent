"""LangGraph checkpointer 短期记忆示例。

checkpointer 按 thread_id 保存图状态，适合会话连续性、人工中断恢复和 time travel。
"""

from __future__ import annotations

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver


agent = create_agent(
    model="openai:gpt-4.1-mini",
    tools=[],
    system_prompt="你是一个简洁的中文助手。",
    checkpointer=InMemorySaver(),
)


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "short-memory-demo"}}

    agent.invoke(
        {"messages": [{"role": "user", "content": "我叫小李，正在学习 Agent。"}]},
        config=config,
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "我刚才说我叫什么？"}]},
        config=config,
    )

    print(result["messages"][-1].content)

