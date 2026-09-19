"""K 线标定体检（`scripts/kline_diagnose.py`）四条判据的边界测试。

为什么值得单测：`scripts/` **不在任何测试或架构守卫的扫描范围内**，而本脚本是
**改 `fortune_score` 系数后的第一道关**（docstring 明写"任何一处被改动都要重跑本脚本"）。
判据写反（`<` 写成 `<=`、`0/100` 边界漏掉一侧、`ups in (0, len)` 漏掉全阴）
会让"该报错时不报错"—— 而此时**黄金快照照样全绿**，因为快照只能证明"和上次一样"，
证明不了"这次是个好形状"。本脚本真抓过事故：open=寅月(木)/close=丑月(土) 时
固定五行差压过年际差，实测 36/36 盘全阳、实体零信息量。

不建盘：`KG.cached_kline_dim` 直接打桩成合成蜡烛，毫秒级，且能把每个判据的
阈值两侧都摆出来（真实命盘无法构造"恰好跨过阈值"的形状）。
"""

from __future__ import annotations

import functools
import importlib.util
from pathlib import Path

import pytest

from app.domain import fortune_score as FS
from tests import kline_golden as KG

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

CASE = {"id": "fake_case"}


@functools.lru_cache(maxsize=1)
def diag():
    """按路径显式加载（`scripts` 不是包，不能靠 import 名撞）。"""
    spec = importlib.util.spec_from_file_location(
        "kline_diag_under_test", SCRIPTS_DIR / "kline_diagnose.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------- 合成蜡烛 ----------------


def _candles(pairs: list[tuple[float, float]]) -> list[dict]:
    """(open, close) 序列 → 蜡烛 dict。isUp 由 close > open 推出（与引擎同口径）。"""
    out = []
    for i, (o, c) in enumerate(pairs):
        out.append(
            {
                "year": 2000 + i,
                "open": o,
                "close": c,
                "high": max(o, c),
                "low": min(o, c),
                "isUp": c > o,
            }
        )
    return out


def _linked(closes: list[float]) -> list[dict]:
    """首尾相接的蜡烛序列（open_i = close_{i-1}），用于衔接与"健康形状"。"""
    pairs, prev = [], closes[0]
    for c in closes:
        pairs.append((prev, c))
        prev = c
    return _candles(pairs)


def _flat_line(close: float, n: int = 10) -> list[dict]:
    """收盘分只有 2 个取值的塌缩序列（会同时触发"平线"与"塌缩"）。"""
    return _candles([(close, close if i % 2 else close + 0.5) for i in range(n)])


# 健康形状：跨度 50、6 个不同取值、不触边界、阴阳混合、首尾相接
HEALTHY = [20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 60.0, 50.0, 40.0, 30.0]


def use(monkeypatch, mapping: dict) -> None:
    """打桩 `cached_kline_dim`；缺键返回 []（等价于"该盘该维度没数据"）。"""
    monkeypatch.setattr(KG, "cached_kline_dim", lambda cid, dim: mapping.get((cid, dim), []))


def _one(candles: list[dict], dim: str = FS.DIM_COMPREHENSIVE) -> dict:
    return {(CASE["id"], dim): candles}


# ---------------- 判据 1+2：不饱和 / 不塌缩 ----------------


class TestDistribution:
    def test_healthy_shape_reports_nothing(self, monkeypatch):
        use(monkeypatch, _one(_linked(HEALTHY)))
        assert diag().report_distribution([CASE], (FS.DIM_COMPREHENSIVE,)) == []

    def test_upper_boundary_counts_as_saturated(self, monkeypatch):
        """恰好 100 必须算触边界 —— 写成 `> 100` 就漏掉整整一类贴顶。"""
        use(monkeypatch, _one(_linked([20.0, 40.0, 60.0, 80.0, 100.0, 60.0, 40.0])))
        problems = diag().report_distribution([CASE], (FS.DIM_COMPREHENSIVE,))
        assert any("硬边界" in p for p in problems)

    def test_lower_boundary_counts_as_saturated(self, monkeypatch):
        use(monkeypatch, _one(_linked([0.0, 20.0, 40.0, 60.0, 80.0, 60.0, 20.0])))
        problems = diag().report_distribution([CASE], (FS.DIM_COMPREHENSIVE,))
        assert any("硬边界" in p for p in problems)

    def test_just_above_lower_boundary_is_fine(self, monkeypatch):
        """0.1 不该被判成触边界 —— 这条钉住"边界是闭区间"这个判断本身。"""
        use(monkeypatch, _one(_linked([0.1, 20.0, 40.0, 60.0, 80.0, 60.0, 20.0])))
        problems = diag().report_distribution([CASE], (FS.DIM_COMPREHENSIVE,))
        assert not any("硬边界" in p for p in problems)

    def test_collapsed_span_is_reported(self, monkeypatch):
        """全部挤在 48-52 之间：跨度远小于 MIN_SPREAD，说明分数塌缩。"""
        use(monkeypatch, _one(_linked([48.0, 52.0, 49.0, 51.0, 50.0, 48.5, 51.5, 50.5])))
        problems = diag().report_distribution([CASE], (FS.DIM_COMPREHENSIVE,))
        assert any("塌缩" in p for p in problems)

    def test_flat_line_is_reported(self, monkeypatch):
        """收盘分取值数 ≤ 5 即视为平线（实体没有信息量）。"""
        use(monkeypatch, _one(_flat_line(50.0)))
        problems = diag().report_distribution([CASE], (FS.DIM_COMPREHENSIVE,))
        assert any("平线" in p for p in problems)

    def test_missing_candles_are_skipped_not_crashed(self, monkeypatch):
        """某盘某维度没有蜡烛时跳过，不该把空盘当成"塌缩到 0"。"""
        use(monkeypatch, {})
        assert diag().report_distribution([CASE], (FS.DIM_COMPREHENSIVE,)) == []


# ---------------- 判据 3：方向非退化 ----------------


class TestDirection:
    def test_mixed_candles_pass(self, monkeypatch):
        use(monkeypatch, _one(_linked(HEALTHY)))
        assert diag().report_direction([CASE], (FS.DIM_COMPREHENSIVE,), False) == []

    def test_all_up_is_degenerate(self, monkeypatch):
        """历史事故形态：整盘全阳 ⇒ 实体宽度恒定，肉眼与统计都读不出信息。"""
        use(monkeypatch, _one(_candles([(10.0 + i, 20.0 + i) for i in range(10)])))
        problems = diag().report_direction([CASE], (FS.DIM_COMPREHENSIVE,), False)
        assert any("方向恒定" in p for p in problems)

    def test_all_down_is_degenerate(self, monkeypatch):
        """全阴同样退化 —— 只查"全阳"是漏判。"""
        use(monkeypatch, _one(_candles([(20.0 + i, 10.0 + i) for i in range(10)])))
        problems = diag().report_direction([CASE], (FS.DIM_COMPREHENSIVE,), False)
        assert any("方向恒定" in p for p in problems)

    def test_single_up_candle_is_not_degenerate(self, monkeypatch):
        """只有 1 根阳线也不算退化（退化是"完全没有另一方向"）。"""
        pairs = [(20.0, 10.0)] * 5 + [(10.0, 20.0)] + [(20.0, 10.0)] * 4
        use(monkeypatch, _one(_candles(pairs)))
        assert diag().report_direction([CASE], (FS.DIM_COMPREHENSIVE,), False) == []


# ---------------- 判据 4：维度有区分度 ----------------


def _shifted(base: list[float], k: float) -> list[float]:
    return [v + k for v in base]


class TestDimensionSpread:
    BASE = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 95.0]

    def _all_dims(self, monkeypatch, mode: str) -> None:
        """mode="distinct"：非综合维度各整体平移（彼此也不同）；mode="same"：全与综合相同。

        偏移量用**递增计数**而不是 `enumerate` 下标 —— 综合维度未必排在第一位，
        用下标会让某个非综合维度正好得到 0 偏移、与综合逐年相同，测试就测歪了。
        """
        mapping, k = {}, 0
        for dim in FS.DIMENSIONS:
            if mode == "same" or dim == FS.DIM_COMPREHENSIVE:
                offset = 0.0
            else:
                k += 1
                offset = float(k)
            mapping[(CASE["id"], dim)] = _candles([(v, v) for v in _shifted(self.BASE, offset)])
        use(monkeypatch, mapping)

    def test_distinguishable_dimensions_pass(self, monkeypatch):
        """每个非综合维度整体平移 ⇒ 与综合逐年不同、彼此也不同。"""
        self._all_dims(monkeypatch, "distinct")
        assert diag().report_dimension_spread([CASE]) == []

    def test_identical_to_comprehensive_is_reported(self, monkeypatch):
        """维度与综合逐年相同 ⇒ 切维度等于摆设。"""
        self._all_dims(monkeypatch, "same")
        problems = diag().report_dimension_spread([CASE])
        assert any("与综合维度差异" in p for p in problems)

    def test_high_overlap_between_dimensions_is_reported(self, monkeypatch):
        """两个非综合维度彼此重合过高 ⇒ 区分度不足。

        构造：维度 A 与维度 B 用同一个偏移、综合用另一个 ——
        这样 A/B 与综合差异够（不触发第一条），但 A 与 B 完全重合。
        """
        mapping = {
            (CASE["id"], FS.DIM_COMPREHENSIVE): _candles([(v, v) for v in self.BASE]),
        }
        for dim in FS.DIMENSIONS:
            if dim != FS.DIM_COMPREHENSIVE:
                mapping[(CASE["id"], dim)] = _candles([(v + 7, v + 7) for v in self.BASE])
        use(monkeypatch, mapping)
        problems = diag().report_dimension_spread([CASE])
        assert any("重合" in p for p in problems)


# ---------------- 判据 5：蜡烛衔接 ----------------


class TestContiguity:
    def test_linked_candles_pass(self, monkeypatch):
        use(monkeypatch, _one(_linked(HEALTHY)))
        assert diag().report_contiguity([CASE]) == []

    def test_gap_is_reported(self, monkeypatch):
        """open 没接上一年 close ⇒ 实体失去同比语义。"""
        broken = _linked(HEALTHY)
        broken[3]["open"] = broken[3]["open"] + 5
        use(monkeypatch, _one(broken))
        problems = diag().report_contiguity([CASE])
        assert any("首尾相接" in p for p in problems)

    def test_single_candle_is_vacuously_contiguous(self, monkeypatch):
        """只有一根蜡烛时没有"衔接"可言，不该报错（也不该除零）。"""
        use(monkeypatch, _one(_candles([(10.0, 20.0)])))
        assert diag().report_contiguity([CASE]) == []


# ---------------- 退出码 ----------------


class TestExitCodes:
    """`scripts/kline_diagnose.py` 声明"可直接挂 CI"，退出码就是它的契约。"""

    def test_clean_run_exits_0(self, monkeypatch, capsys):
        use(monkeypatch, _one(_linked(HEALTHY)))
        monkeypatch.setattr(diag(), "_cases", lambda cid: [CASE])
        assert diag().main(["--mode", "contiguity"]) == 0
        assert "体检通过" in capsys.readouterr().out

    def test_problem_exits_1(self, monkeypatch, capsys):
        use(monkeypatch, _one(_flat_line(50.0)))
        monkeypatch.setattr(diag(), "_cases", lambda cid: [CASE])
        assert diag().main(["--mode", "dist"]) == 1
        assert "体检未通过" in capsys.readouterr().out

    def test_bad_dimension_exits_2(self, monkeypatch):
        """参数错误返 2，与"体检未通过"的 1 区分开 —— CI 里两者含义不同。"""
        monkeypatch.setattr(diag(), "_cases", lambda cid: [CASE])
        assert diag().main(["--dimension", "nope"]) == 2

    def test_unknown_case_exits_2(self, capsys):
        with pytest.raises(SystemExit) as exc:
            diag()._cases("no_such_case_id")
        assert exc.value.code == 2
        assert "未找到命盘" in capsys.readouterr().out
