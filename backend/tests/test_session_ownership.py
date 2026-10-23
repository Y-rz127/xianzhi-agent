"""会话 ID 校验与归属绑定回归测试（不依赖真实 PG/LLM）。"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api import xianzhi_chat as chat_mod
from app.core.http.errors import validate_conversation_id
from app.memory import postgres_memory as pg

pytestmark = pytest.mark.security

VALID_CID = "web-xianzhi-550e8400-e29b-41d4-a716-446655440000"


def test_validate_conversation_id_accepts_random_and_rejects_legacy_or_short() -> None:
    assert validate_conversation_id(VALID_CID) == VALID_CID
    for bad in (
        "default",
        "web-xianzhi-1700000000000",
        "mp-xianzhi__some-user__1700000000000",
        "bad id with spaces",
        "short",
    ):
        with pytest.raises(HTTPException) as exc:
            validate_conversation_id(bad)
        assert exc.value.status_code == 400


def _store_with_final_owner(monkeypatch, owner: str) -> pg.PostgresMemoryStore:
    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params):
            self.sql = sql
            self.params = params
            return self

        def fetchone(self):
            return (owner,)

    class _Pool:
        def connection(self):
            return _Conn()

    monkeypatch.setattr(pg, "_get_pool", lambda: _Pool())
    monkeypatch.setattr(pg, "_ensure_schema", lambda: None)
    return pg.PostgresMemoryStore()


@pytest.mark.parametrize(
    ("owner", "requester", "expected"),
    [
        ("user-a", "user-a", True),
        ("user-a", "user-b", False),
        ("user-a", "", False),
        ("", "", True),
        ("", "user-a", True),
    ],
)
def test_ensure_session_owner_decision(monkeypatch, owner, requester, expected) -> None:
    store = _store_with_final_owner(monkeypatch, owner)
    assert store.ensure_session_owner(VALID_CID, requester) is expected


def test_ensure_session_owner_sql_keeps_first_owner(monkeypatch) -> None:
    """已绑定会话不得被后到的非空 user_id 覆盖（COALESCE 顺序不能反）。"""
    captured = {}

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
            return self

        def fetchone(self):
            return ("user-a",)

    class _Pool:
        def connection(self):
            return _Conn()

    monkeypatch.setattr(pg, "_get_pool", lambda: _Pool())
    monkeypatch.setattr(pg, "_ensure_schema", lambda: None)
    pg.PostgresMemoryStore().ensure_session_owner(VALID_CID, "user-b")

    assert "COALESCE(NULLIF(session_metadata.user_id, ''), EXCLUDED.user_id)" in captured["sql"]


def _patch_chat_repo(monkeypatch, owner_uid: str) -> None:
    async def _get_by_token(token):
        return {"id": token} if token else None

    async def _ensure(cid, uid):
        return uid == owner_uid

    monkeypatch.setattr(chat_mod.repo, "get_by_token", _get_by_token)
    monkeypatch.setattr(chat_mod.repo, "ensure_session_owner", _ensure)


def test_delete_session_evicts_agent(monkeypatch) -> None:
    from app.api import xianzhi as api_mod

    deleted: list[str] = []
    evicted: list[str] = []

    async def _noop_access(session_id, token):
        return None

    async def _delete(session_id):
        deleted.append(session_id)

    class _Ctx:
        def get_xianzhi(self, session_id):
            return object(), asyncio.Lock()

        def evict_xianzhi(self, session_id):
            evicted.append(session_id)

    monkeypatch.setattr(api_mod, "_check_session_access", _noop_access)
    monkeypatch.setattr(api_mod.repo, "delete_session", _delete)

    out = asyncio.run(api_mod.delete_xianzhi_session("s1", token=None, app_ctx=_Ctx()))

    assert out == {"status": "ok"}
    assert deleted == ["s1"]
    assert evicted == ["s1"]


def test_sse_chat_rejects_other_user_and_guest(monkeypatch) -> None:
    _patch_chat_repo(monkeypatch, owner_uid="user-a")

    for token in ("user-b", None):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                chat_mod.chat_with_xianzhi(
                    message="hi",
                    conversation_id=VALID_CID,
                    token=token,
                    app_ctx=object(),
                )
            )
        assert exc.value.status_code == 403


def test_sse_chat_allows_owner_before_agent_lookup(monkeypatch) -> None:
    _patch_chat_repo(monkeypatch, owner_uid="user-a")

    class _Ctx:
        def get_xianzhi(self, cid):
            raise RuntimeError("not initialized")

    result = asyncio.run(
        chat_mod.chat_with_xianzhi(
            message="hi",
            conversation_id=VALID_CID,
            token="user-a",
            app_ctx=_Ctx(),
        )
    )
    assert result == {"error": "Xianzhi not initialized"}
