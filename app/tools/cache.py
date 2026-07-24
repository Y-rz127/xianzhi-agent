"""排盘结果缓存。

以 (出生时间, 性别, sect, yun_sect) 为 key，缓存排盘结果，避免重复计算。
使用 LRU 策略，默认最多缓存 200 条命例。
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Any

from app.logger import log


class BaziCache:
    """八字排盘结果缓存（LRU）。"""

    def __init__(self, max_size: int = 200):
        self._max_size = max_size
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def _make_key(self, birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1, tool: str = "") -> str:
        """生成缓存 key。"""
        raw = f"{birth_time}|{gender}|{sect}|{yun_sect}|{tool}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1, tool: str = "") -> Any | None:
        """获取缓存结果。"""
        key = self._make_key(birth_time, gender, sect, yun_sect, tool)
        with self._lock:
            if key in self._cache:
                ts, val = self._cache[key]
                self._cache.move_to_end(key)
                self._hits += 1
                log.debug("缓存命中: {} (hits={})", tool, self._hits)
                return val
            self._misses += 1
            return None

    def set(self, birth_time: str, gender: str, result: Any, sect: int = 2, yun_sect: int = 1, tool: str = ""):
        """写入缓存。"""
        key = self._make_key(birth_time, gender, sect, yun_sect, tool)
        with self._lock:
            self._cache[key] = (time.time(), result)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)  # LRU 策略，移除最久未使用的，也就是队首
            log.debug("缓存写入: {} (size={})", tool, len(self._cache))

    def stats(self) -> dict:
        """返回缓存统计信息。"""
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(1, self._hits + self._misses),
        }

    def clear(self):
        """清空缓存。"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


bazi_cache = BaziCache(max_size=200)