"""基于文件的对话记忆（对应 Java FileBasedChatMemory）。"""
from __future__ import annotations
import json
from pathlib import Path
from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict
from app.logger import log


class FileBasedChatMemory:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, conversation_id):
        safe = "".join(c for c in conversation_id if c.isalnum() or c in "-_")
        return self.base_dir / "{}.json".format(safe)

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
        existing = self.get(conversation_id)
        existing.extend(messages)
        self._write(conversation_id, existing)

    def clear(self, conversation_id):
        p = self._path(conversation_id)
        if p.exists():
            p.unlink()

    def _write(self, conversation_id, messages):
        p = self._path(conversation_id)
        data = messages_to_dict(messages)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
