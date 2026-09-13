"""Reviewer 两层审核专项回归测试（2026-09-13 审查修复）。

覆盖审查中发现并可复现的问题：
- R1 流年干支校验被宽泛大运关键词绕过（"…这一步运里…"导致漏检）
- R2 大运干支完全无校验（编造大运可过）
- R3 否定词表单字"不/无/非"把肯定断言当否定放行
- R5 合婚双盘同一条 issue 重复两遍
- R6 古籍引用：只认"原文："句式、白名单书名使句级核验形同虚设
- L1 `_parse_json` 贪婪匹配 → 带大括号的思考文字导致审核静默降级为"通过"
- L2 `pass` 字段字符串 "false" 被 bool() 判成 True → 真判不通过被吞
- L3 审核调用绕过统一封装（无 timeout bind、不清 think 标签）
- L5 `review()` 正则短路：调用方以为触发 LLM 深审，实际未调用
"""

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage

from app.agent.workflow.workflow_messages import _compute_shensha, compact_facts
from app.agent.workflow.workflow_models import QuestionIntent
from app.agent.workflow.workflow_support import _parse_json
from app.agent.workflow.workflow_workers import ReviewerWorker, _coerce_pass
from app.agent.workflow.xianzhi_workflow import XianzhiWorkflow
from app.domain.bazi_engine import build_bazi_chart, parse_gender

MALE = "男"
# 固定盘：甲申 庚午 壬申 甲辰（华盖→时柱、学堂→日柱；大运 辛未/壬申/癸酉/甲戌/乙亥/丙子…）
CHART = build_bazi_chart("2004-06-22 08:00", MALE, liunian_start_year=2026, liunian_years=10)
OTHER_CHART = build_bazi_chart("1996-03-08 10:00", "女", liunian_start_year=2026, liunian_years=10)
WORKFLOW = XianzhiWorkflow(chat_model=None)
INTENT = QuestionIntent(domain="personality", label="性格心性", needs_chart=True)
FACTS = compact_facts(CHART, INTENT)


def _issues(answer, facts=FACTS, other=None):
    return WORKFLOW.check_facts(answer, CHART, other, True, facts).issues


# ============================================================
# R1 流年干支校验
# ============================================================

def test_liunian_ganzhi_still_checked_when_sentence_mentions_yun():
    """句中出现"运/走"不再整体跳过流年干支校验（旧版 ±30 字宽泛豁免导致漏检）。"""
    assert any("2030年流年应为庚戌" in i for i in _issues("2030年是己酉年，注意变动。"))
    assert any("2030年流年应为庚戌" in i for i in _issues("2030年是己酉年，这一步运里注意变动。"))
    assert any("2030年流年应为庚戌" in i for i in _issues("2030年是己酉年，你走到关键期。"))


def test_liunian_ganzhi_check_correct_value_passes():
    assert _issues("2030年是庚戌年，注意变动。") == []


def test_dayun_context_is_still_exempt_for_liunian_check():
    """"2030年走壬申大运"里的干支属于大运（本盘第二步大运），不算流年干支错误。"""
    assert _issues("2030年走壬申大运，事业会起来。") == []
    assert _issues("2030年壬申大运里，事业会起来。") == []


# ============================================================
# R2 大运干支校验
# ============================================================

def test_fabricated_dayun_ganzhi_is_caught():
    """编造的大运干支（本盘 12 步大运与流年窗口都没有丁卯）必须报错。"""
    issues = _issues("你下一步走丁卯大运，事业会起来。")
    assert any("丁卯" in i and "大运" in i for i in issues), issues


def test_real_dayun_and_liunian_ganzhi_pass():
    assert _issues("你走到癸酉运，本身是劫财运，又带桃花。") == []
    assert _issues("癸酉运里走己酉年，感情会有波动。") == []


# ============================================================
# R3 否定词判定
# ============================================================

def test_negation_words_like_bucuo_do_not_suppress_positive_assertion():
    """"不错""无论""非常"里的单字不能被当成否定词（否则肯定断言被放行）。

    本盘没有"拱禄"，因此"命中拱禄"这类肯定归属断言必须报错。
    """
    for answer in (
        "你日柱不错，命中拱禄。",
        "你日柱无论怎么看，命中拱禄。",
        "你日柱非常好，命中拱禄。",
    ):
        assert any("拱禄" in i for i in _issues(answer)), answer


def test_real_negation_still_suppresses_assertion():
    """真否定句继续放行，不因 R3 收紧而误报。"""
    for answer in (
        "你日柱没有拱禄。",
        "你日柱不带拱禄。",
        "你命中并非拱禄。",
        "你日柱无拱禄。",
    ):
        assert _issues(answer) == [], answer


# ============================================================
# R5 合婚双盘 issue 去重
# ============================================================

def test_matchmaking_duplicate_issues_are_deduped():
    """合婚双盘时同一条 issue 只记一次（旧版两盘各报一遍）。"""
    worker = ReviewerWorker(chat_model=None)
    issues = worker._regex_review(
        "2030年是己酉年，注意变动。", CHART, "知识", WORKFLOW.check_facts, OTHER_CHART, True, FACTS
    )
    assert issues, "应当报出流年干支错误"
    assert len(issues) == len(set(issues)), issues


# ============================================================
# R6 古籍真实性
# ============================================================

_KNOWLEDGE_WITH_DTS = (
    "【命理规则检索】\n[古籍04｜《滴天髓》注解核心]\n"
    "壬水通河，能泄金气。刚中之德，周流不滞。"
)


def _ancient_issues(answer, knowledge):
    worker = ReviewerWorker(chat_model=None)
    return worker._regex_review(answer, CHART, knowledge, WORKFLOW.check_facts, None, True, FACTS)


def test_ancient_citation_verbatim_in_retrieved_chunk_passes():
    issues = _ancient_issues('《滴天髓》原文：“壬水通河，能泄金气。”你命局正合此论。', _KNOWLEDGE_WITH_DTS)
    assert not any("古籍" in i or "原文" in i for i in issues), issues


def test_ancient_citation_fabricated_sentence_is_caught():
    """书名在检索片段中，但引号原句不在 → 判为伪造原文（旧版只要书名白名单就放行）。"""
    issues = _ancient_issues('《滴天髓》原文：“庚金带煞，刚健为最。”此论正合你盘。', _KNOWLEDGE_WITH_DTS)
    assert any("疑似杜撰原文" in i for i in issues), issues


def test_ancient_citation_non_whitelist_book_caught_with_yun_marker():
    """非白名单书名写成"《X》云：…"也不能绕过（旧版只认"原文："句式）。"""
    issues = _ancient_issues('《麻衣神相》云：“额有伏犀，贵不可言。”', _KNOWLEDGE_WITH_DTS)
    assert any("未在检索结果中出现" in i for i in issues), issues


def test_ancient_citation_whitelist_book_not_retrieved_stays_lenient():
    """白名单书名但本次检索没覆盖该书 → 沿用宽口径放行，不误杀。"""
    issues = _ancient_issues('《滴天髓》原文：“庚金带煞，刚健为最。”此论正合你盘。', "【命理规则检索】无关片段")
    assert not any("古籍" in i or "原文" in i for i in issues), issues


# ============================================================
# L1/L3 JSON 解析与调用封装
# ============================================================

def test_parse_json_survives_prose_braces_and_think_blocks():
    """思考文字/说明里出现大括号不能让 JSON 解析失败（旧版贪婪正则 → 审核静默降级为通过）。"""
    assert _parse_json('{"pass": false, "issues": ["x"]}') == {"pass": False, "issues": ["x"]}
    for raw in (
        '先核对一下 {草稿：年柱甲申} 再给结论：\n{"pass": false, "issues": ["x"]}',
        '<think>排盘是{甲申}，所以有错</think>\n{"pass": false, "issues": ["x"]}',
        '{"pass": false, "issues": ["x"]}\n（以上依据 {排盘事实}。）',
        '```json\n{"pass": false, "issues": ["x"]}\n```',
    ):
        assert _parse_json(raw) == {"pass": False, "issues": ["x"]}, raw


def test_parse_json_prefers_verdict_over_hypothetical_example():
    raw = '<think>若写成 {"pass": true} 就错了</think>\n{"pass": false, "issues": ["x"]}'
    assert _parse_json(raw) == {"pass": False, "issues": ["x"]}


def test_llm_review_parses_verdict_despite_think_block():
    """端到端：think 块 + JSON → 真的按 LLM 结论判不通过（source=llm）。"""
    model = FakeListChatModel(responses=['<think>排盘是{甲申}</think>\n{"pass": false, "issues": ["硬错误"]}'])
    worker = ReviewerWorker(chat_model=model)
    result = worker._llm_review("答案", CHART, "知识", "问题", None, None)
    assert result.ok is False
    assert result.source == "llm"
    assert result.issues == ["硬错误"]


# ============================================================
# L2 pass 字段类型归一化
# ============================================================

def test_coerce_pass_handles_string_values():
    assert _coerce_pass(True) is True
    assert _coerce_pass(False) is False
    assert _coerce_pass("false") is False
    assert _coerce_pass("否") is False
    assert _coerce_pass("不通过") is False
    assert _coerce_pass("true") is True
    assert _coerce_pass(None) is True


def test_llm_review_string_false_is_not_treated_as_pass():
    model = FakeListChatModel(responses=['{"pass": "false", "issues": ["十神事实错误"]}'])
    worker = ReviewerWorker(chat_model=model)
    result = worker._llm_review("答案", CHART, "知识", "问题", None, None)
    assert result.ok is False, "字符串 false 不能被 bool() 当成通过"
    assert result.issues == ["十神事实错误"]


def test_llm_review_pass_false_without_issues_is_treated_as_pass():
    """判不通过却不给 issues：修复器无事可做，按通过处理（避免空修复轮），并计入指标。"""
    model = FakeListChatModel(responses=['{"pass": false, "issues": []}'])
    worker = ReviewerWorker(chat_model=model)
    result = worker._llm_review("答案", CHART, "知识", "问题", None, None)
    assert result.ok is True


# ============================================================
# L5 review() 短路 vs review_llm_only()
# ============================================================

def test_review_short_circuits_on_regex_but_review_llm_only_reaches_llm():
    """review() 命中正则即返回（不调 LLM）；review_llm_only() 必须真的走到 LLM。"""
    model = FakeListChatModel(responses=['{"pass": true, "issues": []}', '{"pass": true, "issues": []}'])
    worker = ReviewerWorker(chat_model=model)
    answer = "你日柱带华盖。"  # 华盖属时柱 → 正则命中

    regex_first = worker.review(
        answer, CHART, "知识", WORKFLOW.check_facts, None, needs_chart=True, facts_text=FACTS
    )
    assert regex_first.source == "regex"
    assert not regex_first.ok

    llm_only = worker.review_llm_only(answer, CHART, "知识", user_prompt="测试问题")
    assert llm_only.source == "llm"
    assert llm_only.ok


def test_review_llm_only_is_safe_without_model():
    worker = ReviewerWorker(chat_model=None)
    result = worker.review_llm_only("任意回答", CHART, "知识")
    assert result.ok and result.source == "regex"


# ============================================================
# L5 端到端：修复稿 regex 仍报问题 → 真的跑 LLM 深审并计入指标
# ============================================================

class _ScriptedModel:
    """按 prompt 内容分派返回值：审核 → 判定 JSON；拆解 → 拆解 JSON；其余 → Worker 回答。"""

    def __init__(self, worker_answer, verdict):
        self.worker_answer = worker_answer
        self.verdict = verdict
        self.review_calls = 0

    def bind(self, **kwargs):
        return self

    def invoke(self, messages, **kwargs):
        text = "\n".join(str(getattr(m, "content", "")) for m in messages)
        if "【待审核回答】" in text:
            self.review_calls += 1
            return AIMessage(content=self.verdict)
        if "domain" in text and "queries" in text:
            return AIMessage(
                content='{"domain":"personality","queries":["性格 十神 格局 特征"],'
                '"needs_chart":true,"other_birth_time":"","other_gender":"","target_dayun":""}'
            )
        return AIMessage(content=self.worker_answer)


def test_repair_second_check_reaches_llm_and_records_metric():
    """修复稿仍被 regex 打回时：LLM 深审必须真的被调用（旧版 review() 被正则短路，LLM 从未调用），
    LLM 判通过则按修复稿定稿并记 reviewer_regex_likely_false_positive。
    """
    from unittest.mock import MagicMock, patch

    from app.agent.xianzhi import Xianzhi
    from app.core.observability import get_metrics

    model = _ScriptedModel(
        worker_answer="你日柱带华盖，爱琢磨，平时喜欢安静。",  # 华盖属时柱 → regex 命中
        verdict='{"pass": true, "issues": []}',
    )
    before = dict(get_metrics()["internal_errors"]).get("reviewer_regex_likely_false_positive", 0)

    with patch("app.agent.xianzhi.create_chat_memory") as m1:
        m1.return_value = MagicMock()
        agent = Xianzhi(chat_model=model, local_tools=[])
        agent.set_conversation_id("test-repair-llm-second-check")
        agent.set_chart_context("2004-06-22 08:00", MALE)
        answer = agent.run("我性格怎么样？")

    assert model.review_calls == 1, "修复后的二次判定必须真的调用 LLM 深审"
    assert "华盖" in answer
    after = dict(get_metrics()["internal_errors"]).get("reviewer_regex_likely_false_positive", 0)
    assert after == before + 1, "regex 疑似误报必须计入 /metrics internal_errors"


# ============================================================
# R7 神煞名单漂移守卫
# ============================================================

def test_computed_shensha_names_are_all_known_to_checker():
    """排盘计算器产出的神煞名必须都在审核名单里（否则新神煞会被误判"排盘事实中无"）。"""
    import datetime as dt
    import inspect
    import ast
    import textwrap

    from app.agent.workflow.workflow_messages import check_facts

    def _literal(varname):
        tree = ast.parse(textwrap.dedent(inspect.getsource(check_facts)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == varname for t in node.targets
            ):
                return set(ast.literal_eval(node.value))
        raise KeyError(varname)

    known = _literal("_SHENSHA_NAMES") | _literal("_SHISHEN_NAMES")
    produced = set()
    for i in range(120):
        d = dt.date(1950, 1, 1) + dt.timedelta(days=i * 53)
        chart = build_bazi_chart(f"{d.isoformat()} 0{i % 9}:30", MALE if i % 2 else "女")
        for item in _compute_shensha(chart.pillars, parse_gender(chart.birth.gender)):
            produced.add(item.get("name", ""))
    assert produced <= known, f"计算器产出但审核名单缺失: {sorted(produced - known)}"
