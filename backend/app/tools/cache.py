"""排盘结果缓存：以 (出生时间, 性别, sect, yun_sect) 为 key 的 LRU 缓存，避免重复计算。"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Any

from app.core.logger import log


class BaziCache:
    def __init__(self, max_size: int = 200):
        self._max_size = max_size
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def make_key(self, birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1, tool: str = "") -> str:
        raw = f"{birth_time}|{gender}|{sect}|{yun_sect}|{tool}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(
        self, birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1, tool: str = ""
    ) -> Any | None:
        key = self.make_key(birth_time, gender, sect, yun_sect, tool)
        with self._lock:
            if key in self._cache:
                val = self._cache[key]
                self._cache.move_to_end(key)
                self._hits += 1
                log.debug("缓存命中: {} (hits={})", tool, self._hits)
                return val
            self._misses += 1
            return None

    def set(
        self, birth_time: str, gender: str, result: Any, sect: int = 2, yun_sect: int = 1, tool: str = ""
    ):
        key = self.make_key(birth_time, gender, sect, yun_sect, tool)
        with self._lock:
            self._cache[key] = result
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)  # LRU：移除最久未使用
            log.debug("缓存写入: {} (size={})", tool, len(self._cache))

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / max(1, total),
            }

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


bazi_cache = BaziCache(max_size=200)
