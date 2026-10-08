"""短语音转写：音频仅在本次请求中转发给 DashScope，不落盘。"""
from __future__ import annotations

import base64
import binascii

import httpx
from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.logger import log

router = APIRouter(prefix="/asr", tags=["ASR"])
_MAX_DATA_URI_CHARS = 10 * 1024 * 1024 * 4 // 3

# DashScope 多模态生成接口认这些容器格式；其余按"识别出来但上游解不开"处理
_DASHSCOPE_FORMATS = {"mp3", "wav", "pcm", "opus", "speex", "amr", "aac"}
_MIME = {"mp3": "audio/mpeg", "wav": "audio/wav", "aac": "audio/aac", "opus": "audio/opus"}


def _sniff(head: bytes) -> tuple[str, int | None]:
    """按魔数判断真实容器格式，并顺带取 WAV 头里的采样率。

    客户端（含微信开发者工具）写死的 format 未必等于落盘文件的真实格式，
    以字节为准才不会出现"声明 mp3、实际 wav"导致上游 DECODE_ERROR。
    """
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        rate = int.from_bytes(head[24:28], "little") if len(head) >= 28 else 0
        return "wav", rate or None
    if head[:4] == b"OggS":
        return "opus", None
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xfa"):
        return "mp3", None
    if head[:5] == b"#!AMR":
        return "amr", None
    if head[4:8] == b"ftyp":
        return "m4a", None
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm", None
    return "", None


def _head_bytes(b64: str) -> bytes:
    chunk = b64[:64]
    chunk += "=" * (-len(chunk) % 4)
    try:
        return base64.b64decode(chunk)
    except (binascii.Error, ValueError):
        return b""


@router.post("/transcribe")
async def transcribe(body: dict):
    audio = body.get("audio")
    if not isinstance(audio, str) or not audio.startswith("data:audio/"):
        raise HTTPException(status_code=400, detail="请上传有效的音频数据")
    if len(audio) > _MAX_DATA_URI_CHARS:
        raise HTTPException(status_code=413, detail="音频过大，请录制 60 秒以内的语音")
    if not settings.dashscope_api_key:
        raise HTTPException(status_code=503, detail="语音识别服务尚未配置")

    b64 = audio.split(",", 1)[1] if "," in audio else ""
    head = _head_bytes(b64)
    sniffed, sniffed_rate = _sniff(head)
    declared = str(body.get("format") or "mp3").lower()
    # 嗅探结果可信时以它为准；嗅探不出来（或不在上游支持列表里）就沿用客户端声明
    fmt = sniffed if sniffed in _DASHSCOPE_FORMATS else declared
    sample_rate = sniffed_rate or 16000
    data_uri = f"data:{_MIME.get(fmt, 'audio/' + fmt)};base64,{b64}"
    log.debug(
        f"[asr] 入参 declared={declared} sniffed={sniffed or '未知'} head={head[:4].hex()} "
        f"→ fmt={fmt} rate={sample_rate} chars={len(b64)}"
    )

    endpoint = settings.dashscope_url.replace(
        "/compatible-mode/v1", "/api/v1/services/aigc/multimodal-generation/generation"
    )
    payload = {
        "model": settings.asr_model,
        "input": {"messages": [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": data_uri}}]}]},
        "parameters": {"format": fmt, "sample_rate": sample_rate},
    }
    try:
        async with httpx.AsyncClient(timeout=45, trust_env=False) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {settings.dashscope_api_key}", "X-DashScope-SSE": "disable"},
                json=payload,
            )
    except Exception as exc:
        # 保留真实原因，否则前端只能拿到一句没有信息量的 502
        log.warning(f"[asr] 调用 DashScope 失败: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=502, detail="语音识别服务暂不可用")

    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.is_error:
        raw = data.get("message") or f"上游返回 {response.status_code}"
        # 音频解出来了但没人声（环境太吵/没说话），对用户来说不是"服务故障"
        if "NO_WORDS" in raw:
            log.info(f"[asr] 音频可解码但无人声 fmt={fmt} sniffed={sniffed or '未知'} chars={len(b64)}")
            raise HTTPException(status_code=422, detail="未识别到清晰的语音")
        # 注意：嗅探出容器≠要改声明。开发者工具录的是 webm（1a45dfa3），
        # 但上游按声明 format=mp3 也能解码（它自己会嗅容器）；贸然把 format 改成
        # webm 反而可能因为不在上游枚举里而直接报参数错。所以这里只改人话提示。
        message = "录音内容不完整或无法识别，请重新录制后再试" if "DECODE_ERROR" in raw else raw
        log.warning(f"[asr] DashScope {response.status_code} fmt={fmt} sniffed={sniffed or '未知'} chars={len(b64)} → {raw}")
        raise HTTPException(status_code=502, detail=message)

    output = data.get("output") or {}
    text = (output.get("output") or {}).get("sentence", {}).get("text") or output.get("text")
    if not text:
        log.warning(f"[asr] 未识别到文本 fmt={fmt} chars={len(b64)} → {str(data)[:300]}")
        raise HTTPException(status_code=422, detail="未识别到清晰的语音")
    log.info(f"[asr] 转写成功 fmt={fmt} rate={sample_rate} chars={len(b64)} → {len(text.strip())} 字")
    return {"text": text.strip(), "model": settings.asr_model}
