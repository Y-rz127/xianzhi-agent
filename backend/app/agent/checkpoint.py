"""LangGraph Postgres checkpointer 的进程级单例。

PostgresSaver 内部持有一把操作锁，并支持 psycopg_pool.ConnectionPool：
每个 checkpoint 读写从池中借连接，DB 操作本身串行，LLM 调用不在锁内，
不会把并发工作流整体串行化。

进程崩溃/重启后，同一 turn_id 的 checkpoint 可由 `invoke(None, config)` 续跑。
"""
from __future__ import annotations

import threading
from typing import Any

from app.core.config import settings
from app.core.logger import log
from app.db.pool import close_checkpoint_pool, get_checkpoint_pool

_saver: Any = None
_init_lock = threading.Lock()


def init_checkpointer() -> bool:
    """启动时初始化并建表；失败只告警，服务按无 checkpointer 模式继续。"""
    global _saver
    if not settings.checkpoint_enabled:
        log.info("LangGraph checkpointer 未启用（CHECKPOINTER_ENABLED=false）")
        return False
    with _init_lock:
        if _saver is not None:
            return True
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            saver = PostgresSaver(get_checkpoint_pool())
            saver.setup()
            _saver = saver
            log.info("LangGraph checkpointer 已启用（Postgres）")
            return True
        except Exception as e:
            log.warning("LangGraph checkpointer 初始化失败，按无断点模式运行: {}", e)
            return False


def get_checkpointer():
    """返回共享 checkpointer；未启用/初始化失败返回 None。"""
    if not settings.checkpoint_enabled:
        return None
    return _saver


def delete_checkpoint_thread(thread_id: str) -> None:
    """删除某一轮的 checkpoint（成功后调用，避免表无限增长）。"""
    saver = _saver
    if saver is None or not thread_id:
        return
    try:
        saver.delete_thread(thread_id)
    except Exception as e:
        log.warning("[checkpoint] 删除 thread={} 失败: {}", thread_id, e)


# 按 thread 最新 checkpoint 的 ts 判定最后活动时间（checkpoint_id 由 uuid6 生成、
# 字符串可排序，但直接换算截止 ID 依赖内部实现，读 checkpoint->>'ts' 更直观）
_STALE_THREADS_SQL = """
SELECT thread_id FROM checkpoints
GROUP BY thread_id
HAVING max((checkpoint->>'ts')::timestamptz) < now() - make_interval(hours => %s)
"""


def purge_stale_checkpoints(max_age_hours: int) -> int:
    """清理超时未再续跑的残留 checkpoint，返回删除的 thread 数。

    正常回合成功后由 delete_checkpoint_thread 即时删除，这里只兜底异常中断
    （进程崩溃/超时）留下的 thread，避免 checkpoint 表长期累积。
    """
    hours = int(max_age_hours or 0)
    if _saver is None or hours <= 0:
        return 0
    try:
        with get_checkpoint_pool().connection() as conn:
            with conn.transaction():
                stale = [r["thread_id"] for r in conn.execute(_STALE_THREADS_SQL, (hours,))]
                if stale:
                    conn.execute("DELETE FROM checkpoint_writes WHERE thread_id = ANY(%s)", (stale,))
                    conn.execute("DELETE FROM checkpoint_blobs WHERE thread_id = ANY(%s)", (stale,))
                    conn.execute("DELETE FROM checkpoints WHERE thread_id = ANY(%s)", (stale,))
    except Exception as e:
        log.warning("[checkpoint] 残留清理失败（下一轮重试）: {}", e)
        return 0
    if stale:
        log.info("[checkpoint] 清理残留 thread {} 个（超过 {}h）", len(stale), hours)
    return len(stale)


def close_checkpointer() -> None:
    global _saver
    with _init_lock:
        _saver = None
    close_checkpoint_pool()
