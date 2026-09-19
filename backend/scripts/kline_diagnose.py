"""命理 K 线标定与体检：分数分布、蜡烛方向、OHLC 自洽性、维度形状。

用途：`fortune_score` 里的系数（K_SCORE / 喜忌基准 / 岁运柱权重 / 关系修正表 /
维度侧重表）**任何一处被改动都要重跑本脚本**，确认新标定仍不饱和、不塌缩、
方向不退化、各维度区分度足够，确认无误后再重生成黄金快照。

为什么单靠黄金快照不够：快照只能证明"和上次一样"，证明不了"这次是好形状"。
本脚本给出的是**形状判据**，两者互补。

四条判据（任一不过会以非零码退出，可直接挂 CI）：

1. **不饱和**：触及 0 / 100 硬边界的样本数应为 0。全贴顶贴底说明 K_SCORE 过大，
   或某个维度的侧重系数把曲线推出了量程。
2. **不塌缩**：每张盘的收盘分取值数 > 5，且全局分位跨度 ≥ 20 分。
   全平线说明喜忌方向算成了恒定值。
3. **方向非退化**：**每一张**盘都必须同时出现阳线与阴线。
   历史事故：`open=寅月(木)` / `close=丑月(土)` 时两者只差一个流月权重，
   寅丑的固定五行差压过年际差，实测 36/36 盘全阳或全阴、实体零信息量。
4. **维度有区分度**：每个非综合维度至少 80% 的年份与综合维度不同，
   且维度两两之间重合 < 50%。否则维度切换等于摆设。

用法：
    # 全量体检（36 个黄金盘 × 5 个维度，约 30s）
    ../.venv/Scripts/python.exe scripts/kline_diagnose.py

    # 只体检某个维度
    ../.venv/Scripts/python.exe scripts/kline_diagnose.py --dimension career

    # 逐命例列出方向分布
    ../.venv/Scripts/python.exe scripts/kline_diagnose.py --mode direction --dimension wealth

    # 指定命盘
    ../.venv/Scripts/python.exe scripts/kline_diagnose.py --case stem_yi
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain import fortune_score as FS  # noqa: E402
from tests import kline_golden as KG  # noqa: E402

MAX_AGE = KG.MAX_AGE
# 分位跨度低于此值即认为"塌缩在中间"
MIN_SPREAD = 20.0
# 非综合维度与综合维度的最小差异年占比
MIN_DIM_DIFF = 0.8
# 两个维度之间允许的最大重合年占比
MAX_DIM_OVERLAP = 0.5


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p / 100)))
    return ordered[idx]


def _cases(case_id: str | None) -> list[dict]:
    out = [c for c in KG.load_cases() if not case_id or c["id"] == case_id]
    if not out:
        print(f"未找到命盘 {case_id}")
        raise SystemExit(2)
    return out


def report_distribution(cases: list[dict], dimensions: tuple[str, ...]) -> list[str]:
    print("=== 分数分布 ===")
    print("%-14s %8s %7s %7s %7s %8s %9s %8s" % (
        "dimension", "n", "p5", "p50", "p95", "跨度", "边界0/100", "实体/振幅"))
    problems: list[str] = []
    for dim in dimensions:
        closes: list[float] = []
        bodies = ranges = 0.0
        flat: list[str] = []
        for case in cases:
            candles = KG.cached_kline_dim(case["id"], dim)
            if not candles:
                continue
            closes.extend(c["close"] for c in candles)
            bodies += sum(abs(c["close"] - c["open"]) for c in candles)
            ranges += sum(c["high"] - c["low"] for c in candles)
            if len({c["close"] for c in candles}) <= 5:
                flat.append(case["id"])
        if not closes:
            continue
        hit = sum(1 for v in closes if v <= 0 or v >= 100)
        span = _percentile(closes, 99) - _percentile(closes, 1)
        label = FS.DIMENSION_LABELS[dim]
        print("%-14s %8d %7.1f %7.1f %7.1f %8.1f %9d %8.3f" % (
            label, len(closes), _percentile(closes, 5), _percentile(closes, 50),
            _percentile(closes, 95), span, hit, bodies / ranges))
        if hit:
            problems.append(f"「{label}」维度有 {hit} 个样本触及 0/100 硬边界")
        if span < MIN_SPREAD:
            problems.append(f"「{label}」维度分位跨度 {span:.1f} < {MIN_SPREAD}（分数塌缩）")
        if flat:
            problems.append(f"「{label}」维度收盘分退化成平线：{flat}")
    return problems


def report_direction(cases: list[dict], dimensions: tuple[str, ...], verbose: bool) -> list[str]:
    print("\n=== 蜡烛方向 ===")
    problems: list[str] = []
    for dim in dimensions:
        label = FS.DIMENSION_LABELS[dim]
        tot_up = tot_n = 0
        degenerate: list[str] = []
        if verbose:
            print("\n[%s] %-24s %6s %5s %7s" % (label, "case", "candles", "阳线", "阳线%"))
        for case in cases:
            candles = KG.cached_kline_dim(case["id"], dim)
            if not candles:
                continue
            ups = sum(1 for c in candles if c["isUp"])
            tot_up += ups
            tot_n += len(candles)
            if verbose:
                print("[%s] %-24s %6d %5d %6.1f%%" % (
                    label, case["id"], len(candles), ups, 100 * ups / len(candles)))
            if ups in (0, len(candles)):
                degenerate.append(f"{case['id']}({ups}/{len(candles)})")
        if tot_n:
            print("%-14s %d 根，阳线 %d（%.1f%%）" % (label, tot_n, tot_up, 100 * tot_up / tot_n))
        if degenerate:
            problems.append(f"「{label}」维度方向恒定、实体无信息量：{'、'.join(degenerate)}")
    return problems


def report_dimension_spread(cases: list[dict]) -> list[str]:
    """维度之间的区分度：与综合的差异、以及维度两两之间的重合。"""
    if len(FS.DIMENSIONS) < 2:
        return []
    print("\n=== 维度区分度 ===")
    problems: list[str] = []
    base_diff: dict[str, float] = {}
    series: dict[str, list[list[float]]] = {}
    for dim in FS.DIMENSIONS:
        rows = []
        for case in cases:
            candles = KG.cached_kline_dim(case["id"], dim)
            if candles:
                rows.append([c["close"] for c in candles])
        series[dim] = rows

    base = series[FS.DIM_COMPREHENSIVE]
    for dim in FS.DIMENSIONS:
        if dim == FS.DIM_COMPREHENSIVE or not base:
            continue
        pairs = zip(base, series[dim])
        tot = diff = 0
        for a, b in pairs:
            diff += sum(1 for x, y in zip(a, b) if x != y)
            tot += len(a)
        ratio = diff / tot if tot else 0.0
        base_diff[dim] = ratio
        print("%-14s 与综合维度 %5.1f%% 年份不同" % (FS.DIMENSION_LABELS[dim], 100 * ratio))
        if ratio < MIN_DIM_DIFF:
            problems.append(f"「{FS.DIMENSION_LABELS[dim]}」与综合维度差异仅 {ratio:.0%}")

    dims = list(FS.DIMENSIONS)
    for i, a in enumerate(dims):
        for b in dims[i + 1 :]:
            if not series[a] or not series[b]:
                continue
            tot = same = 0
            for x, y in zip(series[a], series[b]):
                same += sum(1 for p, q in zip(x, y) if p == q)
                tot += len(x)
            overlap = same / tot if tot else 0.0
            if overlap > MAX_DIM_OVERLAP:
                problems.append(
                    f"「{FS.DIMENSION_LABELS[a]}」与「{FS.DIMENSION_LABELS[b]}」"
                    f"重合 {overlap:.0%}，区分度不足"
                )
    return problems


def report_contiguity(cases: list[dict]) -> list[str]:
    """衔接性与维度无关（open 永远接上年 close），只在综合维度上查一次。"""
    broken: list[str] = []
    for case in cases:
        candles = KG.cached_kline_dim(case["id"], FS.DIM_COMPREHENSIVE)
        for prev, cur in zip(candles, candles[1:]):
            if cur["open"] != prev["close"]:
                broken.append(f"{case['id']} {prev['year']}→{cur['year']}")
    print("\n=== 蜡烛衔接 ===")
    print("  断裂处：%d" % len(broken))
    if broken:
        print("  " + "、".join(broken[:10]))
        return ["相邻蜡烛未首尾相接（实体失去同比语义）"]
    return []


def main(argv: list[str] | None = None) -> int:
    """`argv` 可注入（供测试与其它脚本调用），默认取 `sys.argv` —— 与 `kline_backtest.py` 同口径。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("all", "dist", "direction", "dimensions", "contiguity"), default="all")
    ap.add_argument("--case", default=None, help="只体检指定命盘 id")
    ap.add_argument(
        "--dimension",
        default="all",
        help="维度：all（默认）或 " + "/".join(FS.DIMENSIONS),
    )
    ap.add_argument("-v", "--verbose", action="store_true", help="逐命例列出方向分布")
    args = ap.parse_args(argv)

    if args.dimension == "all":
        dimensions = FS.DIMENSIONS
    elif args.dimension in FS.DIMENSIONS:
        dimensions = (args.dimension,)
    else:
        print(f"--dimension 需为 all 或 {'/'.join(FS.DIMENSIONS)}")
        return 2

    cases = _cases(args.case)
    print(f"体检 {len(cases)} 个黄金命盘 × {len(dimensions)} 个维度"
          f"（K_SCORE={FS.K_SCORE}，max_age={MAX_AGE}）\n")

    problems: list[str] = []
    if args.mode in ("all", "dist"):
        problems += report_distribution(cases, dimensions)
    if args.mode in ("all", "direction"):
        problems += report_direction(cases, dimensions, args.verbose)
    if args.mode in ("all", "dimensions"):
        problems += report_dimension_spread(cases)
    if args.mode in ("all", "contiguity"):
        problems += report_contiguity(cases)

    if problems:
        print("\n!! 体检未通过：")
        for p in problems:
            print("   - " + p)
        return 1
    print("\n体检通过：不饱和、不塌缩、方向非退化、维度有区分度、蜡烛衔接。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
