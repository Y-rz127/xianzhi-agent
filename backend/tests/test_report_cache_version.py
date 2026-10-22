"""报告口径版本：缓存 key 与任务 params 都必须带上，否则改了提示词用户还看到旧报告。

2026-10-22 现场：五行口径修正后，"金 4.21" 的旧报告仍被复用——
① report_generator 进程内缓存 key 不含版本；② /report/tasks 按 params 全等幂等复用，
旧任务 params 里没有版本号，重新提交直接返回旧正文。
"""

from __future__ import annotations


def test_report_cache_key_changes_with_version(monkeypatch):
    """口径版本一变，缓存 key 必须变——否则用户重新生成仍命中旧报告。"""
    from app.tools import report_generator as RG

    base = RG._report_cache_key("2000-08-31 10:00", "女", ["overview"])
    assert RG._report_cache_key("2000-08-31 10:00", "女", ["overview"]) == base

    monkeypatch.setattr(RG, "REPORT_PROMPT_VERSION", "r999")
    assert RG._report_cache_key("2000-08-31 10:00", "女", ["overview"]) != base


def test_task_params_carry_report_version():
    """任务 params 必须带 ver：老任务（无该键）不会被 find_same_task 复用。"""
    from app.api.xianzhi_report import _build_task_params
    from app.tools.report_prompts import REPORT_PROMPT_VERSION

    params = _build_task_params("2000-08-31 10:00", "女", "")

    assert params["ver"] == REPORT_PROMPT_VERSION
    assert set(params) == {"birth_time", "gender", "sections", "ver"}
