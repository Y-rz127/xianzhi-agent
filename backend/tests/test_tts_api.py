"""语音合成（TTS）接口回归测试。

重点守两件事：
1. **端点/请求形状**：TTS 与 ASR 是两套端点，混用会得到同一条 `InvalidParameter: url error`
   （2026-10-22 实测），所以这里钉死 TTS 的端点路径与 body 字段。
2. **落盘而非透传上游 URL**：上游音频 URL 有有效期且是 http（小程序不允许），
   必须服务端落盘、前端从本站取。
"""

from __future__ import annotations

import asyncio
import os
import time

import httpx
import pytest
from starlette.requests import Request

from app.api import tts as T


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 12345)})


class _Resp:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.text = str(self._payload)

    def json(self):
        return self._payload

    @property
    def is_error(self):
        return self.status_code >= 400

    def raise_for_status(self):
        if self.is_error:
            raise httpx.HTTPError("boom")


class _Client:
    """假 httpx.AsyncClient：记录请求，按脚本返回响应。"""

    def __init__(self, post_resp=None, get_resp=None):
        self.post_resp = post_resp or _Resp(200, {"output": {"audio": {"url": "http://x/a.wav"}}})
        self.get_resp = get_resp or _Resp(200, {}, content=b"RIFF0000WAVEfmt ")
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.posts.append((url, json or {}))
        return self.post_resp

    async def get(self, url):
        self.gets.append(url)
        return self.get_resp


@pytest.fixture()
def fake_client(monkeypatch):
    client = _Client()

    def _factory(*args, **kwargs):
        return client

    monkeypatch.setattr(T.httpx, "AsyncClient", _factory)
    return client


def test_tts_endpoint_is_not_asr_endpoint(monkeypatch):
    """TTS 端点必须是 SpeechSynthesizer，不能是 ASR 的 multimodal-generation。"""
    monkeypatch.setattr(T.settings, "dashscope_url", "https://dashscope.aliyuncs.com/compatible-mode/v1", raising=False)
    url = T._tts_endpoint()
    assert url.endswith("/api/v1/services/audio/tts/SpeechSynthesizer")
    assert "multimodal-generation" not in url


def test_synthesize_posts_expected_body(fake_client, monkeypatch, tmp_path):
    """body 形状：input.text / input.voice / input.format / input.sample_rate。"""
    monkeypatch.setattr(T.settings, "data_dir", tmp_path, raising=False)
    monkeypatch.setattr(T.settings, "tts_model", "qwen-audio-3.1-tts-flash", raising=False)
    monkeypatch.setattr(T.settings, "tts_voice", "longanhuan_v3.1", raising=False)

    out = asyncio.run(T.synthesize({"text": "你好，先知"}, _request(), None))
    url, body = fake_client.posts[0]
    assert body["model"] == "qwen-audio-3.1-tts-flash"
    assert body["input"]["text"] == "你好，先知"
    assert body["input"]["voice"] == "longanhuan_v3.1"
    assert body["input"]["format"] == "wav"
    assert body["input"]["sample_rate"] == 24000
    # 落盘 + 返回本站地址（不是上游 URL）
    assert out["url"] == f"/tts/audio/{out['id']}"
    assert not out["url"].startswith("http")
    assert (tmp_path / "tts" / f"{out['id']}.wav").is_file()


def test_synthesize_rejects_empty_and_too_long(fake_client, monkeypatch, tmp_path):
    """空文本 400；超长文本 400（合成耗时/费用随字数线性涨）。"""
    monkeypatch.setattr(T.settings, "data_dir", tmp_path, raising=False)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e1:
        asyncio.run(T.synthesize({"text": "   "}, _request(), None))
    assert e1.value.status_code == 400

    with pytest.raises(HTTPException) as e2:
        asyncio.run(T.synthesize({"text": "字" * (T._MAX_CHARS + 1)}, _request(), None))
    assert e2.value.status_code == 400


def test_synthesize_maps_model_not_enabled_error(fake_client, monkeypatch, tmp_path):
    """模型未开通时上游回 url error → 转成人话提示，而不是把原样丢给用户。"""
    from fastapi import HTTPException

    monkeypatch.setattr(T.settings, "data_dir", tmp_path, raising=False)
    fake_client.post_resp = _Resp(400, {"message": "url error, please check url！"})

    with pytest.raises(HTTPException) as e:
        asyncio.run(T.synthesize({"text": "测试"}, _request(), None))
    assert e.value.status_code == 502
    assert "未开通" in e.value.detail or "端点" in e.value.detail


def test_audio_endpoint_rejects_bad_id(fake_client, monkeypatch, tmp_path):
    """id 必须是 32 位 hex：挡掉路径穿越。"""
    from fastapi import HTTPException

    monkeypatch.setattr(T.settings, "data_dir", tmp_path, raising=False)

    for bad in ["../secret", "abc", "a" * 33, "zz" * 16]:
        with pytest.raises(HTTPException) as e:
            asyncio.run(T.get_audio(bad))
        assert e.value.status_code == 400

    with pytest.raises(HTTPException) as e2:
        asyncio.run(T.get_audio("a" * 32))
    assert e2.value.status_code == 404


def test_expired_audio_is_cleaned(monkeypatch, tmp_path):
    """过期音频在下次合成时顺手清掉，别把磁盘撑满。"""
    monkeypatch.setattr(T.settings, "data_dir", tmp_path, raising=False)
    d = T._tts_dir()
    old = d / ("a" * 32 + ".wav")
    old.write_bytes(b"x")
    os.utime(old, (time.time() - T._TTL_SECONDS - 10, time.time() - T._TTL_SECONDS - 10))
    T._cleanup_expired()
    assert not old.exists()
    # 还没到期的要留着
    fresh = d / ("b" * 32 + ".wav")
    fresh.write_bytes(b"x")
    T._cleanup_expired()
    assert fresh.exists()
