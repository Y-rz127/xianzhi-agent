"""知识文档加载与切分：knowledge_docs markdown → 带标题上下文的检索片段。

切分参数与元数据版本纳入文档指纹（见 fingerprint.py），变更后自动重建索引。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logger import log

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge_docs"

# 切分参数纳入文档指纹，变更后自动重建索引，避免新旧 chunk 混用
CHUNK_SIZE = 600
CHUNK_OVERLAP = 120
# 元数据版本：chunk metadata 结构变更时递增，触发向量库重建（如新增 doc_type 字段）
META_VERSION = 2


# 文档类型 → rerank 权重：断法/规则卡优先，模板库降权（密集术语清单易虚高命中）
DOC_TYPE_WEIGHT = {
    "rule": 1.15,  # 断法类（XX断法.md / 规则卡.md），领域知识核心
    "theory": 1.0,  # 基础理论类（01~08 前缀）
    "classic": 1.0,  # 古籍类
    "case": 0.95,  # 命例案例库
    "ref": 0.9,  # 术语白话对照表
    "process": 0.8,  # 标准分析流程
    "template": 0.7,  # 问答模板库（全局前置约束密集术语清单，易虚高命中）
}


def infer_doc_type(source: str) -> str:
    """根据知识库文件名推断文档类型，用于 rerank 加权。"""
    name = source.lower()
    if name.startswith("古籍"):
        return "classic"
    # 断法/规则卡类：文件名含断法关键词，或序号 ≥10 的实战断事文档
    _RULE_KEYWORDS = ("断法", "规则卡", "格局", "官非", "性格", "贫富", "男女命", "流月流日")
    if any(kw in name for kw in _RULE_KEYWORDS):
        return "rule"
    if "模板库" in name:
        return "template"
    if "术语" in name:
        return "ref"
    if "命例" in name or "案例" in name:
        return "case"
    if "流程" in name:
        return "process"
    return "theory"


def load_knowledge_docs() -> list[Document]:
    """加载 knowledge_docs 目录下全部 markdown 文档。"""
    docs: list[Document] = []
    if not KNOWLEDGE_DIR.exists():
        log.warning("知识库目录不存在: {}", KNOWLEDGE_DIR)
        return docs
    for md in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        doc_type = infer_doc_type(md.name)
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "source": md.name,
                    "doc_type": doc_type,
                },
            )
        )
    log.info("加载命理知识文档 {} 篇", len(docs))
    return docs


def split_chunks(docs: list[Document]) -> list[Document]:
    """两阶段切分：先按 markdown 标题（一/二级）切片，再递归字符切分到 ≤600 字。

    阶段一 MarkdownHeaderTextSplitter：只切到二级标题，避免三级碎片过细稀释主题；
    阶段二 RecursiveCharacterTextSplitter：中文分隔符优先
    （段落→换行→句号→分号→逗号→空格→硬切），仅在单个小节内部拼装，跨小节语义不混杂。
    每个 chunk 前置 [文档标题｜一级标题｜二级标题] 上下文，兼容检索的前缀对齐逻辑。
    """
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "一级标题"), ("##", "二级标题")],
        strip_headers=True,
    )
    header_docs: list[Document] = []
    for doc in docs:
        for piece in header_splitter.split_text(doc.page_content):
            merged = {**doc.metadata, **piece.metadata}  # 保留 source/doc_type + 注入标题层级
            header_docs.append(Document(page_content=piece.page_content, metadata=merged))
    header_docs = [d for d in header_docs if d.page_content.strip()]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )
    chunks = splitter.split_documents(header_docs)
    # 注入标题上下文：文档标题置首 + 章节层级（与检索前缀对齐）
    for chunk in chunks:
        md = chunk.metadata
        source = md.get("source", "")
        title = source.replace(".md", "")
        if "_" in title:
            title = title.split("_", 1)[-1]  # 去掉序号前缀，如 "11_婚恋关系规则卡" → "婚恋关系规则卡"
        parts = [title]
        for h in (md.get("一级标题"), md.get("二级标题")):
            if h and h not in parts:  # 去重：文档标题常与 # 一级标题同名
                parts.append(h)
        chunk.page_content = "[" + "｜".join(parts) + "]\n" + chunk.page_content
    log.info("切分为 {} 个知识片段（两阶段：标题切片→递归切分）", len(chunks))
    return chunks


def docs_hash() -> str:
    """对知识库全部源文件内容计算哈希。"""
    h = hashlib.sha256()
    if KNOWLEDGE_DIR.exists():
        for md in sorted(KNOWLEDGE_DIR.glob("*.md")):
            h.update(md.name.encode("utf-8"))
            h.update(md.read_bytes())
    return h.hexdigest()