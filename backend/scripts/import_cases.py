"""命例库批量导入：名人命例 + 经典格局命例（scripts/cases_seed.json）。

每条命例先做对比验证再入库，验证不过的跳过并列入报告：
  1. 资料只有四柱 → find_birth_dates_from_pillars 反推公历（取 hint_year/solar 附近候选）；
  2. 用排盘引擎按 birth_time 重排，引擎四柱必须与资料四柱 pillars 完全一致。

用法：
    ../.venv/Scripts/python.exe scripts/import_cases.py --check     # 只验证不入库
    ../.venv/Scripts/python.exe scripts/import_cases.py             # 验证 + 导入（按 name 幂等）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

SEED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases_seed.json")


def _split_pillars(s: str) -> list[str]:
    s = s.strip()
    return [s[i * 2: i * 2 + 2] for i in range(4)]


def resolve_birth_time(case: dict) -> tuple[str, str, list[str]]:
    """反推公历出生时间并经引擎复核，返回 (birth_time, 来源说明, 引擎四柱)。

    等价日期只在 1583 年之后取：lunar 库遇到 1582-10 历改空档会抛错，
    且改历前后 Julian/Gregorian 换算漂移会让快速日柱公式与引擎不一致。
    """
    from app.domain.chart_builder import build_bazi_chart
    from app.domain.chart_format import find_birth_dates_from_pillars

    pillars = case["pillars"]
    expected = _split_pillars(pillars)
    today_year = 2026
    target_year = None
    if case.get("solar"):
        target_year = int(case["solar"][:4])
    elif case.get("hint_year"):
        target_year = int(case["hint_year"])
    # 四柱完整组合重现周期受闰年漂移影响，短窗口可能一次不命中，加宽后仍须留在 1583 年后
    max_back = min(max((today_year - target_year + 5) if target_year else 120, 500), today_year - 1583)

    candidates = find_birth_dates_from_pillars(
        pillars, case["gender"], max_years_back=max_back, top_n=50
    )
    # 快速日柱公式与 lunar 引擎在历法边界可能不一致，一律以引擎重排为准复核
    verified = []
    for c in candidates:
        chart = build_bazi_chart(c["birth_time"], case["gender"], dayun_count=8, liunian_years=5)
        if [p.ganzhi for p in chart.pillars] == expected:
            verified.append(c)
    if not verified:
        raise ValueError("四柱反推无候选日期" if not candidates else "反推候选均未通过引擎四柱复核")

    if case.get("solar"):
        want = case["solar"]
        matched = [c for c in verified if c["birth_time"].startswith(want)]
        if not matched:
            raise ValueError(f"公历 {want} 与四柱不符（反推候选：{[c['birth_time'] for c in verified[:3]]}）")
        return matched[0]["birth_time"], f"公历 {want}（与四柱互证）", expected

    target = target_year or 2026
    best = min(verified, key=lambda c: abs(int(c["birth_time"][:4]) - target))
    note = f"四柱反推（取 {target} 年附近）" if target_year else "四柱反推（取最近）"
    return best["birth_time"], note, expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只验证不入库")
    args = parser.parse_args()

    cases = json.loads(open(SEED_FILE, encoding="utf-8").read())["cases"]
    print(f"载入种子命例 {len(cases)} 条\n")

    verified: list[tuple[dict, str, str]] = []
    failed: list[tuple[dict, str]] = []
    for case in cases:
        try:
            birth_time, source, actual = resolve_birth_time(case)
        except Exception as e:
            failed.append((case, str(e)))
            print(f"  ✗ {case['name']}: {e}")
            continue
        verified.append((case, birth_time, source))
        print(f"  ✓ {case['name']}  {birth_time}  {' '.join(actual)}  [{source}]")

    print(f"\n验证通过 {len(verified)} 条，未通过 {len(failed)} 条")
    if args.check:
        return 0 if not failed else 1

    if not verified:
        print("无可导入命例")
        return 1

    from app.api.cases import _build_chart_data, ensure_table
    from app.db.pool import get_pool

    if not ensure_table():
        print("cases 表不可用（PostgreSQL 未连接）")
        return 1

    with get_pool().connection() as conn:
        existing = {r[0] for r in conn.execute("SELECT name FROM cases").fetchall()}
        inserted = 0
        for case, birth_time, _source in verified:
            if case["name"] in existing:
                print(f"  = {case['name']} 已存在，跳过")
                continue
            chart_data = _build_chart_data(birth_time, case["gender"])
            conn.execute(
                "INSERT INTO cases (id, name, tags, birth_time, gender, chart_data, bio, analysis, keypoints, domains) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    str(uuid.uuid4()), case["name"], case["tags"], birth_time, case["gender"],
                    json.dumps(chart_data, ensure_ascii=False),
                    case["bio"], case["analysis"], case["keypoints"], case["domains"],
                ),
            )
            inserted += 1
        print(f"\n导入完成：新增 {inserted} 条，跳过 {len(verified) - inserted} 条（已存在）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
