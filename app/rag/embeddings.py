"""Embedding 工厂：优先 DashScope text-embedding，不可用时按配置回退本地 HuggingFace。"""

from __future__ import annotations

from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.core.logger import log


class BatchEmbeddings(Embeddings):
    """把大批量 embed_documents 拆成小批次，规避 DashScope 单次 ≤20 条限制。"""

    def __init__(self, wrapped: Embeddings, batch_size: int = 20):
        self._wrapped = wrapped
        self._batch_size = batch_size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            result.extend(self._wrapped.embed_documents(texts[i : i + self._batch_size]))
        return result

    def embed_query(self, text: str) -> list[float]:
        return self._wrapped.embed_query(text)


def get_embeddings() -> Embeddings:
    """DashScope 文本嵌入模型（批量调用包一层 BatchEmbeddings）。"""
    from langchain_community.embeddings import DashScopeEmbeddings

    return BatchEmbeddings(
        DashScopeEmbeddings(
            model=settings.embedding_model,
            max_retries=3,
            dashscope_api_key=settings.embedding_api_key,
        )
    )


def _get_local_embeddings() -> Embeddings:
    """本地 HuggingFace embedding（DashScope 不可用时的回退）。"""
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
    except ImportError as e:
        raise RuntimeError("本地 embedding 回退 sentence-transformers") from e
    return HuggingFaceEmbeddings(model_name=settings.embedding_local_model)


def _select_embeddings() -> tuple[Embeddings, str]:
    """选择可用 embedding，返回 (embeddings, embedding_id)。

    优先 DashScope；实测调用失败且允许回退时切换本地模型。
    embedding_id 参与文档指纹，换模型后指纹不匹配会自动重建索引，
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
            e,
            settings.embedding_local_model,
        )
        local = _get_local_embeddings()
        local.embed_query("ping")  # 触发模型下载/加载，不可用则抛错
        return local, "local:{}".format(settings.embedding_local_model)