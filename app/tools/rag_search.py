"""RAG 知识库检索工具，供 Xianzhi 智能体调用。"""
from __future__ import annotations

from langchain_core.tools import tool

from app.rag.vector_store import knowledge_base


@tool
def search_knowledge(query: str) -> str:
    """检索命理知识库，获取天干地支、五行、十神、用神、大运流年等专业知识。

    当需要查阅命理理论、术语解释、排盘规则等专业内容时调用此工具。

    Args:
        query: 检索问题，如"什么是七杀"、"用神怎么取"、"大运顺逆排规则"

    Returns:
        命理知识库中相关的知识片段
    """
    if not knowledge_base.ready:
        return "知识库未就绪"
    return knowledge_base.search_as_text(query)


rag_tools = [search_knowledge]