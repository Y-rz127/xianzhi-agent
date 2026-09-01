"""向量库管理：构建/加载知识索引并提供检索接口（含 TTL 缓存与 rerank）。

- chroma：本地嵌入式（兜底使用，开箱即用）
- postgres：PostgreSQL + pgvector（默认）

嵌入模型、文档切分、指纹持久化分别在 embeddings.py / knowledge.py / fingerprint.py，
本模块只负责"索引的生命周期与检索外观"。
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.core.logger import log
from app.rag.embeddings import _select_embeddings
from app.rag.fingerprint import is_up_to_date, load as _load_fingerprint, save as _save_fingerprint
from app.rag.knowledge import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DOC_TYPE_WEIGHT,
    META_VERSION,
    docs_hash,
    load_knowledge_docs,
    split_chunks,
)
from app.rag.relevance import keyword_overlap

_SEARCH_CACHE_MAX = 200


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

    pre_delete_collection=True 保证重建时以最新文档覆盖。
    """
    from langchain_postgres import PGVector

    store = PGVector.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=settings.postgres_collection,
        connection=settings.pg_dsn(),
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
        connection=settings.pg_dsn(),
        use_jsonb=True,
    )
    log.info("Postgres(pgvector) 向量库复用已有索引（文档未变更，跳过 embedding）")
    return store


def _rebuild_store(chunks: list[Document], embeddings: Embeddings, store_type: str):
    """按配置全量重建向量库，返回 (store, 实际生效的 store_type)。

    高优先级向量库不可用时回退 Chroma，指纹记录实际生效类型，
    避免下次启动重复尝试不可用后端。
    """
    if store_type == "postgres":
        try:
            return _build_postgres(chunks, embeddings), "postgres"
        except Exception as e:
            log.warning("Postgres 向量库不可用，回退 Chroma: {}", e)
    return _build_chroma(chunks, embeddings), "chroma"


def _build_vector_store(embeddings: Embeddings, embedding_id: str, force: bool = False):
    """构建或加载向量库，返回 (store, 实际生效的 store_type)。

    指纹（文档内容 + embedding 模型 + 向量库类型）一致时直接加载已有索引，否则全量重建并更新指纹。
    实际生效类型可能低于配置优先级（如配置了 postgres 但不可用会回退 chroma），
    指纹记录实际生效类型，下次启动优先按其直接复用索引，避免对不可用后端反复重试、每次全量重建。
    当配置切回高优先级后端（如 postgres 恢复可用）时会自动触发全量重建，无需手动 force。
    """
    docs = load_knowledge_docs()
    if not docs:
        return None, ""
    docs_hash_val = docs_hash()
    configured_type = settings.vector_store_type.lower()

    # 指纹中记录的实际生效类型：优先用它判断"索引是否可复用"，跳过对已不可用后端的重试
    fp = _load_fingerprint()
    effective_type = fp.get("store_type", configured_type) if fp else configured_type

    # 显式配置了更高优先级后端（如 postgres）但指纹仍记着回退类型（chroma）：
    # 视为后端已恢复，忽略指纹、按配置类型全量重建，避免永远卡在 chroma 回退
    _priority = {"postgres": 2, "chroma": 1}
    backend_recovered = bool(fp) and _priority.get(configured_type, 1) > _priority.get(effective_type, 1)

    # 指纹未变且未触发后端恢复 → 直接加载已有索引，零 embedding API 调用
    if (
        not force
        and not backend_recovered
        and is_up_to_date(docs_hash_val, embedding_id, effective_type, CHUNK_SIZE, CHUNK_OVERLAP, META_VERSION)
    ):
        log.info("RAG 文档指纹未变，复用已有向量索引 (store_type={})", effective_type)
        try:
            if effective_type == "postgres":
                return _load_postgres(embeddings), "postgres"
            return _load_chroma(embeddings), "chroma"
        except Exception as e:
            log.warning("已有索引加载失败，将全量重建: {}", e)

    log.info("RAG 文档指纹变更或首次构建，开始全量重建向量库 (configured_type={})", configured_type)
    chunks = split_chunks(docs)
    store, actual_type = _rebuild_store(chunks, embeddings, configured_type)
    _save_fingerprint(docs_hash_val, embedding_id, actual_type, CHUNK_SIZE, CHUNK_OVERLAP, META_VERSION)
    return store, actual_type


class KnowledgeBase:
    """命理知识库单例，封装检索接口（带 TTL 检索缓存）。"""

    def __init__(self):
        self._store = None
        self._retriever = None
        self._ready = False
        self._embedding_id = ""
        self._store_type = ""
        self._search_cache: OrderedDict[str, tuple[float, list[Document]]] = OrderedDict()
        self._cache_lock = threading.Lock()
        # 防止并发 init 导致 collection 被互相覆盖删除
        self._init_lock = threading.Lock()
        self._initializing = False

    def init(self, force: bool = False) -> bool:
        """初始化向量库（失败不阻断主流程）。

        Args:
            force: True 时无视指纹强制全量重建（管理接口"重建索引"使用）。
        """
        # 并发保护：另一个线程正在重建时，直接返回当前就绪状态
        with self._init_lock:
            if self._initializing:
                log.warning("RAG init 已在另一线程进行，跳过本次调用")
                return self._ready
            self._initializing = True
        try:
            return self._do_init(force)
        finally:
            with self._init_lock:
                self._initializing = False

    def _do_init(self, force: bool = False) -> bool:
        try:
            embeddings, embedding_id = _select_embeddings()
            self._embedding_id = embedding_id
            self._store, actual_type = _build_vector_store(embeddings, embedding_id, force=force)
            self._store_type = actual_type
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
            log.info("RAG 知识库初始化完成 (store_type={}, embedding={})", self._store_type, embedding_id)
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
        """相似性检索（相似度排序 + 关键词重叠 rerank，兼顾相关性与精确率）。

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
            docs = self._search_reranked(query)
        except Exception as e:
            log.warning("RAG 检索失败: {}", e)
            return []
        if docs:
            total = sum(len(d.page_content) for d in docs)
            log.debug("[RAG] query={} 命中{}条 总{}字", query[:40], len(docs), total)
        if ttl > 0:
            with self._cache_lock:
                self._search_cache[query] = (now, docs)
                while len(self._search_cache) > _SEARCH_CACHE_MAX:
                    self._search_cache.popitem(last=False)
        return docs

    def _search_reranked(self, query: str) -> list[Document]:
        """相似度候选 + （chroma）距离阈值过滤 + 关键词重叠 rerank。

        替代原 MMR：向量召回负责筛选 fetch_k 候选，关键词重叠 rerank 负责精排。
        精排与后端 score 语义无关，避免不同向量库（Chroma L2 距离 vs
        pgvector/milvus 余弦相似度）的 score 方向不一致导致排序反向。
        """
        fetch_k = 3
        k = settings.rag_k
        try:
            scored = self._store.similarity_search_with_score(query, k=fetch_k)
        except Exception as e:
            log.debug("后端不支持 score 检索，回退 MMR: {}", e)
            return self._retriever.invoke(query)
        # 距离阈值过滤（仅 Chroma L2 距离语义；pgvector/milvus 的 score 语义不同，暂不应用）
        if settings.rag_distance_threshold and self._store_type == "chroma":
            scored = [(d, s) for d, s in scored if s <= settings.rag_distance_threshold]
        if not scored:
            return []
        # rerank：关键词覆盖率 × 文档类型权重（断法优先、模板库降权），避免密集术语清单虚高命中
        scored = [
            (
                d,
                s,
                keyword_overlap(query, d.page_content)
                * DOC_TYPE_WEIGHT.get(d.metadata.get("doc_type", ""), 1.0),
            )
            for d, s in scored
        ]
        scored.sort(key=lambda x: -x[2])
        # 最低相关性阈值：覆盖率 < 0.25 的视为不相关，直接丢弃（宁缺毋滥，不兜底返回，
        # 避免无关知识片段进入 prompt 引入噪音）
        _MIN_OVERLAP = 0.25
        top = [item for item in scored if item[2] >= _MIN_OVERLAP][:k]
        log.info(
            "[rerank] query={} 候选数={} 阈值{}以上={}条={}",
            query[:30],
            len(scored),
            _MIN_OVERLAP,
            len(top),
            [(round(o, 3), d.metadata.get("doc_type", "?"), d.page_content[:18]) for d, s, o in top],
        )
        return [d for d, _, _ in top]

    def search_as_text(self, query: str) -> str:
        """检索并拼接为上下文文本，供 LLM 引用。"""
        docs = self.search(query)
        if not docs:
            return "（未检索到相关知识）"
        parts = []
        for i, d in enumerate(docs, 1):
            parts.append(
                "[片段{}] (来源:{}):\n{}".format(i, d.metadata.get("source", "未知"), d.page_content)
            )
        return "\n\n".join(parts)


# 惰性单例：首次调用时构造，导入本模块不产生实例构造副作用；真正的重初始化由 lifespan 后台触发
_kb_instance: KnowledgeBase | None = None
_kb_lock = threading.Lock()


def get_knowledge_base() -> KnowledgeBase:
    """获取知识库惰性单例（首次调用时构造）。"""
    global _kb_instance
    if _kb_instance is None:
        with _kb_lock:
            if _kb_instance is None:
                _kb_instance = KnowledgeBase()
    return _kb_instance