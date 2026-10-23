"""负载/CI 用 OpenAI 兼容假模型服务（不调用真实 DashScope）。

启动：
    python scripts/mock_llm_server.py
后端指向：
    DASHSCOPE_BASE_URL=http://127.0.0.1:9000/v1
    DASHSCOPE_API_KEY=test
    DASHSCOPE_MODEL=mock-model
    DECOMPOSE_MODEL=mock-model
    REVIEWER_MODEL=mock-model
    SUB_APP_MODEL=mock-model
"""
from __future__ import annotations

import json
import os
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI(title="mock-llm")


def _reply_text(messages: list[dict]) -> str:
    text = "\n".join(str(m.get("content") or "") for m in messages)
    if "意图分析模块" in text or ("domain" in text and "queries" in text):
        return json.dumps(
            {
                "domain": "general",
                "queries": ["八字 用神 喜忌", "大运流年 分析"],
                "needs_chart": False,
                "other_birth_time": "",
                "other_gender": "",
                "target_dayun": "",
            },
            ensure_ascii=False,
        )
    if "审核员" in text or "【待审核回答】" in text:
        return '{"pass": true, "issues": []}'
    return "这是压测用的固定回答。命盘信息已收到，整体运势平稳。"


def _response(model: str, content: str) -> dict:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": len(content), "total_tokens": 8 + len(content)},
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model = str(body.get("model") or "mock-model")
    content = _reply_text(body.get("messages") or [])
    if not body.get("stream"):
        return _response(model, content)

    def _events():
        chunk = {
            "id": "chatcmpl-mock",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
        }
        yield "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"
        final = {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
        yield "data: " + json.dumps(final, ensure_ascii=False) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("MOCK_LLM_PORT", "9000")))
