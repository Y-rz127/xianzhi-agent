"""语音合成（TTS）：文本 → 音频文件。

DashScope 的 TTS 与 ASR 是**两套端点**，混用会得到同一条
``InvalidParameter: url error``（与 payload 无关，极难排查，2026-10-22 实测）：

- ASR：``POST /api/v1/services/aigc/multimodal-generation/generation``
  body 用 ``input.messages[].content[].input_audio``
- TTS：``POST /api/v1/services/audio/tts/SpeechSynthesizer``
  body 用 ``input.text / input.voice / input.format / input.sample_rate``

上游返回的音频 URL **有有效期且是 http**（小程序不允许 http 源），所以服务端把音频
拉下来落盘、前端从本站 ``/tts/audio/{id}`` 取：一次解决跨域、过期、http 三重问题。
落盘而不是存内存：多 worker 时 GET 可能落到另一个进程，内存态会随机 404。
"""
from __future__ import annotations

import base64
import binascii
import re
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.deps import get_optional_paid_principal
from app.core.config import settings
from app.core.http.client_ip import client_ip_from_request
from app.core.logger import log
from app.core.quota import enforce_quota

router = APIRouter(prefix="/tts", tags=["TTS"])

# 单次合成文本上限：TTS 耗时与费用随字数线性增长，命理报告全文约 2500 字，4000 够用
_MAX_CHARS = 4000
# 落盘音频保留时长（秒）：前端播完即弃，过期文件在下次合成时顺手清掉
_TTL_SECONDS = 1800
_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _tts_endpoint() -> str:
    """TTS 端点：把 DASHSCOPE_BASE_URL 的兼容模式前缀换成 TTS 服务路径。"""
    base = settings.dashscope_url.rstrip("/")
    for suffix in ("/compatible-mode/v1", "/api/v1"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return f"{base}/api/v1/services/audio/tts/SpeechSynthesizer"


def _tts_dir() -> Path:
    path = Path(settings.data_dir) / "tts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup_expired() -> None:
    """删掉过期音频（顺带做，不单独起定时任务）。"""
    now = time.time()
    for f in _tts_dir().glob("*.wav"):
        try:
            if now - f.stat().st_mtime > _TTL_SECONDS:
                f.unlink()
        except OSError:
            pass


async def _fetch_audio(text: str, voice: str) -> bytes:
    """调 DashScope 合成并把音频字节取回来。"""
    payload = {
        "model": settings.tts_model,
        "input": {"text": text, "voice": voice, "format": "wav", "sample_rate": 24000},
    }
    try:
        async with httpx.AsyncClient(timeout=settings.tts_timeout, trust_env=False) as client:
            response = await client.post(
                _tts_endpoint(),
                headers={"Authorization": f"Bearer {settings.dashscope_api_key}"},
                json=payload,
            )
    except httpx.TimeoutException:
        log.warning("[tts] 合成超时（{}s 预算）", int(settings.tts_timeout))
        raise HTTPException(status_code=504, detail="语音合成超时，请稍后重试")
    except Exception as exc:
        log.warning(f"[tts] 调用 DashScope 失败: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=502, detail="语音合成服务暂不可用")

    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.is_error:
        raw = data.get("message") or f"上游返回 {response.status_code}"
        # 模型未在控制台开通时，上游回的是 url error（与请求内容无关）
        if "url error" in str(raw):
            raw = "语音合成模型未开通或端点不匹配（TTS 与 ASR 端点不同）"
        log.warning(f"[tts] DashScope {response.status_code} → {raw}")
        raise HTTPException(status_code=502, detail=f"语音合成失败：{raw}")

    audio = ((data.get("output") or {}).get("audio")) or {}
    url = audio.get("url")
    raw_b64 = audio.get("data")
    if not url and not raw_b64:
        log.warning(f"[tts] 上游未返回音频: {str(data)[:200]}")
        raise HTTPException(status_code=502, detail="语音合成未返回音频")

    if url:
        try:
            async with httpx.AsyncClient(timeout=settings.tts_timeout, trust_env=False) as client:
                audio_resp = await client.get(url)
                audio_resp.raise_for_status()
                return audio_resp.content
        except Exception as exc:
            log.warning(f"[tts] 下载音频失败: {type(exc).__name__}: {exc}")
            raise HTTPException(status_code=502, detail="语音合成音频下载失败")
    try:
        return base64.b64decode(raw_b64)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=502, detail="语音合成音频解码失败")


@router.post("/synthesize")
async def synthesize(
    body: dict,
    request: Request,
    principal: dict | None = Depends(get_optional_paid_principal),
):
    """文本 → 音频。返回本站音频地址（前端直接播放，不必处理上游过期 URL）。"""
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="文本不能为空")
    if len(text) > _MAX_CHARS:
        raise HTTPException(
            status_code=400, detail=f"文本过长（{len(text)} 字），请控制在 {_MAX_CHARS} 字以内"
        )
    if not settings.dashscope_api_key:
        raise HTTPException(status_code=503, detail="语音合成服务尚未配置")
    await enforce_quota("tts", principal, client_ip_from_request(request), settings.paid_quota_tts_daily)
    voice = str(body.get("voice") or settings.tts_voice).strip() or settings.tts_voice

    _cleanup_expired()
    content = await _fetch_audio(text, voice)
    audio_id = uuid.uuid4().hex
    path = _tts_dir() / f"{audio_id}.wav"
    try:
        path.write_bytes(content)
    except OSError as exc:
        log.warning(f"[tts] 音频落盘失败: {exc}")
        raise HTTPException(status_code=500, detail="语音合成结果保存失败")

    log.info(f"[tts] 合成完成 voice={voice} chars={len(text)} bytes={len(content)}")
    return {
        "id": audio_id,
        "url": f"/tts/audio/{audio_id}",
        "mime": "audio/wav",
        "size": len(content),
        "chars": len(text),
        "model": settings.tts_model,
        "voice": voice,
    }


@router.get("/audio/{audio_id}")
async def get_audio(audio_id: str):
    """取合成好的音频（前端播放入口）。"""
    if not _ID_RE.match(audio_id):
        raise HTTPException(status_code=400, detail="音频 id 不合法")
    path = _tts_dir() / f"{audio_id}.wav"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="音频已过期，请重新合成")
    return FileResponse(path, media_type="audio/wav", filename=f"{audio_id}.wav")
