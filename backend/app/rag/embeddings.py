"""Embedding 工厂：优先 DashScope text-embedding，不可用时按配置回退本地 HuggingFace。"""

from __future__ import annotations

from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.core.logger import log


class BatchEmbeddings(Embeddings):
    """把大批量 embed_documents 拆成小批次，同时满足条数与总字符数双上限。

    背景：DashScope 部分文本嵌入模型（如 qwen 系 flash）超限时不会返回错误，
    而是"挂死不响应"直到客户端超时（实测 qwen3.7-text-embedding-flash 单条 ≥600 字、
    或一批总字符 ≈8.2k 即挂死）。仅按条数拆批（旧版固定 20 条）在长文本/大批量下仍会触发。
    因此同时用 batch_size 与 max_chars_per_batch 收敛每个请求，规避挂死。
    """

    def __init__(self, wrapped: Embeddings, batch_size: int = 10, max_chars_per_batch: int = 6000):
        self._wrapped = wrapped
        self._batch_size = max(1, int(batch_size))
        self._max_chars_per_batch = max(1, int(max_chars_per_batch))

    def _batch(self, texts: list[str]) -> list[list[str]]:
        """按「条数上限 + 总字符上限」切批；单条超限时单独成批。"""
        batches: list[list[str]] = []
        cur: list[str] = []
        cur_chars = 0
        for t in texts:
            # 单条本身超限（罕见，正常 chunk ≤600 字不会触发）——单独一批，避免拖垮整体
            if len(t) > self._max_chars_per_batch:
                if cur:
                    batches.append(cur)
                    cur, cur_chars = [], 0
                batches.append([t])
                continue
            cur.append(t)
            cur_chars += len(t)
            if len(cur) >= self._batch_size or cur_chars >= self._max_chars_per_batch:
                batches.append(cur)
                cur, cur_chars = [], 0
        if cur:
            batches.append(cur)
        return batches

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for batch in self._batch(texts):
            result.extend(self._wrapped.embed_documents(batch))
        return result

    def embed_query(self, text: str) -> list[float]:
        return self._wrapped.embed_query(text)


def get_embeddings() -> Embeddings:
    """DashScope 文本嵌入（OpenAI 兼容端点 compatible-mode/v1 + 批量拆分）。

    注意：必须走 compatible-mode/v1 而非原生 DashScopeEmbeddings（原生 SDK 端点）。
    qwen3.7-text-embedding-flash 在原生端点长输入会挂死 300s 无响应（2026-09-04 排查）。
    但实测该 flash 模型即便在兼容端点，单条 ≥600 字 / 一批总字符 ≈8.2k 时仍会挂死不返回
    （约 60s 客户端超时），因此默认 embedding 模型请用 text-embedding-v2（长输入与大批量均稳定 <2s）。
    批量条数与单次总字符上限见 settings.embedding_batch_size / embedding_max_chars_per_batch。
    """
    from langchain_openai import OpenAIEmbeddings

    return BatchEmbeddings(
        OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.embedding_api_key,
            base_url=settings.dashscope_url,
            timeout=60,
            max_retries=3,
            # 切片长度远小于 8192 token，关闭本地 tiktoken 预切分，整段直传
            check_embedding_ctx_length=False,
        ),
        batch_size=settings.embedding_batch_size,
        max_chars_per_batch=settings.embedding_max_chars_per_batch,
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