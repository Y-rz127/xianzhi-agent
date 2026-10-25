"""DashScope embedding 的启动探测口径守卫。

回归背景（2026-10-25）：`_select_embeddings` 原先直接拿 `get_embeddings()` 返回的客户端
`embed_query("ping")` 做探测，而那个客户端是 `timeout=60, max_retries=3` —— 那是给真实批次
（10 条 × 600 字）用的。DashScope 一抖就变成 4×60s：端口已经在听、`/api/health/ready` 却报
`rag: ok=false`，全量跑测从 76s 拖到 6 分钟、断言还全对，极易被误判成"最近改动引入了性能回归"。

现在探测走独立的 `_probe_dashscope`（短超时 + 不重试）。这两条断言就是钉住"别再退回去"。
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.rag import embeddings


def test_probe_client_uses_short_timeout_and_no_retry(monkeypatch):
    """探测客户端必须是短超时、零重试 —— 抖动时最多等一次 timeout，不叠乘。"""
    captured: dict = {}

    class FakeOpenAIEmbeddings:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def embed_query(self, text: str):
            return [0.0]

    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeOpenAIEmbeddings)

    embeddings._probe_dashscope()

    assert captured["timeout"] == embeddings._PROBE_TIMEOUT
    assert captured["max_retries"] == 0
    # 下限别调太小：服务启动瞬间有 5~6 个 LLM 探活在抢同一个企业代理，8s 会把
    # "排队等代理"误判成"服务挂了"（2026-10-25 踩过，RAG 直接降级）。
    # 上限也别放开：真挂了不该让启动干等太久。
    assert 10 <= embeddings._PROBE_TIMEOUT <= 30


def test_select_embeddings_probes_instead_of_pinging_real_client(monkeypatch):
    """`_select_embeddings` 只能走 `_probe_dashscope`，不许拿真实客户端自己 ping。"""

    class Boom:
        def embed_query(self, text: str):
            raise AssertionError("不该用真实客户端 ping：会吃 60s × 3 次重试")

    calls: list[int] = []
    monkeypatch.setattr(embeddings, "get_embeddings", lambda: Boom())
    monkeypatch.setattr(embeddings, "_probe_dashscope", lambda: calls.append(1))

    got, embedding_id = embeddings._select_embeddings()

    assert calls == [1]
    assert isinstance(got, Boom)
    assert embedding_id.startswith("dashscope:")


def test_select_embeddings_falls_back_when_probe_raises(monkeypatch):
    """探测失败且允许回退时，切本地模型并把 embedding_id 切到 local:。"""

    class FakeLocal:
        def embed_query(self, text: str):
            return [0.0]

    def _boom():
        raise RuntimeError("connection timeout")

    monkeypatch.setattr(embeddings, "get_embeddings", lambda: object())
    monkeypatch.setattr(embeddings, "_probe_dashscope", _boom)
    monkeypatch.setattr(embeddings, "_get_local_embeddings", lambda: FakeLocal())
    monkeypatch.setattr(settings, "embedding_local_fallback", True)

    got, embedding_id = embeddings._select_embeddings()

    assert isinstance(got, FakeLocal)
    assert embedding_id.startswith("local:")


def test_select_embeddings_raises_when_fallback_disabled(monkeypatch):
    """不允许回退时探测失败就直接抛，别静默换成别的模型（换了指纹就对不上）。"""

    def _boom():
        raise RuntimeError("connection timeout")

    monkeypatch.setattr(embeddings, "get_embeddings", lambda: object())
    monkeypatch.setattr(embeddings, "_probe_dashscope", _boom)
    monkeypatch.setattr(settings, "embedding_local_fallback", False)

    with pytest.raises(RuntimeError):
        embeddings._select_embeddings()


def test_local_fallback_fails_fast_when_model_not_cached(monkeypatch):
    """内网没有 HF 缓存时必须秒抛，不许去 huggingface.co 等十几秒再报错。

    没这条约束时，本地回退会真的发 HEAD 请求拿 config.json，内网每次都要等
    WinError 10060，把「DashScope 抖动」放大成「启动卡住 + 一大屏弃用警告」。
    """
    monkeypatch.setattr("huggingface_hub.try_to_load_from_cache", lambda *a, **k: None)

    with pytest.raises(RuntimeError, match="未下载"):
        embeddings._get_local_embeddings()


def test_local_fallback_uses_cache_when_present(monkeypatch):
    """有本地缓存时正常构造，且不传联网参数。"""
    captured: dict = {}

    class FakeHF:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "huggingface_hub.try_to_load_from_cache", lambda *a, **k: "/fake/hf/config.json"
    )
    monkeypatch.setattr("langchain_community.embeddings.HuggingFaceEmbeddings", FakeHF)

    got = embeddings._get_local_embeddings()

    assert isinstance(got, FakeHF)
    assert captured["model_name"] == settings.embedding_local_model
