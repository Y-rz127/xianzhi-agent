"""报告任务数据访问（同步 psycopg，异步调用方自行 to_thread）。

任务状态机：pending → running → done / failed。
payload 存储产物字节（PDF 或 Markdown UTF-8），跨副本共享。
"""
from __future__ import annotations

import json
from typing import Any

from app.db.pool import get_pool

_STATUS_DONE = "done"
_STATUS_FAILED = "failed"
_STATUS_RUNNING = "running"
_STATUS_PENDING = "pending"


def _params_json(params: dict) -> str:
    """参数序列化：sort_keys 让同一组参数总是得到同一 JSON 文本（JSONB 比较本来也忽略键序）。"""
    return json.dumps(params, ensure_ascii=False, sort_keys=True)


def create_task(kind: str, params: dict, user_id: str = "") -> str:
    """新建 pending 任务（绑定提交用户），返回任务 ID。"""
    with get_pool().connection() as conn:
        row = conn.execute(
            """INSERT INTO report_tasks (kind, params, user_id) VALUES (%s, %s::jsonb, %s) RETURNING id""",
            (kind, _params_json(params), user_id or ""),
        ).fetchone()
        return str(row[0])


def get_task(task_id: str) -> dict | None:
    with get_pool().connection() as conn:
        row = conn.execute(
            """SELECT id, kind, params, status, payload, error, created_at, updated_at, user_id
               FROM report_tasks WHERE id = %s""",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)


def find_same_task(kind: str, params: dict, user_id: str = "", within_hours: int = 1) -> str | None:
    """查找同一用户的同参数任务：pending/running 直接复用；done 且未过期（1 小时内）也复用。"""
    with get_pool().connection() as conn:
        row = conn.execute(
            """SELECT id FROM report_tasks
               WHERE kind = %s AND params = %s::jsonb AND user_id = %s
                 AND (status IN ('pending', 'running')
                      OR (status = 'done' AND updated_at > now() - interval '%s hours'))
               ORDER BY created_at DESC LIMIT 1""",
            (kind, _params_json(params), user_id or "", within_hours),
        ).fetchone()
        return str(row[0]) if row else None


def get_or_create_task(
    kind: str, params: dict, user_id: str = "", within_hours: int = 1
) -> tuple[str, str, bool]:
    """原子查重并建任务，返回 (task_id, status, created)。

    为什么需要：先 find 再 create 是典型的 check-then-act 竞态——两个并发提交都查不到，
    结果生成两份报告、烧两倍 LLM。这里用事务级 advisory lock 把同键提交串行化；
    连接池是 autocommit，必须显式 `conn.transaction()` 包住锁与查询，否则锁语句
    提交后立即释放，等于没锁。
    """
    params_json = _params_json(params)
    lock_key = f"{kind}\x1f{params_json}\x1f{user_id or ''}"
    with get_pool().connection() as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_key,))
            row = conn.execute(
                """SELECT id, status FROM report_tasks
                   WHERE kind = %s AND params = %s::jsonb AND user_id = %s
                     AND (status IN ('pending', 'running')
                          OR (status = 'done' AND updated_at > now() - interval '%s hours'))
                   ORDER BY created_at DESC LIMIT 1""",
                (kind, params_json, user_id or "", within_hours),
            ).fetchone()
            if row:
                return str(row[0]), str(row[1]), False
            row = conn.execute(
                """INSERT INTO report_tasks (kind, params, user_id)
                   VALUES (%s, %s::jsonb, %s) RETURNING id, status""",
                (kind, params_json, user_id or ""),
            ).fetchone()
            return str(row[0]), str(row[1]), True


def delete_task(task_id: str) -> None:
    """删除尚未入队的 pending 任务（配额拒绝时回滚，避免留下孤儿任务）。"""
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM report_tasks WHERE id = %s AND status = 'pending'", (task_id,))


def mark_running(task_id: str) -> bool:
    """pending → running。返回是否抢占成功（false = 状态已变，放弃执行）。"""
    with get_pool().connection() as conn:
        row = conn.execute(
            """UPDATE report_tasks SET status = 'running', updated_at = now()
               WHERE id = %s AND status = 'pending' RETURNING id""",
            (task_id,),
        ).fetchone()
        return row is not None


def complete(task_id: str, payload: bytes) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            """UPDATE report_tasks SET status = 'done', payload = %s, updated_at = now()
               WHERE id = %s""",
            (payload, task_id),
        )


def fail(task_id: str, error: str) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            """UPDATE report_tasks SET status = 'failed', error = %s, updated_at = now()
               WHERE id = %s""",
            (error[:1000], task_id),
        )


def list_pending(limit: int = 500) -> list[str]:
    """列出仍处于 pending 的任务 ID（启动时重新入队，覆盖取号后崩溃的孤儿）。"""
    with get_pool().connection() as conn:
        rows = conn.execute(
            """SELECT id FROM report_tasks WHERE status = 'pending'
               ORDER BY created_at LIMIT %s""",
            (limit,),
        ).fetchall()
    return [str(row[0]) for row in rows]


def reconcile_after_restart() -> None:
    """启动时修复悬挂任务：running（执行到一半进程死了）→ failed。

    pending 不在这里判失败：交由启动流程重新入队（tasks.worker.requeue_pending）。
    取号后进程崩溃的任务 DB 仍是 pending、队列里却没有它，重新入队才能继续执行；
    队列积压导致的 pending 也不该被误杀。
    """
    with get_pool().connection() as conn:
        conn.execute(
            """UPDATE report_tasks SET status = 'failed', error = '服务重启中断，请重新提交', updated_at = now()
               WHERE status = 'running'"""
        )


def delete_old(days: int = 7) -> None:
    """清理过期任务及其产物（提交新任务时顺带执行，低频够用）。"""
    with get_pool().connection() as conn:
        conn.execute(
            """DELETE FROM report_tasks
               WHERE updated_at < now() - interval '%s days' AND status IN ('done', 'failed')""",
            (days,),
        )


def _row_to_dict(row: Any) -> dict:
    return {
        "id": str(row[0]),
        "kind": row[1],
        "params": row[2] if isinstance(row[2], dict) else json.loads(row[2]),
        "status": row[3],
        "payload": row[4],
        "error": row[5],
        "created_at": row[6],
        "updated_at": row[7],
        "user_id": row[8] or "",
    }
