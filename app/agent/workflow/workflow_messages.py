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
    # Worker 配置优先（专业 Worker 提供 length_rule 和 skip_facts）
    if worker is None:
        worker = WORKERS.get(intent.domain, WORKERS["general"])
    # needs_chart 覆盖 skip_facts：用户问"我命盘是不是XX"时需要注入命盘事实
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
        from app.db import user_data
        profile = user_data.get_chart_profile(
            getattr(ctx, "user_id", "") or "",
            ctx.birth_time,
            ctx.gender,
        )
        if not profile:
            return ""
        verified, disputed = user_data.get_chart_facts_for_llm(profile["id"], limit=6)
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
        HumanMessage(content=(
            f"【用户问题】\n{_wrap_user_input(user_prompt)}\n\n"
            f"【原回答】\n{raw_answer}\n\n"
            f"【发现的问题】\n" + "\n".join(f"- {issue}" for issue in checked.issues) + "\n\n"
            + (f"【正确排盘事实】\n{facts}\n\n" if facts else "")
            + (f"【合婚基础数据（系统规则）】\n{getattr(intent, 'match_basis', '')}\n\n"
               if getattr(intent, "match_basis", "") else "")
            + f"【可用规则】\n{knowledge}\n\n"
            "请输出修正后的最终回答。"
        )),
    ]


def invoke(chat_model, messages: list[BaseMessage]) -> str:
    """调用 LLM 生成回答，过滤 <think> 推理过程并去重。"""
    response = chat_model.invoke(messages)
    content = (getattr(response, "content", "") or "").strip()
    # 过滤 reasoning model 的 <think>...</think> 推理过程，避免重复显示
    content = clean_think_tags(content)
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
        f"{p.name}:{'、'.join(shensha_by_pillar.get(p.name, [])) or '—'}"
        for p in chart.pillars
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
        import re as _re
        m = _re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", birth_str)
        if m:
            by, bm, bd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            age = today.year - by - ((today.month, today.day) < (bm, bd))
            current_age = f"; 当前周岁: {age}岁"
    except Exception:
        pass
    return "\n".join([
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
    ])


def compact_facts(chart: BaziChart, intent: QuestionIntent) -> str:
    """命盘事实块（含合婚双盘时追加对方盘事实）。"""
    facts = fact_block(chart, intent)
    # 合婚双盘：追加对方命盘事实
    second = getattr(intent, "second_chart", None)
    if second is not None:
        facts += "\n\n【对方命盘事实】\n" + fact_block(second.chart, intent)
    return facts


def check_facts(answer: str, chart: BaziChart, other_chart: BaziChart | None = None) -> FactCheckResult:
    """校验回答中的四柱/大运/流年是否与系统排盘一致。

    other_chart 为合婚双盘时的对方命盘：同一干支若出现在任一张合法盘上即视为正确，
    避免把回答中对「对方/自己」各自正确的陈述误判为对方盘错误。
    """
    issues: list[str] = []
    year_to_gz: dict[int, str] = {item.year: item.ganzhi for item in chart.liunian}
    if other_chart is not None:
        for item in other_chart.liunian:
            year_to_gz.setdefault(item.year, item.ganzhi)
    # 大运干支白名单：匹配到的干支如果是某步大运干支，且上下文有大运关键词，则跳过流年校验
    dayun_gz_set: set[str] = {item.ganzhi for item in chart.dayun}
    if other_chart is not None:
        dayun_gz_set.update(item.ganzhi for item in other_chart.dayun)
    _DAYUN_KEYWORDS = ("大运", "交运", "交", "步入", "起运", "运柱", "走", "行运")
    for match in YEAR_GANZHI_RE.finditer(answer):
        year = int(match.group("year"))
        stated = match.group("ganzhi")
        expected = year_to_gz.get(year)
        if not expected or stated == expected:
            continue
        # 大运语境排除：年份+干支附近若明确在描述大运（出现大运关键词），则该干支视为大运而非流年，跳过校验。
            # 直接以「年份附近有大运关键词」语义判断，避免把大运干支误判为流年错误（不依赖 dayun 集合完整度）。
            start = max(0, match.start() - 18)
            end = min(len(answer), match.end() + 18)
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

    return FactCheckResult(ok=not issues, issues=issues)
