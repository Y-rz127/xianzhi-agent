import datetime as dt

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agent.workflow.workflow_messages import fact_block
from app.agent.workflow.workflow_retrieval import build_theory_queries
from app.agent.workflow.xianzhi_workflow import (
    XianzhiWorkflow,
    build_chart_context,
    classify_question,
    detect_theory_topic,
)
from app.agent.xianzhi import Xianzhi

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


def test_detect_theory_topic_basic_concept():
    """理论术语识别：单概念 → 单条精准 query"""
    topic, query = detect_theory_topic("请问用神是什么意思")
    assert topic == "用神"
    assert "用神" in query
    assert "调候" in query


def test_detect_theory_topic_prefers_longer_keyword():
    """长关键词优先于短关键词（如"长生十二宫" 优先于 "长生"）"""
    topic, _ = detect_theory_topic("长生十二宫是怎么排的")
    assert topic == "长生十二宫"


def test_detect_theory_topic_returns_none_for_unrelated():
    """无关问题 → None，走 fallback"""
    assert detect_theory_topic("你好") is None
    assert detect_theory_topic("今天适合跳槽吗") is None


def test_build_theory_queries_uses_focused_queries():
    """理论问题：识别到术语时以用户原句为首条、术语精准 query 其次，
    不叠加个性化/命例/古籍/断法"""
    _workflow = XianzhiWorkflow(chat_model=None)
    queries, meta = build_theory_queries("用神是什么")
    assert len(queries) == 2
    assert meta.startswith("topic=")
    assert queries[0] == "用神是什么"           # 用户原句置首
    assert "用神" in queries[1]                  # 术语精准 query
    # 验证不含无关的"空亡 桃花 神煞 禄神"等内容
    assert "空亡" not in queries[0] and "空亡" not in queries[1]
    assert "桃花" not in queries[0] and "桃花" not in queries[1]


def test_build_theory_queries_fallback_when_no_topic():
    """未识别到具体术语时走 fallback：仅保留用户原句，不追加泛化 query。

    口径变更（降噪）：泛化兜底 query 总会命中术语白话对照表 chunk，
    对综合性理论回答引入噪音，故 fallback 不再叠加。
    """
    _workflow = XianzhiWorkflow(chat_model=None)
    queries, meta = build_theory_queries("命理学有哪些流派")
    assert meta == "fallback"
    assert len(queries) == 1
    assert queries[0] == "命理学有哪些流派"


def test_decompose_query_parses_llm_json():
    """LLM 拆解：枭神夺食问题 → theory 域 + 精准 query + needs_chart=True"""
    llm_output = '{"domain":"theory","queries":["枭神夺食 偏印 食神 条件"],"needs_chart":true}'
    model = FakeListChatModel(responses=[llm_output])
    workflow = XianzhiWorkflow(chat_model=model)
    intent = workflow._decompose_query("我命盘是不是枭神夺食了")
    assert intent is not None
    assert intent.domain == "theory"
    assert intent.needs_chart is True
    assert len(intent.queries) == 1
    assert "枭神夺食" in intent.queries[0]


def test_decompose_query_fallback_on_invalid_json():
    """LLM 输出非法 JSON → 返回 None，调用方走 classify_question"""
    model = FakeListChatModel(responses=["这不是JSON"])
    workflow = XianzhiWorkflow(chat_model=model)
    intent = workflow._decompose_query("随便问个问题")
    assert intent is None


def test_decompose_query_fallback_when_no_chat_model():
    """无 chat_model → 直接返回 None"""
    workflow = XianzhiWorkflow(chat_model=None)
    assert workflow._decompose_query("任何问题") is None


def test_needs_chart_overrides_skip_facts():
    """needs_chart=True 时，theory worker 的 skip_facts 被覆盖，注入命盘事实"""
    llm_output = '{"domain":"theory","queries":["枭神夺食"],"needs_chart":true}'
    model = FakeListChatModel(responses=[llm_output, "你的命盘没有枭神夺食。"])
    workflow = XianzhiWorkflow(chat_model=model)
    ctx = build_chart_context("1990-05-20 14:30", MALE)
    intent = workflow._decompose_query("我是不是枭神夺食了")
    assert intent is not None and intent.needs_chart
    # 验证 _build_messages 不 skip facts
    messages = workflow._build_messages("我是不是枭神夺食了", intent, ctx, "知识", [], None)
    human_content = [m for m in messages if hasattr(m, "content") and "用户问题" in m.content][-1].content
    assert "系统排盘事实" in human_content


def test_build_messages_no_longer_injects_similar_cases_for_duanshi():
    """回归：相似命例注入已在重构中移除（f150847 移除相似命盘检索），断事类不再注入命例参考。"""
    workflow = XianzhiWorkflow(chat_model=None)
    ctx = build_chart_context("1990-05-20 14:30", MALE)
    intent = classify_question("我的婚姻感情怎么样？", today=dt.date(2026, 7, 5))

    messages = workflow._build_messages("我的婚姻感情怎么样？", intent, ctx, "知识", [], None)
    human_content = [m for m in messages if hasattr(m, "content") and "用户问题" in m.content][-1].content

    assert "相似命例参考" not in human_content
    assert "不得照搬结论" not in human_content


def test_build_messages_skips_similar_cases_for_theory():
    """理论解释不注入案例，避免概念问答被命例带偏。"""
    workflow = XianzhiWorkflow(chat_model=None)
    ctx = build_chart_context("1990-05-20 14:30", MALE)
    intent = classify_question("用神是什么意思", today=dt.date(2026, 7, 5))

    messages = workflow._build_messages("用神是什么意思", intent, ctx, "知识", [], None)
    human_content = [m for m in messages if hasattr(m, "content") and "用户问题" in m.content][-1].content

    assert "相似命例参考" not in human_content


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


def test_fact_block_exposes_special_pattern_and_useful_hint():
    """命盘事实须显式携带：用神提示（取用神参考）+ 特殊格局分类（专旺/从格），
    供 LLM 在其上叠加合化/调候/大运破格推理。"""
    _workflow = XianzhiWorkflow(chat_model=None)
    ctx = build_chart_context("1990-05-20 14:30", MALE)
    intent = classify_question("我的命局用神是什么", today=dt.date(2026, 7, 5))

    facts = fact_block(ctx.chart, intent)

    # 取用神参考：必须进事实
    assert "用神提示:" in facts
    # 方案B：特殊格局分类显式成行，取值须为 {无, 专旺, 从格}
    sp_lines = [ln for ln in facts.splitlines() if ln.startswith("特殊格局:")]
    assert sp_lines, "事实块缺少「特殊格局:」行"
    sp_val = sp_lines[0].split("特殊格局:", 1)[1].strip()
    assert sp_val in ("无", "专旺", "从格")
