"""RAG 知识库检索工具，供 Xianzhi 智能体调用。"""
from __future__ import annotations

import re

from langchain_core.tools import tool

from app.rag.vector_store import knowledge_base


# 来源文件名 → 用户可读分类标签
# 避免 LLM 看到"11_婚恋关系规则卡.md"后误写"《婚恋关系规则卡》"
# 真正古籍才标注书名号能引用的书名
_SOURCE_LABEL_MAP = {
    "01_天干地支基础": "基础理论·天干地支",
    "02_五行生克关系": "基础理论·五行生克",
    "03_十神详解": "基础理论·十神",
    "04_用神喜忌": "基础理论·用神喜忌",
    "05_大运流年": "基础理论·大运流年",
    "06_纳音五行": "基础理论·纳音",
    "07_神煞初探": "基础理论·神煞",
    "08_八字排盘基础": "基础理论·排盘",
    "09_玄学史古籍": "古籍·玄学史",
    "10_事业财运规则卡": "断法·事业财运",
    "11_婚恋关系规则卡": "断法·婚恋关系",
    "12_合冲刑害规则卡": "断法·合冲刑害",
    "13_大运流年咨询规则卡": "断法·大运流年咨询",
    "14_格局完整体系": "断法·格局体系",
    "15_六亲完整断法": "断法·六亲",
    "16_健康伤病断法": "断法·健康伤病",
    "17_学业功名断法": "断法·学业功名",
    "18_官非口舌出行": "断法·官非出行",
    "19_性格心性详断": "断法·性格心性",
    "20_子女子嗣断法": "断法·子女子嗣",
    "21_贫富层次判断": "断法·贫富层次",
    "22_男女命差异化论命": "断法·男女命差异",
    "23_流月流日断事细则": "断法·流月流日",
    "24_标准分析流程": "流程·标准分析",
    "25_术语白话对照表": "术语对照表",
    "26_问答模板库": "问答模板",
    "27_命例案例库": "命例库",
    "古籍01_渊海子平核心赋诀": "古籍·《渊海子平》",
    "古籍02_子平真诠全文摘录": "古籍·《子平真诠》",
    "古籍03_穷通宝鉴十天干十二月喜忌": "古籍·《穷通宝鉴》",
    "古籍04_滴天髓注解核心": "古籍·《滴天髓》",
    "古籍05_三命通会精选条文": "古籍·《三命通会》",
    "古籍06_神峰通考精选": "古籍·《神峰通考》",
    "古籍07_盲派实用口诀": "古籍·盲派口诀",
}


def _humanize_source(raw: str) -> str:
    """把文件名（11_婚恋关系规则卡.md）转为可读分类标签，避免 LLM 误引用。

    仅真实古籍可保留书名号；规则卡/断法/流程统一改为"分类·主题"形式。
    """
    if not raw:
        return "未分类"
    stem = re.sub(r"\.(md|txt)$", "", raw).strip()
    label = _SOURCE_LABEL_MAP.get(stem)
    if label:
        return label
    # 未登记的来源降级：去掉序号和扩展名后直接显示
    return re.sub(r"^\d+_", "", stem)


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
    """检索命理知识库（34份典籍与实战文档），获取可直接引用的专业内容。

    知识库内容范围（按场景调用）：
    - 古籍原文：渊海子平、子平真诠、穷通宝鉴、滴天髓、三命通会、神峰通考、盲派口诀
      （适合：需要引用经典论断、查找古籍原句佐证时）
    - 命例案例库：古籍经典命造、8种典型命局结构示范（官印相生/食神生财/伤官见官/三刑入命等）
      （适合：用户命局相似时查相似命例对照分析）
    - 断法体系：格局完整体系、六亲断法、健康伤病、学业功名、官非口舌、性格心性、子女子嗣、贫富层次、男女命差异化论命、流月流日细则
      （适合：具体断事问题，如"看健康""看父母""看子女"）
    - 规则卡：事业财运、婚恋关系、合冲刑害、大运流年咨询标准口径
      （适合：事业/感情/财运/大运等专题咨询）
    - 基础理论：天干地支、五行生克、十神详解、用神喜忌、大运流年、纳音五行、神煞、排盘规则、玄学史古籍
      （适合：术语解释、排盘规则、用神取法等理论问题）
    - 术语白话对照表 + 问答模板库 + 标准分析流程

    常用调用场景：
    - 用户问"什么是七杀/食神/用神"等术语解释时
    - 用户问"用神怎么取""大运顺逆排规则"等理论问题时
    - 分析具体命局时，查相似命例或古籍论断佐证
    - 用户问健康/六亲/官非等断事方向时，查对应断法体系
    - 需要引用古籍原文增强权威性时

    Args:
        query: 检索问题，自然语言即可。
              如"什么是七杀"、"用神怎么取"、"伤官见官怎么断"、"渊海子平论七杀"、"健康断法"

    Returns:
        命理知识库中相关的知识片段，包含来源标注
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
        source = _humanize_source(doc.metadata.get("source", ""))
        parts.append("[片段{}] (检索:{} 来源:{}):\n{}".format(i, expanded, source, doc.page_content))
    return "\n\n".join(parts)


rag_tools = [search_knowledge]
