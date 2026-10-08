"""回测引擎单测：立春换岁换算、单盘预测标签、命中率与随机基线。

刻意**不连数据库、不走进口**：回测是纯函数，用合成标注就能把"模型有区分度 / 没区分度 /
全判反"三种极端情形钉死。真实标注攒够之前，这三条是引擎唯一的正确性依据。

合成标注怎么造才有效
--------------------
不能手写"某年吉"——那是在用我的假定验我的假定。做法是**先取模型的预测标签**，
再按确定规则反推标注：

- 对齐：标注 = 预测 → 命中率必须为 1
- 反向：标注 = 预测的反面 → 吉凶命中率必须为 0（平对平仍算命中）
- 无关：标注用固定种子随机生成 → 命中率必须回落到 `randomBaseline` 附近

第三条是关键：它证明"命中率高"不是靠标签分布偶然对齐刷出来的。
"""

from __future__ import annotations

import copy
import datetime
import random
from functools import lru_cache

import pytest
from lunar_python import Solar

from app.domain import fortune_score as FS, kline_backtest as KB
from app.domain.xipan import _year_ganzhi, ganzhi_year_of
from tests import bazi_golden as BG


@lru_cache(maxsize=None)
def chart_of(case_id: str):
    """建盘较贵（约 0.35s），跨用例缓存。"""
    return BG.build_case_chart(BG.find_case(case_id))


def _events_from_labels(pred: dict, rule) -> list[dict]:
    """按 rule(label) → polarity 反推标注，覆盖该盘全部年份。"""
    return [
        {"ganzhiYear": y, "polarity": rule(v["label"]), "domain": "general"}
        for y, v in sorted(pred["years"].items())
    ]


# ---------------- 立春换岁 ----------------


class TestGanzhiYearOf:
    def test_january_belongs_to_previous_lunar_year(self):
        """1-2 月按公历年填是最高频的录入错误，这条把它钉住。"""
        assert ganzhi_year_of("1990-01-15") == 1989
        assert ganzhi_year_of("1990-02-03") == 1989
        assert ganzhi_year_of("1990-02-04") == 1990  # 1990 立春当天

    def test_day_of_lichun_counts_as_new_year(self):
        """粒度只到日：立春当天算当年（事件标注拿不到时辰）。"""
        assert ganzhi_year_of(datetime.date(2026, 2, 4)) == 2026
        assert ganzhi_year_of(datetime.date(2026, 2, 3)) == 2025

    def test_accepts_str_date_and_datetime(self):
        d = datetime.date(2020, 6, 1)
        assert ganzhi_year_of("2020-06-01") == ganzhi_year_of(d) == ganzhi_year_of(
            datetime.datetime(2020, 6, 1, 23, 30)
        )

    def test_matches_lunar_python_across_a_full_year(self):
        """换算结果必须与排盘库的立春口径逐年一致（含闰年与立春前边界）。"""
        for day in range(1, 366):
            d = datetime.date(2024, 1, 1) + datetime.timedelta(days=day - 1)
            lunar = Solar.fromYmdHms(d.year, d.month, d.day, 12, 0, 0).getLunar()
            assert _year_ganzhi(ganzhi_year_of(d)) == lunar.getYearInGanZhiByLiChun(), str(d)

    def test_rejects_unsupported_type(self):
        with pytest.raises(ValueError):
            ganzhi_year_of(20260115)


# ---------------- 单年预测 ----------------


class TestYearScore:
    def test_close_matches_candle(self):
        pred = KB.predict_chart(chart_of("stem_ren"))
        candle = {c["year"]: c for c in FS.build_kline(chart_of("stem_ren"), max_age=KB.AGE_SPAN)}
        y = sorted(pred["years"])[0]
        assert KB.year_score(candle[y], KB.PREDICTOR_CLOSE) == candle[y]["close"]

    def test_mean_predictor_is_month_average_plus_relation(self):
        candle = {"close": 1.0, "monthScores": [10.0, 20.0, 30.0], "relationAdj": 2.0}
        assert KB.year_score(candle, KB.PREDICTOR_MEAN) == 22.0

    def test_mean_falls_back_to_close_without_months(self):
        assert KB.year_score({"close": 42.0, "monthScores": []}, KB.PREDICTOR_MEAN) == 42.0

    def test_unknown_predictor_raises(self):
        with pytest.raises(ValueError):
            KB.year_score({"close": 1.0}, "nope")


class TestPredictChart:
    def test_thresholds_come_from_full_span_and_split_into_thirds(self):
        """吉/凶界线取全期分位，故三类样本量应大致均衡（这是阈值没取错的最简证据）。"""
        pred = KB.predict_chart(chart_of("stem_ren"))
        counts = {"吉": 0, "平": 0, "凶": 0}
        for v in pred["years"].values():
            counts[v["label"]] += 1
        n = sum(counts.values())
        assert n == len(pred["years"])
        for label, c in counts.items():
            assert 0.2 * n <= c <= 0.45 * n, f"{label} 类样本量失衡：{counts}"

    def test_thresholds_are_not_affected_by_max_age_of_events(self):
        """同 max_age 两次调用完全相等（回测可复现的前提）。"""
        chart = chart_of("stem_ren")
        assert KB.predict_chart(chart) == KB.predict_chart(chart)

    def test_score_above_up_cut_is_ji_and_below_down_cut_is_xiong(self):
        pred = KB.predict_chart(chart_of("stem_ren"))
        down, up = pred["thresholds"]["down"], pred["thresholds"]["up"]
        for v in pred["years"].values():
            assert KB.label_of(v["score"], down, up) == v["label"]

    def test_labels_are_anchored_to_bazi_ganzhi(self):
        pred = KB.predict_chart(chart_of("stem_ren"))
        for year, v in pred["years"].items():
            assert v["ganzhi"] == _year_ganzhi(year)

    def test_rejects_unknown_dimension_and_predictor(self):
        chart = chart_of("stem_ren")
        with pytest.raises(ValueError):
            KB.predict_chart(chart, dimension="nope")
        with pytest.raises(ValueError):
            KB.predict_chart(chart, predictor="nope")

    @pytest.mark.parametrize("max_age", [0, -1, KB.MAX_AGE_LIMIT + 1])
    def test_rejects_bad_max_age(self, max_age):
        with pytest.raises(ValueError):
            KB.predict_chart(chart_of("stem_ren"), max_age=max_age)


class TestWilsonInterval:
    def test_none_without_samples(self):
        assert KB.wilson_interval(0, 0) is None

    def test_brackets_point_estimate_and_stays_in_unit_range(self):
        lo, hi = KB.wilson_interval(7, 10)
        assert 0.0 <= lo < 0.7 < hi <= 1.0

    def test_all_hits_lower_bound_rises_with_n(self):
        """10/10 的区间下界必然高于 3/3：样本多才算数，这正是要给区间的原因。"""
        small = KB.wilson_interval(3, 3)
        big = KB.wilson_interval(30, 30)
        assert big[0] > small[0]


# ---------------- 回测主流程 ----------------


class TestRunBacktest:
    def setup_method(self):
        self.chart = chart_of("stem_ren")
        self.pred = KB.predict_chart(self.chart)
        self.year = sorted(self.pred["years"])[0]

    def _run(self, events, **kw):
        return KB.run_backtest([(self.chart, events)], **kw)

    def test_perfect_alignment_scores_one(self):
        events = _events_from_labels(self.pred, lambda lab: {"吉": 1, "平": 0, "凶": -1}[lab])
        out = self._run(events)
        assert out["summary"]["hitRate"] == 1.0
        assert out["summary"]["hitRateStrict"] == 1.0
        assert out["summary"]["ok"] is True
        assert out["summary"]["significant"] is True
        assert out["misses"] == []

    def test_inverted_alignment_scores_zero_on_decided(self):
        """全判反时吉凶命中率必须为 0（平对平仍算命中，故总命中率不为 0）。"""
        events = _events_from_labels(self.pred, lambda lab: {"吉": -1, "平": 0, "凶": 1}[lab])
        out = self._run(events)
        assert out["summary"]["hitRateStrict"] == 0.0
        assert out["summary"]["lift"] < 0
        assert out["summary"]["significant"] is False
        assert len(out["misses"]) == KB.MISS_EXAMPLES

    def test_uncorrelated_labels_fall_back_to_random_baseline(self):
        """核心反例：标注与预测无关时，命中率必须回落到随机基线（不是高于）。

        随机标注用固定种子生成，故结论可复现；容差取约 3 个标准误。
        """
        rng = random.Random(0)
        events = [
            {"ganzhiYear": y, "polarity": rng.choice([1, -1]), "domain": "general"}
            for y in sorted(self.pred["years"])
        ]
        s = self._run(events)["summary"]
        assert abs(s["hitRate"] - s["randomBaseline"]) < 0.15, s
        assert s["significant"] is False

    def test_random_baseline_tracks_label_distribution(self):
        """事件全为凶时，"全猜凶"的基线才是那个该被超越的数（而不是 1/3）。"""
        events = [
            {"ganzhiYear": y, "polarity": -1, "domain": "general"} for y in sorted(self.pred["years"])
        ]
        s = self._run(events)["summary"]
        assert s["majorityBaseline"] == 1.0
        assert s["randomBaseline"] == round(
            sum(v["label"] == "凶" for v in self.pred["years"].values())
            / len(self.pred["years"]),
            4,
        )

    def test_pooled_charts_keep_per_chart_thresholds(self):
        """多盘汇总时阈值各按自己分布取，且分组样本数加总等于总数。"""
        chart_b = chart_of("stem_jia")
        pred_b = KB.predict_chart(chart_b)
        events_a = _events_from_labels(self.pred, lambda lab: {"吉": 1, "平": 0, "凶": -1}[lab])
        events_b = _events_from_labels(pred_b, lambda lab: {"吉": 1, "平": 0, "凶": -1}[lab])
        out = KB.run_backtest([(self.chart, events_a), (chart_b, events_b)])
        assert out["charts"] == 2
        assert out["events"]["used"] == len(events_a) + len(events_b)
        assert sum(g["samples"] for g in out["byChart"]) == out["events"]["used"]
        assert out["summary"]["hitRate"] == 1.0

    def test_auto_dimension_follows_event_domain(self):
        events = [
            {"ganzhiYear": self.year, "polarity": 1, "domain": "wealth"},
            {"ganzhiYear": self.year, "polarity": -1, "domain": "career"},
            {"ganzhiYear": self.year, "polarity": 1, "domain": "general"},
        ]
        out = self._run(events, dimension=KB.DIMENSION_AUTO)
        assert {g["dimension"] for g in out["byDimension"]} == {"wealth", "career", "comprehensive"}

    def test_explicit_dimension_overrides_domain(self):
        events = [{"ganzhiYear": self.year, "polarity": 1, "domain": "wealth"}]
        out = self._run(events, dimension="health")
        assert {g["dimension"] for g in out["byDimension"]} == {"health"}

    def test_events_before_qiyun_are_unmatched_not_wrong(self):
        """起运前的童限期 K 线没有刻度，事件只能报"未覆盖"，不能算成判错。"""
        events = [
            {"ganzhiYear": self.pred["startYear"] - 1, "polarity": 1, "domain": "general"},
            {"ganzhiYear": self.year, "polarity": 1, "domain": "general"},
        ]
        out = self._run(events)
        assert out["events"] == {
            "total": 2,
            "used": 1,
            "unmatched": 1,
            "invalid": 0,
            "duplicate": 0,
        }
        assert out["unmatchedYears"][0]["ganzhiYear"] == self.pred["startYear"] - 1
        assert any("K 线区间" in w for w in out["warnings"])

    def test_invalid_polarity_is_skipped_with_warning(self):
        events = [
            {"ganzhiYear": self.year, "polarity": 1, "domain": "general"},
            {"ganzhiYear": self.year, "polarity": 5, "domain": "general"},
            {"ganzhiYear": self.year, "polarity": None, "domain": "general"},
        ]
        out = self._run(events)
        assert out["events"]["invalid"] == 2
        assert out["events"]["used"] == 1
        assert any("polarity 非法" in w for w in out["warnings"])

    def test_duplicate_anchor_is_reported_not_merged(self):
        """同盘同年同域同极性录两条：两条都算，但要报出来（否则样本数被虚高）。"""
        events = [
            {"ganzhiYear": self.year, "polarity": 1, "domain": "general"},
            {"ganzhiYear": self.year, "polarity": 1, "domain": "general"},
        ]
        out = self._run(events)
        assert out["events"]["used"] == 2
        assert out["events"]["duplicate"] == 1
        assert any("重复锚点" in w for w in out["warnings"])

    def test_insufficient_samples_are_flagged(self):
        out = self._run([{"ganzhiYear": self.year, "polarity": 1, "domain": "general"}], min_samples=20)
        assert out["summary"]["ok"] is False
        assert out["summary"]["samples"] == 1
        assert any("样本不足" in w for w in out["warnings"])

    def test_empty_events_are_not_an_error(self):
        out = self._run([])
        assert out["summary"]["samples"] == 0
        assert out["summary"]["hitRate"] is None
        assert out["summary"]["ok"] is False
        assert any("没有任何可用样本" in w for w in out["warnings"])

    def test_misses_are_ranked_by_surprise(self):
        """错判样例按"惊讶度"排：判吉却凶的，分数越高越该被看到。"""
        events = _events_from_labels(self.pred, lambda lab: {"吉": -1, "平": 0, "凶": 1}[lab])
        out = self._run(events)
        moves = [
            (m["score"] if m["truth"] == "凶" else 100.0 - m["score"]) for m in out["misses"]
        ]
        assert moves == sorted(moves, reverse=True)

    def test_does_not_mutate_input(self):
        events = _events_from_labels(self.pred, lambda lab: {"吉": 1, "平": 0, "凶": -1}[lab])
        snapshot = copy.deepcopy(events)
        self._run(events)
        assert events == snapshot

    def test_rejects_bad_dimension_predictor_and_min_samples(self):
        with pytest.raises(ValueError):
            self._run([], dimension="nope")
        with pytest.raises(ValueError):
            self._run([], predictor="nope")
        with pytest.raises(ValueError):
            self._run([], min_samples=0)


def test_thresholds_are_per_chart_relative_not_absolute():
    """两张盘都取自己的上 1/3，故同一分数在两张盘上可以落在不同档 —— 这是刻意的。"""
    a = KB.predict_chart(chart_of("stem_ren"))
    b = KB.predict_chart(chart_of("zhuanwang_quzhi"))
    assert a["thresholds"]["up"] != b["thresholds"]["up"]
