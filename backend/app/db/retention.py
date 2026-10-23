"""用户数据保留期清理：删除超过保留天数的会话消息、生辰、命盘画像与反馈。

默认 90 天；`MESSAGE_RETENTION_DAYS=0` 表示不自动清理。
显式保存的命例（cases/chart_cases）与收藏不在此列，避免误删用户主动保存的内容。
"""
from __future__ import annotations

from app.core.logger import log
from app.db.pool import get_pool


def purge_expired(days: int) -> dict[str, int]:
    """按保留期清理过期数据，返回各表删除行数。"""
    keep_days = int(days or 0)
    if keep_days <= 0:
        return {}
    stats: dict[str, int] = {}
    with get_pool().connection() as conn:
        with conn.transaction():
            # 会话消息与生辰信息：仅清理超过保留期未活动的会话
            cur = conn.execute(
                """DELETE FROM message_store
                   WHERE session_id IN (
                       SELECT session_id FROM session_metadata
                       WHERE updated_at < now() - make_interval(days => %s)
                   )""",
                (keep_days,),
            )
            stats["messages"] = cur.rowcount or 0
            cur = conn.execute(
                """DELETE FROM session_birth_info
                   WHERE session_id IN (
                       SELECT session_id FROM session_metadata
                       WHERE updated_at < now() - make_interval(days => %s)
                   )""",
                (keep_days,),
            )
            stats["session_birth_info"] = cur.rowcount or 0
            cur = conn.execute(
                """DELETE FROM session_metadata
                   WHERE updated_at < now() - make_interval(days => %s)""",
                (keep_days,),
            )
            stats["sessions"] = cur.rowcount or 0

            # 命盘画像（chart_facts 由外键级联删除）
            cur = conn.execute(
                """DELETE FROM chart_profiles
                   WHERE updated_at < now() - make_interval(days => %s)""",
                (keep_days,),
            )
            stats["chart_profiles"] = cur.rowcount or 0

            # 含用户问题/回答的反馈与解读记录
            cur = conn.execute(
                """DELETE FROM answer_feedback
                   WHERE created_at < now() - make_interval(days => %s)""",
                (keep_days,),
            )
            stats["answer_feedback"] = cur.rowcount or 0
            cur = conn.execute(
                """DELETE FROM ai_interpretation_records
                   WHERE created_at < now() - make_interval(days => %s)""",
                (keep_days,),
            )
            stats["ai_interpretation_records"] = cur.rowcount or 0
            cur = conn.execute(
                """DELETE FROM feedback
                   WHERE created_at < now() - make_interval(days => %s)""",
                (keep_days,),
            )
            stats["feedback"] = cur.rowcount or 0
    return stats


def purge_expired_safely(days: int) -> dict[str, int]:
    """后台任务调用入口：失败只告警，不影响主流程。"""
    try:
        return purge_expired(days)
    except Exception as e:
        log.warning("[retention] 过期数据清理失败（下一轮重试）: {}", e)
        return {}
