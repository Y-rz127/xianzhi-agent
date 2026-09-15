"""工作流消息拼装与事实校验（含双盘/合婚/Reflextion 修复消息）。

纯函数模块：供 XianzhiWorkflow Supervisor 委托调用，不持有实例状态。
从 app/agent/xianzhi_workflow.py 抽离（解耦：把"消息装配 + 事实校验"这一单一职责独立成模块），
行为与原内联实现完全一致。
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import replace as _dc_replace

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agent.core.base_agent import _wrap_user_input
from app.agent.prompts import (
    DOMAIN_PROCEDURE_TEMPLATE,
    DOMAIN_STEP_FOCUS,
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
    _dedupe_content,
)
from app.agent.workflow.workflow_workers import WORKERS
from app.core.config import settings as _settings
from app.core.logger import log
from app.domain.analysis_calc import (
    CONTROLS,
    GAN_WUXING,
)
from app.domain.chart_builder import (
    BaziChart,
    _compute_shensha,
    build_bazi_chart,
    parse_gender,
)
from app.domain.domain_brief import build_domain_brief
from app.domain.tables import (
    GAN_CHONG,
    GAN_HE,
)
from app.domain.yun_relations import (
    SuiRelations,
    current_sui,
    effective_target_years,
    format_sui_relations,
    liunian_relations,
    liuyue_line,
    relations_for,
    resolve_target_dayuns,
)
from app.tools.text_clean import clean_think_tags, strip_user_input_boundary

# 工作流生成/修复产出长文本（含思维链），60s 默认超时不够，单独放宽
_WORKFLOW_LLM_TIMEOUT = _settings.workflow_llm_timeout

# fact_block 注入的流年行硬上限（防长跨度指认时 prompt 爆炸）
_MAX_LIUNIAN_LINES = 20


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
    # 分析规程：仅注入领域简报时追加（闲聊等零注入场景不塞规程）
    if _build_domain_brief_inject(ctx.chart, intent):
        system += "\n\n" + DOMAIN_PROCEDURE_TEMPLATE.format(
            领域=worker.label, 聚焦点=DOMAIN_STEP_FOCUS.get(intent.domain, "")
        )
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
        "岁运关系一律引用【岁运关系】段，不得自行编排天克地冲/岁运并临；流月干支以该段流月行为准。"
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
    skip = worker.skip_facts and not intent.needs_chart
    facts = "" if skip else compact_facts(ctx.chart, intent)
    # Reflextion 改写器：带上 Worker 专属断法，确保修复后仍符合领域规范
    sys_content = reflect_sysprompt

    if worker.expertise_prompt:
        preamble = WORKER_PREAMBLE_TEMPLATE.format(领域=worker.label)
        sys_content += "\n" + preamble + "\n" + worker.expertise_prompt
    # 分析规程与生成路径同 gate：注入领域简报时追加
    if not skip and _build_domain_brief_inject(ctx.chart, intent):
        sys_content += "\n\n" + DOMAIN_PROCEDURE_TEMPLATE.format(
            领域=worker.label, 聚焦点=DOMAIN_STEP_FOCUS.get(intent.domain, "")
        )
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
    content = strip_user_input_boundary(content)
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


def _gan_relations_line(chart: BaziChart) -> str:
    """天干关系：干合、干冲、干克、三奇（仅统计四柱天干内的关系）。"""
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
    parts = []
    if gan_he:
        parts.append(f"合={'、'.join(gan_he)}")
    if gan_chong:
        parts.append(f"冲={'、'.join(gan_chong)}")
    if gan_ke:
        parts.append(f"克={'、'.join(gan_ke)}")
    if sanqi:
        parts.append(f"三奇={'、'.join(sanqi)}")
    return "；".join(parts) if parts else "—"


def _shensha_by_pillar_line(chart: BaziChart) -> str:
    """神煞按柱分组注入文本（与前端表格展示一致）。"""
    shensha_all = _compute_shensha(chart.pillars, parse_gender(chart.birth.gender))
    shensha_by_pillar: dict[str, list[str]] = {}
    for _s in shensha_all:
        shensha_by_pillar.setdefault(_s.get("pillar") or "全局", []).append(_s["name"])
    return "\n".join(
        f"  {p.name}:{'、'.join(shensha_by_pillar.get(p.name, [])) or '—'}" for p in chart.pillars
    )


def _dayun_lines(chart: BaziChart, intent: QuestionIntent) -> list[str]:
    """大运每步一行；目标大运优先放前，其余按年龄顺序（便于 LLM 按行命中）。"""
    dayun = list(chart.dayun)
    hit_idxs = {d.index for d in resolve_target_dayuns(chart, intent.target_dayun)}
    if hit_idxs:
        dayun.sort(key=lambda d: (0 if d.index in hit_idxs else 1, d.index))
    return [
        f"  {item.ganzhi}({item.shishen_gan}) {item.start_year}-{item.end_year} {item.start_age}-{item.end_age}岁"
        f"{'  ← 目标' if item.index in hit_idxs else ''}"
        f"\n    藏干[{'、'.join(item.hidden_stems) or '—'}] 副星[{'、'.join(item.shishen_zhi) or '—'}]"
        f"\n    星运[{item.changsheng or '—'}] 神煞[{'、'.join(s['name'] for s in item.shensha) or '—'}]"
        for item in dayun
    ]


def _liunian_lines(chart: BaziChart, intent: QuestionIntent, today: _dt.date) -> list[str]:
    """流年每年一行：显式年份 ∪ 大运换算年份，缺失时按需补建（_MAX_LIUNIAN_LINES 防爆）。"""
    years = effective_target_years(chart, intent.target_years, intent.target_dayun)
    if years:
        years = years[:_MAX_LIUNIAN_LINES]
        liunian_items = [item for item in chart.liunian if item.year in set(years)]
        missing_years = sorted(set(years) - {item.year for item in liunian_items})
        if missing_years:
            ext_chart = build_bazi_chart(
                chart.birth.solar,
                chart.birth.gender,
                sect=chart.birth.sect,
                yun_sect=chart.birth.yun_sect,
                liunian_start_year=min(missing_years),
                liunian_years=max(missing_years) - min(missing_years) + 1,
            )
            liunian_items.extend(item for item in ext_chart.liunian if item.year in set(missing_years))
            liunian_items.sort(key=lambda x: x.year)
    else:
        current_year = today.year
        liunian_items = [item for item in chart.liunian if current_year <= item.year <= current_year + 9]
        if not liunian_items:
            liunian_items = chart.liunian[:4]
    return [
        f"  {item.year}年:{item.ganzhi}({item.shishen_gan}) {item.age}虚岁 所在大运:{item.dayun_ganzhi or '-'}"
        f"\n    藏干[{'、'.join(item.hidden_stems) or '—'}] 副星[{'、'.join(item.shishen_zhi) or '—'}]"
        f"\n    星运[{item.changsheng or '—'}] 神煞[{'、'.join(s['name'] for s in item.shensha) or '—'}]"
        for item in liunian_items
    ]


def _current_age_text(chart: BaziChart, today: _dt.date) -> str:
    """当前周岁文本，避免 LLM 自行推算出错（解析失败返回空串）。"""
    birth_str = chart.birth.solar or ""
    try:
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", birth_str)
        if m:
            by, bm, bd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            age = today.year - by - ((today.month, today.day) < (bm, bd))
            return f"; 当前周岁: {age}岁"
    except Exception:
        pass
    return ""


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
    current_age = _current_age_text(chart, today)
    return "\n".join(
        [
            f"当前日期: {today.year}年{today.month}月{today.day}日{current_age}",
            f"出生: {chart.birth.solar}; 性别: {chart.birth.gender}; 农历: {chart.birth.lunar}; 生肖: {chart.birth.shengxiao}",
            f"四柱: {pillars}",
            f"四柱详述:\n{pillar_detail}",
            "神煞（按柱）:",
            _shensha_by_pillar_line(chart),
            f"日主: {chart.wuxing.day_master}({chart.wuxing.day_master_wuxing}); 强弱: {chart.wuxing.strength}; 分数: {chart.wuxing.strength_score}",
            f"特殊格局: {chart.wuxing.special_pattern or '无'}",
            f"五行权重: {chart.wuxing.counts}; 最旺: {chart.wuxing.strongest}; 最弱: {chart.wuxing.weakest}",
            f"用神提示: {chart.wuxing.useful_hint}",
            f"十神结构: {chart.analysis.ten_gods}; 透干: {chart.analysis.exposed_stems or '-'}; 通根: {chart.analysis.rooted_stems or '-'}",
            f"天干关系: {_gan_relations_line(chart)}",
            f"地支关系: 合={chart.analysis.combinations or '-'}; 冲={chart.analysis.clashes or '-'}; 害={chart.analysis.harms or '-'}; 破={chart.analysis.breaks or '-'}; 刑={chart.analysis.punishments or '-'}; 三合/三会={chart.analysis.three_assemblies or '-'}",
            f"调候: 月令{chart.analysis.season}; {chart.analysis.adjustment}",
            f"判断置信度: {chart.analysis.confidence}",
            f"起运: {chart.start_yun['startDate']} 起; {chart.start_yun['direction']}; 起运年龄 {chart.start_yun['startYear']}年{chart.start_yun['startMonth']}月{chart.start_yun['startDay']}日",
            "大运:",
            *_dayun_lines(chart, intent),
            "相关流年:",
            *(_liunian_lines(chart, intent, today) or ["  （未指定）"]),
            "口径: " + "；".join(chart.warnings),
        ]
    )


def _build_domain_brief_inject(chart: BaziChart, intent: QuestionIntent) -> str:
    """领域简报注入文本（needs_chart 且有投影映射时非空）。"""
    if not intent.needs_chart:
        return ""
    return build_domain_brief(chart, intent.domain)


def build_sui_section(chart: BaziChart, intent: QuestionIntent) -> str:
    """岁运关系注入文本（generate 与 Reviewer 共用，保证同源一致）。"""
    today = _dt.date.today()
    items: list[SuiRelations] = []
    for d in resolve_target_dayuns(chart, intent.target_dayun):
        if len(d.ganzhi) == 2:
            items.append(
                relations_for(
                    chart,
                    dayun_ganzhi=d.ganzhi,
                    label=f"第{d.index}步{d.ganzhi}({d.start_year}-{d.end_year})",
                )
            )
    # 童限期（未交大运）：指认「当前」时 chart.dayun 无步骤覆盖今年，resolve 返回空，
    # 以当年小运作岁柱占位，避免岁运关系整段落空。
    if not items and (intent.target_dayun or "").strip() in ("当前", "現在"):
        gz, is_tongxian = current_sui(chart)
        if is_tongxian and len(gz) == 2:
            items.append(relations_for(chart, liunian_ganzhi=gz, label=gz, is_tongxian=True))
    # 流年指认时自动推导所在大运，注入大运×原局关系（否则大模型只知流年所在大运干支，
    # 却不知该大运与原局的合/冲/害/刑/引动等关系）
    # 无指认时也注入当前大运×原局关系，否则开放性问题（如"啥时候遇到正缘"）完全无岁运关系
    if not items:
        target_years_set = set(intent.target_years)
        if not target_years_set:
            cur_dy = [d for d in chart.dayun if d.start_year <= today.year <= d.end_year]
            if cur_dy:
                target_years_set = {today.year}
        seen_gz = set()
        for ln in chart.liunian or []:
            if ln.year in target_years_set and len(ln.dayun_ganzhi or "") == 2:
                gz = ln.dayun_ganzhi
                if gz not in seen_gz:
                    seen_gz.add(gz)
                    d = next((d for d in chart.dayun if d.ganzhi == gz), None)
                    label = f"第{d.index}步{gz}({d.start_year}-{d.end_year})" if d else gz
                    items.append(relations_for(chart, dayun_ganzhi=gz, label=label))
    # 流年关系：明确点名年份优先，大运区间换算年份补足剩余名额（上限约束注入长度）
    explicit = sorted(set(intent.target_years))
    derived = [
        y
        for y in effective_target_years(chart, intent.target_years, intent.target_dayun)
        if y not in set(explicit)
    ]
    # 岁运关系流年上限：取实际需要的流年数，不超过 _MAX_LIUNIAN_LINES 防 prompt 爆炸
    sui_max = min(len(explicit) + len(derived), _MAX_LIUNIAN_LINES)
    target_years_sui = (explicit + derived)[:sui_max]
    # 无指认时补入今年~今年+9年的流年关系（10年），否则开放性问题完全无流年关系
    if not target_years_sui and not intent.target_dayun:
        target_years_sui = sorted(
            {item.year for item in chart.liunian if today.year <= item.year <= today.year + 9}
        )[:10]
    # chart.liunian 可能不够覆盖目标年份，按需补建
    sui_chart = chart
    missing_sui = sorted(set(target_years_sui) - {item.year for item in chart.liunian})
    if missing_sui:
        ext = build_bazi_chart(
            chart.birth.solar,
            chart.birth.gender,
            sect=chart.birth.sect,
            yun_sect=chart.birth.yun_sect,
            liunian_start_year=min(missing_sui),
            liunian_years=max(missing_sui) - min(missing_sui) + 1,
        )
        merged_liunian = list(chart.liunian) + [item for item in ext.liunian if item.year in set(missing_sui)]
        merged_liunian.sort(key=lambda x: x.year)
        sui_chart = _dc_replace(chart, liunian=merged_liunian)
    items += liunian_relations(sui_chart, target_years_sui)
    parts = [format_sui_relations(items)]
    known = {item.year for item in chart.liunian}
    # 流年指认：每一年展开 12 流月（最多 2 年，避免 prompt 爆炸）
    # 大运指认不展开流月——大运问的是 10 年格局，流年关系已覆盖，月级别仅流年指认时才注入
    for year in intent.target_years[:2]:
        if year in known:
            parts.append(liuyue_line(chart, year))
    return "\n".join(p for p in parts if p)


# 十神 / 神煞名表（单一事实源）：check_facts 的存在性与归属校验、修复前后事实差异比对共用。

def compact_facts(chart: BaziChart, intent: QuestionIntent) -> str:
    """命盘事实块（含合婚双盘、领域投影、岁运关系）。"""
    facts = fact_block(chart, intent)
    # 合婚双盘：追加对方命盘事实
    second = getattr(intent, "second_chart", None)
    if second is not None:
        facts += "\n\n【对方命盘事实】\n" + fact_block(second.chart, intent)
    # 领域投影 + 岁运关系：仅 needs_chart 且该领域有简报时注入
    brief = _build_domain_brief_inject(chart, intent)
    if brief:
        facts += f"\n\n【本领域盘面要素 · {intent.label}】\n{brief}"
        sui = build_sui_section(chart, intent)
        if sui:
            facts += f"\n\n【岁运关系】\n{sui}"
    return facts


