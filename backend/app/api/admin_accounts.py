"""管理员账号管理 API。"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/admin/accounts", tags=["Admin Accounts"])

ADMIN_DATA_FILE = Path("./data/admin_accounts.json")

# 账号数据保存在本地 JSON，因此哈希格式必须带上算法、迭代次数和盐值，
# 以便后续调整参数而不破坏已有账户。
_PASSWORD_SCHEME = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 310_000
_MAX_PASSWORD_ITERATIONS = 1_000_000


def _load_accounts() -> list[dict]:
    if not ADMIN_DATA_FILE.exists():
        return []
    try:
        with open(ADMIN_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save_accounts(accounts: list[dict]) -> None:
    ADMIN_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ADMIN_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


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


def _init_default_admin() -> None:
    """首次启动时从环境变量初始化默认管理员（未配置则跳过，生产环境更安全）。"""
    accounts = _load_accounts()
    if accounts:
        return
    username = os.environ.get("DEFAULT_ADMIN_USERNAME", "").strip()
    password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "").strip()
    if not username or not password:
        return
    accounts.append({
        "id": "default",
        "username": username,
        "password_hash": _hash_admin_password(password),
        "nickname": "超级管理员",
        "enabled": True,
        "is_super": True,
        "created_at": datetime.datetime.now().isoformat(),
    })
    _save_accounts(accounts)


_init_default_admin()


@router.post("/login")
async def admin_login(req: Request) -> dict:
    body = await req.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    accounts = _load_accounts()
    for acc in accounts:
        if acc.get("username") != username:
            continue
        password_matches, needs_migration = _verify_admin_password(
            password, acc.get("password_hash", "")
        )
        if password_matches:
            if not acc.get("enabled", True):
                raise HTTPException(status_code=403, detail="账号已被禁用")
            if needs_migration:
                acc["password_hash"] = _hash_admin_password(password)
                _save_accounts(accounts)
            return {
                "id": acc["id"],
                "username": acc["username"],
                "nickname": acc.get("nickname", ""),
            }
    raise HTTPException(status_code=401, detail="用户名或密码错误")


@router.get("")
async def list_admin_accounts() -> dict:
    accounts = [
        {
            "id": acc["id"],
            "username": acc["username"],
            "nickname": acc.get("nickname", ""),
            "enabled": acc.get("enabled", True),
            "is_super": acc.get("is_super", acc["id"] == "default"),
            "created_at": acc.get("created_at", ""),
        }
        for acc in _load_accounts()
    ]
    return {"total": len(accounts), "accounts": accounts}


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
    accounts = _load_accounts()
    if any(acc.get("username") == username for acc in accounts):
        raise HTTPException(status_code=409, detail="用户名已存在")
    new_account = {
        "id": f"acc_{uuid.uuid4().hex}",
        "username": username,
        "password_hash": _hash_admin_password(password),
        "nickname": nickname or username,
        "enabled": True,
        "created_at": datetime.datetime.now().isoformat(),
    }
    accounts.append(new_account)
    _save_accounts(accounts)
    return {"id": new_account["id"], "username": new_account["username"], "message": "创建成功"}


@router.put("/{account_id}")
async def update_admin_account(account_id: str, req: Request) -> dict:
    body = await req.json()
    accounts = _load_accounts()
    for i, acc in enumerate(accounts):
        if acc["id"] == account_id:
            if "nickname" in body:
                accounts[i]["nickname"] = body["nickname"]
            if "password" in body and body["password"]:
                if len(body["password"]) < 4:
                    raise HTTPException(status_code=400, detail="密码长度至少 4 个字符")
                accounts[i]["password_hash"] = _hash_admin_password(body["password"])
            if "enabled" in body:
                if acc.get("is_super", acc["id"] == "default") and not bool(body["enabled"]):
                    raise HTTPException(status_code=403, detail="不能禁用超级管理员账号")
                accounts[i]["enabled"] = bool(body["enabled"])
            _save_accounts(accounts)
            return {"message": "更新成功"}
    raise HTTPException(status_code=404, detail="账号不存在")


@router.delete("/{account_id}")
async def delete_admin_account(account_id: str) -> dict:
    if account_id == "default":
        raise HTTPException(status_code=403, detail="不能删除超级管理员账号")
    accounts = _load_accounts()
    kept = [acc for acc in accounts if acc["id"] != account_id]
    if len(kept) == len(accounts):
        raise HTTPException(status_code=404, detail="账号不存在")
    _save_accounts(kept)
    return {"message": "删除成功"}
