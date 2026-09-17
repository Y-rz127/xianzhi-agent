"""审核 LLM 输出被截断时的"抢救结论"回归测试（2026-09-15 线上问题）。

现场：修复后的二次审核，模型已经明确给出 `{"pass": false, "issues": [...]}`，
但输出顶到上限被截断（issues 写了两大段 + 思考块）→ JSON 不闭合 → `_parse_json`
的平衡扫描也救不回来 → 旧实现一律 `return FactCheckResult(ok=True)`，
**把模型的否决静默丢掉、带病回答直接上线**，日志里只留一条 WARNING。

修法：
- `_salvage_verdict()` 从残缺输出里抠 `"pass": true/false` 与 issues 字符串
  （兼容最后一条被截断、没有闭合引号的 issue）；
- 抠到结论就按结论走（source="llm_salvaged"），抠不到才沿用"降级为通过 + 记指标"；
- 判不通过但 issues 全被截断时，给修复器一条可执行的通用问题，不静默放行。
"""

from __future__ import annotations

import pytest

from app.agent.workflow import workflow_workers as wk
from app.agent.workflow.workflow_workers import ReviewerWorker, _salvage_verdict
from app.domain.chart_builder import build_bazi_chart

CHART = build_bazi_chart("2004-06-22 08:00", "男")

# 现场那段（截断在最后一条 issue 中间）
TRUNCATED = """{
"pass": false,
"issues": [
"十神事实错误：回答称'地支酉金是印星'，与排盘事实不符",
"五行生克逻辑错误：回答称'天干癸水…能把过旺金气往外疏一点'"""


# ---------------- _salvage_verdict ----------------
def test_salvage_recovers_pass_false_and_complete_issue():
    passed, issues = _salvage_verdict(TRUNCATED)
    assert passed is False
    assert issues[0] == "十神事实错误：回答称'地支酉金是印星'，与排盘事实不符"


def test_salvage_keeps_truncated_last_issue():
    """最后一条被截断（没有闭合引号）也要捞出来，供修复器定位。"""
    _, issues = _salvage_verdict(TRUNCATED)
    assert len(issues) == 2
    assert issues[1].startswith("五行生克逻辑错误：回答称'天干癸水")


def test_salvage_pass_true_with_empty_issues():
    assert _salvage_verdict('{"pass": true, "issues": []}') == (True, [])


def test_salvage_handles_escaped_quotes():
    raw = r'{"pass": false, "issues": ["回答写了 \"必然而然\" 这种绝对化表述"]}'
    passed, issues = _salvage_verdict(raw)
    assert passed is False
    assert '"必然而然"' in issues[0]  # 转义被还原


def test_salvage_returns_none_without_pass_field():
    """连 pass 都抠不到时返回 None，由调用方走原有的降级路径。"""
    assert _salvage_verdict("模型今天不想输出 JSON，只说了些别的") is None
    assert _salvage_verdict("") is None
    assert _salvage_verdict('{"issues": ["没有 pass 字段"]}') is None


def test_salvage_ignores_field_name_tokens():
    """issues 数组里的字段名本身不算问题；数组闭合后不得再捞结构字符。"""
    _, issues = _salvage_verdict('{"pass": false, "issues": ["pass", "真实问题"]}')
    assert issues == ["真实问题"]
    # 实测踩过：闭合数组后仍去捞"最后一条未闭合字符串"，把 "]}"/"]" 当成 issue
    _, only_field = _salvage_verdict('{"pass": false, "issues": ["pass"]}')
    assert only_field == []


@pytest.mark.parametrize(
    "value,expected",
    [("否", False), ("false", False), ("不通过", False), ("no", False), (True, True), ("是", True)],
)
def test_coerce_pass_string_values(value, expected):
    """`_coerce_pass` 的既有口径不能被抢救逻辑破坏。"""
    assert wk._coerce_pass(value) is expected


def test_pass_false_without_issues_still_converts_to_pass(monkeypatch):
    """保持既有设计：判不通过却不给 issues 时按通过处理（避免空修复轮），仅记指标。"""
    result = _review(monkeypatch, '{"pass": "否"}')

    assert result.ok is True
    assert result.source == "llm"


# ---------------- _llm_review 端到端（假模型）----------------
class _FakeResp:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self.content = content
        self.response_metadata = {"finish_reason": finish_reason}


class _FakeModel:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self._content = content
        self._finish = finish_reason

    def bind(self, **kwargs):
        return self

    def invoke(self, messages):
        return _FakeResp(self._content, self._finish)


def _review(monkeypatch, llm_output: str, *, finish_reason: str = "stop", answer: str = "测试回答"):
    """跑一次 LLM 深审（打桩 invoke_review_with_meta，返回 (正文, finish_reason)）。"""
    monkeypatch.setattr(
        wk, "invoke_review_with_meta", lambda model, messages: (llm_output, finish_reason)
    )
    worker = ReviewerWorker(_FakeModel(""))
    return worker._llm_review(
        answer=answer, chart=CHART, knowledge="", user_prompt="测试问题", ctx=None, second_chart=None
    )


def test_truncated_pass_false_is_no_longer_silently_approved(monkeypatch):
    """核心回归：模型说 pass=false（哪怕 JSON 被截断）不得判通过。"""
    result = _review(monkeypatch, TRUNCATED)

    assert result.ok is False
    assert result.source == "llm_salvaged"
    assert result.issues, "必须带 issue，否则修复器无事可做"


def test_truncated_pass_false_without_issues_gets_generic_issue(monkeypatch):
    """issues 全被截断：给一条可执行的通用问题，而不是静默放行。"""
    result = _review(monkeypatch, '{"pass": false, "issues": [')

    assert result.ok is False
    assert len(result.issues) == 1
    assert "截断" in result.issues[0]


def test_truncated_pass_true_still_approves(monkeypatch):
    result = _review(monkeypatch, '{"pass": true, "issues": [')

    assert result.ok is True
    assert result.source == "llm_salvaged"


def test_unparseable_without_pass_field_still_fails_open(monkeypatch):
    """保持既有兜底：连结论都拿不到时按通过处理，并记指标（宁可不误杀）。"""
    result = _review(monkeypatch, "我觉得这段回答还行，就不输出 JSON 了")

    assert result.ok is True
    assert result.source == "regex_fallback"


def test_valid_json_path_unchanged(monkeypatch):
    result = _review(monkeypatch, '{"pass": false, "issues": ["十神与排盘事实不符"]}')

    assert result.ok is False
    assert result.source == "llm"
    assert result.issues == ["十神与排盘事实不符"]


# ---------------- finish_reason=length 的权威信号 ----------------
def _err_count(key: str) -> int:
    from app.core.observability import get_metrics

    return int(dict(get_metrics()["internal_errors"]).get(key, 0))


def test_truncated_finish_reason_is_recorded(monkeypatch):
    """被截断要落指标，便于统计"审核有多少次是撞上限"，而不是靠不闭合反推。"""
    before = _err_count("reviewer_output_truncated")
    _review(monkeypatch, TRUNCATED, finish_reason="length")
    assert _err_count("reviewer_output_truncated") == before + 1


def test_normal_finish_reason_not_recorded(monkeypatch):
    before = _err_count("reviewer_output_truncated")
    _review(monkeypatch, '{"pass": true, "issues": []}', finish_reason="stop")
    assert _err_count("reviewer_output_truncated") == before


def test_finish_reason_of_reads_metadata():
    from app.agent.workflow.workflow_support import finish_reason_of

    assert finish_reason_of(_FakeResp("x", "length")) == "length"
    assert finish_reason_of(_FakeResp("x", "STOP")) == "stop"  # 大小写归一
    assert finish_reason_of(object()) == ""  # 拿不到就返回空串，不影响主流程
