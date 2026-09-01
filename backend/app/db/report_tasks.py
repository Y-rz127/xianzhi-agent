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


def create_task(kind: str, params: dict) -> str:
    """新建 pending 任务，返回任务 ID。"""
    with get_pool().connection() as conn:
        row = conn.execute(
            """INSERT INTO report_tasks (kind, params) VALUES (%s, %s) RETURNING id""",
            (kind, json.dumps(params, ensure_ascii=False)),
        ).fetchone()
        return str(row[0])


def get_task(task_id: str) -> dict | None:
    with get_pool().connection() as conn:
        row = conn.execute(
            """SELECT id, kind, params, status, payload, error, created_at, updated_at
               FROM report_tasks WHERE id = %s""",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)


def find_same_task(kind: str, params: dict, within_hours: int = 1) -> str | None:
    """查找同参数任务：pending/running 直接复用；done 且未过期（1 小时内）也复用。"""
    with get_pool().connection() as conn:
        row = conn.execute(
            """SELECT id FROM report_tasks
               WHERE kind = %s AND params = %s
                 AND (status IN ('pending', 'running')
                      OR (status = 'done' AND updated_at > now() - interval '%s hours'))
               ORDER BY created_at DESC LIMIT 1""",
            (kind, json.dumps(params, ensure_ascii=False), within_hours),
        ).fetchone()
        return str(row[0]) if row else None


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


def reconcile_after_restart(stale_pending_minutes: int = 10) -> None:
    """启动时修复悬挂任务（worker 崩溃/重启导致）：
    - running：执行到一半进程死了 → failed
    - pending 超时：入队消息已被消费但状态未推进（BRPOP 与 mark_running 之间崩溃）→ failed
    """
    with get_pool().connection() as conn:
        conn.execute(
            """UPDATE report_tasks SET status = 'failed', error = '服务重启中断，请重新提交', updated_at = now()
               WHERE status = 'running'"""
        )
        conn.execute(
            """UPDATE report_tasks SET status = 'failed', error = '任务超时未执行，请重新提交', updated_at = now()
               WHERE status = 'pending' AND created_at < now() - interval '%s minutes'""",
            (stale_pending_minutes,),
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
    }