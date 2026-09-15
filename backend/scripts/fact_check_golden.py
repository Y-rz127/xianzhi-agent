"""审核黄金样本的操作入口：列出当前判定 / 比对差异 / 重生成快照。

用法：
    ../.venv/Scripts/python.exe scripts/fact_check_golden.py --list
    ../.venv/Scripts/python.exe scripts/fact_check_golden.py --diff
    ../.venv/Scripts/python.exe scripts/fact_check_golden.py --update
    ../.venv/Scripts/python.exe scripts/fact_check_golden.py --show bad_liunian   # 单条详情
"""

from __future__ import annotations

import argparse
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from tests import fact_check_golden as F  # noqa: E402


def cmd_list(only_intent: str = "") -> None:
    cases = F.load_cases()
    snapshot = F.read_snapshot()
    print(f"{len(cases)} 条样本（基准日 {F.REFERENCE_DATE}，流年起 {F.LIUNIAN_START_YEAR}）\n")
    for case in cases:
        if only_intent and case["intent"] != only_intent:
            continue
        snap = snapshot.get(case["id"])
        mark = {"ok": "应放行", "violation": "应拦截", "regression": "回归"}[case["intent"]]
        flag = "✓" if snap and snap["ok"] else "✗"
        print(f"{flag} [{mark}] {case['id']:<28} {case['answer'][:38]}")
        if snap and snap["issues"]:
            for issue in snap["issues"]:
                print(f"      → {issue}")


def cmd_diff() -> int:
    snapshot = F.read_snapshot()
    total = 0
    for case in F.load_cases():
        if case["id"] not in snapshot:
            print(f"[缺失] {case['id']} 无快照")
            total += 1
            continue
        diffs = F.diff_paths(snapshot[case["id"]], F.run_case(case))
        if diffs:
            total += len(diffs)
            print(f"\n[{case['id']}] {case['desc']}")
            print(f"     回答：{case['answer']}")
            for d in diffs:
                print(f"  - {d}")
    print(f"\n合计 {total} 处差异" if total else "\n全部一致")
    return 1 if total else 0


def cmd_update() -> None:
    if F.write_snapshot(F.run_all()):
        print(f"已重写 {F.SNAPSHOT_FILE}")
        print("注意：请用 git diff 人工核对每处变化，确认都是预期的口径调整。")
    else:
        print("内容无变化，未写盘。")


def cmd_show(case_id: str) -> None:
    case = next((c for c in F.load_cases() if c["id"] == case_id), None)
    if case is None:
        raise SystemExit(f"未找到样本 {case_id}")
    print(f"id       : {case['id']}")
    print(f"desc     : {case['desc']}")
    print(f"命盘用例 : {case['chart_case']}" + (
        f"  对方盘 {case['other_chart']}" if case.get("other_chart") else ""
    ))
    print(f"needs_chart: {case.get('needs_chart', True)}")
    print(f"回答     : {case['answer']}")
    snap = F.read_snapshot().get(case_id)
    print(f"期望     : {snap}")
    print(f"实际     : {F.run_case(case)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="", choices=("", "ok", "violation", "regression"))
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--show", metavar="CASE_ID")
    args = ap.parse_args()

    if args.list or args.only:
        cmd_list(args.only)
    elif args.diff:
        raise SystemExit(cmd_diff())
    elif args.update:
        cmd_update()
    elif args.show:
        cmd_show(args.show)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
