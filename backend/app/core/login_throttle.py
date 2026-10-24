"""管理员登录防爆破：单 IP 限流 + 账号连续失败锁定。

Redis 共享计数保证多副本一致；Redis 不可用时退化为进程内存（单副本语义）。
登录是低频管理操作，存储故障时不阻断管理员登录（可用性优先）。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.logger import log
from app.core.redis_client import get_redis, rate_limit_allow

_IP_KEY_PREFIX = "rl:admin-login:"
_FAIL_KEY_PREFIX = "admin:login:fail:"
_LOCK_KEY_PREFIX = "admin:login:lock:"

# 首次写入时设置窗口过期，避免失败计数永久累积
_FAIL_LUA = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('PEXPIRE', KEYS[1], ARGV[1]) end
return n
"""

_local_ip_hits: dict[str, deque] = defaultdict(deque)
_local_fails: dict[str, tuple[int, float]] = {}
_local_locks: dict[str, float] = {}


def _normalize(username: str) -> str:
    return (username or "").strip().lower() or "unknown"


def _sweep(now: float) -> None:
    for ip, hits in list(_local_ip_hits.items()):
        if not hits or now - hits[-1] > 120:
            _local_ip_hits.pop(ip, None)
    window = max(60, settings.admin_login_fail_window_seconds)
    for user, (_count, started) in list(_local_fails.items()):
        if now - started > window:
            _local_fails.pop(user, None)
    for user, until in list(_local_locks.items()):
        if now >= until:
            _local_locks.pop(user, None)


async def ip_login_allowed(ip: str) -> bool:
    """单 IP 每分钟登录尝试上限；limit<=0 关闭。"""
    limit = settings.admin_login_ip_limit
    if limit <= 0:
        return True
    verdict = await rate_limit_allow(f"{_IP_KEY_PREFIX}{ip or 'unknown'}", limit, 60)
    if verdict is not None:
        return verdict
    now = time.monotonic()
    _sweep(now)
    hits = _local_ip_hits[ip or "unknown"]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= limit:
        return False
    hits.append(now)
    return True


async def account_login_locked(username: str) -> bool:
    """账号是否处于失败锁定期；lock_seconds<=0 或 max_fails<=0 关闭锁定。"""
    if settings.admin_login_lock_seconds <= 0 or settings.admin_login_max_fails <= 0:
        return False
    user = _normalize(username)
    now = time.monotonic()
    _sweep(now)
    if _local_locks.get(user, 0.0) > now:
        return True
    r = await get_redis()
    if r is None:
        return False
    try:
        return bool(await r.exists(f"{_LOCK_KEY_PREFIX}{user}"))
    except Exception as e:
        log.warning("[login-throttle] 锁定查询异常，按进程内存判定: {}", e)
        return False


async def record_login_failure(username: str) -> bool:
    """记录一次密码错误；达到阈值即锁定并返回 True。"""
    max_fails = settings.admin_login_max_fails
    lock_seconds = settings.admin_login_lock_seconds
    if max_fails <= 0 or lock_seconds <= 0:
        return False
    user = _normalize(username)
    window_ms = max(60, settings.admin_login_fail_window_seconds) * 1000
    r = await get_redis()
    if r is not None:
        try:
            count = int(await r.eval(_FAIL_LUA, 1, f"{_FAIL_KEY_PREFIX}{user}", window_ms))
            if count >= max_fails:
                await r.set(f"{_LOCK_KEY_PREFIX}{user}", "1", ex=lock_seconds)
                return True
            return False
        except Exception as e:
            log.warning("[login-throttle] 失败计数异常，降级进程内存: {}", e)
    now = time.monotonic()
    _sweep(now)
    count, started = _local_fails.get(user, (0, now))
    if now - started > max(60, settings.admin_login_fail_window_seconds):
        count, started = 0, now
    count += 1
    _local_fails[user] = (count, started)
    if count >= max_fails:
        _local_locks[user] = now + lock_seconds
        return True
    return False


async def clear_login_failures(username: str) -> None:
    """登录成功后清除失败计数与锁定。"""
    user = _normalize(username)
    _local_fails.pop(user, None)
    _local_locks.pop(user, None)
    r = await get_redis()
    if r is None:
        return
    try:
        await r.delete(f"{_FAIL_KEY_PREFIX}{user}", f"{_LOCK_KEY_PREFIX}{user}")
    except Exception as e:
        log.warning("[login-throttle] 清理失败计数异常: {}", e)
