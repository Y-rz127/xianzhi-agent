"""LLM 成本归因（用途标签）的守卫测试。

背景（为什么值得一组测试）
--------------------------
`/metrics` 的成本页按 `模型 × 用途` 分组，用途来自 `llm_tag(...)` 这个 contextvar，
默认值是 `unknown`。漏包 `llm_tag` 不会报错、不会少一次调用，只会让成本页多出一行
**无法解释的 unknown**——2026-09-20 实测：三条 unknown 全是启动探活（`probe_sub_models`），
K 线批注的两次调用同样没有标签。这类问题只有"人肉看成本页"才发现，必须固化断言。

这组测试锁三件事：
1. 已有标签取值都在 `CANONICAL_TAGS` 白名单里（新路径必须先登记，成本页才不会出现野标签）；
2. 未打标签的调用会留一条**可 grep** 的 WARNING（按模型只报一次，不刷屏）；
3. 每个合法标签在前端 `Observability.vue` 的中文映射里都有对应项（否则页面显示裸英文/unknown）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.llm_throttle import (
    CANONICAL_TAGS,
    ThrottledModel,
    llm_tag,
    llm_usage_tag,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
OBSERVABILITY_VUE = REPO_ROOT / "frontend" / "web" / "src" / "views" / "Observability.vue"

# 源码里 llm_tag("xxx") 的字面量调用
_TAG_CALL_RE = re.compile(r"llm_tag\(\s*[\"']([a-zA-Z0-9_\-]+)[\"']\s*\)")


@pytest.fixture(autouse=True)
def _reset_untagged_warned():
    """"已警告过"的集合是进程级状态，逐用例清掉，避免用例间互相影响。"""
    import app.core.llm_throttle as throttle

    throttle._untagged_warned.clear()
    yield
    throttle._untagged_warned.clear()


class _Usage:
    prompt_tokens = 5
    completion_tokens = 7


class _Inner:
    """最小内层模型：返回带 token 用量元数据的响应（计量才会上报）。"""

    model_name = "fake-model"

    def invoke(self, *_args, **_kwargs):
        from types import SimpleNamespace

        return SimpleNamespace(usage_metadata=_Usage())


def _capture_warnings() -> tuple[list[str], int]:
    """挂 loguru sink 收集 WARNING（logger.py 只往 stderr/文件写，caplog 抓不到）。"""
    from app.core.logger import log

    lines: list[str] = []
    sink_id = log.add(lines.append, level="WARNING", format="{message}")
    return lines, sink_id


# ============================================================
# 1. 标签白名单：新调用路径必须先登记
# ============================================================


def _source_tag_literals() -> dict[str, list[str]]:
    """扫描后端源码，返回 {标签: [文件...]}。"""
    found: dict[str, list[str]] = {}
    for path in sorted((BACKEND_DIR / "app").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for tag in _TAG_CALL_RE.findall(text):
            found.setdefault(tag, []).append(str(path.relative_to(BACKEND_DIR)))
    return found


def test_every_tag_literal_is_registered():
    """源码里用到的标签都必须登记在 CANONICAL_TAGS（否则前端映射与成本口径会各自漂移）。"""
    unregistered = {
        tag: files for tag, files in _source_tag_literals().items() if tag not in CANONICAL_TAGS
    }
    assert not unregistered, f"未登记的用途标签：{unregistered}；请补进 CANONICAL_TAGS 与前端映射"


def test_all_call_sites_are_found():
    """守住扫描本身：至少应扫到 workflow/chitchat/react/summary/report/kline/probe/子应用。"""
    found = set(_source_tag_literals())
    missing = set(CANONICAL_TAGS) - found
    assert not missing, f"这些标签没有任何 llm_tag 调用点（清单过期或调用被删）：{sorted(missing)}"


def test_canonical_tags_are_documented_in_frontend_map():
    """每个合法标签都要在前端成本页有中文用途映射，页面才不会显示裸英文/unknown。"""
    if not OBSERVABILITY_VUE.exists():  # 只部署后端时跳过
        pytest.skip("前端源码不在本检出内")
    text = OBSERVABILITY_VUE.read_text(encoding="utf-8")
    missing = [tag for tag in CANONICAL_TAGS if f"{tag}:" not in text]
    assert not missing, f"前端 Observability.vue 缺少用途映射：{missing}"


# ============================================================
# 2. 未打标签 → 可 grep 的警告（按模型只报一次）
# ============================================================


def test_untagged_call_warns_once_and_still_reports():
    """漏包 llm_tag 时：留一条 WARNING，同时**照常上报**（不能静默丢计量）。"""
    from app.core.observability import get_metrics

    model = ThrottledModel(_Inner())
    lines, sink_id = _capture_warnings()
    try:
        model.invoke([])
        model.invoke([])
    finally:
        from app.core.logger import log

        log.remove(sink_id)

    tagged = [line for line in lines if "未打用途标签" in line]
    assert len(tagged) == 1, f"同一模型的未标注调用只该警告一次：{lines}"
    assert "fake-model" in tagged[0]
    assert llm_usage_tag.get() == "unknown", "警告不该改变默认标签"

    rows = [row for row in get_metrics()["llm"] if row["model"] == "fake-model"]
    assert rows, "未打标签也要照常计入成本页（只是用途为 unknown）"
    assert rows[0]["tag"] == "unknown"
    assert rows[0]["calls"] == 2


def test_tagged_call_does_not_warn():
    """包了 llm_tag 的调用不该出现任何"未打用途标签"警告。"""
    model = ThrottledModel(_Inner())
    lines, sink_id = _capture_warnings()
    try:
        with llm_tag("workflow"):
            model.invoke([])
    finally:
        from app.core.logger import log

        log.remove(sink_id)

    assert not [line for line in lines if "未打用途标签" in line]


def test_stream_path_also_warns_for_untagged_calls():
    """流式路径同样要能暴露漏标签（usage 聚合在最后一个 chunk）。"""
    from types import SimpleNamespace

    class _StreamInner(_Inner):
        def stream(self, *_args, **_kwargs):
            yield SimpleNamespace(usage_metadata=_Usage())

    model = ThrottledModel(_StreamInner())
    lines, sink_id = _capture_warnings()
    try:
        list(model.stream([]))
    finally:
        from app.core.logger import log

        log.remove(sink_id)

    assert [line for line in lines if "未打用途标签" in line]


# ============================================================
# 3. 两条已修的历史缺口：启动探活 / K 线批注
# ============================================================


def test_probe_call_lands_as_probe_tag_in_metrics():
    """启动探活经 ThrottledModel 计量后必须是 tag=probe（修前是 unknown，见 2026-09-20 成本页）。"""
    from types import SimpleNamespace

    from app.core.llm_health import SubModelSpec, probe_sub_models
    from app.core.observability import get_metrics

    class _ProbeInner(_Inner):
        model_name = "probe-fake-model"

    wrapped = ThrottledModel(_ProbeInner())
    spec = SubModelSpec(
        label="子应用解读",
        attr="sub_app_model",
        env_key="SUB_APP_ENABLE_THINKING",
        model_name="probe-fake-model",
        enable_thinking=False,
        rebuild=lambda flag: wrapped,
        model=wrapped,
    )
    results = probe_sub_models([spec], SimpleNamespace(sub_app_model=wrapped))
    assert results[0].ok

    rows = [row for row in get_metrics()["llm"] if row["model"] == "probe-fake-model"]
    assert [row["tag"] for row in rows] == ["probe"], f"探活用途标签不对：{rows}"
