"""PII 脱敏 Guardrail 示例。

使用 LangChain 内置 PIIMiddleware 对邮箱、信用卡、API Key 等敏感信息做处理。
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware


agent = create_agent(
    model="openai:gpt-4.1-mini",
    tools=[],
    middleware=[
        PIIMiddleware("email", strategy="redact", apply_to_input=True),
        PIIMiddleware("credit_card", strategy="mask", apply_to_input=True),
        PIIMiddleware(
            "api_key",
            detector=r"sk-[a-zA-Z0-9]{20,}",
            strategy="block",
            apply_to_input=True,
        ),
    ],
)


if __name__ == "__main__":
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "我的邮箱是 test@example.com，卡号是 5105-1051-0510-5100。",
                }
            ]
        }
    )
    print(result["messages"][-1].content)

