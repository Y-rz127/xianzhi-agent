"""断事知识（chart_facts）的归属隔离测试（不依赖真实 PG/LLM）。

`chart_facts` 是"某用户 × 某命盘"的长期记忆：A 确认过的事只该在 A 重新挂同一张盘时
被引用，绝不能出现在另一个用户 B 的提问里（两个人的实际经历不可能一样，串台会让
回答凭空冒出别人的人生细节）。

隔离靠两处，这里各钉一颗钉子：
① 注入侧 `get_chart_facts_text` 必须用 `ctx.user_id` 去取画像 —— 少了它就会退化成
   "按命盘取"，同八字的人立刻互相串台，而且**不会报错**，只会让 B 看到 A 的事；
② 接口侧 `GET /feedback/profiles/{id}/facts` 必须校验画像是本人的——只校验 token
   有效等于任何登录用户拿到 profile_id 就能读别人的断事知识（IDOR）。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.agent.workflow.workflow_messages import get_chart_facts_text
from app.agent.workflow.workflow_models import WorkflowChartContext
from app.api import feedback as feedback_api

BIRTH = "2004-06-22 07:28"
PROFILE_A = "profile-a"
PROFILE_B = "profile-b"


def _ctx(user_id: str, birth_time: str = BIRTH, gender: str = "男") -> WorkflowChartContext:
    return WorkflowChartContext(
        birth_time=birth_time, gender=gender, sect=2, yun_sect=1, chart=None, user_id=user_id
    )


class _FakeProfileStore:
    """按 (user_id, birth_time, gender) 存画像的假库，口径与真实 SQL 一致。"""

    def __init__(self, facts: dict[str, tuple[list[str], list[str]]]):
        self.profiles = {
            ("user-a", BIRTH, "男"): {"id": PROFILE_A},
            ("user-b", BIRTH, "男"): {"id": PROFILE_B},
        }
        self.facts = facts
        self.lookups: list[tuple] = []
        self.fact_calls: list[str] = []

    def get_chart_profile(self, user_id, birth_time, gender):
        self.lookups.append((user_id, birth_time, gender))
        return self.profiles.get((user_id, birth_time, gender))

    def get_chart_facts_for_llm(self, profile_id, limit=10):
        self.fact_calls.append(profile_id)
        return self.facts.get(profile_id, ([], []))


@pytest.fixture
def store(monkeypatch):
    """接管 chart_store 的两个读函数（get_chart_facts_text 内部是函数级 import）。"""
    import app.db.chart_store as chart_store

    fake = _FakeProfileStore(
        {
            PROFILE_A: (["2019 年父亲住院，家里花了不少钱"], []),
            PROFILE_B: (["2021 年换了工作，离开老家"], []),
        }
    )
    monkeypatch.setattr(chart_store, "get_chart_profile", fake.get_chart_profile)
    monkeypatch.setattr(chart_store, "get_chart_facts_for_llm", fake.get_chart_facts_for_llm)
    return fake


# ---------------- ① 注入侧：按用户隔离 ----------------
def test_same_chart_different_user_does_not_leak_facts(store):
    """同八字、不同用户：B 绝不能看到 A 确认过的事实。"""
    text_a = get_chart_facts_text(_ctx("user-a"))
    text_b = get_chart_facts_text(_ctx("user-b"))

    assert "父亲住院" in text_a
    assert "父亲住院" not in text_b
    assert "换了工作" in text_b
    assert "换了工作" not in text_a


def test_lookup_key_includes_user_id(store):
    """画像查询必须带 user_id 与命盘两段 —— 只按命盘查就会跨用户串台。"""
    get_chart_facts_text(_ctx("user-a"))
    assert store.lookups == [("user-a", BIRTH, "男")]


def test_unknown_user_gets_nothing_and_no_facts_query(store):
    """没有画像（新用户/别的账号）→ 不注入，也不该去查事实表。"""
    assert get_chart_facts_text(_ctx("user-c")) == ""
    assert store.fact_calls == []


def test_guest_without_user_id_gets_nothing(store):
    """游客 user_id 为空：绝不能因为"空串"就匹配到某个人的画像。"""
    assert get_chart_facts_text(_ctx("")) == ""
    assert store.fact_calls == []


def test_missing_birth_info_skips_lookup(store):
    assert get_chart_facts_text(_ctx("user-a", birth_time="")) == ""
    assert get_chart_facts_text(_ctx("user-a", gender="")) == ""
    assert store.lookups == []


# ---------------- ② 接口侧：只能读自己的画像 ----------------
def _call_profile_facts(monkeypatch, *, owner: str | None, requester: str) -> dict:
    async def _uid(token):
        return requester

    async def _profile(profile_id):
        return {"id": profile_id, "user_id": owner} if owner is not None else None

    async def _facts(profile_id, confidence, limit):
        return [{"id": "f1", "confidence": "verified"}]

    monkeypatch.setattr(feedback_api, "_require_uid", _uid)
    monkeypatch.setattr(feedback_api.repo, "get_chart_profile_by_id", _profile)
    monkeypatch.setattr(feedback_api.repo, "get_chart_facts", _facts)
    return asyncio.run(feedback_api.get_profile_facts(PROFILE_A, token="t", confidence=None, limit=20))


def test_owner_can_read_own_profile_facts(monkeypatch):
    out = _call_profile_facts(monkeypatch, owner="user-a", requester="user-a")
    assert out["facts"][0]["id"] == "f1"


def test_other_users_profile_is_404(monkeypatch):
    """别人的画像一律 404（不区分不存在与无权，免得变成枚举探针）。"""
    with pytest.raises(HTTPException) as exc:
        _call_profile_facts(monkeypatch, owner="user-a", requester="user-b")
    assert exc.value.status_code == 404


def test_missing_profile_is_404(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call_profile_facts(monkeypatch, owner=None, requester="user-a")
    assert exc.value.status_code == 404


def test_unauthorized_requester_is_rejected_before_any_lookup(monkeypatch):
    """没有有效 token：先 401，连画像都不查。"""
    looked: list[str] = []

    async def _uid(token):
        raise HTTPException(status_code=401, detail="请先登录")

    async def _profile(profile_id):
        looked.append(profile_id)
        return {"id": profile_id, "user_id": "user-a"}

    monkeypatch.setattr(feedback_api, "_require_uid", _uid)
    monkeypatch.setattr(feedback_api.repo, "get_chart_profile_by_id", _profile)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            feedback_api.get_profile_facts(PROFILE_A, token=None, confidence=None, limit=20)
        )
    assert exc.value.status_code == 401
    assert looked == []


def test_facts_are_not_queried_for_foreign_profile(monkeypatch):
    """非本人时不该再去查事实表（少一次无谓查询，也避免任何泄漏面）。"""
    called: list[str] = []

    async def _uid(token):
        return "user-b"

    async def _profile(profile_id):
        return {"id": profile_id, "user_id": "user-a"}

    async def _facts(*args):
        called.append(args[0])
        return []

    monkeypatch.setattr(feedback_api, "_require_uid", _uid)
    monkeypatch.setattr(feedback_api.repo, "get_chart_profile_by_id", _profile)
    monkeypatch.setattr(feedback_api.repo, "get_chart_facts", _facts)
    with pytest.raises(HTTPException):
        asyncio.run(
            feedback_api.get_profile_facts(PROFILE_A, token="t", confidence=None, limit=20)
        )
    assert called == []


# ---------------- 写入侧：事实落在谁名下 ----------------
def test_extracted_fact_is_stored_under_acting_user(monkeypatch):
    """反馈提取的事实必须写到"当前登录用户"名下（匿名也不能借用别人的身份）。"""
    calls: list[tuple] = []

    async def _upsert(user_id, birth_time, gender, chart_data, interaction_count=1):
        calls.append(("upsert", user_id))
        return PROFILE_A

    async def _add_fact(**kwargs):
        calls.append(("fact", kwargs["user_id"], kwargs["chart_profile_id"]))
        return "f1"

    async def _profile(user_id, birth_time, gender):
        return None

    monkeypatch.setattr(feedback_api.repo, "upsert_chart_profile", _upsert)
    monkeypatch.setattr(feedback_api.repo, "add_chart_fact", _add_fact)
    monkeypatch.setattr(feedback_api.repo, "get_chart_profile", _profile)
    asyncio.run(
        feedback_api._extract_fact_to_profile(
            "user-b", BIRTH, "男", "conv-1", "我今年工作怎么样", "回答…", "up", "准", {}
        )
    )

    assert calls[0] == ("upsert", "user-b")
    assert calls[1] == ("fact", "user-b", PROFILE_A)
