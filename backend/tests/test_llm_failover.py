"""FailoverModel / _retryable 单测（不联网，用 fake 模型验证降级判定）。

回归背景：主模型 `qwen3.8-2.4t-a95b` 免费额度用尽，上游返回
`openai.PermissionDeniedError 403 AllocationQuota.FreeTierOnly`。
旧 `_retryable` 只认限流/超时/5xx/模型不存在，403 落到末尾 `return False`
→ `invoke()` 直接抛出，**链上其它健康模型一次都没试**，用户只看到"分析过程遇到错误"。
（实测：修前前 7 次请求全部快速失败，第 8 次熔断打开后才偶然切走；修后第 1 次即切成功。）

验证点：
1. 额度/配额类错误（DashScope FreeTierOnly、OpenAI insufficient_quota、欠费）判定为可降级；
2. 401 鉴权失败、400 参数非法等请求本身的问题仍不降级（不误伤）；
3. FailoverModel.invoke 在额度 403 时切到链上下一模型并成功返回；
4. 链上全部模型额度耗尽时抛 ModelUnavailableError（而不是原始 403）。
"""

from __future__ import annotations

import pytest

import app.core.llm_failover as fo
from app.core.config import settings
from app.core.llm_failover import FailoverModel, ModelUnavailableError, _is_quota_exhausted, _retryable

# 上游原文（DashScope 兼容模式实测返回体）
DASHSCOPE_403 = (
    "Error code: 403 - {'error': {'message': 'Free quota exhausted. To continue accessing the "
    "model on a paid basis, please add funds or disable the \"use free tier only\" mode in the "
    "management console.', 'type': 'AllocationQuota.FreeTierOnly', 'param': None, "
    "'code': 'AllocationQuota.FreeTierOnly'}}"
)


class PermissionDeniedError(Exception):
    """模拟 openai.PermissionDeniedError（_retryable 走类名匹配）。"""

    def __init__(self, message: str = DASHSCOPE_403):
        super().__init__(message)


class AuthenticationError(Exception):
    """模拟 openai.AuthenticationError（401：key 失效，同 key 换模型也没用）。"""


class BadRequestError(Exception):
    """模拟 openai.BadRequestError（400：请求本身不合法）。"""


class RateLimitError(Exception):
    """模拟 openai.RateLimitError（429：限流，可降级）。"""


class _FakeModel:
    """最小假模型：按预设异常失败或返回固定标记。"""

    def __init__(self, name: str, exc: Exception | None = None):
        self.model_name = name
        self._exc = exc
        self.calls = 0

    def invoke(self, *args, **kwargs):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return f"ok:{self.model_name}"


def _failover(primary_exc: Exception | None, backup_exc: Exception | None = None):
    """构造 [主模型(settings.dashscope_model) → backup] 两段链，返回 (fm, primary, backup)。"""
    primary = _FakeModel(settings.dashscope_model, primary_exc)
    backup = _FakeModel("backup-model", backup_exc)
    fm = FailoverModel(primary, lambda name: backup if name == "backup-model" else primary)
    return fm, primary, backup


# ---------------- 1. 额度类错误可降级 ----------------
@pytest.mark.parametrize(
    "exc",
    [
        PermissionDeniedError(DASHSCOPE_403),  # 百炼免费额度用尽（本次事故）
        PermissionDeniedError("Error code: 403 - insufficient_quota"),  # OpenAI 额度用尽
        PermissionDeniedError("Your account is in arrearage, please recharge"),  # 阿里云欠费
        PermissionDeniedError("insufficient balance"),  # 余额不足
        PermissionDeniedError("You exceeded your current quota, please check your plan"),
    ],
)
def test_quota_errors_are_retryable(exc):
    assert _is_quota_exhausted(exc) is True
    assert _retryable(exc) is True


# ---------------- 2. 非额度类错误不误判 ----------------
@pytest.mark.parametrize(
    "exc",
    [
        AuthenticationError("Error code: 401 - Incorrect API key provided"),  # 401 鉴权失败
        BadRequestError("Error code: 400 - invalid messages format"),  # 400 参数非法
        BadRequestError("Error code: 400 - total tokens exceed max length"),
    ],
)
def test_non_quota_errors_are_not_retryable(exc):
    assert _is_quota_exhausted(exc) is False
    assert _retryable(exc) is False


def test_rate_limit_still_retryable():
    """既有口径不能被本次改动破坏：429 限流仍降级。"""
    assert _retryable(RateLimitError("Error code: 429 - rate limit reached")) is True


# ---------------- 3. 行为：额度 403 时切到下一模型 ----------------
def test_failover_switches_model_on_quota_403(monkeypatch):
    fm, primary, backup = _failover(PermissionDeniedError(DASHSCOPE_403))
    monkeypatch.setattr(fo, "get_active_chain", lambda: [settings.dashscope_model, "backup-model"])

    assert fm.invoke("hi") == "ok:backup-model"  # 第 1 次调用就切走，不再直接抛错
    assert primary.calls == 1
    assert backup.calls == 1


def test_failover_does_not_switch_on_auth_error(monkeypatch):
    """401 鉴权失败（同 key 换模型无用）：不降级，直接抛出。"""
    err = AuthenticationError("Error code: 401 - Incorrect API key provided")
    fm, primary, backup = _failover(err)
    monkeypatch.setattr(fo, "get_active_chain", lambda: [settings.dashscope_model, "backup-model"])

    with pytest.raises(AuthenticationError):
        fm.invoke("hi")
    assert primary.calls == 1
    assert backup.calls == 0


# ---------------- 3b. bind_tools 必须覆盖全链（不只 primary） ----------------
# 事故锚点（2026-10-08）：模型每次都把工具调用写成文本（DSML/JSON），排查发现
# FailoverModel._derive 只把 bind_tools 应用在 primary 上，链上备选模型是裸建的。
# 而链首往往不是 primary（PG 里可配任意顺序），于是**真正被调用的模型没绑工具**，
# 只能照提示词里的工具说明手搓文本调用。修后五链位全部走原生 tool_calls。


class _FakeBindable:
    """可 bind_tools 的假模型：记录绑没绑、绑了什么。"""

    def __init__(self, name: str, tools=None):
        self.model_name = name
        self.tools = tools

    def bind_tools(self, tools, **kwargs):
        return _FakeBindable(self.model_name, tools)

    def with_config(self, config, **kwargs):
        return _FakeBindable(self.model_name, self.tools)

    def invoke(self, *args, **kwargs):
        return "{}:tools={}".format(self.model_name, None if self.tools is None else len(self.tools))


def _chain_failover(monkeypatch, chain: list[str]):
    """构造多链位 FailoverModel（primary = chain[0]）。"""
    primary = _FakeBindable(chain[0])
    instances = {name: _FakeBindable(name) for name in chain}
    fm = FailoverModel(primary, lambda name: instances.get(name) or primary)
    monkeypatch.setattr(fo, "get_active_chain", lambda: chain)
    return fm, instances


def test_bind_tools_covers_all_chain_models(monkeypatch):
    """bind_tools 后，链上每个模型（含懒建的备选）都拿到工具。"""
    chain = ["m-a", "m-b", "m-c"]
    fm, instances = _chain_failover(monkeypatch, chain)

    bound = fm.bind_tools(["T1", "T2"])
    assert bound.invoke("x") == "m-a:tools=2", "primary 应立即可用（不用等懒建）"

    for name in chain:
        inst = bound._resolve_model(name)
        assert inst.tools == ["T1", "T2"], f"{name} 没绑到工具（旧 bug 现场）"


def test_bind_tools_survives_derive_chain(monkeypatch):
    """多次派生（bind_tools → with_config）后，链上模型仍带全部变换。"""
    chain = ["m-a", "m-b"]
    fm, instances = _chain_failover(monkeypatch, chain)

    bound = fm.bind_tools(["T"]).with_config({"tags": ["x"]})
    for name in chain:
        inst = bound._resolve_model(name)
        assert inst.tools == ["T"], f"{name} 在派生链后丢了工具绑定"


def test_bind_accumulates_for_chain(monkeypatch):
    """bind(**kwargs) 累积到 _bound，invoke 时投给每个链位（既有行为不回归）。"""
    chain = ["m-a", "m-b"]
    fm, instances = _chain_failover(monkeypatch, chain)

    bound = fm.bind(temperature=0.5)
    assert bound._bound == {"temperature": 0.5}
    # primary 失败时切到 m-b，参数同样带过去
    instances["m-a"].invoke = lambda *a, **kw: (_ for _ in ()).throw(PermissionDeniedError(DASHSCOPE_403))
    assert bound.invoke("x") == "m-b:tools=None"


# ---------------- 4. 全链额度耗尽 → ModelUnavailableError ----------------
def test_all_models_quota_exhausted_raises_model_unavailable(monkeypatch):
    fm, primary, backup = _failover(
        PermissionDeniedError(DASHSCOPE_403),
        PermissionDeniedError("Error code: 403 - Free quota exhausted."),
    )
    monkeypatch.setattr(fo, "get_active_chain", lambda: [settings.dashscope_model, "backup-model"])

    with pytest.raises(ModelUnavailableError):
        fm.invoke("hi")
    assert primary.calls == 1 and backup.calls == 1
