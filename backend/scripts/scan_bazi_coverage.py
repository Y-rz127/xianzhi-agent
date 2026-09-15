"""扫描命盘样本空间：覆盖面统计 + 稀有特殊格局定位。

用途：挑选/复核黄金命盘快照（`tests/fixtures/bazi_golden_cases.json`）的代表样本。
新增格局或改动强弱判定后，重跑可看出哪些桶失去覆盖。

实现要点：覆盖矩阵与特殊格局只取决于四柱五行权重，因此走
`Solar → EightChar → _build_wuxing_analysis` 轻量路径（约 1ms/例），
不构建大运/流年/细盘（约 72ms/例，慢 70 倍）。需要完整命盘时请另用 `build_bazi_chart`。

用法：
    # 覆盖矩阵（10 日干 / 强弱五档 / 特殊格局）
    ../.venv/Scripts/python.exe scripts/scan_bazi_coverage.py --days 400

    # 定位专旺/从格等稀有格局（扫描量大，建议加 --hours 或缩窄 --days）
    ../.venv/Scripts/python.exe scripts/scan_bazi_coverage.py --mode special \\
        --start 1900-01-01 --days 40000 --hours 0,4,8,12,16,20
"""

from __future__ import annotations

import argparse
import collections
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lunar_python import Solar  # noqa: E402

from app.domain.analysis_calc import _build_wuxing_analysis  # noqa: E402

DEFAULT_HOURS = (0, 6, 12, 18, 23)
STEMS = ("甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸")


def _wuxing(birth: datetime.datetime):
    ec = Solar.fromYmdHms(birth.year, birth.month, birth.day, birth.hour, 0, 0).getLunar().getEightChar()
    return _build_wuxing_analysis(ec)


def _iter_births(start: datetime.date, days: int, hours: tuple[int, ...]):
    for offset in range(days):
        d = start + datetime.timedelta(days=offset)
        for h in hours:
            yield f"{d.isoformat()} {h:02d}:00"


def scan_matrix(start: datetime.date, days: int, hours: tuple[int, ...]) -> dict:
    by_stem: dict[str, list[str]] = collections.defaultdict(list)
    by_strength: dict[str, list[str]] = collections.defaultdict(list)
    by_special: dict[str, list[str]] = collections.defaultdict(list)
    by_wx_pattern: dict[str, list[str]] = collections.defaultdict(list)

    for birth in _iter_births(start, days, hours):
        w = _wuxing(datetime.datetime.fromisoformat(birth))
        by_stem[w.day_master].append(birth)
        by_strength[w.strength].append(birth)
        if w.special_pattern:
            by_special[w.special_pattern].append(birth)
            # 专旺/从格的具体格名（润下/从财/…）取自 useful_hint 首句
            by_wx_pattern[w.useful_hint.split("（")[0]].append(birth)

    return {
        "by_stem": by_stem,
        "by_strength": by_strength,
        "by_special": by_special,
        "by_wx_pattern": by_wx_pattern,
    }


def find_special(start: datetime.date, days: int, hours: tuple[int, ...], limit_per_kind: int) -> dict:
    hits: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    scanned = 0
    for birth in _iter_births(start, days, hours):
        scanned += 1
        w = _wuxing(datetime.datetime.fromisoformat(birth))
        if not w.special_pattern:
            continue
        label = w.useful_hint.split("（")[0]
        if len(hits[label]) < limit_per_kind:
            hits[label].append((birth, f"score={w.strength_score} strength={w.strength}"))
    print(f"共扫描 {scanned} 例")
    return hits


def _report(title: str, table: dict[str, list[str]], expected: tuple[str, ...] = ()) -> None:
    print(f"\n=== {title} （{len(table)} 类）===")
    for key in sorted(table, key=lambda k: (-len(table[k]), k)):
        print(f"  {key or '(空)':<12} {len(table[key]):>6}  例：{table[key][0]}")
    missing = [k for k in expected if k not in table]
    if missing:
        print(f"  !! 未覆盖：{missing}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("matrix", "special"), default="matrix")
    ap.add_argument("--start", default="1985-01-01", help="起始日期 YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--hours", default=",".join(str(h) for h in DEFAULT_HOURS))
    ap.add_argument("--limit-per-kind", type=int, default=3)
    args = ap.parse_args()

    start = datetime.date.fromisoformat(args.start)
    hours = tuple(int(h) for h in args.hours.split(","))
    print(f"{start} 起 {args.days} 天 × {len(hours)} 时辰 = {args.days * len(hours)} 样本")

    if args.mode == "special":
        hits = find_special(start, args.days, hours, args.limit_per_kind)
        if not hits:
            print("未命中任何特殊格局，扩大 --days 或 --hours")
            return
        for label in sorted(hits):
            print(f"\n=== {label} ===")
            for birth, note in hits[label]:
                print(f"  {birth}   {note}")
        return

    res = scan_matrix(start, args.days, hours)
    _report("日干覆盖", res["by_stem"], expected=STEMS)
    _report("强弱五档", res["by_strength"])
    _report("特殊格局", res["by_special"], expected=("专旺", "从格"))
    _report("格局细名", res["by_wx_pattern"])


if __name__ == "__main__":
    main()
