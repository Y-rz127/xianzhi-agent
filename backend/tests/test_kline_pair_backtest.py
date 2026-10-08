"""合盘（关系）回测引擎：逐年标签、逐项诊断、命中率与窗口口径。

为什么单开一个文件：`test_kline_backtest` 覆盖的是单盘那一套（`predict_chart` /
`run_backtest`），合盘是**另一条预测源**（共振分），共用统计但阈值来源、事件字段、
错判样例都不同。混在一个文件里，改单盘时容易连带改坏合盘的口径而不自知。

本文件用真实命盘（黄金用例，建盘缓存）而不是桩 —— 阈值分位、交换对称、
窗口边界这些正是最容易在桩上"看起来对"的地方。
"""

from __future__ import annotations

from functools import lru_cache

import pytest

from app.domain import kline_backtest as KB
from tests.test_kline_backtest import chart_of

CASE_A = "stem_ren"
CASE_B = "stem_jia"


@lru_cache(maxsize=1)
def _pair():
    """一对真实命盘（建盘约 0.35s/张，跨用例缓存）。"""
    return chart_of(CASE_A), chart_of(CASE_B)


def _events_from_labels(pred: dict, *, only_decided: bool = True, flip: bool = False) -> list[dict]:
    """按引擎自己的逐年标签反推标注：吉→1、凶→-1、(平→0)。

    这是**方向性**校验的标准做法（单盘回测也是这么测的）：把引擎的标签当真相回灌，
    若哪一段把吉凶接反了（polarity 符号、pred/truth 对调），命中率会掉到 0 而不是 1。
    """
    out = []
    for year, v in sorted(pred["years"].items()):
        label = v["label"]
        if label == KB.LABEL_UP:
            pol = 1
        elif label == KB.LABEL_DOWN:
            pol = -1
        elif only_decided:
            continue
        else:
            pol = 0
        out.append(
            {
                "ganzhiYear": year,
                "polarity": -pol if flip else pol,
                "relation": "夫妻",
                "note": f"{year}",
            }
        )
    return out


# ---------------- predict_pair ----------------


class TestPredictPair:
    def test_returns_per_year_labels_and_terms(self):
        a, b = _pair()
        pred = KB.predict_pair(a, b)
        assert pred["predictor"] == KB.PAIR_PREDICTOR_RESONANCE
        assert pred["dimension"] == KB.DIM_COMPREHENSIVE
        assert pred["startYear"] <= pred["endYear"]
        assert len(pred["years"]) == pred["endYear"] - pred["startYear"] + 1
        for year, v in pred["years"].items():
            assert v["label"] in KB.LABELS
            assert isinstance(v["score"], float)
            assert set(v["terms"]) == set(KB.TERMS_ORDER)

    def test_labels_are_roughly_balanced_by_construction(self):
        """阈值取该对全期分布分位，故三档应大致三等分 —— 若某档为空，说明切分口径坏了。"""
        a, b = _pair()
        pred = KB.predict_pair(a, b)
        counts = {label: 0 for label in KB.LABELS}
        for v in pred["years"].values():
            counts[v["label"]] += 1
        n = len(pred["years"])
        for label, c in counts.items():
            assert 0.2 * n < c < 0.47 * n, f"{label} 占比异常：{c}/{n}"

    def test_is_symmetric_in_a_and_b(self):
        """共振分交换甲乙逐字相同（这是 `pair_key` 排序拼接的前提），标签也必须相同。"""
        a, b = _pair()
        forward = KB.predict_pair(a, b)
        backward = KB.predict_pair(b, a)
        assert forward["years"] == backward["years"]
        assert forward["thresholds"] == backward["thresholds"]

    def test_span_is_the_intersection_of_both_charts(self):
        """两盘起运年不同，童限期没有共同刻度，故区间比单盘短。"""
        a, b = _pair()
        pred = KB.predict_pair(a, b)
        from app.domain.fortune_score import build_kline

        single_a = build_kline(a, max_age=KB.AGE_SPAN)
        single_b = build_kline(b, max_age=KB.AGE_SPAN)
        assert pred["startYear"] == max(single_a[0]["year"], single_b[0]["year"])
        assert pred["endYear"] == min(single_a[-1]["year"], single_b[-1]["year"])

    def test_thresholds_are_relative_not_absolute(self):
        """「顺」是该对自己一辈子里的高位，不是跨对可比的绝对刻度。"""
        a, b = _pair()
        pred = KB.predict_pair(a, b)
        assert pred["thresholds"]["down"] < pred["thresholds"]["up"]
        assert pred["thresholds"]["collapsed"] is False

    @pytest.mark.parametrize("kw", [{"dimension": "nope"}, {"max_age": 0}, {"max_age": 999}])
    def test_rejects_bad_options(self, kw):
        a, b = _pair()
        with pytest.raises(ValueError):
            KB.predict_pair(a, b, **kw)


# ---------------- 逐项诊断 ----------------


class TestTermDiagnostics:
    def _rows(self, *, with_down: bool = True):
        rows = [
            {"truth": KB.LABEL_UP, "terms": {"trend": 10.0, "align": 10.0, "sync": 0.0, "palace": 5.0}},
            {"truth": KB.LABEL_UP, "terms": {"trend": 12.0, "align": 8.0, "sync": 0.0, "palace": 5.0}},
        ]
        if with_down:
            rows += [
                {"truth": KB.LABEL_DOWN, "terms": {"trend": 0.0, "align": 2.0, "sync": 0.0, "palace": 7.0}},
                {"truth": KB.LABEL_DOWN, "terms": {"trend": 2.0, "align": 0.0, "sync": 0.0, "palace": 8.0}},
            ]
        return rows

    def test_delta_is_up_mean_minus_down_mean(self):
        out = {d["term"]: d for d in KB._term_diagnostics(self._rows())}
        assert list(out) == list(KB.TERMS_ORDER)
        assert out["trend"]["meanUp"] == 11.0
        assert out["trend"]["meanDown"] == 1.0
        assert out["trend"]["delta"] == 10.0
        assert out["trend"]["signOk"] is True

    def test_negative_delta_flags_the_culprit_term(self):
        """delta<=0 就是"这一项在帮倒忙"，这是权重调参该先看的地方。"""
        out = {d["term"]: d for d in KB._term_diagnostics(self._rows())}
        assert out["palace"]["delta"] == -2.5
        assert out["palace"]["signOk"] is False

    def test_zero_delta_is_not_reported_as_ok(self):
        """平手不算方向正确 —— 0 项对区分度没有贡献，不能算"通过"。"""
        out = {d["term"]: d for d in KB._term_diagnostics(self._rows())}
        assert out["sync"]["delta"] == 0.0
        assert out["sync"]["signOk"] is False

    def test_missing_side_yields_none(self):
        """只有吉没有凶时不能硬算均值差，应给 None 而不是 0（0 会被读成"没作用"）。"""
        out = {d["term"]: d for d in KB._term_diagnostics(self._rows(with_down=False))}
        assert out["trend"]["delta"] is None
        assert out["trend"]["signOk"] is None
        assert out["trend"]["samplesUp"] == 2
        assert out["trend"]["samplesDown"] == 0

    def test_mid_rows_are_ignored(self):
        """实际为平的年份不参与逐项诊断：它既不是"该高"也不是"该低"。"""
        rows = self._rows() + [{"truth": KB.LABEL_MID, "terms": {"trend": 999.0}}]
        out = {d["term"]: d for d in KB._term_diagnostics(rows)}
        assert out["trend"]["meanUp"] == 11.0


# ---------------- run_pair_backtest ----------------


class TestRunPairBacktest:
    def _run(self, events, *, a=None, b=None, **kw):
        a = a or _pair()[0]
        b = b or _pair()[1]
        kw.setdefault("min_samples", 20)
        return KB.run_pair_backtest([(a, b, events)], **kw)

    def test_perfect_labels_hit_everything(self):
        a, b = _pair()
        events = _events_from_labels(KB.predict_pair(a, b))
        out = self._run(events, a=a, b=b)
        s = out["summary"]
        assert s["samples"] == len(events)
        assert s["hitRateStrict"] == 1.0
        assert s["liftStrict"] > 0
        assert s["ok"] is True
        assert s["significant"] is True
        assert not [w for w in out["warnings"] if "样本不足" in w]

    def test_flipped_labels_miss_everything(self):
        """方向被接反时命中率必须是 0（而不是接近随机），否则这个测试没有鉴别力。"""
        a, b = _pair()
        events = _events_from_labels(KB.predict_pair(a, b), flip=True)
        out = self._run(events, a=a, b=b)
        assert out["summary"]["hitRateStrict"] == 0.0
        assert out["summary"]["significant"] is False

    def test_reports_window_even_when_nothing_matched(self):
        """事件全落在窗口外时必须说得出区间，否则用户以为是自己没录进去。"""
        a, b = _pair()
        pred = KB.predict_pair(a, b)
        events = [
            {"ganzhiYear": pred["endYear"] + 5, "polarity": 1},
            {"ganzhiYear": pred["startYear"] - 5, "polarity": -1},
        ]
        out = self._run(events, a=a, b=b)
        assert out["events"]["used"] == 0
        assert out["events"]["unmatched"] == 2
        assert out["summary"]["samples"] == 0
        assert out["spanFrom"] == pred["startYear"]
        assert out["spanTo"] == pred["endYear"]
        assert out["ageSpan"] == KB.AGE_SPAN
        assert out["unmatchedYears"][0]["pair"]
        assert any(f"1-{KB.AGE_SPAN} 虚岁" in w for w in out["warnings"])

    def test_span_is_reported_without_events_too(self):
        """一条事件都没有时窗口仍要回 —— 前端要靠它解释"为什么这条不算"。"""
        out = self._run([])
        assert out["summary"]["samples"] == 0
        assert out["spanFrom"] is not None and out["spanTo"] is not None

    def test_invalid_polarity_is_counted_not_crashed(self):
        a, b = _pair()
        pred = KB.predict_pair(a, b)
        year = pred["startYear"]
        events = [{"ganzhiYear": year, "polarity": 7}]
        out = self._run(events, a=a, b=b)
        assert out["events"]["invalid"] == 1
        assert out["events"]["used"] == 0
        assert any("polarity 非法" in w for w in out["warnings"])

    def test_duplicate_anchor_is_reported(self):
        """同对·同年·同极性记两遍会虚高样本数，不拦但必须报。"""
        a, b = _pair()
        events = _events_from_labels(KB.predict_pair(a, b))[:3] * 2
        out = self._run(events, a=a, b=b)
        assert out["events"]["duplicate"] == 3
        assert any("重复锚点" in w for w in out["warnings"])

    def test_low_samples_says_so_instead_of_printing_a_percentage(self):
        a, b = _pair()
        events = _events_from_labels(KB.predict_pair(a, b))[:3]
        out = self._run(events, a=a, b=b, min_samples=20)
        assert out["summary"]["samples"] == 3
        assert out["summary"]["ok"] is False
        assert out["summary"]["hitRate"] is not None  # 仍算，只是不可用
        assert any("样本不足" in w for w in out["warnings"])

    def test_relies_on_relation_for_grouping_only(self):
        """关系类型只做复盘切片：改 relation 不该改变任何命中率。"""
        a, b = _pair()
        events = _events_from_labels(KB.predict_pair(a, b))
        for e in events:
            e["relation"] = "夫妻"
        base = self._run(events, a=a, b=b)
        for e in events:
            e["relation"] = "同事"
        switched = self._run(events, a=a, b=b)
        assert base["summary"] == switched["summary"]
        assert base["byRelation"][0]["relation"] == "夫妻"
        assert switched["byRelation"][0]["relation"] == "同事"

    def test_blank_relation_becomes_unlabelled(self):
        a, b = _pair()
        events = _events_from_labels(KB.predict_pair(a, b))[:5]
        for e in events:
            e["relation"] = ""
        out = self._run(events, a=a, b=b)
        assert out["byRelation"][0]["relation"] == "未标注"

    def test_term_diagnostics_reach_the_result(self):
        a, b = _pair()
        events = _events_from_labels(KB.predict_pair(a, b))
        out = self._run(events, a=a, b=b)
        assert [d["term"] for d in out["termDiagnostics"]] == list(KB.TERMS_ORDER)
        for d in out["termDiagnostics"]:
            assert d["samplesUp"] > 0 and d["samplesDown"] > 0
            assert d["delta"] is not None

    def test_misses_carry_pair_and_relation(self):
        a, b = _pair()
        events = _events_from_labels(KB.predict_pair(a, b), flip=True)
        out = self._run(events, a=a, b=b)
        assert out["misses"], "全错的情况下不该没有错判样例"
        assert set(out["misses"][0]) >= {"pair", "year", "ganzhi", "pred", "truth", "score", "relation"}

    def test_multiple_pairs_are_aggregated(self):
        """多对汇总时阈值仍各对各的分布取，pairs 计数必须是去重后的对数。"""
        a, b = _pair()
        c = chart_of("stem_bing")
        events_ab = _events_from_labels(KB.predict_pair(a, b))[:20]
        events_ac = _events_from_labels(KB.predict_pair(a, c))[:20]
        out = KB.run_pair_backtest(
            [(a, b, events_ab), (a, c, events_ac)], min_samples=20
        )
        assert out["summary"]["samples"] == 40
        assert out["pairs"] == 2
        assert len(out["byPair"]) == 2

    @pytest.mark.parametrize(
        "kw",
        [
            {"dimension": "nope"},
            {"dimension": "auto"},  # 关系事件没有事业/健康之分，不存在 auto 映射
            {"min_samples": 0},
        ],
    )
    def test_rejects_bad_options(self, kw):
        with pytest.raises(ValueError):
            self._run([], **kw)


def test_single_chart_backtest_also_reports_its_span():
    """单盘回测与合盘同款回报：前端两处都要能说清"窗口是多少"。"""
    chart = chart_of(CASE_A)
    out = KB.run_backtest([(chart, [])])
    assert out["ageSpan"] == KB.AGE_SPAN
    assert out["spanFrom"] is not None and out["spanTo"] is not None
    assert out["spanFrom"] < out["spanTo"]
