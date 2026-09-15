"""`check_facts` 审核黄金样本：构建 / 比对 / 更新。

为什么需要它：`check_facts`（451 行）是阶段 3 要拆的下一个巨型函数，
主要风险不是崩，而是**误判**——把合法表述判成违规（误杀）或把编造判成合法（漏检）。
两者都不会抛异常，只会让审核质量静默劣化。

它是**纯函数**（无 LLM、无 IO），输入 `(answer, chart, other_chart, needs_chart)`、
输出 `(ok, issues)`，因此可以整条固化：任何口径变化都会在 `issues` 文本上留下逐字差异。

样本里的 3 条 `intent="regression"` 是历史事故的回归锚点（见 cases.json 的 desc）：
单字否定词误判、大运词导致跳过流年校验、编造大运撞上流年干支被放行。

用法：
    ../.venv/Scripts/python.exe scripts/fact_check_golden.py --list     # 看样本与当前判定
    ../.venv/Scripts/python.exe scripts/fact_check_golden.py --diff     # 只比对，不写盘
    ../.venv/Scripts/python.exe scripts/fact_check_golden.py --update   # 重生成（须先人工核对 diff）
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

from app.agent.workflow.fact_check import check_facts
from app.domain.chart_builder import build_bazi_chart
from tests import bazi_golden

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
CASES_FILE = FIXTURE_DIR / "fact_check_cases.json"
SNAPSHOT_FILE = FIXTURE_DIR / "fact_check_snapshots.json"

# 参考时间与流年起点必须钉死，否则命盘随系统日期漂移（与 bazi_golden 保持一致）
REFERENCE_DATE = bazi_golden.REFERENCE_DATE
LIUNIAN_START_YEAR = bazi_golden.LIUNIAN_START_YEAR


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))["cases"]


def _build_chart(spec: dict[str, Any]):
    return build_bazi_chart(
        spec["birth"],
        spec["gender"],
        liunian_start_year=LIUNIAN_START_YEAR,
        today=datetime.date.fromisoformat(REFERENCE_DATE),
    )


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """跑一条样本，返回可序列化结果。"""
    chart = bazi_golden.build_case_chart(bazi_golden.find_case(case["chart_case"]))
    other = _build_chart(case["other_chart"]) if case.get("other_chart") else None
    result = check_facts(
        case["answer"],
        chart,
        other_chart=other,
        needs_chart=case.get("needs_chart", True),
    )
    return {"ok": result.ok, "issues": result.issues}


def run_all() -> dict[str, dict[str, Any]]:
    return {case["id"]: run_case(case) for case in load_cases()}


# ---------------- 快照读写 ----------------


def read_snapshot() -> dict[str, Any]:
    if not SNAPSHOT_FILE.exists():
        return {}
    return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))


def write_snapshot(data: dict[str, Any]) -> bool:
    """写入快照；内容无变化则不落盘（保留 diff 信号，见 bazi_golden.write_snapshot）。"""
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if SNAPSHOT_FILE.exists() and SNAPSHOT_FILE.read_text(encoding="utf-8") == payload:
        return False
    SNAPSHOT_FILE.write_text(payload, encoding="utf-8")
    return True


def update_enabled() -> bool:
    return os.environ.get("UPDATE_FACT_CHECK", "").strip() not in ("", "0", "false", "False")


def diff_paths(expected: Any, actual: Any, path: str = "") -> list[str]:
    """复用命盘快照的递归比对（含列表按标识键定位）。"""
    return bazi_golden.diff_paths(expected, actual, path)
