import json
from pathlib import Path

from app.evaluation.xianzhi_eval import evaluate_answer_case


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "xianzhi_answer_eval.json"


def _cases():
    return {case["id"]: case for case in json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]}


def test_evaluate_answer_accepts_consultation_style_answer():
    case = _cases()["career_change_2026"]
    answer = (
        "2026年可以看机会，但不建议裸辞。你这步在乙酉大运里，2026年流年是丙午，"
        "工作上容易被项目、职位变化或外部机会推动。我的建议是先谈清楚岗位边界和直属领导，"
        "再决定是否换工作；如果只是情绪上想走，反而容易冲动。"
    )

    result = evaluate_answer_case(case, answer)

    assert result.ok, result.issues


def test_evaluate_answer_rejects_wrong_facts_and_report_dump():
    case = _cases()["career_change_2026"]
    answer = (
        "【四柱】这是完整报告。2026年是乙巳年，你一定适合换工作，必然升职。"
    )

    result = evaluate_answer_case(case, answer)

    assert not result.ok
    assert any("2026年流年应为丙午" in issue for issue in result.issues)
    assert any("report dump" in issue for issue in result.issues)
    assert any("forbidden" in issue for issue in result.issues)
