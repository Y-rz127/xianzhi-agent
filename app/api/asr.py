"""ASR 语音转文字接口：仅做请求内转发，不保存音频文件到服务器。"""
from __future__ import annotations

import base64

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.common import client_error
from app.core.config import settings
from app.core.logger import log

router = APIRouter(prefix="/asr", tags=["ASR"])

# 10MB 音频上限（Base64 编码后约 13MB+）
_MAX_AUDIO_BYTES = 10 * 1024 * 1024

_MIME_TYPES: dict[str, str] = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "aac": "audio/aac",
}


class TranscribeRequest(BaseModel):
    audio: str = Field(..., min_length=1, description="Base64 编码的音频数据，可选 data:xxx;base64, 前缀")
    format: str | None = Field(default=None, description="音频格式，如 wav/mp3/aac；默认读取 ASR_FORMAT")


class TranscribeResponse(BaseModel):
    text: str


def _strip_data_url(audio_b64: str) -> str:
    """去掉 data URL 前缀，只保留 base64 数据。"""
    if audio_b64.startswith("data:"):
        parts = audio_b64.split(";")
        if "base64" in parts[-1]:
            return parts[-1].split(",")[-1]
        return audio_b64.split(",")[-1]
    return audio_b64


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(req: TranscribeRequest):
    """接收前端 Base64 音频，调用 DashScope qwen-audio-3.0-asr-flash 同步识别。"""
    audio_b64 = _strip_data_url(req.audio)
    try:
        raw_bytes = base64.b64decode(audio_b64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="音频数据不是有效的 Base64")

    if len(raw_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="音频文件过大，请控制在 10MB 以内")

    fmt = (req.format or settings.asr_format).lower()
    mime = _MIME_TYPES.get(fmt, "audio/wav")
    data_url = f"data:{mime};base64,{audio_b64}"

    payload = {
        "model": settings.asr_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_url},
                    }
                ],
            }
        ],
    }

    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.dashscope_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            log.error("ASR API 返回错误: status={} body={}", e.response.status_code, e.response.text)
            raise HTTPException(status_code=502, detail="语音识别服务暂不可用")
        except httpx.RequestError as e:
            log.error("ASR 请求失败: {}", e)
            raise HTTPException(status_code=502, detail="语音识别服务连接失败")
        except Exception as e:
            log.exception("ASR 处理异常")
            raise HTTPException(status_code=500, detail=client_error(e))

    text = ""
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except Exception:
        log.warning("ASR 响应结构异常: {}", data)
        raise HTTPException(status_code=502, detail="语音识别结果解析失败")

    return TranscribeResponse(text=text)
