"""终审看到的五行口径必须和回答正文一致（全局 vs 对日干影响）。

背景（2026-10-25 用户反馈）：`format_review_context`（workflow Reviewer 深审的事实上下文）
和 `build_verdict_context`（引擎初判裁决）原先只给 `wuxing.counts` —— "对日干影响、日干不计"
这一口径；而回答正文和命盘页引用的是 `global_counts`（含日干本气）。

对水日主的盘两者能差整整 1.0（日干本气那一份），连"最旺/最弱"都会换人：
样例盘 counts 下最弱是水(0.66)，global 下最弱是木(1.58)。审核员拿错口径去核对，
会把本来正确的回答判成"与排盘不符"。

这两个口径的存在本身是对的（影响口径专供判强弱，全局口径供引用），
所以断言是"**两个都必须出现**"，不是"只留全局"。
"""

from __future__ import annotations

from datetime import date

from app.agent.verdict import build_verdict_context
from app.domain.chart_builder import build_bazi_chart
from app.domain.chart_format import format_review_context

# 水日主（壬），日干本气使两个口径在水上相差 1.0，最旺/最弱也随之不同
_CHART = build_bazi_chart("2004-06-22 07:28", "男", today=date(2026, 10, 25))


def test_sample_chart_actually_distinguishes_the_two_scopes():
    """样例盘的两个口径必须真的不一样，否则下面几条断言没有区分力。"""
    wx = _CHART.wuxing
    assert wx.counts != wx.global_counts, "样例盘两口径相同，测试失去意义，请换一个日主的盘"


def test_review_context_carries_both_scopes():
    """审核员上下文同时给全局与影响两个口径（正文用全局，判强弱用影响）。"""
    wx = _CHART.wuxing
    text = format_review_context(_CHART)

    assert str(wx.global_counts) in text, "审核员看不到全局五行分布，无法核对正文引用"
    assert str(wx.counts) in text, "审核员看不到影响口径，无法复核强弱判断"


def test_review_context_strongest_weakest_use_global_scope():
    """最旺/最弱必须按全局口径算 —— 回答正文和命盘页说的就是这个。"""
    wx = _CHART.wuxing
    g_strong = max(wx.global_counts, key=wx.global_counts.get)
    g_weak = min(wx.global_counts, key=wx.global_counts.get)
    expected = f"最旺/最弱（全局）: {g_strong}({wx.global_counts[g_strong]}) / {g_weak}({wx.global_counts[g_weak]})"

    assert expected in format_review_context(_CHART)


def test_verdict_context_carries_both_scopes():
    """引擎初判裁决同样要两个口径：影响口径复核强弱，全局口径对齐命盘页。"""
    wx = _CHART.wuxing
    text = build_verdict_context(_CHART)

    assert str(wx.counts) in text
    assert str(wx.global_counts) in text
