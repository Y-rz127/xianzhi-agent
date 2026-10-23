"""付费接口日配额：Redis 原子计数，Redis 不可用时 fail-closed。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.core.config import settings
from app.core.logger import log
from app.core.redis_client import get_redis

_CST = timezone(timedelta(hours=8))
_QUOTA_TTL_SECONDS = 90_000  # 25 小时，覆盖跨日
_QUOTA_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


class QuotaUnavailable(RuntimeError):
    """配额存储不可用。"""


def _today() -> str:
    return datetime.now(_CST).strftime("%Y%m%d")


async def consume_quota(scope: str, kind: str, limit: int) -> bool:
    """消耗一次配额；limit<=0 表示不限。Redis 异常抛 QuotaUnavailable。"""
    if limit <= 0:
        return True
    r = await get_redis()
    if r is None:
        raise QuotaUnavailable("配额服务不可用")
    key = f"quota:{kind}:{scope}:{_today()}"
    try:
        count = await r.eval(_QUOTA_LUA, 1, key, _QUOTA_TTL_SECONDS)
    except Exception as e:
        log.warning("[quota] Redis 计数失败: {}", e)
        raise QuotaUnavailable("配额服务不可用") from e
    return int(count) <= limit


def quota_scope(principal: dict | None, ip: str) -> str:
    if principal and principal.get("id"):
        return f"user:{principal['id']}"
    return f"ip:{ip or 'unknown'}"


async def enforce_quota(kind: str, principal: dict | None, ip: str, user_limit: int) -> None:
    """登录用户按账号配额，游客按 IP + 全局游客配额；超限 429，存储故障 503。"""
    limit = user_limit if principal else settings.paid_quota_guest_daily
    try:
        allowed = await consume_quota(quota_scope(principal, ip), kind, limit)
    except QuotaUnavailable as e:
        raise HTTPException(status_code=503, detail="配额服务暂不可用，请稍后再试") from e
    if not allowed:
        raise HTTPException(status_code=429, detail="今日使用次数已达上限，请明天再试")
