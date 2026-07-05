"""Router Agent 路由示例。

用一个轻量路由器把问题分给不同专家函数。真实项目可以把专家函数替换成子 Agent。
"""

from __future__ import annotations


def route(question: str) -> str:
    if "代码" in question or "报错" in question:
        return "coding"
    if "论文" in question or "资料" in question:
        return "research"
    return "general"


def coding_agent(question: str) -> str:
    return f"[Coding Agent] 分析代码问题：{question}"


def research_agent(question: str) -> str:
    return f"[Research Agent] 检索和总结资料：{question}"


def general_agent(question: str) -> str:
    return f"[General Agent] 普通回答：{question}"


AGENTS = {
    "coding": coding_agent,
    "research": research_agent,
    "general": general_agent,
}


def router_agent(question: str) -> str:
    agent_name = route(question)
    return AGENTS[agent_name](question)


if __name__ == "__main__":
    print(router_agent("帮我看一下这段代码为什么报错"))

