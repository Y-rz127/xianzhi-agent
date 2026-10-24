"""管理员账号管理 API（账号数据存 PG，多副本共享、重启不丢）。"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import json
import os
import uuid

from fastapi import APIRouter, HTTPException, Request

from app.core.admin_token import create_admin_token
from app.core.config import settings
from app.core.http.client_ip import client_ip_from_request
from app.core.logger import log
from app.core.login_throttle import (
    account_login_locked,
    clear_login_failures,
    ip_login_allowed,
    record_login_failure,
)
from app.core.observability import record_error
from app.db import admin_accounts as admin_store

router = APIRouter(prefix="/admin/accounts", tags=["Admin Accounts"])

# 旧版账号文件：仅用于首次启动播种到 PG，导入后改名为 .imported，不再读写
ADMIN_DATA_FILE = settings.data_dir / "admin_accounts.json"

_PASSWORD_SCHEME = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 310_000
_MAX_PASSWORD_ITERATIONS = 1_000_000


def _hash_admin_password(password: str, salt: bytes | None = None) -> str:
    """生成自描述的 PBKDF2 密码哈希，供管理员账户持久化使用。"""
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PASSWORD_ITERATIONS
    )
    return f"{_PASSWORD_SCHEME}${_PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_admin_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """验证密码，返回 ``(匹配, 需要迁移)``。

    旧版账户使用无盐 SHA-256。成功验证后由登录流程立即替换为 PBKDF2，
    因此升级不会中断既有管理员的访问。
    """
    if not isinstance(stored_hash, str) or not stored_hash:
        return False, False
    if "$" not in stored_hash:
        legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy_hash, stored_hash), True

    try:
        scheme, iterations, salt_hex, expected_hex = stored_hash.split("$", 3)
        if scheme != _PASSWORD_SCHEME:
            return False, False
        rounds = int(iterations)
        if not 1 <= rounds <= _MAX_PASSWORD_ITERATIONS:
            return False, False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), rounds
        ).hex()
    except (TypeError, ValueError):
        return False, False
    return hmac.compare_digest(actual, expected_hex), rounds != _PASSWORD_ITERATIONS


def _load_legacy_json() -> list[dict]:
    """读取旧版 JSON 账号文件（仅播种用）。"""
    if not ADMIN_DATA_FILE.exists():
        return []
    try:
        with open(ADMIN_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [
                    acc
                    for acc in data
                    if isinstance(acc, dict)
                    and acc.get("id")
                    and acc.get("username")
                    and acc.get("password_hash")
                ]
    except (json.JSONDecodeError, OSError) as e:
        log.warning("旧版管理员账号文件读取失败，跳过导入: {}", e)
    return []


def init_admin_accounts() -> None:
    """首次启动播种：账号表为空时导入旧 JSON（改名备份），否则按环境变量建默认管理员。"""
    if admin_store.count_accounts() > 0:
        return
    legacy = _load_legacy_json()
    if legacy:
        inserted = admin_store.insert_many(legacy)
        backup = ADMIN_DATA_FILE.with_name(ADMIN_DATA_FILE.name + ".imported")
        try:
            ADMIN_DATA_FILE.replace(backup)
        except OSError as e:
            log.warning("旧版管理员账号文件备份失败（请手工处理）: {}", e)
        log.info("已从旧版 JSON 导入 {} 个管理员账号，原文件备份为 {}", inserted, backup.name)
        return
    username = os.environ.get("DEFAULT_ADMIN_USERNAME", "").strip()
    password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "").strip()
    if not username or not password:
        return
    admin_store.create_account(
        {
            "id": "default",
            "username": username,
            "password_hash": _hash_admin_password(password),
            "nickname": "超级管理员",
            "enabled": True,
            "is_super": True,
            "created_at": datetime.datetime.now().isoformat(),
        }
    )
    log.info("已按环境变量创建默认超级管理员 {}", username)


def _db_unavailable(action: str, exc: Exception) -> None:
    log.error("管理员账号库不可用（{}），拒绝本次请求: {}", action, exc)


@router.post("/login")
async def admin_login(req: Request) -> dict:
    body = await req.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    if not await ip_login_allowed(client_ip_from_request(req)):
        record_error("admin_login_ip_limited")
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")
    if await account_login_locked(username):
        record_error("admin_login_account_locked")
        raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后再试")
    try:
        account = await asyncio.to_thread(admin_store.get_by_username, username)
    except Exception as e:
        _db_unavailable("login", e)
        raise HTTPException(status_code=503, detail="账号服务暂不可用，请稍后再试") from e
    if account is None:
        if await record_login_failure(username):
            record_error("admin_login_account_locked")
            raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后再试")
        record_error("admin_login_failed")
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    password_matches, needs_migration = _verify_admin_password(
        password, account.get("password_hash", "")
    )
    if not password_matches:
        if await record_login_failure(username):
            record_error("admin_login_account_locked")
            raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后再试")
        record_error("admin_login_failed")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not account.get("enabled", True):
        raise HTTPException(status_code=403, detail="账号已被禁用")

    if needs_migration:
        try:
            await asyncio.to_thread(
                admin_store.update_account,
                account["id"],
                {"password_hash": _hash_admin_password(password)},
            )
        except Exception as e:
            # 哈希升级失败不影响本次登录，下次登录会重试
            log.warning("管理员密码哈希升级失败: {}", e)
    await clear_login_failures(username)
    token, expires_in = create_admin_token(account)
    return {
        "id": account["id"],
        "username": account["username"],
        "nickname": account.get("nickname", ""),
        "token": token,
        "expires_in": expires_in,
    }


@router.get("")
async def list_admin_accounts() -> dict:
    try:
        accounts = await asyncio.to_thread(admin_store.list_accounts)
    except Exception as e:
        _db_unavailable("list", e)
        raise HTTPException(status_code=503, detail="账号服务暂不可用，请稍后再试") from e
    items = [
        {
            "id": acc["id"],
            "username": acc["username"],
            "nickname": acc.get("nickname", ""),
            "enabled": acc.get("enabled", True),
            "is_super": acc.get("is_super", acc["id"] == "default"),
            "created_at": acc.get("created_at", ""),
        }
        for acc in accounts
    ]
    return {"total": len(items), "accounts": items}


@router.post("")
async def create_admin_account(req: Request) -> dict:
    body = await req.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    nickname = body.get("nickname", "").strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    if len(username) < 3 or len(username) > 32:
        raise HTTPException(status_code=400, detail="用户名长度需在 3-32 个字符之间")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="密码长度至少 4 个字符")
    account = {
        "id": f"acc_{uuid.uuid4().hex}",
        "username": username,
        "password_hash": _hash_admin_password(password),
        "nickname": nickname or username,
        "enabled": True,
        "is_super": False,
        "created_at": datetime.datetime.now().isoformat(),
    }
    try:
        created = await asyncio.to_thread(admin_store.create_account, account)
    except Exception as e:
        _db_unavailable("create", e)
        raise HTTPException(status_code=503, detail="账号服务暂不可用，请稍后再试") from e
    if not created:
        raise HTTPException(status_code=409, detail="用户名已存在")
    return {"id": account["id"], "username": account["username"], "message": "创建成功"}


@router.put("/{account_id}")
async def update_admin_account(account_id: str, req: Request) -> dict:
    body = await req.json()
    try:
        current = await asyncio.to_thread(admin_store.get_by_id, account_id)
    except Exception as e:
        _db_unavailable("update", e)
        raise HTTPException(status_code=503, detail="账号服务暂不可用，请稍后再试") from e
    if current is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    fields: dict = {}
    if "nickname" in body:
        fields["nickname"] = body["nickname"]
    if "password" in body and body["password"]:
        if len(body["password"]) < 4:
            raise HTTPException(status_code=400, detail="密码长度至少 4 个字符")
        fields["password_hash"] = _hash_admin_password(body["password"])
    if "enabled" in body:
        is_super = current.get("is_super", account_id == "default")
        if is_super and not bool(body["enabled"]):
            raise HTTPException(status_code=403, detail="不能禁用超级管理员账号")
        fields["enabled"] = bool(body["enabled"])
    if not fields:
        return {"message": "更新成功"}

    try:
        updated = await asyncio.to_thread(admin_store.update_account, account_id, fields)
    except Exception as e:
        _db_unavailable("update", e)
        raise HTTPException(status_code=503, detail="账号服务暂不可用，请稍后再试") from e
    if not updated:
        raise HTTPException(status_code=404, detail="账号不存在")
    return {"message": "更新成功"}


@router.delete("/{account_id}")
async def delete_admin_account(account_id: str) -> dict:
    if account_id == "default":
        raise HTTPException(status_code=403, detail="不能删除超级管理员账号")
    try:
        deleted = await asyncio.to_thread(admin_store.delete_account, account_id)
    except Exception as e:
        _db_unavailable("delete", e)
        raise HTTPException(status_code=503, detail="账号服务暂不可用，请稍后再试") from e
    if not deleted:
        raise HTTPException(status_code=404, detail="账号不存在")
    return {"message": "删除成功"}

