"""API 层公共工具：错误文案、异常收敛、输入校验与文件响应。"""
from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from fastapi import HTTPException, Response

from app.config import settings
from app.logger import log


def client_error(e: Exception) -> str:
    """生产环境返回通用错误文案，避免泄露内部路径/依赖细节。"""
    if settings.debug:
        return str(e)
    return "服务内部错误，请稍后重试"


@contextmanager
def api_guard(
    log_message: str,
    *,
    bad_request: tuple[type[Exception], ...] = (),
) -> Iterator[None]:
    """统一收敛接口异常：HTTPException 原样透传，bad_request 转 400，其余记日志转 500。

    Args:
        log_message: 记入日志的中文场景描述。
        bad_request: 视为参数错误（400）并原样返回文案的异常类型，如 ValueError。
    """
    try:
        yield
    except HTTPException:
        raise
    except bad_request as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception(log_message)
        raise HTTPException(status_code=500, detail=client_error(e))


def attachment_response(content: str | bytes, media_type: str, filename: str) -> Response:
    """构造带 Content-Disposition 的下载响应（PDF / JSON / JSONL 导出共用）。"""
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def jsonl_attachment(samples: list[dict], filename_prefix: str) -> Response:
    """将样本列表导出为 JSONL 下载响应（文件名带时间戳）。"""
    content = "\n".join(json.dumps(s, ensure_ascii=False) for s in samples)
    filename = f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    return attachment_response(content, "application/x-ndjson; charset=utf-8", filename)


def check_message_length(message: str):
    """单条消息长度限制，防止超长输入打爆 token 账单。"""
    if message and len(message) > settings.max_message_length:
        raise HTTPException(
            status_code=400,
            detail="消息过长（{} 字），请控制在 {} 字以内".format(len(message), settings.max_message_length),
        )


def message_too_long_text(message: str) -> str:
    """WS 场景的长度提示文案（无法抛 HTTPException）。"""
    return "消息过长（{} 字），请控制在 {} 字以内".format(len(message or ""), settings.max_message_length)


def is_message_too_long(message: str) -> bool:
    return bool(message) and len(message) > settings.max_message_length
