"""基于先知图的咨询流程是确定性的。
对先知答案质量进行离线检查。
这些检查是故意设计为确定性的：它们验证事实性锚点、禁止的幻觉内容以及对话结构，而无需调用模型。
用法大概是准备一批测试用例（JSON），跑一轮得到 EvalResult 列表，看哪些用例没过。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.xianzhi_workflow import XianzhiWorkflow, build_chart_context


REPORT_MARKERS = ("【基本信息】", "【四柱】", "【五行】", "完整报告", "第一章", "第二章")


@dataclass(frozen=True)
class EvalResult:
    """单条评估结果的容器：命例 id、是否通过、问题列表。"""
    case_id: str
    ok: bool
    issues: list[str]


def evaluate_answer_case(case: dict[str, Any], answer: str) -> EvalResult:
    """对单条答案做确定性离线评估：必含/禁含词、长度区间、报告体检测 + 事实校验。
    1. 必含词检查    → 答案里有没有该出现的术语
    2. 禁含词检查    → 答案里有没有不该出现的东西
    3. 长度检查      → 40~900 字
    4. 报告体检测    → 有没有把完整报告原文 dump 出来
    5. 事实校验      → 调用 workflow.check_facts() 检查命盘事实是否说错
    """
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
    """批量评估（一对一映射 case→answer），返回 EvalResult 列表。"""
    return [evaluate_answer_case(case, answers.get(case["id"], "")) for case in cases]

