"""基于文件的对话记忆（对应 Java FileBasedChatMemory）。"""
from __future__ import annotations
import json
import threading
from pathlib import Path
from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict
from app.logger import log


class FileBasedChatMemory:
    """基于本地 JSON 文件的对话记忆（对应 Java FileBasedChatMemory）。

    每个会话对应一个 JSON 文件（按 conversation_id 命名），消息以
    langchain 字典格式持久化。类级锁表保证跨实例并发读写安全。
    """
    # 类级锁表：按会话文件路径加锁，跨实例也能防止并发读写丢消息
    _locks: dict[str, threading.Lock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, base_dir):
        """初始化记忆存储目录（不存在则创建）。"""
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, conversation_id):
        """将会话 ID 转义为安全的本地文件路径，防止目录遍历。"""
        safe = "".join(c for c in conversation_id if c.isalnum() or c in "-_")
        return self.base_dir / "{}.json".format(safe)

    def _lock_for(self, conversation_id) -> threading.Lock:
        """返回（或创建）该会话专属的文件锁，防止并发读写丢消息。"""
        key = str(self._path(conversation_id))
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def get(self, conversation_id):
        """读取会话全部历史消息；文件不存在或读取失败时返回空列表。"""
        p = self._path(conversation_id)
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return messages_from_dict(data)
        except Exception as e:
            log.warning("读取记忆失败 {}: {}", conversation_id, e)
            return []

    def add(self, conversation_id, messages):
        """追加消息到会话（读-改-写整体持锁，避免并发覆盖丢消息）。"""
        # 读-改-写整体持锁，避免并发请求互相覆盖导致消息丢失
        with self._lock_for(conversation_id):
            existing = self.get(conversation_id)
            existing.extend(messages)
            self._write(conversation_id, existing)

    def clear(self, conversation_id):
        """删除会话对应的记忆文件。"""
        with self._lock_for(conversation_id):
            p = self._path(conversation_id)
            if p.exists():
                p.unlink()

    def _write(self, conversation_id, messages):
        """将消息列表以 JSON 形式写入会话文件。"""
        p = self._path(conversation_id)
        data = messages_to_dict(messages)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
