"""Agent 集成测试示例。

使用 FakeListChatModel 避免真实模型调用，让测试稳定、便宜、可重复。
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.language_models.chat_models import BaseChatModel


@tool
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"{city} 晴，25 摄氏度"


class FixedChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fixed-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        message = AIMessage(content="北京晴，25 摄氏度")
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_agent_returns_fixed_answer() -> None:
    agent = create_agent(model=FixedChatModel(), tools=[get_weather])
    result = agent.invoke({"messages": [{"role": "user", "content": "北京天气？"}]})
    assert "北京" in result["messages"][-1].content

