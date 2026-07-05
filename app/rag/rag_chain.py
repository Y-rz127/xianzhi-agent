"""RAG 问答链（带对话记忆，对应 Java 项目的 LoveApp RAG 模式）。

LCEL 链：检索知识 + 历史记忆 + 提示词 + LLM。
历史记忆根据 MEMORY_STORE_TYPE 自动切换 file / postgres。
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.chat_history import InMemoryChatMessageHistory
import uuid
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.config import settings
from app.rag.vector_store import knowledge_base
from app.logger import log


RAG_SYSTEM_PROMPT = """你是先知，一位精通八字命理的预测师。
请结合下方【命理知识库】的内容回答用户问题，确保专业准确。

【命理知识库】
{context}

回答原则：
- 优先依据知识库内容，知识库无相关内容时如实说明
- 表述专业但易懂，必要时举例
- 涉及具体排盘分析时，建议用户先调用排盘工具
- 客观中立，引导理性看待命理"""

RAG_HUMAN_PROMPT = "{question}"


class RagChatChain:
    """带历史记忆的 RAG 对话链。"""

    def __init__(self, chat_model: BaseChatModel):
        self.chat_model = chat_model
        # 内存缓存（file 模式或 PG 不可用时回退）
        self._histories: dict[str, InMemoryChatMessageHistory] = {}
        # PG 历史记忆（postgres 模式时启用）
        self._use_pg = settings.memory_store_type.lower() == "postgres"
        self._pg_conn = None
        if self._use_pg:
            try:
                import psycopg
                from langchain_postgres import PostgresChatMessageHistory
                self._pg_conn = psycopg.connect(settings.postgres_connection_string, autocommit=True)
                self._pg_factory = PostgresChatMessageHistory
                # 首次连接时建表（create_tables 是静态方法）
                try:
                    self._pg_factory.create_tables(self._pg_conn, settings.memory_table_name)
                except Exception as ce:
                    log.warning("RAG 记忆表创建失败（可能已存在）: {}", ce)
                log.info("RAG 历史记忆: PostgreSQL (table={})", settings.memory_table_name)
            except Exception as e:
                log.warning("PostgresChatMessageHistory 不可用，RAG 回退内存: {}", e)
                self._use_pg = False
        self._chain = None
        self._build()

    def _build(self):
        prompt = ChatPromptTemplate.from_messages([
            ("system", RAG_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="history"),
            ("human", RAG_HUMAN_PROMPT),
        ])

        # LCEL 链：检索上下文 + 透传问题 + prompt + model
        chain = (
            {
                "context": lambda x: knowledge_base.search_as_text(x["question"]),
                "question": RunnablePassthrough() | (lambda x: x["question"] if isinstance(x, dict) else x),
                "history": lambda x: x.get("history", []),
            }
            | prompt
            | self.chat_model
        )
        self._chain = chain

    def _load_history(self, session_id: str) -> list[BaseMessage]:
        """加载某会话历史消息（PG 持久化或内存）。"""
        if self._use_pg and self._pg_factory is not None:
            try:
                h = self._pg_factory(
                    settings.memory_table_name,
                    str(uuid.uuid5(uuid.NAMESPACE_DNS, session_id)),
                    sync_connection=self._pg_conn,
                )
                return h.messages
            except Exception as e:
                log.warning("读取PG历史失败，回退内存: {}", e)
        # 内存回退
        if session_id not in self._histories:
            self._histories[session_id] = InMemoryChatMessageHistory()
        return self._histories[session_id].messages

    def _save_history(self, session_id: str, question: str, answer: str):
        """保存一轮对话到记忆（PG 或内存）。"""
        if self._use_pg and self._pg_factory is not None:
            try:
                h = self._pg_factory(
                    settings.memory_table_name,
                    str(uuid.uuid5(uuid.NAMESPACE_DNS, session_id)),
                    sync_connection=self._pg_conn,
                )
                h.add_message(HumanMessage(content=question))
                h.add_message(AIMessage(content=answer))
                return
            except Exception as e:
                log.warning("写入PG历史失败，回退内存: {}", e)
        # 内存回退
        history = self._histories.setdefault(session_id, InMemoryChatMessageHistory())
        history.add_message(HumanMessage(content=question))
        history.add_message(AIMessage(content=answer))

    def chat(self, question: str, session_id: str = "default") -> str:
        """同步问答（带记忆）。"""
        history_msgs = self._load_history(session_id)
        try:
            response = self._chain.invoke(
                {"question": question, "history": history_msgs},
            )
            self._save_history(session_id, question, response.content)
            return response.content
        except Exception as e:
            log.exception("RAG 问答失败")
            return "RAG 问答失败: {}".format(e)

    async def chat_stream(self, question: str, session_id: str = "default"):
        """流式问答（带记忆）。"""
        history_msgs = self._load_history(session_id)
        ctx = knowledge_base.search_as_text(question)
        full = ""
        try:
            async for chunk in self.chat_model.astream(
                [
                    ("system", RAG_SYSTEM_PROMPT.format(context=ctx)),
                    *history_msgs,
                    ("human", question),
                ]
            ):
                if chunk.content:
                    full += chunk.content
                    yield chunk.content
            self._save_history(session_id, question, full)
        except Exception as e:
            log.exception("RAG 流式问答失败")
            yield "\n[RAG 流式问答失败: {}]".format(e)