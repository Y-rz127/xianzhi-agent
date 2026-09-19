"""上游 LLM 配置类错误的识别 / 一次性上报 / 子模型启动探活（2026-09-19 现场回归）。

背景（为什么值得一组测试）
--------------------------
`_make_model()` 曾把 `enable_thinking` 写死 False，而 reviewer 用的模型只接受 True：
每一轮审核都 400 → 被 `_llm_review` 的兜底吞成 `FactCheckResult(ok=True, source="regex_fallback")`，
日志里只有一行 WARNING，答案照常输出。**第二层审核实际上从未运行**，而所有测试与类型检查都是绿的。

这组测试锁住三件事：
1. 能把它与"网络抖动/限流"区分开（否则又会混进同一条降级路径）；
2. 永久性错误只报一次 ERROR（逐轮刷屏等于没报），且计入**独立**指标；
3. 启动探活发现"该模型只接受思考模式"时会自动纠正并复探 —— 静默失败变成启动即可见/自愈。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.agent.workflow.workflow_workers import ReviewerWorker
from app.core.llm_health import (
    SubModelSpec,
    is_thinking_restricted,
    probe_sub_models,
    report_once,
    reset_reported_once,
)
from app.core.logger import log
from app.domain.chart_builder import build_bazi_chart

# 上游 400 的原文（DashScope 兼容模式）：唯一稳定的锚点是参数名 + "restricted"
RESTRICTED = (
    "Error code: 400 - {'error': {'message': '<400> InternalError.Algo.InvalidParameter: "
    "The value of the enable_thinking parameter is restricted to True.', 'type': "
    "'invalid_request_error', 'code': 'invalid_parameter_error'}}"
)

CHART = build_bazi_chart("2004-06-22 08:00", "男", liunian_start_year=2026, liunian_years=10)


@pytest.fixture(autouse=True)
def _clean_reported():
    """`report_once` 的"已报过"标记是进程级状态，逐用例清掉，避免用例间互相影响。"""
    reset_reported_once()
    yield
    reset_reported_once()


def _capture(level: str = "ERROR"):
    """挂一个 loguru sink 收集日志（logger.py 只往 stderr/文件写，caplog 抓不到）。

    `format="{message}"` 是为了断言时不必剥时间戳/级别前缀。
    """
    lines: list[str] = []
    sink_id = log.add(lines.append, level=level, format="{message}")
    return lines, sink_id


def _metrics(key: str) -> int:
    from app.core.observability import get_metrics

    return int(dict(get_metrics()["internal_errors"]).get(key, 0))


# ============================================================
# 1. 分类：只认"模型只接受思考模式"，不误伤其他失败
# ============================================================

def test_recognizes_observed_upstream_message():
    assert is_thinking_restricted(RESTRICTED)
    # 异常对象与纯字符串都要认（调用方两处都在用）
    assert is_thinking_restricted(RuntimeError(RESTRICTED))


def test_does_not_swallow_other_failures():
    """网络抖动、限流、别的参数被拒 —— 都不是这一类，必须继续走 WARNING + 降级。"""
    assert not is_thinking_restricted(TimeoutError("Connection timed out"))
    assert not is_thinking_restricted(RuntimeError("Error code: 429 - rate limit exceeded"))
    assert not is_thinking_restricted(
        RuntimeError("Error code: 400 - Unsupported parameter: temperature (kimi-k3)")
    )
    # 提到 enable_thinking 但语义是"不支持这个参数"，修法是去掉参数而不是改成 True
    assert not is_thinking_restricted(
        RuntimeError("Error code: 400 - InvalidParameter: enable_thinking is not supported")
    )


# ============================================================
# 2. 一次性上报
# ============================================================

def test_report_once_emits_only_first_time():
    lines, sink_id = _capture()
    try:
        assert report_once("k", "error", "第一次 {}", "甲") is True
        assert report_once("k", "error", "第二次 {}", "乙") is False
    finally:
        log.remove(sink_id)

    joined = "\n".join(lines)
    assert "第一次 甲" in joined
    assert "第二次" not in joined, "永久性错误逐轮打印会把日志刷满"


def test_report_once_is_per_key():
    lines, sink_id = _capture()
    try:
        assert report_once("a", "error", "A") is True
        assert report_once("b", "error", "B") is True
    finally:
        log.remove(sink_id)
    # loguru 会给每条补一个换行，比对前 strip 掉
    assert {"A", "B"} <= {ln.strip() for ln in lines}


# ============================================================
# 3. Reviewer 运行期：配置错误 → 独立指标 + 只报一次 ERROR
# ============================================================

class _RejectingModel:
    """审核调用必然抛"只接受思考模式"的假模型。"""

    def __init__(self) -> None:
        self.calls = 0

    def bind(self, **kwargs):
        return self

    def invoke(self, messages, **kwargs):
        self.calls += 1
        raise RuntimeError(RESTRICTED)


def test_reviewer_config_error_gets_its_own_metric_and_reports_once():
    model = _RejectingModel()
    worker = ReviewerWorker(chat_model=model)
    before_cfg = _metrics("reviewer_llm_config_error")
    before_plain = _metrics("reviewer_llm_error")

    lines, sink_id = _capture()
    try:
        first = worker.review_llm_only("你日柱带华盖，爱琢磨。", CHART, "知识", user_prompt="测试")
        second = worker.review_llm_only("你日柱带华盖，爱琢磨。", CHART, "知识", user_prompt="测试")
    finally:
        log.remove(sink_id)

    # 行为不变：仍然"降级为纯正则通过"（审核不阻断出答案），但必须可观测
    assert first.ok and first.source == "regex_fallback"
    assert second.ok and second.source == "regex_fallback"
    assert model.calls == 2, "两次调用都应真的打到模型（不是被别处短路）"

    assert _metrics("reviewer_llm_config_error") == before_cfg + 2, "配置错误要有独立计数"
    assert _metrics("reviewer_llm_error") == before_plain, "不能再混进偶发失败计数"

    errors = [ln for ln in lines if "配置错误" in ln]
    assert len(errors) == 1, f"同类配置错误只该报一次，实际 {len(errors)} 次"
    assert "REVIEWER_ENABLE_THINKING" in errors[0], "报错必须直接给出该改哪个环境变量"


class _TransientFailModel:
    """偶发失败（超时）不能走一次性上报，否则真故障会被静默吞掉。"""

    def bind(self, **kwargs):
        return self

    def invoke(self, messages, **kwargs):
        raise TimeoutError("Connection timed out")


def test_transient_reviewer_failure_still_warns_every_time():
    worker = ReviewerWorker(chat_model=_TransientFailModel())
    before_cfg = _metrics("reviewer_llm_config_error")
    before_plain = _metrics("reviewer_llm_error")

    lines, sink_id = _capture(level="WARNING")
    try:
        worker.review_llm_only("你日柱带华盖。", CHART, "知识", user_prompt="测试")
        worker.review_llm_only("你日柱带华盖。", CHART, "知识", user_prompt="测试")
    finally:
        log.remove(sink_id)

    assert _metrics("reviewer_llm_error") == before_plain + 2
    assert _metrics("reviewer_llm_config_error") == before_cfg
    assert len([ln for ln in lines if "LLM 审核失败" in ln]) == 2, "偶发失败需要看频率，不能被去重"


# ============================================================
# 4. 启动探活
# ============================================================

class _PingModel:
    """探活用的最小假模型：可配置成功 / 抛指定异常。"""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return AIMessage(content="pong")


def _spec(model, *, enable_thinking=False, rebuild=None, label="Reviewer 审核", attr="reviewer_model"):
    return SubModelSpec(
        label=label,
        attr=attr,
        env_key="REVIEWER_ENABLE_THINKING",
        model_name="glm-5.3",
        enable_thinking=enable_thinking,
        rebuild=rebuild or (lambda flag: model),
        model=model,
    )


def test_probe_passes_when_model_accepts_config():
    model = _PingModel()
    ctx = SimpleNamespace(reviewer_model=model)
    results = probe_sub_models([_spec(model)], ctx)

    assert len(results) == 1
    assert results[0].ok and not results[0].fixed
    assert results[0].enable_thinking is False
    assert model.calls == 1


def test_probe_auto_corrects_thinking_restricted_model():
    """只接受思考的模型：探活改 True 重建 + 复探 + 回写 AppContext，并提示该设哪个环境变量。"""
    rebuilt = _PingModel()
    calls: list[bool] = []

    def rebuild(flag: bool):
        calls.append(flag)
        return rebuilt

    broken = _PingModel(error=RuntimeError(RESTRICTED))
    ctx = SimpleNamespace(reviewer_model=broken)

    lines, sink_id = _capture(level="WARNING")
    try:
        results = probe_sub_models([_spec(broken, rebuild=rebuild)], ctx)
    finally:
        log.remove(sink_id)

    assert calls == [True], "只该重建一次，且是切成 True"
    assert results[0].ok and results[0].fixed and results[0].enable_thinking is True
    assert rebuilt.calls == 1, "纠正后必须复探（不能只是假定修好了）"
    assert ctx.reviewer_model is rebuilt, "生效实例要写回 AppContext，否则纠正只停在日志里"
    assert any("REVIEWER_ENABLE_THINKING=true" in ln for ln in lines), "必须给出可直接照抄的配置"


def test_probe_does_not_guess_on_other_failures():
    """非 thinking 配置问题 → 原样报 ERROR，不改配置、不重建。"""
    calls: list[bool] = []

    def rebuild(flag: bool):
        calls.append(flag)
        return _PingModel()

    broken = _PingModel(error=TimeoutError("Connection timed out"))
    ctx = SimpleNamespace(reviewer_model=broken)

    lines, sink_id = _capture()
    try:
        results = probe_sub_models([_spec(broken, rebuild=rebuild)], ctx)
    finally:
        log.remove(sink_id)

    assert calls == [], "不许猜测性重建"
    assert not results[0].ok and not results[0].fixed
    assert ctx.reviewer_model is broken
    assert any("不是 thinking 配置问题" in ln for ln in lines)


def test_probe_reports_when_thinking_already_on():
    """已配 True 仍被同一错误拒绝：说明不是这个开关的问题，不许再自动改。"""
    broken = _PingModel(error=RuntimeError(RESTRICTED))
    ctx = SimpleNamespace(reviewer_model=broken)

    lines, sink_id = _capture()
    try:
        results = probe_sub_models([_spec(broken, enable_thinking=True)], ctx)
    finally:
        log.remove(sink_id)

    assert not results[0].ok and not results[0].fixed
    assert any("已配 enable_thinking=true 仍被拒" in ln for ln in lines)


def test_probe_never_raises_when_rebuild_explodes():
    """探活跑在启动后台任务里：连 rebuild 炸了都不能把服务带下去（只上报，不抛）。"""
    def boom(flag: bool):
        raise RuntimeError("构造失败")

    broken = _PingModel(error=RuntimeError(RESTRICTED))
    ctx = SimpleNamespace(reviewer_model=broken)

    lines, sink_id = _capture()
    try:
        results = probe_sub_models([_spec(broken, rebuild=boom)], ctx)
    finally:
        log.remove(sink_id)

    assert len(results) == 1 and not results[0].ok
    assert "构造失败" in results[0].error
    assert ctx.reviewer_model is broken, "重建失败时不许改 AppContext（留着原实例，行为与改动前一致）"
    assert any("切成 enable_thinking=true 后仍失败" in ln for ln in lines)


def test_probe_never_raises_when_spec_build_explodes():
    """连"首个实例"都是现场构造的（spec.model 为空）时，构造炸了同样只上报。"""
    def boom(flag: bool):
        raise RuntimeError("首次构造失败")

    spec = _spec(model=None, rebuild=boom)
    lines, sink_id = _capture()
    try:
        results = probe_sub_models([spec], SimpleNamespace())
    finally:
        log.remove(sink_id)

    assert len(results) == 1 and not results[0].ok
    assert "重建失败" in lines[0] or any("重建失败" in ln for ln in lines)
