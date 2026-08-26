"""用户账户存储（昵称 + 密码登录，多端同步）。

主存储为 PostgreSQL，复用 app.memory.postgres_memory 的模块级连接池；
密码用 pbkdf2_hmac 加盐哈希，登录后签发随机 token 存库（支持多端）。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
import uuid
from typing import Optional

from app.core.logger import log
from app.memory.postgres_memory import _get_pool

_TABLE_READY = False

# get_by_token 高频调用下每请求都 UPDATE last_active_at 会写放大，
# 进程内按 uid 记录上次刷新时间，间隔内不重复写
_LAST_ACTIVE_FLUSH_INTERVAL = 300  # 秒
_last_active_flush: dict[str, float] = {}
_last_active_lock = threading.Lock()


def _should_flush_last_active(uid: str) -> bool:
    """是否需要刷新该用户 last_active_at（进程内节流，避免聊天高频写放大）。"""
    now = time.time()
    with _last_active_lock:
        last = _last_active_flush.get(uid, 0)
        if now - last < _LAST_ACTIVE_FLUSH_INTERVAL:
            return False
        _last_active_flush[uid] = now
        return True


def _hash_password(password: str, salt: str) -> str:
    """使用 pbkdf2_hmac(sha256) + 盐值对密码进行哈希，返回十六进制字符串。"""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000
    ).hex()


def _ensure_table():
    """惰性建表：首次调用时创建 users 表与索引（兼容旧库补 wx_openid 列）。"""
    global _TABLE_READY
    if _TABLE_READY:
        return
    try:
        with _get_pool().connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    nickname TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    avatar TEXT DEFAULT '',
                    wx_openid TEXT UNIQUE,
                    token TEXT,
                    token_created_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    last_active_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
            conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS wx_openid TEXT UNIQUE")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_wx_openid ON users(wx_openid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_token ON users(token)")
        _TABLE_READY = True
        log.info("用户表(users)已就绪")
    except Exception as e:
        log.warning("用户表(users)创建失败: {}", e)


def create_user(nickname: str, password: str) -> dict:
    """注册新用户；昵称重复或参数非法时抛 ValueError。返回用户字典（含 token）。"""
    nickname = (nickname or "").strip()
    if len(nickname) < 2 or len(nickname) > 20:
        raise ValueError("昵称需为 2-20 个字符")
    if len(password or "") < 6:
        raise ValueError("密码至少 6 位")
    _ensure_table()
    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)
    token = secrets.token_hex(32)
    uid = str(uuid.uuid4())
    with _get_pool().connection() as conn:
        # SELECT-then-INSERT 存在竞态窗口，同昵称并发注册由下方 UNIQUE 约束兜底
        exists = conn.execute(
            "SELECT id FROM users WHERE nickname = %s", (nickname,)
        ).fetchone()
        if exists:
            raise ValueError("该昵称已被占用")
        try:
            conn.execute(
                """
                INSERT INTO users (id, nickname, password_hash, password_salt, token, token_created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (uid, nickname, password_hash, salt, token),
            )
        except Exception as e:
            # 并发撞 UNIQUE 约束 → 转换为与前置检查一致的 ValueError
            if getattr(e, "sqlstate", None) == "23505":
                raise ValueError("该昵称已被占用") from e
            raise
    return _public_user(
        {
            "id": uid,
            "nickname": nickname,
            "avatar": "",
            "token": token,
            "created_at": None,
            "last_active_at": None,
        }
    )


def authenticate(nickname: str, password: str) -> Optional[dict]:
    """校验昵称+密码；成功返回含 token 的用户字典，失败返回 None。"""
    nickname = (nickname or "").strip()
    _ensure_table()
    with _get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id, nickname, avatar, password_hash, password_salt, token FROM users WHERE nickname = %s",
            (nickname,),
        ).fetchone()
        if not row:
            return None
        uid, nick, avatar, pw_hash, pw_salt, token = row
        # 常数时间比较，防时序侧信道
        if not hmac.compare_digest(_hash_password(password, pw_salt), pw_hash):
            return None
        if not token:
            token = secrets.token_hex(32)
            conn.execute(
                "UPDATE users SET token = %s, token_created_at = NOW() WHERE id = %s",
                (token, uid),
            )
        conn.execute("UPDATE users SET last_active_at = NOW() WHERE id = %s", (uid,))
        return _public_user(
            {"id": str(uid), "nickname": nick, "avatar": avatar or "", "token": token}
        )


def get_by_token(token: str) -> Optional[dict]:
    """按登录 token 查询用户；token 为空或查询/其他异常时返回 None。"""
    if not token:
        return None
    _ensure_table()
    try:
        with _get_pool().connection() as conn:
            row = conn.execute(
                "SELECT id, nickname, avatar FROM users WHERE token = %s", (token,)
            ).fetchone()
            if not row:
                return None
            if _should_flush_last_active(str(row[0])):
                conn.execute(
                    "UPDATE users SET last_active_at = NOW() WHERE id = %s", (row[0],)
                )
            return _public_user(
                {"id": str(row[0]), "nickname": row[1], "avatar": row[2] or ""}
            )
    except Exception as e:
        log.warning("按 token 查用户失败: {}", e)
        return None


def get_by_id(uid: str) -> Optional[dict]:
    """按用户 id 查询公开用户字典；失败返回 None。"""
    _ensure_table()
    try:
        with _get_pool().connection() as conn:
            row = conn.execute(
                "SELECT id, nickname, avatar FROM users WHERE id = %s", (uid,)
            ).fetchone()
            if not row:
                return None
            return _public_user(
                {"id": str(row[0]), "nickname": row[1], "avatar": row[2] or ""}
            )
    except Exception as e:
        log.warning("按 id 查用户失败: {}", e)
        return None


def update_user(uid: str, nickname: str = None, avatar: str = None, password: str = None) -> dict:
    """更新昵称/头像/密码；返回更新后的用户字典。"""
    _ensure_table()
    sets, params = [], []
    if nickname is not None:
        nickname = nickname.strip()
        if len(nickname) < 2 or len(nickname) > 20:
            raise ValueError("昵称需为 2-20 个字符")
        sets.append("nickname = %s")
        params.append(nickname)
    if avatar is not None:
        sets.append("avatar = %s")
        params.append(avatar)
    if password is not None:
        if len(password) < 6:
            raise ValueError("密码至少 6 位")
        salt = secrets.token_hex(16)
        sets.append("password_hash = %s")
        sets.append("password_salt = %s")
        params.extend([_hash_password(password, salt), salt])
        # 改密码则作废旧 token，强制重新登录
        sets.append("token = %s")
        params.append(secrets.token_hex(32))
    if not sets:
        raise ValueError("没有可更新的字段")
    params.append(uid)
    with _get_pool().connection() as conn:
        if nickname is not None:
            dup = conn.execute(
                "SELECT id FROM users WHERE nickname = %s AND id <> %s", (nickname, uid)
            ).fetchone()
            if dup:
                raise ValueError("该昵称已被占用")
        conn.execute(
            "UPDATE users SET {} WHERE id = %s".format(", ".join(sets)), params
        )
    return get_by_id(uid)


def list_users(limit: int = 200, offset: int = 0) -> list:
    """管理后台：列出用户（含统计）。"""
    _ensure_table()
    with _get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, nickname, avatar, created_at, last_active_at
            FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s
            """,
            (limit, offset),
        ).fetchall()
        return [
            {
                "id": str(r[0]),
                "nickname": r[1],
                "avatar": r[2] or "",
                "createdAt": str(r[3]) if r[3] else "",
                "lastActiveAt": str(r[4]) if r[4] else "",
            }
            for r in rows
        ]


def count_users() -> int:
    """返回用户总数。"""
    _ensure_table()
    with _get_pool().connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return int(row[0]) if row else 0


def create_or_get_by_wxopenid(wx_openid: str, nickname: str = None) -> dict:
    """微信登录：按 openid 查找用户，不存在则自动注册（生成随机昵称）。返回含 token 的用户字典。"""
    _ensure_table()
    with _get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id, nickname, avatar FROM users WHERE wx_openid = %s", (wx_openid,)
        ).fetchone()
        if row:
            uid, nick, avatar = row
            token = secrets.token_hex(32)
            conn.execute(
                "UPDATE users SET token = %s, token_created_at = NOW(), last_active_at = NOW() WHERE id = %s",
                (token, uid),
            )
            return _public_user(
                {"id": str(uid), "nickname": nick, "avatar": avatar or "", "token": token}
            )
        uid = str(uuid.uuid4())
        if not nickname or not nickname.strip():
            nickname = f"微信用户_{secrets.token_hex(3)}"
        nickname = nickname.strip()
        # 微信昵称可能撞名，加数字后缀保证唯一
        base_nick = nickname
        suffix = 1
        while True:
            exists = conn.execute("SELECT id FROM users WHERE nickname = %s", (nickname,)).fetchone()
            if not exists:
                break
            suffix += 1
            nickname = f"{base_nick}_{suffix}"
        salt = secrets.token_hex(16)
        password_hash = _hash_password(secrets.token_hex(32), salt)  # 随机密码，微信登录不使用
        token = secrets.token_hex(32)
        conn.execute(
            """
            INSERT INTO users (id, nickname, password_hash, password_salt, wx_openid, token, token_created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
            (uid, nickname, password_hash, salt, wx_openid, token),
        )
        log.info("微信新用户注册: id=%s openid=...%s", uid, wx_openid[-8:])
        return _public_user(
            {"id": uid, "nickname": nickname, "avatar": "", "token": token}
        )


def _public_user(u: dict) -> dict:
    """返回给前端的用户结构（含 token 仅用于登录/注册响应）。"""
    return {
        "id": u.get("id"),
        "nickname": u.get("nickname"),
        "avatar": u.get("avatar", ""),
        "token": u.get("token"),
        "createdAt": str(u["created_at"]) if u.get("created_at") else None,
        "lastActiveAt": str(u["last_active_at"]) if u.get("last_active_at") else None,
    }
