"""RAG 向量知识库管理。

加载命理知识 markdown，切分、向量化、入库，提供检索能力。
向量库支持：
- chroma  : 本地嵌入式（默认，开箱即用）
- postgres: PostgreSQL + pgvector（生产级，可扩展）
- milvus  : Milvus（参考笔记 07_RAG）

Embedding 默认用阿里云 DashScope text-embedding-v2；
DashScope 不可用（欠费/网络）时按配置回退本地 HuggingFace 模型。

启动加速与成本控制：
- 文档指纹（源文件内容 hash + embedding 模型标识）持久化到本地，
  指纹未变时直接加载已有索引，零 embedding API 调用；
- 检索结果带 TTL 的 LRU 缓存，同一 query 短期内不重复检索。
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.logger import log


KNOWLEDGE_DIR = Path(__file__).parent / "knowledge_docs"
_FINGERPRINT_FILE = "knowledge_fingerprint.json"
_SEARCH_CACHE_MAX = 200


def get_embeddings() -> Embeddings:
    """DashScope 文本嵌入模型（对应笔记 07 的 DashScopeEmbeddings）。"""
    from langchain_community.embeddings import DashScopeEmbeddings
    return DashScopeEmbeddings(
        model=settings.embedding_model,
        max_retries=3,
        dashscope_api_key=settings.dashscope_api_key,
    )


def _get_local_embeddings() -> Embeddings:
    """本地 HuggingFace embedding（DashScope 不可用时的回退）。

    需要额外安装: pip install sentence-transformers
    首次使用会自动下载模型（约 100MB），之后完全离线可用。
    """
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
    except ImportError as e:
        raise RuntimeError(
            "本地 embedding 回退需要安装 sentence-transformers："
            "pip install sentence-transformers"
        ) from e
    return HuggingFaceEmbeddings(model_name=settings.embedding_local_model)


def _select_embeddings() -> tuple[Embeddings, str]:
    """选择可用 embedding，返回 (embeddings, embedding_id)。

    优先 DashScope；实测调用失败且允许回退时切换本地模型。
    embedding_id 参与文档指纹计算，换模型后指纹不匹配会自动重建索引，
    保证查询向量与入库向量来自同一模型。
    """
    dashscope = get_embeddings()
    try:
        dashscope.embed_query("ping")
        return dashscope, "dashscope:{}".format(settings.embedding_model)
    except Exception as e:
        if not settings.embedding_local_fallback:
            raise
        log.warning(
            "DashScope embedding 不可用（{}），回退本地模型 {}",
            e, settings.embedding_local_model,
        )
        local = _get_local_embeddings()
        local.embed_query("ping")  # 触发模型下载/加载，不可用则抛错
        return local, "local:{}".format(settings.embedding_local_model)


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
    """切分文档为片段。

    用 RecursiveCharacterTextSplitter 多级递归切分，针对中文命理文档优化：
    - separators 优先按段落、句号、分号切分，保证语义完整
    - chunk_size 适当放宽到 800，避免长段落（古籍原文、调候表）被强行截断
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=80,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )
    chunks = splitter.split_documents(docs)
    log.info("切分为 {} 个知识片段", len(chunks))
    return chunks


# ============================================================
# 文档指纹：源文件内容 + embedding 模型 + 向量库类型
# 指纹一致说明已有索引可直接复用，无需重新 embedding
# ============================================================

def _docs_hash() -> str:
    """对知识库全部源文件内容计算哈希。"""
    h = hashlib.sha256()
    if KNOWLEDGE_DIR.exists():
        for md in sorted(KNOWLEDGE_DIR.glob("*.md")):
            h.update(md.name.encode("utf-8"))
            h.update(md.read_bytes())
    return h.hexdigest()


def _fingerprint_path() -> Path:
    return settings.vector_db_dir / _FINGERPRINT_FILE


def _load_fingerprint() -> dict | None:
    p = _fingerprint_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_fingerprint(docs_hash: str, embedding_id: str, store_type: str) -> None:
    p = _fingerprint_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "docs_hash": docs_hash,
        "embedding_id": embedding_id,
        "store_type": store_type,
        "updated_at": time.time(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_up_to_date(docs_hash: str, embedding_id: str, store_type: str) -> bool:
    fp = _load_fingerprint()
    if not fp:
        return False
    return (
        fp.get("docs_hash") == docs_hash
        and fp.get("embedding_id") == embedding_id
        and fp.get("store_type") == store_type
    )


# ============================================================
# 向量库构建 / 加载
# ============================================================

def _build_chroma(chunks: list[Document], embeddings: Embeddings):
    """Chroma 本地持久化向量库（全量重建）。"""
    from langchain_chroma import Chroma
    store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name="xianzhi_knowledge",
        persist_directory=str(settings.vector_db_dir),
    )
    log.info("Chroma 向量库重建完成: {}", settings.vector_db_dir)
    return store


def _load_chroma(embeddings: Embeddings):
    """加载已有 Chroma 索引（指纹一致时调用，零 embedding 调用）。"""
    from langchain_chroma import Chroma
    store = Chroma(
        collection_name="xianzhi_knowledge",
        embedding_function=embeddings,
        persist_directory=str(settings.vector_db_dir),
    )
    # 空集合视为无效（例如上次重建被中断），触发重建
    try:
        if store._collection.count() == 0:
            raise RuntimeError("Chroma 集合为空")
    except AttributeError:
        pass  # 老版本无 _collection，跳过空检查
    log.info("Chroma 向量库复用已有索引（文档未变更，跳过 embedding）")
    return store


def _build_postgres(chunks: list[Document], embeddings: Embeddings):
    """PostgreSQL + pgvector 向量库（全量重建）。

    使用 langchain_postgres.PGVector，连接串从 .env 读取。
    pre_delete_collection=True 保证重建时以最新文档覆盖。
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
    log.info("Postgres(pgvector) 向量库重建完成: collection={}", settings.postgres_collection)
    return store


def _load_postgres(embeddings: Embeddings):
    """加载已有 pgvector 索引（指纹一致时调用）。"""
    from langchain_postgres import PGVector
    store = PGVector(
        embeddings=embeddings,
        collection_name=settings.postgres_collection,
        connection=settings.postgres_connection_string,
        use_jsonb=True,
    )
    log.info("Postgres(pgvector) 向量库复用已有索引（文档未变更，跳过 embedding）")
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
    log.info("Milvus 向量库重建完成: {}", settings.milvus_uri)
    return store


def _load_milvus(embeddings: Embeddings):
    """加载已有 Milvus 索引（指纹一致时调用）。"""
    from langchain_milvus import Milvus
    store = Milvus(
        embedding_function=embeddings,
        collection_name="xianzhi_knowledge",
        connection_args={"uri": settings.milvus_uri},
    )
    log.info("Milvus 向量库复用已有索引（文档未变更，跳过 embedding）")
    return store


def _rebuild_store(chunks: list[Document], embeddings: Embeddings, store_type: str):
    """按配置全量重建向量库，返回 (store, 实际生效的 store_type)。

    高优先级向量库不可用时回退 Chroma，指纹记录实际生效类型，
    避免下次启动重复尝试不可用后端。
    """
    # 1. PostgreSQL + pgvector
    if store_type == "postgres":
        try:
            return _build_postgres(chunks, embeddings), "postgres"
        except Exception as e:
            log.warning("Postgres 向量库不可用，回退 Chroma: {}", e)

    # 2. Milvus
    if store_type == "milvus" and settings.milvus_uri:
        try:
            return _build_milvus(chunks, embeddings), "milvus"
        except Exception as e:
            log.warning("Milvus 不可用，回退 Chroma: {}", e)

    # 3. 默认 Chroma
    return _build_chroma(chunks, embeddings), "chroma"


def _build_vector_store(embeddings: Embeddings, embedding_id: str, force: bool = False):
    """构建或加载向量库。

    指纹（文档内容 + embedding 模型 + 向量库类型）一致时直接加载已有索引，
    否则全量重建并更新指纹。
    """
    docs = _load_knowledge_docs()
    if not docs:
        return None
    docs_hash = _docs_hash()
    store_type = settings.vector_store_type.lower()

    # 指纹未变 → 直接加载已有索引，零 embedding API 调用
    if not force and _is_up_to_date(docs_hash, embedding_id, store_type):
        log.info("RAG 文档指纹未变，复用已有向量索引（零 embedding 调用）")
        try:
            if store_type == "postgres":
                return _load_postgres(embeddings)
            if store_type == "milvus" and settings.milvus_uri:
                return _load_milvus(embeddings)
            return _load_chroma(embeddings)
        except Exception as e:
            log.warning("已有索引加载失败，将全量重建: {}", e)

    log.info("RAG 文档指纹变更或首次构建，开始全量重建向量库 (store_type={})", store_type)
    chunks = _split_chunks(docs)
    store, actual_type = _rebuild_store(chunks, embeddings, store_type)
    _save_fingerprint(docs_hash, embedding_id, actual_type)
    return store


class KnowledgeBase:
    """命理知识库单例，封装检索接口（带 TTL 检索缓存）。"""

    def __init__(self):
        self._store = None
        self._retriever = None
        self._ready = False
        self._embedding_id = ""
        self._search_cache: OrderedDict[str, tuple[float, list[Document]]] = OrderedDict()
        self._cache_lock = threading.Lock()

    def init(self, force: bool = False) -> bool:
        """初始化向量库（失败不阻断主流程）。

        内部根据文档指纹（源文件 hash + embedding 模型 + 向量库类型）
        决定复用已有索引还是全量重建。

        Args:
            force: True 时无视指纹强制全量重建（管理接口"重建索引"使用）。
        """
        try:
            embeddings, embedding_id = _select_embeddings()
            self._embedding_id = embedding_id
            self._store = _build_vector_store(embeddings, embedding_id, force=force)
            if self._store is None:
                return False
            self._retriever = self._store.as_retriever(
                search_kwargs={
                    "k": settings.rag_k,
                    "fetch_k": settings.rag_k * 3,
                    "lambda_mult": settings.rag_mmr_lambda,
                },
                search_type="mmr",
            )
            self._ready = True
            # 索引变化后旧缓存失效
            with self._cache_lock:
                self._search_cache.clear()
            log.info("RAG 知识库初始化完成 (store_type={}, embedding={})",
                     settings.vector_store_type, embedding_id)
            return True
        except Exception as e:
            log.warning("RAG 知识库初始化失败: {}", e)
            return False

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def embedding_id(self) -> str:
        return self._embedding_id

    def search(self, query: str) -> list[Document]:
        """相似性检索（MMR，兼顾相关性与多样性）。

        同一 query 在 RAG_SEARCH_CACHE_TTL 秒内直接命中缓存，
        避免多轮对话重复调用 embedding。
        """
        if not self._ready:
            return []
        ttl = settings.rag_search_cache_ttl
        now = time.time()
        if ttl > 0:
            with self._cache_lock:
                hit = self._search_cache.get(query)
                if hit and now - hit[0] < ttl:
                    self._search_cache.move_to_end(query)
                    log.debug("检索缓存命中: {}", query[:30])
                    return hit[1]
        try:
            docs = self._retriever.invoke(query)
        except Exception as e:
            log.warning("RAG 检索失败: {}", e)
            return []
        # 打印每条结果的相似度（Chroma MMR 返回的文档暂无 score 字段，
        # 但可通过 with_distance 模式获取；此处仅记录命中数量和长度）
        if docs:
            total = sum(len(d.page_content) for d in docs)
            log.debug("[RAG] query={} 命中{}条 总{}字", query[:40], len(docs), total)
        if ttl > 0:
            with self._cache_lock:
                self._search_cache[query] = (now, docs)
                while len(self._search_cache) > _SEARCH_CACHE_MAX:
                    self._search_cache.popitem(last=False)
        return docs

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
