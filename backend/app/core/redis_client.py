"""Redis 异步客户端（跨副本共享状态：限流等）。

降级策略：
- REDIS_URL 未配置 → 接口返回 None，调用方回退进程内存实现
- 连接失败进入 30s 冷却：Redis 宕机时避免每个请求都卡在连接超时上
- PING 成功缓存 5s：避免为每个请求付一次探测往返
"""
from __future__ import annotations

import secrets
import time

from app.core.config import settings
from app.core.logger import log

_client = None       # redis.asyncio.Redis | None
_last_ok = 0.0       # 上次 PING 成功时间（monotonic）
_down_until = 0.0    # 连接失败后冷却截止时间（monotonic）

_COOL_DOWN = 30.0
_OK_TTL = 5.0

# 滑动窗口限流（ZSET 原子操作）：剔除窗口外记录 → 计数 → 未超限则写入并续期
_RATE_LIMIT_LUA = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, tonumber(ARGV[1]) - tonumber(ARGV[2]))
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then return 0 end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('PEXPIRE', KEYS[1], ARGV[2])
return 1
"""


def _build_client() -> None:
    global _client
    try:
        import redis.asyncio as aioredis

        _client = aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            decode_responses=True,
            health_check_interval=30,
        )
    except Exception as e:
        log.warning("Redis 初始化失败，降级为进程内存: {}", e)
        _client = None


async def get_redis():
    """返回全局 Redis 客户端；未配置/冷却期内/不可达时返回 None。"""
    global _last_ok, _down_until
    if not settings.redis_url:
        return None
    now = time.monotonic()
    if _client is None:
        if now < _down_until:
            return None
        _build_client()
    if _client is None:
        return None
    if now - _last_ok < _OK_TTL:
        return _client
    try:
        await _client.ping()
        _last_ok = now
        return _client
    except Exception:
        log.warning("Redis 不可达，降级为进程内存（冷却 {}s）", _COOL_DOWN)
        _last_ok = 0.0
        _down_until = now + _COOL_DOWN
        return None


async def rate_limit_allow(key: str, limit: int, window_seconds: int):
    """Redis 滑动窗口限流判定。True=放行，False=拦截，None=不可用（调用方降级）。"""
    r = await get_redis()
    if r is None:
        return None
    try:
        now = time.time()
        result = await r.eval(
            _RATE_LIMIT_LUA,
            1,
            key,
            now,
            window_seconds * 1000,
            limit,
            # member 唯一化：同一毫秒内多次写入不能被 ZADD 覆盖合并
            f"{now:.6f}:{secrets.token_hex(4)}",
        )
        return bool(result)
    except Exception:
        log.warning("Redis 限流判定异常，降级为进程内存")
        return None


async def close_redis() -> None:
    """关闭全局连接（应用退出时调用）。"""
    global _client, _last_ok
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None
            _last_ok = 0.0