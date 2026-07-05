import datetime as dt

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agent.xianzhi import Xianzhi
from app.agent.xianzhi_workflow import XianzhiWorkflow, build_chart_context, classify_question


MALE = "\u7537"


def test_classify_question_extracts_domain_and_relative_years():
    intent = classify_question("今年适合换工作吗？", today=dt.date(2026, 7, 5))

    assert intent.domain == "career"
    assert intent.target_years == [2026]
    assert intent.wants_report is False


def test_workflow_extends_liunian_for_target_year():
    workflow = XianzhiWorkflow(chat_model=None)
    ctx = build_chart_context("1990-05-20 14:30", MALE)
    intent = classify_question("2036年财运怎么样？", today=dt.date(2026, 7, 5))

    extended = workflow._extend_chart_if_needed(ctx, intent)

    assert any(item.year == 2036 for item in extended.chart.liunian)
    assert any(item.dayun_ganzhi for item in extended.chart.liunian if item.year == 2036)


def test_fact_checker_catches_wrong_liunian_and_pillar():
    workflow = XianzhiWorkflow(chat_model=None)
    ctx = build_chart_context("1990-05-20 14:30", MALE)

    result = workflow.check_facts("2026年是乙巳年，年柱是辛未。", ctx.chart)

    assert not result.ok
    assert any("2026年流年应为丙午" in issue for issue in result.issues)
    assert any("年柱应为庚午" in issue for issue in result.issues)


def test_fact_checker_allows_correct_facts():
    workflow = XianzhiWorkflow(chat_model=None)
    ctx = build_chart_context("1990-05-20 14:30", MALE)

    result = workflow.check_facts("2026年是丙午年，年柱是庚午。", ctx.chart)

    assert result.ok


def test_xianzhi_prefers_workflow_when_chart_context_exists():
    model = FakeListChatModel(responses=["2026年可以看机会，但不建议裸辞。2026年是丙午年，年柱是庚午。"])
    agent = Xianzhi(chat_model=model, local_tools=[])
    agent.set_conversation_id("test-workflow")
    agent.set_chart_context("1990-05-20 14:30", MALE)

    result = agent.run("今年适合换工作吗？")

    assert "不建议裸辞" in result
    assert "丙午" in result
