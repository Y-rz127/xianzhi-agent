"""RAG 向量知识库管理。

加载命理知识 markdown，切分、向量化、入库，提供检索能力。
向量库支持：
- chroma  : 本地嵌入式（默认，开箱即用）
- postgres: PostgreSQL + pgvector（生产级，可扩展）
- milvus  : Milvus（参考笔记 07_RAG）

Embedding 用阿里云 DashScope text-embedding-v2。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import CharacterTextSplitter

from app.config import settings
from app.logger import log


KNOWLEDGE_DIR = Path(__file__).parent / "knowledge_docs"


def get_embeddings() -> Embeddings:
    """DashScope 文本嵌入模型（对应笔记 07 的 DashScopeEmbeddings）。"""
    from langchain_community.embeddings import DashScopeEmbeddings
    return DashScopeEmbeddings(
        model=settings.embedding_model,
        max_retries=3,
        dashscope_api_key=settings.dashscope_api_key,
    )


def _load_knowledge_docs() -> list[Document]:
    """加载 knowledge_docs 目录下全部 markdown 文档。"""
    docs: list[Document] = []
    if not KNOWLEDGE_DIR.exists():
        log.warning("知识库目录不存在: {}", KNOWLEDGE_DIR)
        return docs
    for md in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        docs.append(Document(page_content=text, metadata={"source": md.name}))
    log.info("加载命理知识文档 {} 篇", len(docs))
    return docs


def _split_chunks(docs: list[Document]) -> list[Document]:
    """切分文档为片段。"""
    splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(docs)
    log.info("切分为 {} 个知识片段", len(chunks))
    return chunks


def _build_chroma(chunks: list[Document], embeddings: Embeddings):
    """Chroma 本地持久化向量库。"""
    from langchain_chroma import Chroma
    store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name="xianzhi_knowledge",
        persist_directory=str(settings.vector_db_dir),
    )
    log.info("Chroma 向量库就绪: {}", settings.vector_db_dir)
    return store


def _build_postgres(chunks: list[Document], embeddings: Embeddings):
    """PostgreSQL + pgvector 向量库。

    使用 langchain_postgres.PGVector，连接串从 .env 读取。
    drop_old=True 保证每次启动以最新文档重建（学习项目场景下够用）。
    """
    from langchain_postgres import PGVector
    store = PGVector.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=settings.postgres_collection,
        connection=settings.postgres_connection_string,
        pre_delete_collection=True,
        use_jsonb=True,
    )
    log.info("Postgres(pgvector) 向量库就绪: collection={}", settings.postgres_collection)
    return store


def _build_milvus(chunks: list[Document], embeddings: Embeddings):
    """Milvus 向量库（参考笔记 07_RAG）。"""
    from langchain_milvus import Milvus
    store = Milvus.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name="xianzhi_knowledge",
        connection_args={"uri": settings.milvus_uri},
        drop_old=True,
    )
    log.info("Milvus 向量库就绪: {}", settings.milvus_uri)
    return store


def _build_vector_store(embeddings: Embeddings):
    """根据配置构建向量库。"""
    docs = _load_knowledge_docs()
    if not docs:
        return None
    chunks = _split_chunks(docs)

    store_type = settings.vector_store_type.lower()

    # 1. PostgreSQL + pgvector
    if store_type == "postgres":
        try:
            return _build_postgres(chunks, embeddings)
        except Exception as e:
            log.warning("Postgres 向量库不可用，回退 Chroma: {}", e)

    # 2. Milvus
    if store_type == "milvus" and settings.milvus_uri:
        try:
            return _build_milvus(chunks, embeddings)
        except Exception as e:
            log.warning("Milvus 不可用，回退 Chroma: {}", e)

    # 3. 默认 Chroma
    return _build_chroma(chunks, embeddings)


class KnowledgeBase:
    """命理知识库单例，封装检索接口。"""

    def __init__(self):
        self._store = None
        self._retriever = None
        self._ready = False

    def init(self) -> bool:
        """初始化向量库（应用启动时调用）。失败返回 False。"""
        try:
            embeddings = get_embeddings()
            self._store = _build_vector_store(embeddings)
            if self._store is None:
                return False
            self._retriever = self._store.as_retriever(
                search_kwargs={"k": settings.rag_k},
                search_type="mmr",
            )
            self._ready = True
            log.info("RAG 知识库初始化完成 (store_type={})", settings.vector_store_type)
            return True
        except Exception as e:
            log.warning("RAG 知识库初始化失败: {}", e)
            return False

    @property
    def ready(self) -> bool:
        return self._ready

    def search(self, query: str) -> list[Document]:
        """相似性检索（MMR，兼顾相关性与多样性）。"""
        if not self._ready:
            return []
        try:
            return self._retriever.invoke(query)
        except Exception as e:
            log.warning("RAG 检索失败: {}", e)
            return []

    def search_as_text(self, query: str) -> str:
        """检索并拼接为上下文文本，供 LLM 引用。"""
        docs = self.search(query)
        if not docs:
            return "（未检索到相关知识）"
        parts = []
        for i, d in enumerate(docs, 1):
            parts.append("[片段{}] (来源:{}):\n{}".format(i, d.metadata.get("source", "未知"), d.page_content))
        return "\n\n".join(parts)


# 全局单例
knowledge_base = KnowledgeBase()