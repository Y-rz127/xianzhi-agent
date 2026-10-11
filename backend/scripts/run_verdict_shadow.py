"""LLM 命盘裁决影子批跑：黄金 38 盘 + 3 报障锚点，落库 chart_verdicts 并打印差异报告。

影子纪律：结果只进 chart_verdicts 表，不参与任何线上判定。

用法：
    ../.venv/Scripts/python.exe scripts/run_verdict_shadow.py            # 全量
    ../.venv/Scripts/python.exe scripts/run_verdict_shadow.py --limit 5  # 冒烟
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

ANCHORS = [
    ("anchor_congsha", "1898-09-19 18:00", "男"),   # 从杀目标盘 戊戌辛酉乙酉乙酉
    ("anchor_yinzhong", "2004-06-22 08:00", "男"),  # 甲申庚午壬申甲辰
    ("anchor_shazhong", "2005-09-28 18:00", "男"),  # 乙酉乙酉乙卯乙酉
]


async def main(limit: int) -> int:
    from langchain_openai import ChatOpenAI

    from app.agent.verdict import run_shadow_verdict
    from app.core.config import settings
    from tests import bazi_golden as G

    model = ChatOpenAI(
        model=settings.dashscope_model,
        base_url=settings.dashscope_url,
        api_key=settings.dashscope_api_key,
        timeout=180,
        max_retries=1,
        # 裁决是结构化判断不是深度推理，关思考模式：qwen 思考模型默认开
        # enable_thinking 会导致单次 4 分钟+，批量跑不动（实测 2/3 超时）
        extra_body={"enable_thinking": False},
    )

    jobs = []
    for case in G.load_cases():
        jobs.append((case["id"], case["birth"], case["gender"]))
    jobs.extend(ANCHORS)
    if limit > 0:
        jobs = jobs[:limit]

    print(f"影子批跑 {len(jobs)} 张盘，模型 {settings.dashscope_model}\n")
    ok = invalid = same = diff_cnt = 0
    diff_lines = []
    for i, (cid, birth, gender) in enumerate(jobs, 1):
        from app.domain.chart_builder import build_bazi_chart

        chart = build_bazi_chart(birth, gender)
        row = await run_shadow_verdict(chart, model)
        if row["status"] == "ok":
            ok += 1
            if row["diff"]:
                diff_cnt += 1
                diff_lines.append(f"{cid}: {row['diff']}")
                print(f"  [{i}/{len(jobs)}] {cid}: 差异 → {row['diff']}")
            else:
                same += 1
                print(f"  [{i}/{len(jobs)}] {cid}: 一致")
        else:
            invalid += 1
            print(f"  [{i}/{len(jobs)}] {cid}: ✗ invalid（{row['raw_text'][:80]}）")

    print(f"\n=== 影子报告 ===")
    print(f"成功 {ok}（一致 {same} / 差异 {diff_cnt}）、invalid {invalid}")
    if diff_lines:
        print("\n全部差异：")
        for line in diff_lines:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 张（冒烟）")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.limit)))
