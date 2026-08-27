"""工作流消息拼装与事实校验（含双盘/合婚/Reflextion 修复消息）。

纯函数模块：供 XianzhiWorkflow Supervisor 委托调用，不持有实例状态。
从 app/agent/xianzhi_workflow.py 抽离（解耦：把"消息装配 + 事实校验"这一单一职责独立成模块），
行为与原内联实现完全一致。
"""

from __future__ import annotations

import datetime as _dt
import re

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agent.core.base_agent import _wrap_user_input
from app.agent.prompts import (
    ORACLE_BASE_SYSTEM,
    WORKER_PREAMBLE_TEMPLATE,
    WORKFLOW_FACT_REDLINE,
    reflect_sysprompt,
)
from app.agent.workflow.workflow_models import (
    DomainWorker,
    FactCheckResult,
    QuestionIntent,
    WorkflowChartContext,
)
from app.agent.workflow.workflow_support import (
    GANZHI_RE,
    YEAR_GANZHI_RE,
    _dedupe_content,
)
from app.agent.workflow.workflow_workers import WORKERS
from app.core.logger import log
from app.domain.bazi_engine import (
    CONTROLS,
    GAN_CHONG,
    GAN_HE,
    GAN_WUXING,
    BaziChart,
    _compute_shensha,
    parse_gender,
)
from app.tools.text_clean import clean_think_tags

# 工作流生成/修复产出长文本（含思维链），60s 默认超时不够，单独放宽
_WORKFLOW_LLM_TIMEOUT = 180.0

# 防御：剥离模型回显的用户输入边界标记（防止 LLM 把 "--- USER INPUT BEGIN/END ---" 原样当作回答输出）
_USER_INPUT_BOUNDARY_RE = re.compile(
    r"---\s*USER\s+INPUT\s+BEGIN\s*---[\s\S]*?---\s*USER\s+INPUT\s+END\s*---"
)


def _strip_user_input_boundary(content: str) -> str:
    """移除回答里回显的 ```--- USER INPUT BEGIN/END ---``` 边界块及其包裹的复述内容。

    用户输入被 _wrap_user_input 包上边界标记以防指令注入；若模型把整段标记连同
    用户原话一并当回答输出，这里一次性剥掉，保证用户永远看不到内部标记。
    """
    if not content:
        return content
    cleaned = _USER_INPUT_BOUNDARY_RE.sub("", content)
    # 清理剥离后可能残留的多余空行
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def build_messages(
    user_prompt: str,
    intent: QuestionIntent,
    ctx: WorkflowChartContext,
    knowledge: str,
    history: list[BaseMessage],
    worker: DomainWorker | None = None,
    summary: str = "",
) -> list[BaseMessage]:
    """组装发给 LLM 的消息列表（system + 断法抬头 + 事实 + 知识 + 历史 + 用户提问）。

    Worker 配置优先（专业 Worker 提供 length_rule / skip_facts）；needs_chart 覆盖
    skip_facts：当用户问「我命盘是不是 XX」时必须注入命盘事实。尾部补入历史与会话摘要。
    """
    if worker is None:
        worker = WORKERS.get(intent.domain, WORKERS["general"])
    skip = worker.skip_facts and not intent.needs_chart
    facts = "" if skip else compact_facts(ctx.chart, intent)
    recent_history = compact_history(history, summary)
    # 篇幅规则：详批优先 → Worker 专属规则
    if intent.wants_report:
        length_rule = "可以分段深入，但仍要围绕用户问题，不要堆砌全盘。"
    else:
        length_rule = worker.length_rule
    system = ORACLE_BASE_SYSTEM + "\n\n" + WORKFLOW_FACT_REDLINE
    # 追加 Worker 专属断法规则（专业 Worker 的领域知识），统一加"倾向性，须结合原局"抬头
    if worker.expertise_prompt:
        preamble = WORKER_PREAMBLE_TEMPLATE.format(领域=worker.label)
        system += "\n" + preamble + "\n" + worker.expertise_prompt
    human = (
        f"【用户问题】\n{_wrap_user_input(user_prompt)}\n\n"
        f"【识别意图】\n领域={intent.label}; 目标年份={intent.target_years or '未指定'}; 置信度={intent.confidence}\n\n"
        f"【最近对话摘要】\n{recent_history}\n\n"
    )
    if facts:
        human += f"【系统排盘事实】\n{facts}\n\n"
    match_basis = getattr(intent, "match_basis", "")
    if match_basis:
        human += f"【合婚基础数据（系统规则）】\n{match_basis}\n\n"
    # 注入该命盘的历史断事知识（已验证/已否定）
    chart_facts_text = get_chart_facts_text(ctx)
    if chart_facts_text:
        human += f"【历史断事参考】\n{chart_facts_text}\n\n"
    human += (
        f"【命理规则检索】\n{knowledge}\n\n"
        f"【输出要求】\n{length_rule}\n"
        "如果提到具体年份，必须同时核对该年流年干支和所在大运。"
    )
    return [SystemMessage(content=system), HumanMessage(content=human)]


def get_chart_facts_text(ctx: WorkflowChartContext) -> str:
    """从命盘画像中获取历史断事知识，供 LLM 上下文注入。"""
    if not ctx.birth_time or not ctx.gender:
        return ""
    try:
        from app.db.chart_store import get_chart_facts_for_llm, get_chart_profile

        profile = get_chart_profile(
            getattr(ctx, "user_id", "") or "",
            ctx.birth_time,
            ctx.gender,
        )
        if not profile:
            return ""
        verified, disputed = get_chart_facts_for_llm(profile["id"], limit=6)
        lines = []
        if verified:
            lines.append("【已验证断事】以下均为用户确认过的历史事实，可直接引用：")
            for v in verified:
                lines.append(f"  • {v}")
        if disputed:
            lines.append("【已否定断事】以下判断用户已明确否认，务必避免重复：")
            for d in disputed:
                lines.append(f"  ✗ {d}")
        return "\n".join(lines)
    except Exception as e:
        log.warning("[断事知识] 加载失败: {}", e)
        return ""


def build_repair_messages(
    raw_answer: str,
    checked: FactCheckResult,
    user_prompt: str,
    intent: QuestionIntent,
    ctx: WorkflowChartContext,
    knowledge: str,
    worker: DomainWorker | None = None,
) -> list[BaseMessage]:
    """Reflextion 修复消息：带上 Worker 专属断法，让 LLM 基于 issues 反思修复。"""
    if worker is None:
        worker = WORKERS.get(intent.domain, WORKERS["general"])
    facts = "" if worker.skip_facts else compact_facts(ctx.chart, intent)
    # Reflextion 改写器：带上 Worker 专属断法，确保修复后仍符合领域规范
    sys_content = reflect_sysprompt

    if worker.expertise_prompt:
        preamble = WORKER_PREAMBLE_TEMPLATE.format(领域=worker.label)
        sys_content += "\n" + preamble + "\n" + worker.expertise_prompt
    return [
        SystemMessage(content=sys_content),
        HumanMessage(
            content=(
                f"【用户问题】\n{_wrap_user_input(user_prompt)}\n\n"
                f"【原回答】\n{raw_answer}\n\n"
                f"【发现的问题】\n"
                + "\n".join(f"- {issue}" for issue in checked.issues)
                + "\n\n"
                + (f"【正确排盘事实】\n{facts}\n\n" if facts else "")
                + (
                    f"【合婚基础数据（系统规则）】\n{getattr(intent, 'match_basis', '')}\n\n"
                    if getattr(intent, "match_basis", "")
                    else ""
                )
                + f"【可用规则】\n{knowledge}\n\n"
                "请输出修正后的最终回答。"
            )
        ),
    ]


def invoke(chat_model, messages: list[BaseMessage]) -> str:
    """调用 LLM 生成回答，过滤  thinking 推理过程并去重。

    工作流 generate/repair 产出为长文本（含思维链），60s 默认超时频繁触发
    ReadTimeout，故单独放宽（与 report_generator 的 300s 同思路）。
    """
    response = chat_model.bind(timeout=_WORKFLOW_LLM_TIMEOUT).invoke(messages)
    content = (getattr(response, "content", "") or "").strip()
    content = clean_think_tags(content)
    content = _strip_user_input_boundary(content)
    if not content:
        return "我先看盘面，当前信息足够排盘，但模型没有生成有效解读。你可以换一个更具体的问题继续问。"
    return _dedupe_content(content)


def compact_history(history: list[BaseMessage], summary: str = "") -> str:
    """压缩历史对话为可注入 LLM 的简短文本（最近 3 轮 + 会话摘要）。"""
    if not history and not summary:
        return "（无）"
    parts = []
    if summary:
        parts.append(f"【历史摘要】{summary}")
    recent = history[-6:] if history else []
    recent_3 = recent[-3:]
    if recent_3:
        chunks = []
        for msg in recent_3:
            role = msg.__class__.__name__.replace("Message", "")
            content = str(getattr(msg, "content", "")).strip()
            if content:
                chunks.append(f"{role}: {content[:250]}")
        if chunks:
            parts.append("【最近对话】\n" + "\n".join(chunks))
    return "\n\n".join(parts) if parts else "（无）"


def fact_block(chart: BaziChart, intent: QuestionIntent) -> str:
    """单张命盘的紧凑事实块（不含对方盘逻辑，供 compact_facts 复用）。"""
    today = _dt.date.today()
    pillars = " ".join(f"{p.name}:{p.ganzhi}({p.nayin})" for p in chart.pillars)
    # 四柱详述：藏干/副星/星运/自坐/空亡（表格新增字段，必须随排盘事实进 LLM 才能正确推理）
    pillar_detail = "\n".join(
        f"  {p.name}{'（日主）' if p.name == '日柱' else ''} {p.ganzhi}: "
        f"主星[{p.shishen_gan or '—'}] "
        f"藏干[{'、'.join(p.hidden_stems) or '—'}] "
        f"副星[{'、'.join(p.shishen_zhi) or '—'}] "
        f"星运[{p.changsheng or '—'}] "
        f"自坐[{p.zizuo or '—'}] "
        f"空亡[{p.xunkong or '—'}]"
        for p in chart.pillars
    )
    # 天干关系：干合、干冲、干克、三奇
    visible_gans = [p.gan for p in chart.pillars if p.gan]
    gan_he: list[str] = []
    gan_chong: list[str] = []
    gan_ke: list[str] = []
    for i in range(len(visible_gans)):
        for j in range(i + 1, len(visible_gans)):
            pair = frozenset((visible_gans[i], visible_gans[j]))
            if pair in GAN_HE:
                gan_he.append(GAN_HE[pair])
            if pair in GAN_CHONG:
                gan_chong.append(GAN_CHONG[pair])
            # 天干相克（木克土、土克水、水克火、火克金、金克木）
            wx_i = GAN_WUXING.get(visible_gans[i], "")
            wx_j = GAN_WUXING.get(visible_gans[j], "")
            if wx_i and wx_j:
                if CONTROLS.get(wx_i) == wx_j:
                    gan_ke.append(f"{visible_gans[i]}克{visible_gans[j]}")
                elif CONTROLS.get(wx_j) == wx_i:
                    gan_ke.append(f"{visible_gans[j]}克{visible_gans[i]}")
    # 三奇贵人：四柱天干中同时出现甲戊庚/乙丙丁/壬癸辛
    gan_set = set(visible_gans)
    sanqi: list[str] = []
    if {"甲", "戊", "庚"} <= gan_set:
        sanqi.append("甲戊庚（三奇贵人）")
    if {"乙", "丙", "丁"} <= gan_set:
        sanqi.append("乙丙丁（三奇贵人）")
    if {"壬", "癸", "辛"} <= gan_set:
        sanqi.append("壬癸辛（三奇贵人）")
    gan_rel_parts = []
    if gan_he:
        gan_rel_parts.append(f"合={'、'.join(gan_he)}")
    if gan_chong:
        gan_rel_parts.append(f"冲={'、'.join(gan_chong)}")
    if gan_ke:
        gan_rel_parts.append(f"克={'、'.join(gan_ke)}")
    if sanqi:
        gan_rel_parts.append(f"三奇={'、'.join(sanqi)}")
    gan_relation_line = "；".join(gan_rel_parts) if gan_rel_parts else "—"
    # 神煞：按柱分组注入，确保与前端表格展示一致（此前完全缺失，LLM 看不到神煞）
    shensha_all = _compute_shensha(chart.pillars, parse_gender(chart.birth.gender))
    shensha_by_pillar: dict[str, list[str]] = {}
    for _s in shensha_all:
        shensha_by_pillar.setdefault(_s.get("pillar") or "全局", []).append(_s["name"])
    shensha_line = "；".join(
        f"{p.name}:{'、'.join(shensha_by_pillar.get(p.name, [])) or '—'}" for p in chart.pillars
    )
    dayun_lines = [
        f"{item.ganzhi}({item.shishen_gan}) {item.start_year}-{item.end_year} {item.start_age}-{item.end_age}岁 "
        f"藏干[{'、'.join(item.hidden_stems) or '—'}] 副星[{'、'.join(item.shishen_zhi) or '—'}] "
        f"星运[{item.changsheng or '—'}] 神煞[{'、'.join(s['name'] for s in item.shensha) or '—'}]"
        for item in chart.dayun
    ]
    if intent.target_years:
        liunian_items = [item for item in chart.liunian if item.year in set(intent.target_years)]
    else:
        current_year = today.year
        liunian_items = [item for item in chart.liunian if current_year <= item.year <= current_year + 3]
        if not liunian_items:
            liunian_items = chart.liunian[:4]
    liunian_lines = [
        f"{item.year}年:{item.ganzhi}({item.shishen_gan}) {item.age}虚岁 所在大运:{item.dayun_ganzhi or '-'} "
        f"藏干[{'、'.join(item.hidden_stems) or '—'}] 副星[{'、'.join(item.shishen_zhi) or '—'}] "
        f"星运[{item.changsheng or '—'}] 神煞[{'、'.join(s['name'] for s in item.shensha) or '—'}]"
        for item in liunian_items
    ]
    # 计算用户当前周岁，避免 LLM 自行推算出错
    birth_str = chart.birth.solar or ""
    current_age = ""
    try:
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", birth_str)
        if m:
            by, bm, bd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            age = today.year - by - ((today.month, today.day) < (bm, bd))
            current_age = f"; 当前周岁: {age}岁"
    except Exception:
        pass
    return "\n".join(
        [
            f"当前日期: {today.year}年{today.month}月{today.day}日{current_age}",
            f"出生: {chart.birth.solar}; 性别: {chart.birth.gender}; 农历: {chart.birth.lunar}; 生肖: {chart.birth.shengxiao}",
            f"四柱: {pillars}",
            f"四柱详述:\n{pillar_detail}",
            f"神煞（按柱）: {shensha_line}",
            f"日主: {chart.wuxing.day_master}({chart.wuxing.day_master_wuxing}); 强弱: {chart.wuxing.strength}; 分数: {chart.wuxing.strength_score}",
            f"特殊格局: {chart.wuxing.special_pattern or '无'}",
            f"五行权重: {chart.wuxing.counts}; 最旺: {chart.wuxing.strongest}; 最弱: {chart.wuxing.weakest}",
            f"用神提示: {chart.wuxing.useful_hint}",
            f"十神结构: {chart.analysis.ten_gods}; 透干: {chart.analysis.exposed_stems or '-'}; 通根: {chart.analysis.rooted_stems or '-'}",
            f"天干关系: {gan_relation_line}",
            f"地支关系: 合={chart.analysis.combinations or '-'}; 冲={chart.analysis.clashes or '-'}; 害={chart.analysis.harms or '-'}; 刑={chart.analysis.punishments or '-'}; 三合/三会/破={chart.analysis.three_assemblies or '-'}",
            f"调候: 月令{chart.analysis.season}; {chart.analysis.adjustment}",
            f"判断置信度: {chart.analysis.confidence}",
            f"起运: {chart.start_yun['startDate']} 起; {chart.start_yun['direction']}; 起运年龄 {chart.start_yun['startYear']}年{chart.start_yun['startMonth']}月{chart.start_yun['startDay']}日",
            "大运: " + "；".join(dayun_lines),
            "相关流年: " + ("；".join(liunian_lines) if liunian_lines else "未指定"),
            "口径: " + "；".join(chart.warnings),
        ]
    )


def compact_facts(chart: BaziChart, intent: QuestionIntent) -> str:
    """命盘事实块（含合婚双盘时追加对方盘事实）。"""
    facts = fact_block(chart, intent)
    # 合婚双盘：追加对方命盘事实
    second = getattr(intent, "second_chart", None)
    if second is not None:
        facts += "\n\n【对方命盘事实】\n" + fact_block(second.chart, intent)
    return facts


def check_facts(
    answer: str,
    chart: BaziChart,
    other_chart: BaziChart | None = None,
    needs_chart: bool = True,
) -> FactCheckResult:
    """校验回答中的四柱/大运/流年/十神/神煞是否与系统排盘一致。

    Args:
        other_chart: 合婚双盘时的对方命盘，同一干支若出现在任一张合法盘上即视为正确。
        needs_chart: 当前回答是否属于"绑定命盘分析"场景（命盘分析/合婚/流年大运推演等）。
            - True（默认）：严格校验十神/神煞的存在性与柱位归属，禁止凭空捏造
            - False（理论/术语解释场景）：仅校验**归属断言**（"你命盘有X""年柱X"等绑定命盘的表述），
              纯术语解释（"红鸾主喜庆""正财代表求财"）不受限，避免误杀理论问答。
    """
    issues: list[str] = []
    year_to_gz: dict[int, str] = {item.year: item.ganzhi for item in chart.liunian}
    if other_chart is not None:
        for item in other_chart.liunian:
            year_to_gz.setdefault(item.year, item.ganzhi)
    _DAYUN_KEYWORDS = ("大运", "交运", "起运", "运柱", "行运", "运", "步入", "走", "交")
    for match in YEAR_GANZHI_RE.finditer(answer):
        year = int(match.group("year"))
        stated = match.group("ganzhi")
        expected = year_to_gz.get(year)
        if not expected or stated == expected:
            continue
        # 大运语境排除：年份+干支附近若明确在描述大运（出现大运关键词），则该干支视为大运而非流年，跳过校验。
        # 直接以「年份附近有大运关键词」语义判断，避免把大运干支误判为流年错误（不依赖 dayun 集合完整度）。
        start = max(0, match.start() - 30)
        end = min(len(answer), match.end() + 30)
        context = answer[start:end]
        if any(kw in context for kw in _DAYUN_KEYWORDS):
            continue
        issues.append(f"{year}年流年应为{expected}，回答写成了{stated}")

    # 每个柱名下，两张盘各自合法的干支都算正确
    valid: dict[str, set[str]] = {}
    for p in chart.pillars:
        valid.setdefault(p.name, set()).add(p.ganzhi)
    if other_chart is not None:
        for p in other_chart.pillars:
            valid.setdefault(p.name, set()).add(p.ganzhi)
    primary = {p.name: p.ganzhi for p in chart.pillars}
    for name, expected_set in valid.items():
        pattern = re.compile(rf"{name}[^。；;，,、\n]{{0,8}}(?P<ganzhi>{GANZHI_RE.pattern})")
        for match in pattern.finditer(answer):
            stated = match.group("ganzhi")
            if stated not in expected_set:
                issues.append(f"{name}应为{primary[name]}，回答写成了{stated}")

    # 十神事实校验 + 神煞事实校验
    # 核心原则：
    #   needs_chart=True（绑定命盘分析）→ 严格，任何十神/神煞组合断言、归属断言都校验
    #   needs_chart=False（理论问答）   → 宽松，仅当回答出现「绑定命盘的归属断言」时才校验，
    #                                     纯术语解释（"红鸾主喜庆""正财主求财"）放行
    #
    # 归属断言的正则锚点：出现"你命盘/命中/八字/四柱/原局/局中/年柱/月柱/日柱/时柱"等
    #  + 紧随其后出现的十神/神煞名，即视为在对命盘做归属断言。

    # NOTE: "大运""流年"不列入锚点。check_facts 中 actual_shensha_all / actual_shishen
    #       仅收集了 chart.pillars（原盘四柱）的静态事实。大运/流年是动态岁运，
    #       其十神神煞不在原盘事实里，用作锚点会产生系统性误杀（如"大运带桃花"）。
    _ASSERT_ANCHORS = (
        "你命盘",
        "你的命盘",
        "命中",
        "命里",
        "命带",
        "命有",
        "八字",
        "四柱",
        "原局",
        "局中",
        "盘里",
        "盘中",
        "命局",
        "命宫",
        "身带",
        "身有",
        "年柱",
        "月柱",
        "日柱",
        "时柱",
        "年支",
        "月支",
        "日支",
        "时支",
        "年干",
        "月干",
        "日干",
        "时干",
    )
    _SHISHEN_NAMES = [
        "正财",
        "偏财",
        "正官",
        "七杀",
        "偏印",
        "正印",
        "食神",
        "伤官",
        "比肩",
        "劫财",
        "日主",
        "禄神",
    ]
    _SHENSHA_NAMES = [
        "天乙贵人",
        "太极贵人",
        "文昌贵人",
        "羊刃",
        "飞刃",
        "学堂",
        "正学堂",
        "词馆",
        "正词馆",
        "金舆",
        "福星贵人",
        "天厨贵人",
        "国印贵人",
        "流霞",
        "红艳煞",
        "天德贵人",
        "月德贵人",
        "天德合",
        "月德合",
        "德秀贵人",
        "天医",
        "华盖",
        "桃花",
        "驿马",
        "将星",
        "劫煞",
        "亡神",
        "灾煞",
        "吊客",
        "病符",
        "红鸾",
        "天喜",
        "孤辰",
        "寡宿",
        "丧门",
        "披麻",
        "血刃",
        "勾绞煞",
        "元辰",
        "天罗",
        "地网",
        "魁罡",
        "十恶大败",
        "十灵日",
        "八专日",
        "九丑日",
        "阴差阳错",
        "孤鸾煞",
        "六秀日",
        "天赦日",
        "金神",
        "天转日",
        "地转日",
        "四废日",
        "拱禄",
        "三奇贵人",
        "童子煞",
        "空亡",
    ]

    # 收集排盘中实际存在的十神集合（主星+副星，含合婚双盘）
    actual_shishen: set[str] = set()
    for chart_src in [chart] + ([other_chart] if other_chart else []):
        for p in chart_src.pillars:
            if p.shishen_gan and p.shishen_gan != "日主":
                actual_shishen.add(p.shishen_gan)
            for s in p.shishen_zhi:
                if s:
                    actual_shishen.add(s)

    # 收集排盘中实际存在的神煞集合（按柱分组，含合婚双盘）
    actual_shensha_by_pillar: dict[str, set[str]] = {}
    actual_shensha_all: set[str] = set()
    for chart_src in [chart] + ([other_chart] if other_chart else []):
        shensha_list = _compute_shensha(chart_src.pillars, parse_gender(chart_src.birth.gender))
        for s in shensha_list:
            name = s.get("name", "")
            pillar = s.get("pillar", "")
            if name:
                actual_shensha_all.add(name)
                if pillar:
                    actual_shensha_by_pillar.setdefault(pillar, set()).add(name)

    _SENT_SPLIT = re.compile(r"[。；;！!？?\n\r]")
    _NEG_TOKENS = (
        "没见",
        "没有",
        "不带",
        "不含",
        "未见",
        "并无",
        "毫无",
        "不存在",
        "没",
        "不",
        "无",
        "未",
        "非",
        "否",
    )
    # 动态岁运语境标识：出现即认为在讲外部流年/大运，而非原盘静态断言
    _DYNAMIC_CTX = re.compile(r"\d{4}|大运|流年|岁运|年运|运上|流月|流日")
    # "桃花年""红鸾运"等约定俗成 → 目标词后紧接年/运/月 视为动态流年讨论
    _DYNA_SUFFIX = re.compile(r"[年运月令日限]")
    # 正向归属暗示词：只有这些词在目标词附近，才认为是在"断言命盘拥有 X"
    _OWNERSHIP_HINTS = (
        "有",
        "带",
        "含",
        "透",
        "藏",
        "坐",
        "落",
        "居",
        "入命",
        "入盘",
        "出现",
        "存在",
        "透出",
        "显现",
        "见",
        "配",
    )

    def _sentence_has_negative_between(sent: str, a_pos: int, b_pos: int) -> bool:
        """判断 sent 中 a_pos 与 b_pos 之间（含边界附近±2）是否存在否定词。"""
        lo, hi = sorted([a_pos, b_pos])
        lo = max(0, lo - 2)
        hi = min(len(sent), hi + 2)
        seg = sent[lo:hi]
        return any(tok in seg for tok in _NEG_TOKENS)

    def _sentence_is_theory_definition(sent: str, target_word: str) -> bool:
        """判断该句是否是在做纯理论定义/区别解释，而非命盘断言。"""
        for anchor in _ASSERT_ANCHORS:
            if anchor in sent:
                return False
        theory_markers = (
            "主",
            "代表",
            "是指",
            "是",
            "为",
            "含义",
            "意思",
            "解释",
            "区别",
            "指",
            "属于",
            "象征",
            "表示",
            "掌管",
            "管",
            "分类",
            "分为",
            "有真假",
            "有内",
            "有墙",
            "说明",
            "意味着",
            "一般",
            "通常",
            "传统",
        )
        t_pos = sent.find(target_word)
        tail = sent[t_pos:]
        return any(m in tail for m in theory_markers)

    def _sentence_in_dynamic_context(sent: str, target_word: str, t_pos: int) -> bool:
        """判断目标词是否出现在动态岁运语境中（不是原盘断言）。"""
        if _DYNAMIC_CTX.search(sent):
            return True
        after_pos = t_pos + len(target_word)
        if after_pos < len(sent):
            nc = sent[after_pos : after_pos + 1]
            if _DYNA_SUFFIX.search(nc):
                return True
        return False

    def _ownership_hint_nearby(sent: str, t_pos: int, target_word: str) -> bool:
        """目标词附近是否有"有/带/含/透/藏..."等归属暗示。"""
        win = sent[max(0, t_pos - 8) : min(len(sent), t_pos + len(target_word) + 8)]
        return any(h in win for h in _OWNERSHIP_HINTS)

    def _sentence_asserts_positive(sent: str, target_word: str) -> bool:
        """检查单句：该句是否在「肯定地断言命盘带有 target_word」。

        返回 True 仅当满足：
        A) 句中有原盘锚点（非大运流年）+ 锚点与 target_word 之间无否定词；或
        B) needs_chart=True 且：①非动态岁运语境 ②非否定 ③非理论定义
           ④目标词附近存在归属暗示（有/带/透/藏...）。
        """
        t_pos = sent.find(target_word)
        if t_pos < 0:
            return False
        # A) 锚点 + 目标词 路径（锚点已不含大运/流年）
        for anchor in _ASSERT_ANCHORS:
            a_pos = sent.find(anchor)
            if a_pos < 0:
                continue
            if not _sentence_has_negative_between(sent, a_pos, t_pos):
                return True
        # B) needs_chart=True 无锚点路径：绑定命盘分析但句中没说盘/柱
        if needs_chart:
            # 动态岁运语境（大运/流年/年份数字/X年X运）→ 不是原盘断言
            if _sentence_in_dynamic_context(sent, target_word, t_pos):
                return False
            # 否定词在目标词附近
            wide_lo = max(0, t_pos - 6)
            wide_hi = min(len(sent), t_pos + len(target_word) + 6)
            if any(tok in sent[wide_lo:wide_hi] for tok in _NEG_TOKENS):
                return False
            # 理论定义？
            if _sentence_is_theory_definition(sent, target_word):
                return False
            # 必须有归属暗示，否则只是随口提及（如"遇到桃花年别急上头"中不是在说命盘带桃花）
            if not _ownership_hint_nearby(sent, t_pos, target_word):
                return False
            return True
        return False

    def _answer_makes_binding_assertion(target_word: str) -> bool:
        """判断回答是否在**肯定地断言**命盘事实层面带有 target_word（十神/神煞）。

        必须排除：
        - 否定句（没见/没有/不带/无/未/非 等，锚点与目标词之间出现）
        - 纯理论定义句（XX主XX/XX代表XX，且句中无锚点）
        """
        if target_word not in answer:
            return False
        for sent in _SENT_SPLIT.split(answer):
            if target_word not in sent:
                continue
            if _sentence_asserts_positive(sent, target_word):
                return True
        return False

    # ===== 十神：组合断言校验 =====
    _SHISHEN_PAIRS = [
        ("偏正财都有", "偏财", "正财"),
        ("正偏财同现", "正财", "偏财"),
        ("偏正财同现", "偏财", "正财"),
        ("正偏财都有", "正财", "偏财"),
        ("偏正财混杂", "偏财", "正财"),
        ("正偏财混杂", "正财", "偏财"),
        ("财星混杂", "偏财", "正财"),
        ("官杀混杂", "正官", "七杀"),
        ("杀官混杂", "七杀", "正官"),
        ("印星混杂", "正印", "偏印"),
        ("正偏印同现", "正印", "偏印"),
        ("偏正印同现", "偏印", "正印"),
        ("枭印同现", "偏印", "正印"),
    ]
    for phrase, need_a, need_b in _SHISHEN_PAIRS:
        if _answer_makes_binding_assertion(phrase):
            has_a = need_a in actual_shishen
            has_b = need_b in actual_shishen
            if not (has_a and has_b):
                missing = need_a if not has_a else need_b
                issues.append(f"排盘事实中无{missing}，回答却说「{phrase}」，与十神事实不符")

    # ===== 十神：单个归属断言校验 =====
    for name in _SHISHEN_NAMES:
        if name == "日主":
            continue
        if _answer_makes_binding_assertion(name) and name not in actual_shishen:
            issues.append(f"排盘事实中无「{name}」，回答却断言命盘带有，与十神事实不符")

    # ===== 神煞：存在性断言校验 =====
    for name in _SHENSHA_NAMES:
        if _answer_makes_binding_assertion(name) and name not in actual_shensha_all:
            issues.append(f"排盘事实中无「{name}」，回答却断言命盘带有，与神煞事实不符")

    # ===== 神煞：柱位归属断言校验 =====
    _pillar_names = [p.name for p in chart.pillars]
    for name in actual_shensha_all:
        if name not in answer:
            continue
        for sent in _SENT_SPLIT.split(answer):
            if name not in sent:
                continue
            for pn in _pillar_names:
                if name in actual_shensha_by_pillar.get(pn, set()):
                    continue
                if pn not in sent:
                    continue
                # 排除否定：如"日柱没有金舆"不算错误归属断言
                a_pos, t_pos = sent.find(pn), sent.find(name)
                if _sentence_has_negative_between(sent, a_pos, t_pos):
                    continue
                actual_pillar = (
                    "、".join(p for p in _pillar_names if name in actual_shensha_by_pillar.get(p, set()))
                    or "无"
                )
                issues.append(f"「{name}」属于{actual_pillar}，回答却关联到{pn}，与神煞事实不符")
                break

    return FactCheckResult(ok=not issues, issues=issues)
