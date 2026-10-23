"""对话轮次防重放：同一 client_msg_id 只执行一次，重复请求返回答已生成的结果。

前端每次发送生成一个 client_msg_id；网络重试/多标签页重复提交/代理重放会带着
同一个 ID 再来一次。这里用 Redis SET NX 抢占执行权，完成后再把答案写回，
让重复请求直接拿结果，不再调用 LLM。Redis 不可用时降级为进程内表
（单副本内仍能防重放，多副本场景由 Redis 兜底）。
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass

from app.core.logger import log
from app.core.redis_client import get_redis

STATUS_NEW = "new"
STATUS_RUNNING = "running"
STATUS_DONE = "done"

_RUNNING_TTL = 900  # 单轮生成实测可达 427s，留 2 倍余量
_DONE_TTL = 600
_LOCAL_MAX = 500

# Redis 释放：只删自己占的 running，避免误删已写入的完成结果
_RELEASE_RUNNING_LUA = """
if redis.call('GET', KEYS[1]) == 'running' then return redis.call('DEL', KEYS[1]) end
return 0
"""

_local: dict[str, tuple[float, str]] = {}
_local_lock = threading.Lock()


@dataclass(frozen=True)
class TurnState:
    """重复请求的判定结果：new=可执行，running=正在执行，done=直接复用答案。"""

    status: str
    answer: str = ""


def _key(conversation_id: str, client_msg_id: str, user_id: str) -> str:
    raw = "\x1f".join((conversation_id, user_id or "", client_msg_id))
    return "xianzhi:turn:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _parse(raw: str | None) -> TurnState:
    if not raw or raw == STATUS_RUNNING:
        return TurnState(STATUS_RUNNING)
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return TurnState(STATUS_RUNNING)
    if isinstance(data, dict) and data.get("status") == STATUS_DONE:
        return TurnState(STATUS_DONE, str(data.get("answer") or ""))
    return TurnState(STATUS_RUNNING)


def _local_begin(key: str) -> TurnState:
    now = time.monotonic()
    with _local_lock:
        # 顺手清理过期项，避免进程内存无限增长
        expired = [k for k, (exp, _v) in _local.items() if exp <= now]
        for k in expired:
            _local.pop(k, None)
        hit = _local.get(key)
        if hit:
            return _parse(hit[1])
        if len(_local) >= _LOCAL_MAX:
            oldest = min(_local, key=lambda k: _local[k][0])
            _local.pop(oldest, None)
        _local[key] = (now + _RUNNING_TTL, STATUS_RUNNING)
        return TurnState(STATUS_NEW)


async def begin_turn(conversation_id: str, client_msg_id: str, user_id: str = "") -> TurnState:
    """抢占该轮执行权；已存在时返回 running/done。"""
    key = _key(conversation_id, client_msg_id, user_id)
    r = await get_redis()
    if r is not None:
        try:
            if await r.set(key, STATUS_RUNNING, nx=True, ex=_RUNNING_TTL):
                return TurnState(STATUS_NEW)
            return _parse(await r.get(key))
        except Exception as e:
            log.warning("轮次防重放 Redis 异常，降级进程内: {}", e)
    return _local_begin(key)


async def complete_turn(
    conversation_id: str, client_msg_id: str, user_id: str, answer: str
) -> None:
    """记录本轮最终答案，供重复请求复用。"""
    key = _key(conversation_id, client_msg_id, user_id)
    value = json.dumps({"status": STATUS_DONE, "answer": answer or ""}, ensure_ascii=False)
    r = await get_redis()
    if r is not None:
        try:
            await r.set(key, value, ex=_DONE_TTL)
            return
        except Exception as e:
            log.warning("轮次结果写入 Redis 失败，降级进程内: {}", e)
    with _local_lock:
        _local[key] = (time.monotonic() + _DONE_TTL, value)


async def release_turn(conversation_id: str, client_msg_id: str, user_id: str = "") -> None:
    """本轮失败时释放执行权，允许用户立即重试。"""
    key = _key(conversation_id, client_msg_id, user_id)
    r = await get_redis()
    if r is not None:
        try:
            await r.eval(_RELEASE_RUNNING_LUA, 1, key)
            return
        except Exception as e:
            log.warning("轮次执行权释放失败: {}", e)
    with _local_lock:
        hit = _local.get(key)
        if hit and hit[1] == STATUS_RUNNING:
            _local.pop(key, None)
