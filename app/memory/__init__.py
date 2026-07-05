"""记忆模块：根据配置返回文件版或 PostgreSQL 版对话记忆。"""
from __future__ import annotations
from app.config import settings
from app.logger import log


def create_chat_memory():
    """根据 MEMORY_STORE_TYPE 配置返回对应实现。

    - file    : FileBasedChatMemory（默认，本地 JSON 文件）
    - postgres: PostgresChatMemory（持久化到 PostgreSQL）
    """
    store_type = settings.memory_store_type.lower()
    if store_type == "postgres":
        from app.memory.postgres_memory import PostgresChatMemory
        log.info("对话记忆存储: PostgreSQL (table={})", settings.memory_table_name)
        return PostgresChatMemory(
            connection_string=settings.postgres_connection_string,
            table_name=settings.memory_table_name,
        )
    # 默认文件存储
    from app.memory.chat_memory import FileBasedChatMemory
    log.info("对话记忆存储: File (dir={})", settings.memory_dir)
    return FileBasedChatMemory(settings.memory_dir)