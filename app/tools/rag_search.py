"""RAG 知识库检索工具，供 Xianzhi 智能体调用。"""
from __future__ import annotations

from langchain_core.tools import tool

from app.rag.vector_store import knowledge_base


QUERY_EXPANSIONS = {
    "career": {
        "keywords": ("事业", "工作", "职业", "跳槽", "升职", "创业", "岗位"),
        "queries": ("事业 官杀 印星 食伤 大运", "工作变动 流年 大运 合冲"),
    },
    "wealth": {
        "keywords": ("财运", "赚钱", "收入", "投资", "生意", "破财"),
        "queries": ("财星 食伤生财 大运流年", "正财 偏财 投资 破财"),
    },
    "love": {
        "keywords": ("感情", "恋爱", "桃花", "复合", "对象", "脱单"),
        "queries": ("桃花 配偶星 感情 流年", "日支 夫妻宫 合冲刑害"),
    },
    "marriage": {
        "keywords": ("婚姻", "结婚", "离婚", "配偶", "合婚"),
        "queries": ("婚姻 配偶宫 夫妻星", "结婚年份 大运流年 合冲"),
    },
    "liunian": {
        "keywords": ("大运", "流年", "今年", "明年", "年份", "运势"),
        "queries": ("大运流年 作用关系", "流年与原局 立春 分界"),
    },
    "yongshen": {
        "keywords": ("用神", "喜忌", "强弱", "格局", "五行"),
        "queries": ("用神 喜忌 日主强弱", "五行 生克 制化 调候"),
    },
}


def expand_knowledge_queries(query: str) -> list[str]:
    """Expand a user query into a small set of domain-aware retrieval queries."""
    text = query or ""
    queries = [text.strip()] if text.strip() else []
    for item in QUERY_EXPANSIONS.values():
        if any(keyword in text for keyword in item["keywords"]):
            queries.extend(item["queries"])
    if not queries:
        queries.append("八字 命理 基础 大运 流年 用神")
    deduped: list[str] = []
    for q in queries:
        if q and q not in deduped:
            deduped.append(q)
    return deduped[:4]


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
    docs = []
    seen = set()
    for expanded in expand_knowledge_queries(query):
        for doc in knowledge_base.search(expanded):
            key = (doc.metadata.get("source", ""), doc.page_content[:120])
            if key in seen:
                continue
            seen.add(key)
            docs.append((expanded, doc))
            if len(docs) >= 6:
                break
        if len(docs) >= 6:
            break
    if not docs:
        return "（未检索到相关知识）"
    parts = []
    for i, (expanded, doc) in enumerate(docs, 1):
        source = doc.metadata.get("source", "未知")
        parts.append("[片段{}] (检索:{} 来源:{}):\n{}".format(i, expanded, source, doc.page_content))
    return "\n\n".join(parts)


rag_tools = [search_knowledge]
