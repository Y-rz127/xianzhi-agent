"""AI 恋爱大师应用（分支功能，对应 Java LoveApp）。"""
from __future__ import annotations
from typing import AsyncIterator
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from app.memory.chat_memory import FileBasedChatMemory
from app.logger import log

SYSTEM_PROMPT = """你是"恋爱大师"，一位有十几年心理咨询和情感辅导经验的老师，性格像一位见多识广、热心肠的知心姐姐/哥哥。

身份与能力：
- 精通恋爱心理、亲密关系、婚姻家庭、情感修复
- 见过形形色色的感情故事，不评判、不道德绑架
- 能从对方的言行细节里读懂潜台词

说话风格（重要）：
- 像真人聊天，不要用表格、不要分太多层级标题、不要用 emoji 结尾
- 先一句话直接给判断或共情，再讲2-3个关键点，最后给一条实在的建议
- 长度控制：简单问题3-5句话，复杂问题最多2-3段，绝不长篇大论
- 该幽默时幽默（比如调侃直男直女的迷惑操作），该严肃时严肃（比如家暴、出轨、精神控制）
- 有亲和力，像朋友在跟你聊，而不是机器人在输出报告
- 用"你"而不是"您"，自然口语化，可以适当用语气词
- 不确定的事直说"这个要看具体情况"，不装懂、不绝对化
- 避免AI味重的表达：不要"总结一下""需要注意的是""好消息/需要注意"这种模板腔
- 不要一上来就问一堆问题，先回应对方情绪，再顺其自然地问1-2个关键信息

回答原则：
- 客观中立，不站队、不拉偏架
- 引导用户理性看待感情问题，但不冷冰冰
- 涉及安全风险（家暴、自伤、被跟踪等）时，明确提醒寻求专业帮助
- 不替用户做决定，帮用户看清局面，让用户自己选
"""


class LoveApp:
    def __init__(self, chat_model, memory):
        self.chat_model = chat_model
        self.memory = memory

    def _load_history(self, chat_id: str) -> list[BaseMessage]:
        """滑动窗口记忆：按 token 预算逆序截取最近的消息。

        - 中文 1 字 ≈ 1.5 token，英文 1 字符 ≈ 0.25 token
        - 预算 3000 token（比先知 2000 大一档，情感对话更依赖上下文情绪连贯）
        """
        history = self.memory.get(chat_id)
        if not history:
            return []
        max_tokens = 3000
        total_tokens = 0
        selected = []
        for msg in reversed(history):
            content = msg.content if hasattr(msg, "content") else str(msg)
            cn_chars = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
            en_chars = len(content) - cn_chars
            token_count = int(cn_chars * 1.5 + en_chars * 0.25)
            if total_tokens + token_count <= max_tokens:
                selected.append(msg)
                total_tokens += token_count
            else:
                break
        return list(reversed(selected))

    def chat(self, message, chat_id="default"):
        history = self._load_history(chat_id)
        msgs = [SystemMessage(content=SYSTEM_PROMPT)] + history + [HumanMessage(content=message)]
        resp = self.chat_model.invoke(msgs)
        self.memory.add(chat_id, [HumanMessage(content=message), resp])
        return resp.content

    async def chat_stream(self, message, chat_id="default"):
        history = self._load_history(chat_id)
        msgs = [SystemMessage(content=SYSTEM_PROMPT)] + history + [HumanMessage(content=message)]
        collected = []
        async for chunk in self.chat_model.astream(msgs):
            text = chunk.content
            if text:
                collected.append(text)
                yield text
        full = "".join(collected)
        self.memory.add(chat_id, [HumanMessage(content=message), AIMessage(content=full)])
