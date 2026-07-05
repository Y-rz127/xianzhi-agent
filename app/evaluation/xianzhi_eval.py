"""Offline checks for Xianzhi answer quality.

The checks are intentionally deterministic: they validate factual anchors,
forbidden hallucinations and conversational shape without calling a model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.xianzhi_workflow import XianzhiWorkflow, build_chart_context


REPORT_MARKERS = ("【基本信息】", "【四柱】", "【五行", "完整报告", "第一章", "第二章")


@dataclass(frozen=True)
class EvalResult:
    case_id: str
    ok: bool
    issues: list[str]


def evaluate_answer_case(case: dict[str, Any], answer: str) -> EvalResult:
    issues: list[str] = []
    required_terms = case.get("required_terms", [])
    forbidden_terms = case.get("forbidden_terms", [])
    max_chars = int(case.get("max_chars", 900))
    min_chars = int(case.get("min_chars", 40))

    for term in required_terms:
        if term not in answer:
            issues.append(f"missing required term: {term}")
    for term in forbidden_terms:
        if term in answer:
            issues.append(f"contains forbidden term: {term}")

    if len(answer) < min_chars:
        issues.append(f"answer too short: {len(answer)} < {min_chars}")
    if len(answer) > max_chars:
        issues.append(f"answer too long: {len(answer)} > {max_chars}")

    if not case.get("allow_report_style", False) and any(marker in answer for marker in REPORT_MARKERS):
        issues.append("answer looks like a report dump")

    chart = build_chart_context(
        case["birth_time"],
        case["gender"],
        case.get("sect", 2),
        case.get("yun_sect", 1),
    )
    workflow = XianzhiWorkflow(chat_model=None)
    fact_check = workflow.check_facts(answer, chart.chart)
    issues.extend(fact_check.issues)

    return EvalResult(case_id=case["id"], ok=not issues, issues=issues)


def evaluate_answer_cases(cases: list[dict[str, Any]], answers: dict[str, str]) -> list[EvalResult]:
    return [evaluate_answer_case(case, answers.get(case["id"], "")) for case in cases]

