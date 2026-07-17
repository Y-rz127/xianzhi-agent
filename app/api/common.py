"""API 层公共工具：错误文案与输入校验。"""
from __future__ import annotations

from fastapi import HTTPException

from app.config import settings


def client_error(e: Exception) -> str:
    """生产环境返回通用错误文案，避免泄露内部路径/依赖细节。"""
    if settings.debug:
        return str(e)
    return "服务内部错误，请稍后重试"


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
