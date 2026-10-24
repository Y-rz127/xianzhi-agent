"""管理员账号数据访问（同步 psycopg，异步调用方自行 to_thread）。"""
from __future__ import annotations

from typing import Any

from psycopg.errors import UniqueViolation

from app.db.pool import get_pool

_COLUMNS = "id, username, password_hash, nickname, enabled, is_super, created_at"


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "username": row[1],
        "password_hash": row[2],
        "nickname": row[3],
        "enabled": row[4],
        "is_super": row[5],
        "created_at": row[6].isoformat() if row[6] else "",
    }


def list_accounts() -> list[dict]:
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM admin_accounts ORDER BY created_at, username"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def count_accounts() -> int:
    with get_pool().connection() as conn:
        row = conn.execute("SELECT count(*) FROM admin_accounts").fetchone()
    return int(row[0]) if row else 0


def get_by_username(username: str) -> dict | None:
    with get_pool().connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM admin_accounts WHERE username = %s", (username,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_by_id(account_id: str) -> dict | None:
    with get_pool().connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM admin_accounts WHERE id = %s", (account_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_account(account: dict) -> bool:
    """插入账号；用户名冲突返回 False（并发下也由唯一约束兜住）。"""
    try:
        with get_pool().connection() as conn:
            conn.execute(
                """INSERT INTO admin_accounts
                       (id, username, password_hash, nickname, enabled, is_super, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s::timestamptz, now()))""",
                (
                    account["id"],
                    account["username"],
                    account["password_hash"],
                    account.get("nickname") or account["username"],
                    account.get("enabled", True),
                    account.get("is_super", False),
                    account.get("created_at") or None,
                ),
            )
        return True
    except UniqueViolation:
        return False


def insert_many(accounts: list[dict]) -> int:
    """批量播种（旧 JSON 导入），已存在的主键/用户名跳过，返回实际插入条数。"""
    if not accounts:
        return 0
    inserted = 0
    with get_pool().connection() as conn:
        for account in accounts:
            result = conn.execute(
                """INSERT INTO admin_accounts
                       (id, username, password_hash, nickname, enabled, is_super, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s::timestamptz, now()))
                   ON CONFLICT DO NOTHING""",
                (
                    account["id"],
                    account["username"],
                    account["password_hash"],
                    account.get("nickname") or account["username"],
                    account.get("enabled", True),
                    account.get("is_super", False),
                    account.get("created_at") or None,
                ),
            )
            inserted += result.rowcount or 0
    return inserted


def update_account(account_id: str, fields: dict[str, Any]) -> bool:
    """按传入字段更新；无字段或无匹配行返回 False。"""
    allowed = {
        key: value
        for key, value in fields.items()
        if key in ("nickname", "password_hash", "enabled")
    }
    if not allowed:
        return False
    assignments = ", ".join(f"{key} = %s" for key in allowed)
    params = [*allowed.values(), account_id]
    with get_pool().connection() as conn:
        result = conn.execute(
            f"UPDATE admin_accounts SET {assignments}, updated_at = now() WHERE id = %s",
            params,
        )
    return bool(result.rowcount)


def delete_account(account_id: str) -> bool:
    with get_pool().connection() as conn:
        result = conn.execute("DELETE FROM admin_accounts WHERE id = %s", (account_id,))
    return bool(result.rowcount)
