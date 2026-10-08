"""黄金命盘快照的操作入口：重生成 / 查看差异 / 导出被指纹化的段。

用法：
    # 只看差异，不写盘
    ../.venv/Scripts/python.exe scripts/golden_bazi.py --diff

    # 重生成全部快照（等价 UPDATE_GOLDEN=1 跑测试）
    ../.venv/Scripts/python.exe scripts/golden_bazi.py --update

    # 列出用例与覆盖情况
    ../.venv/Scripts/python.exe scripts/golden_bazi.py --list

    # 查看某用例的字段；被指纹化的段会输出真实内容（未投影）
    ../.venv/Scripts/python.exe scripts/golden_bazi.py --show zhuanwang_quzhi xipan.liuyue
    ../.venv/Scripts/python.exe scripts/golden_bazi.py --show stem_jia chart.wuxing

    # 导出被指纹化段的真实内容到文件（便于与改动前对比）
    ../.venv/Scripts/python.exe scripts/golden_bazi.py --dump xipan.liuyue /tmp/liuyue.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from tests import bazi_golden as G  # noqa: E402


def cmd_list() -> None:
    cases = G.load_cases()
    print(f"{len(cases)} 个用例，基准日 {G.REFERENCE_DATE}，流年起 {G.LIUNIAN_START_YEAR}\n")
    print(f"{'id':<26} {'出生':<18} {'性别':<4} {'日主':<4} {'强弱':<6} {'格局':<8} 说明")
    for case in cases:
        snap = G.build_case_snapshot(case)
        w = snap["chart"]["wuxing"]
        exists = "✓" if G.snapshot_path(case["id"]).exists() else "·"
        print(
            f"{exists} {case['id']:<24} {case['birth']:<18} {case['gender']:<4} "
            f"{w['day_master']:<4} {w['strength']:<6} {w['special_pattern'] or '-':<8} {case['desc']}"
        )


def cmd_diff() -> int:
    total = 0
    for case in G.load_cases():
        if not G.snapshot_path(case["id"]).exists():
            print(f"[缺失] {case['id']} 无快照文件")
            total += 1
            continue
        diffs = G.diff_paths(G.read_snapshot(case["id"]), G.build_case_snapshot(case))
        if diffs:
            total += len(diffs)
            print(f"\n[{case['id']}] {len(diffs)} 处差异：")
            for d in diffs[:30]:
                print(f"  - {d}")
            if len(diffs) > 30:
                print(f"  …另有 {len(diffs) - 30} 处")
    print(f"\n合计 {total} 处差异" if total else "\n全部一致")
    return 1 if total else 0


def cmd_update() -> None:
    for case in G.load_cases():
        path = G.write_snapshot(G.build_case_snapshot(case))
        print(f"已写入 {path}")
    print("\n注意：请用 git diff 人工核对每处变化，确认都是预期行为。")


def cmd_show(case_id: str, dotted: str) -> None:
    case = _find_case(case_id)
    if dotted.startswith("xipan.") and dotted.split(".")[1] in G.DIGEST_ONLY_XIPAN_KEYS:
        key = dotted.split(".")[1]
        print(f"# {case_id} 的 xipan.{key} 未投影真实内容（快照中只存指纹）")
        _print_json(G.raw_xipan_section(case, key))
        return
    snap = G.read_snapshot(case_id)
    _print_json(G.get_by_path(snap, dotted))


def cmd_dump(section: str, out_path: str) -> None:
    """导出所有用例在某个 xipan 段的真实内容（按用例 id 聚合）。"""
    key = section.split(".")[-1]
    payload = {
        c["id"]: G.raw_xipan_section(c, key)
        for c in G.load_cases()
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"已导出 {len(payload)} 个用例的 xipan.{key} → {out_path}")


def _find_case(case_id: str) -> dict:
    for case in G.load_cases():
        if case["id"] == case_id:
            return case
    raise SystemExit(f"未找到用例 {case_id}，用 --list 查看可用 id")


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="列出用例与覆盖情况")
    ap.add_argument("--diff", action="store_true", help="只比对差异，不写盘")
    ap.add_argument("--update", action="store_true", help="重生成全部快照")
    ap.add_argument("--show", nargs=2, metavar=("CASE_ID", "PATH"), help="查看某用例字段")
    ap.add_argument("--dump", nargs=2, metavar=("SECTION", "OUT_PATH"), help="导出指纹化段全文")
    args = ap.parse_args()

    if args.list:
        cmd_list()
    elif args.diff:
        raise SystemExit(cmd_diff())
    elif args.update:
        cmd_update()
    elif args.show:
        cmd_show(*args.show)
    elif args.dump:
        cmd_dump(*args.dump)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
