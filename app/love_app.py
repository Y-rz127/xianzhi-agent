"""AI 恋爱大师应用（分支功能，对应 Java LoveApp）。"""
from __future__ import annotations
from typing import AsyncIterator
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from app.memory.chat_memory import FileBasedChatMemory

SYSTEM_PROMPT = "扮演深耕恋爱心理领域的专家。开场向用户表明身份，告知用户可倾诉恋爱难题。围绕单身、恋爱、已婚三种状态提问。引导用户详述事情经过、对方反应及自身想法，以便给出专属解决方案。"


class LoveApp:
    def __init__(self, chat_model, memory):
        self.chat_model = chat_model
        self.memory = memory

    def chat(self, message, chat_id="default"):
        history = self.memory.get(chat_id)
        msgs = [SystemMessage(content=SYSTEM_PROMPT)] + history + [HumanMessage(content=message)]
        resp = self.chat_model.invoke(msgs)
        self.memory.add(chat_id, [HumanMessage(content=message), resp])
        return resp.content

    async def chat_stream(self, message, chat_id="default"):
        history = self.memory.get(chat_id)
        msgs = [SystemMessage(content=SYSTEM_PROMPT)] + history + [HumanMessage(content=message)]
        collected = []
        async for chunk in self.chat_model.astream(msgs):
            text = chunk.content
            if text:
                collected.append(text)
                yield text
        full = "".join(collected)
        self.memory.add(chat_id, [HumanMessage(content=message), AIMessage(content=full)])
