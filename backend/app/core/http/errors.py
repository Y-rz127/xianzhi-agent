"""HTTP / WS 层错误文案与输入限额（core 层，零业务依赖）。

原位于 ``app/api/common.py``：因 ``sub_app`` 也要用，被迫从子应用 import api 层，
形成 ``sub_app → api`` 倒置边（报告 P0-4）。本模块只依赖 ``core.config``，
下沉到 core 后 api / sub_app 均可直接使用，倒置边消除。
"""

from __future__ import annotations

from fastapi import HTTPException

from app.core.config import settings


def client_error(e: Exception) -> str:
    """生产环境返回通用错误文案，避免泄露内部路径/依赖细节。"""
    return str(e) if settings.debug else "服务内部错误，请稍后重试"


def _too_long_text(length: int) -> str:
    return "消息过长（{} 字），请控制在 {} 字以内".format(length, settings.max_message_length)


def check_message_length(message: str):
    """单条消息长度限制，防止超长输入打爆 token 账单。"""
    if message and len(message) > settings.max_message_length:
        raise HTTPException(status_code=400, detail=_too_long_text(len(message)))


def message_too_long_text(message: str) -> str:
    """WS 场景的长度提示文案（无法抛 HTTPException）。"""
    return _too_long_text(len(message or ""))


def is_message_too_long(message: str) -> bool:
    return bool(message) and len(message) > settings.max_message_length
