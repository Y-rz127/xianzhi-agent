"""高风险工具 Human-in-the-loop 审批示例。

HumanInTheLoopMiddleware 会在敏感工具执行前中断，等待 approve/edit/reject/respond。
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


@tool
def search(query: str) -> str:
    """Search public information."""
    return f"搜索结果：{query}"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email. This is a sensitive operation."""
    return f"邮件已发送给 {to}，标题：{subject}"


agent = create_agent(
    model="openai:gpt-4.1-mini",
    tools=[search, send_email],
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={
                "search": False,
                "send_email": True,
            }
        )
    ],
    checkpointer=InMemorySaver(),
)


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "hitl-email-demo"}}
    first = agent.invoke(
        {"messages": [{"role": "user", "content": "给 team@example.com 发邮件说会议改到三点。"}]},
        config=config,
    )
    print("等待审批：", first)

    resumed = agent.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config=config,
    )
    print(resumed["messages"][-1].content)

