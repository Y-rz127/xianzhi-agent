"""基于文件的对话记忆（对应 Java FileBasedChatMemory）。"""
from __future__ import annotations
import json
import threading
from pathlib import Path
from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict
from app.logger import log


class FileBasedChatMemory:
    # 类级锁表：按会话文件路径加锁，跨实例也能防止并发读写丢消息
    _locks: dict[str, threading.Lock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, conversation_id):
        safe = "".join(c for c in conversation_id if c.isalnum() or c in "-_")
        return self.base_dir / "{}.json".format(safe)

    def _lock_for(self, conversation_id) -> threading.Lock:
        key = str(self._path(conversation_id))
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def get(self, conversation_id):
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
        # 读-改-写整体持锁，避免并发请求互相覆盖导致消息丢失
        with self._lock_for(conversation_id):
            existing = self.get(conversation_id)
            existing.extend(messages)
            self._write(conversation_id, existing)

    def clear(self, conversation_id):
        with self._lock_for(conversation_id):
            p = self._path(conversation_id)
            if p.exists():
                p.unlink()

    def _write(self, conversation_id, messages):
        p = self._path(conversation_id)
        data = messages_to_dict(messages)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
