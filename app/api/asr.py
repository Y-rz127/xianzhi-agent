"""短语音转写：音频仅在本次请求中转发给 DashScope，不落盘。"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from app.core.config import settings

router = APIRouter(prefix="/asr", tags=["ASR"])
_MAX_DATA_URI_CHARS = 10 * 1024 * 1024 * 4 // 3


@router.post("/transcribe")
async def transcribe(body: dict):
    audio = body.get("audio")
    if not isinstance(audio, str) or not audio.startswith("data:audio/"):
        raise HTTPException(status_code=400, detail="请上传有效的音频数据")
    if len(audio) > _MAX_DATA_URI_CHARS:
        raise HTTPException(status_code=413, detail="音频过大，请录制 60 秒以内的语音")
    if not settings.dashscope_api_key:
        raise HTTPException(status_code=503, detail="语音识别服务尚未配置")
    endpoint = settings.dashscope_url.replace("/compatible-mode/v1", "/api/v1/services/aigc/multimodal-generation/generation")
    payload = {"model": settings.asr_model, "input": {"messages": [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": audio}}]}]}, "parameters": {"format": body.get("format", "mp3"), "sample_rate": 16000}}
    try:
        async with httpx.AsyncClient(timeout=45, trust_env=False) as client:
            response = await client.post(endpoint, headers={"Authorization": f"Bearer {settings.dashscope_api_key}", "X-DashScope-SSE": "disable"}, json=payload)
        data = response.json()
        if response.is_error:
            raise HTTPException(status_code=502, detail=data.get("message") or "语音识别失败")
        text = (data.get("output") or {}).get("output", {}).get("sentence", {}).get("text") or (data.get("output") or {}).get("text")
        if not text:
            raise HTTPException(status_code=422, detail="未识别到清晰的语音")
        return {"text": text.strip(), "model": settings.asr_model}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="语音识别服务暂不可用")
