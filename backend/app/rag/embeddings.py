"""Embedding 工厂：优先 DashScope text-embedding，不可用时按配置回退本地 HuggingFace。"""

from __future__ import annotations

from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.core.logger import log

# 启动探测用的超时/重试。真实批次走 get_embeddings() 的 60s/3 次重试。
#
# 探测只做"快速判定"，8s 足够：DashScope 单条 embedding 平时 0.2~0.5s，真正慢的是
# **启动瞬间的并发排队** —— 实测 6 并发里有 1 个会被企业代理卡 40s+（APIConnectionError），
# 这时把超时调到 25s 也照样超时，只是每次启动白等 25 秒。
# 关键前提：**探测失败不再判死 RAG**（见 `_select_embeddings`）—— 复用已有 pgvector 索引
# 根本不需要 embedding，真正的 `embed_query` 只发生在检索时。所以这里取小值只影响
# "启动慢多少"，不影响可用性；别为了等拥塞再往上调。
_PROBE_TIMEOUT = 8.0
_PROBE_RETRIES = 0


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
    （约 60s 客户端超时）。

    **默认模型是 qwen3.7-text-embedding（1024维），2026-10-14 由 text-embedding-v2 换来的**：
    本项目 797 chunk / 40 条口语探针实测 recall@3 33/40→39/40、MRR 0.792→0.929，
    单价同档（0.0005 元/千 token）。原先 docstring 里"默认用 text-embedding-v2"的建议
    是 2026-09-04 排查 flash 挂死时的临时结论，flash 挂死问题已由 BatchEmbeddings 解决，该建议作废。
    批次条数与单次总字符上限见 settings.embedding_batch_size / embedding_max_chars_per_batch；
    **API 硬上限按模型不同**（v2=25 / v4=10 / qwen3.7=20），当前默认 10 对三者均安全。
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


def _probe_dashscope() -> None:
    """用短超时客户端探一次 DashScope embedding，不可用即抛。

    刻意不复用 `get_embeddings()`：那个客户端的 60s / 3 次重试是给**真实批次**用的
    （单批 10 条 × 600 字，长尾确实可能几十秒）。探测只需要回答"通不通"，
    用同一套重试会把一次网络抖动放大成 4×60s——端口已经在听、健康检查却报 degraded，
    看起来像服务挂了。2026-10-25 实测：DashScope 一抖，RAG 初始化从 1s 变 300s，
    全量跑测也被拖到 6 分钟。
    """
    from langchain_openai import OpenAIEmbeddings

    probe = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
        base_url=settings.dashscope_url,
        timeout=_PROBE_TIMEOUT,
        max_retries=_PROBE_RETRIES,
        check_embedding_ctx_length=False,
    )
    probe.embed_query("ping")


def _get_local_embeddings() -> Embeddings:
    """本地 HuggingFace embedding（DashScope 不可用时的回退）。

    内网环境基本走不到成功路径：没有外网，连 huggingface.co 的 config.json 都要等
    WinError 10060（十几秒起）。先用 `try_to_load_from_cache` 查本地缓存 —— 这个调用
    不联网、毫秒级 —— 没缓存就直接抛，别让启动白等十几秒再打一堆
    `LangChainDeprecationWarning` 把日志刷花。
    """
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
    except ImportError as e:
        raise RuntimeError("本地 embedding 回退需要 langchain-community + sentence-transformers") from e

    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        try_to_load_from_cache = None  # type: ignore[assignment]

    if try_to_load_from_cache is not None:
        # 命中返回缓存文件路径（str），未命中返回 _CACHED_NO_EXIST 或 None，两者都不是 str
        cached = try_to_load_from_cache(settings.embedding_local_model, "config.json")
        if not isinstance(cached, str):
            raise RuntimeError(
                "本地 embedding 模型未下载（{}），内网无法从 huggingface.co 拉取；"
                "如需启用本地回退，请先在有网机器上下载到 HF 缓存目录再拷贝".format(
                    settings.embedding_local_model
                )
            )
    return HuggingFaceEmbeddings(model_name=settings.embedding_local_model)


def _select_embeddings() -> tuple[Embeddings, str]:
    """选择可用 embedding，返回 (embeddings, embedding_id)。

    优先 DashScope；探测失败且本地模型**确实可用**时才回退。
    embedding_id 参与文档指纹，换模型后指纹不匹配会自动重建索引，
    保证查询向量与入库向量来自同一模型。

    探测走 `_probe_dashscope`（短超时、不重试），不用返回的这个客户端自己去 ping ——
    否则一次抖动就是 4×60s，启动阶段白等 5 分钟。

    **探测失败不等于 DashScope 挂了**，所以不判死：
    实测启动瞬间 6 个探活并发时，5 个 0.3~0.6s 返回，1 个会被企业代理卡 46s
    （`APIConnectionError`）—— 纯粹是并发连接排队，跟服务健康无关。
    更关键的是：**复用已有 pgvector 索引根本不需要 embedding**，真正的
    `embed_query` 只发生在检索时，那时启动期的拥塞早已过去。
    所以本地回退也不可用时（内网没预下载），仍然带着 DashScope 起来，
    让 RAG 就绪；检索真失败会被 `search()` 的 try/except 兜住返回空，
    比"整个 RAG 不可用、问一句零知识"要好。
    """
    dashscope = get_embeddings()
    try:
        _probe_dashscope()
        return dashscope, "dashscope:{}".format(settings.embedding_model)
    except Exception as e:
        if not settings.embedding_local_fallback:
            raise
        log.warning(
            "DashScope embedding 探测失败（{}），尝试本地回退 {}",
            e,
            settings.embedding_local_model,
        )
        try:
            local = _get_local_embeddings()
            local.embed_query("ping")  # 触发模型加载，不可用则抛错
        except Exception as local_err:
            log.warning(
                "本地回退也不可用（{}），继续使用 DashScope，检索时再试", local_err
            )
            return dashscope, "dashscope:{}".format(settings.embedding_model)
        return local, "local:{}".format(settings.embedding_local_model)
