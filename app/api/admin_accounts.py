"""管理员账号管理 API。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/admin/accounts", tags=["Admin Accounts"])

ADMIN_DATA_FILE = Path("./data/admin_accounts.json")


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


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _init_default_admin() -> None:
    accounts = _load_accounts()
    if not accounts:
        import datetime
        accounts.append({
            "id": "default",
            "username": "Yrz666",
            "password_hash": _hash_password("20040505"),
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
        if acc.get("username") == username and acc.get("password_hash") == _hash_password(password):
            if not acc.get("enabled", True):
                raise HTTPException(status_code=403, detail="账号已被禁用")
            return {
                "id": acc["id"],
                "username": acc["username"],
                "nickname": acc.get("nickname", ""),
            }
    raise HTTPException(status_code=401, detail="用户名或密码错误")


@router.get("")
async def list_admin_accounts() -> dict:
    accounts = _load_accounts()
    result = []
    for acc in accounts:
        result.append({
            "id": acc["id"],
            "username": acc["username"],
            "nickname": acc.get("nickname", ""),
            "enabled": acc.get("enabled", True),
            "is_super": acc.get("is_super", acc["id"] == "default"),
            "created_at": acc.get("created_at", ""),
        })
    return {"total": len(result), "accounts": result}


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
    for acc in accounts:
        if acc.get("username") == username:
            raise HTTPException(status_code=409, detail="用户名已存在")
    import time, datetime
    new_id = f"acc_{int(time.time())}"
    new_account = {
        "id": new_id,
        "username": username,
        "password_hash": _hash_password(password),
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
                accounts[i]["password_hash"] = _hash_password(body["password"])
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
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc["id"] != account_id]
    if len(accounts) == original_len:
        raise HTTPException(status_code=404, detail="账号不存在")
    _save_accounts(accounts)
    return {"message": "删除成功"}