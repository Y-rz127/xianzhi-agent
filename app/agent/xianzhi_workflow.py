"""基于先知图表的确定性工作流。

这是一个轻量级的状态机式编排层。它将复杂的图表信息保留在LLM之外，让模型专注于解读和自然对话。
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.domain.bazi_engine import BaziChart, build_bazi_chart, format_fact_context
from app.logger import log
from app.rag.vector_store import knowledge_base


def _dedupe_content(content: str) -> str:
    """检测并移除完全重复的内容（推理模型 think 块泄漏的兜底）。"""
    content = content.strip()
    if len(content) < 100:
        return content
    mid = len(content) // 2
    first_half = content[:mid].strip()
    second_half = content[mid:].strip()
    if first_half == second_half and len(first_half) > 50:
        log.warning("检测到 LLM 输出内容重复，已去重（长度 {}）", len(first_half))
        return first_half
    return content


GANZHI_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")
YEAR_GANZHI_RE = re.compile(r"(?P<year>\d{4})年[^。；;，,、\n]{0,12}(?P<ganzhi>[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])")


DOMAIN_KEYWORDS = {
    "career": ("事业", "工作", "职业", "跳槽", "换工作", "升职", "创业", "老板", "岗位", "offer"),
    "wealth": ("财运", "赚钱", "收入", "投资", "生意", "偏财", "正财", "破财", "资产"),
    "love": ("感情", "恋爱", "桃花", "对象", "复合", "分手", "脱单"),
    "marriage": ("婚姻", "结婚", "离婚", "配偶", "另一半", "合婚"),
    "health": ("健康", "身体", "疾病", "失眠", "焦虑", "病"),
    "liunian": ("今年", "明年", "流年", "大运", "运势", "哪年", "年份", "最近"),
    "study": ("学习", "考试", "考研", "升学", "证书"),
    "theory": ("是什么", "什么意思", "寓意", "解释", "含义", "什么是", "讲讲", "说说",
               "空亡", "桃花", "羊刃", "华盖", "七杀", "食神", "伤官", "正官", "偏印",
               "用神", "格局", "纳音", "神煞", "刑冲合害", "伏吟", "反吟", "禄神",
               "调候", "通根", "透干", "墓库", "长生", "帝旺", "死绝"),
    "chitchat": ("你好", "在吗", "谢谢", "辛苦", "早上好", "晚上好", "晚安",
                 "最近怎么样", "吃饭了吗", "在干嘛", "无聊", "心情", "压力大",
                 "烦", "累", "开心", "难过", "生日快乐", "新年好"),
}

DOMAIN_LABELS = {
    "career": "事业工作",
    "wealth": "财运收入",
    "love": "恋爱感情",
    "marriage": "婚姻关系",
    "health": "健康状态",
    "liunian": "大运流年",
    "study": "学习考试",
    "theory": "术语理论",
    "chitchat": "闲聊问候",
    "general": "综合咨询",
}

DOMAIN_RULE_QUERIES = {
    "career": ("八字事业 官杀 印星 食伤 大运流年", "工作变动 跳槽 流年 大运 命理"),
    "wealth": ("八字财运 正财 偏财 食伤 生财 大运", "破财 投资 流年 财星 命理"),
    "love": ("八字感情 桃花 配偶星 合冲 流年", "恋爱复合 八字 大运 流年"),
    "marriage": ("八字婚姻 配偶宫 夫妻星 合冲刑害", "结婚年份 大运流年 婚姻 命理"),
    "health": ("八字健康 五行寒暖燥湿 失衡", "健康 流年 冲克 命理"),
    "liunian": ("大运流年 作用关系 流年与原局", "流年 干支 立春 大运"),
    "study": ("八字学习考试 印星 食伤 官星", "考试 升学 大运流年 命理"),
    "theory": ("术语解释 天干地支 五行 十神 用神", "空亡 桃花 神煞 禄神 含义",
               "古籍 子平真诠 渊海子平 滴天髓 术语"),
    "chitchat": (),
    "general": ("八字 用神 喜忌 大运流年 综合分析",),
}


@dataclass(frozen=True)
class QuestionIntent:
    domain: str
    label: str
    target_years: list[int] = field(default_factory=list)
    wants_report: bool = False
    confidence: float = 0.5


@dataclass
class WorkflowChartContext:
    birth_time: str
    gender: str
    sect: int
    yun_sect: int
    chart: BaziChart


@dataclass(frozen=True)
class FactCheckResult:
    ok: bool
    issues: list[str] = field(default_factory=list)


# ============================================================
# 多 Agent 协作架构：Supervisor(本类) + 专业 Worker + Reviewer
# 参考 学习资料/智能体开发笔记/16_多Agent协作
#   - WorkerResult 最小结果协议（多Agent状态边界.md）
#   - 专业 Worker 按领域拆分断法 prompt + 专属检索 query
#   - Reviewer 独立交叉校验（事实 + 古籍真实性 + 合规）
# ============================================================


@dataclass(frozen=True)
class WorkerResult:
    """Worker 返回的最小结果协议（不返回完整对话历史，避免上下文爆炸）。"""
    status: str  # "done" | "blocked" | "failed"
    summary: str  # 断语结论
    evidence: list[str] = field(default_factory=list)  # 古籍引用 + 检索片段
    risks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DomainWorker:
    """领域 Worker 配置：专属断法 prompt + 额外检索 query。

    Supervisor（XianzhiWorkflow.answer）按 intent.domain 分派给对应 Worker。
    Worker 只持有"专业领域知识"，执行逻辑复用 Supervisor 的 _retrieve_rules / _build_messages / _invoke。
    """
    domain: str
    label: str
    expertise_prompt: str  # 追加到通用 system prompt 末尾的领域断法规则
    extra_queries: tuple[str, ...] = ()  # 叠加到 DOMAIN_RULE_QUERIES 之外的领域专属检索
    length_rule: str = "默认控制在3-6段，先结论后依据。"
    skip_facts: bool = False  # theory/chitchat 跳过命盘事实注入


# 专业 Worker 注册表（Supervisor 按 domain 查表分派）
WORKERS: dict[str, DomainWorker] = {
    "career": DomainWorker(
        domain="career",
        label="事业工作",
        expertise_prompt=(
            "【事业专项断法】\n"
            "- 官杀为事业主星：正官主稳定公职、体制内；七杀主开创、变动、武职、创业\n"
            "- 印星为权力依托：印星生扶则职位稳、有靠山；印星受克则失权、降职\n"
            "- 食伤为才干技能：食伤生财凭技术赚钱；食伤制杀能压住压力、掌权\n"
            "- 大运流年遇官杀旺地、印星生扶，多为升职/创业良机\n"
            "- 官杀混杂、伤官见官、劫财夺财，多主事业动荡、口舌是非\n"
            "- 判断事业层次看格局清浊：清格主贵，浊格主劳碌"
        ),
        extra_queries=("官星 印星 食伤 事业 升职 断法", "伤官见官 官杀混杂 事业动荡 命理"),
    ),
    "wealth": DomainWorker(
        domain="wealth",
        label="财运收入",
        expertise_prompt=(
            "【财运专项断法】\n"
            "- 正财主工薪稳定收入，偏财主投资、横财、经营之财\n"
            "- 食伤生财为正道：有食伤生财则财源绵长；财星无源则财来财去\n"
            "- 财库主积蓄：辰戌丑未为四库，财入库主能守财；财库逢冲则破财\n"
            "- 比劫夺财：比劫旺则破财、分财，须见官杀制或食伤化\n"
            "- 身旺财旺为富格，身弱财旺则富屋贫人，反主求财辛苦\n"
            "- 大运流年走财旺之乡、食伤生扶之地，主进财；走比劫、印星夺食之地主破财"
        ),
        extra_queries=("正财 偏财 食伤生财 财库 断法", "比劫夺财 破财 身弱财旺 命理"),
    ),
    "love": DomainWorker(
        domain="love",
        label="恋爱感情",
        expertise_prompt=(
            "【感情桃花专项断法】\n"
            "- 男以财星为配偶星，女以官杀为配偶星；配偶星透干有力、得位则缘分稳\n"
            "- 日支为配偶宫：日支坐财官印多为得配偶助力；坐比劫羊刃主争合、分离\n"
            "- 桃花星（子午卯酉）旺相主异性缘好；桃花逢冲合多主动婚恋\n"
            "- 红艳、咸池主感情纠葛；孤辰寡宿主孤独\n"
            "- 大运流年遇配偶星、桃花、合入日支，多为动婚恋之期\n"
            "- 配偶星被冲合化、坐比劫，多主感情波折、第三者"
        ),
        extra_queries=("桃花 配偶星 日支 感情 断法", "咸池 红艳 孤辰寡宿 感情 命理"),
    ),
    "marriage": DomainWorker(
        domain="marriage",
        label="婚姻关系",
        expertise_prompt=(
            "【婚姻专项断法】\n"
            "- 配偶宫（日支）宜静不宜动：逢冲合刑害则婚姻动荡\n"
            "- 男看财星、女看官杀为夫妻星：透干有气、不被刑冲为吉\n"
            "- 夫妻星得位（月支/日支）为正配；偏位或他柱多为晚婚或再婚\n"
            "- 婚姻看大运流年引动：逢合入配偶宫、夫妻星透出，多为动婚之期\n"
            "- 比劫成群夺财（男）、伤官见官（女）多主克配偶、离婚\n"
            "- 古籍依据：《滴天髓》论婚姻、《三命通会》论夫妻宫"
        ),
        extra_queries=("配偶宫 夫妻星 合冲刑害 婚姻 断法", "克配偶 离婚 晚婚 命理 古籍"),
    ),
    "health": DomainWorker(
        domain="health",
        label="健康状态",
        expertise_prompt=(
            "【健康专项断法】\n"
            "- 五行失衡主病：木主肝胆、火主心血、土主脾胃、金主肺肠、水主肾膀胱\n"
            "- 寒暖燥湿失宜主病：冬生水旺无火调候主寒证；夏生火旺无水润局主燥证\n"
            "- 日主受克太过主病：金多克木主肝疾，火多克金主肺疾\n"
            "- 七杀攻身、羊刃冲合，多主外伤、手术、急症\n"
            "- 刑冲入本命盘的宫位，对应脏腑易病\n"
            "合规提示：命理健康参考仅供参考，涉及重病必须劝导就医，不替代医疗诊断。"
        ),
        extra_queries=("五行失衡 寒暖燥湿 疾病 健康 断法", "七杀攻身 羊刃 外伤 手术 命理"),
    ),
    "study": DomainWorker(
        domain="study",
        label="学习考试",
        expertise_prompt=(
            "【学业专项断法】\n"
            "- 印星主学业文凭：印星为用神、生扶日主则学业有成\n"
            "- 食伤主才智发挥：食伤旺相则思维敏捷、善表达\n"
            "- 官星主功名：官印相生主考试顺利、得功名\n"
            "- 文昌星、华盖主聪明好学；空亡华盖主孤高\n"
            "- 大运流年走印星、官星、食伤生扶之地，主考试升学之机\n"
            "- 印星受克、官杀混杂，多主学业分心、考试不利"
        ),
        extra_queries=("印星 食伤 官星 文昌 学习考试 断法",),
    ),
    "liunian": DomainWorker(
        domain="liunian",
        label="大运流年",
        expertise_prompt=(
            "【大运流年专项断法】\n"
            "- 大运看十年大势，流年看一年吉凶；大运定基调，流年定应期\n"
            "- 大运与原局关系：生扶用神则吉，克伐用神则凶\n"
            "- 流年与大运、原局形成合冲刑害，多主当年重大事件\n"
            "- 太岁当头、岁运并临，主变动重大\n"
            "- 流年透出配偶星、财星、官星，多主当年婚恋、进财、升职\n"
            "- 流年走比劫、伤官、七杀攻身，主破财、口舌、疾病\n"
            "- 立春换年口径：流年以立春为界，不以正月初一"
        ),
        extra_queries=("大运流年 作用关系 流年断法 应期", "太岁 岁运并临 立春换年 命理"),
    ),
    "theory": DomainWorker(
        domain="theory",
        label="术语理论",
        expertise_prompt=(
            "【术语解释规范】\n"
            "- 术语定义必须以知识库检索内容为准，不得自行编造\n"
            "- 解释顺序：先给标准定义 → 再给命理含义 → 必要时引古籍原文\n"
            "- 古籍引用格式：「《典籍名》原文：XXX」，简短自然嵌入\n"
            "- 涉及多流派解释时，说明主流观点与分歧\n"
            "- 不结合具体命盘断事，只做术语理论说明"
        ),
        length_rule="术语解释≤200字，先给结论，后给依据，必要时引典籍原文。",
        skip_facts=True,
    ),
    "chitchat": DomainWorker(
        domain="chitchat",
        label="闲聊问候",
        expertise_prompt="",
        length_rule="闲聊1-3句，≤150字，像朋友聊天自然回应。",
        skip_facts=True,
    ),
    "general": DomainWorker(
        domain="general",
        label="综合咨询",
        expertise_prompt="",
    ),
}


def classify_question(text: str, today: _dt.date | None = None) -> QuestionIntent:
    today = today or _dt.date.today()
    years = sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", text)})
    if "今年" in text:
        years.append(today.year)
    if "明年" in text:
        years.append(today.year + 1)
    years = sorted(set(years))

    best_domain = "general"
    best_score = 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_domain = domain
            best_score = score

    # 闲聊场景优先级提升：含强闲聊信号词时，直接判定为 chitchat，避免被 liunian 的"最近"等词抢走
    CHITCHAT_STRONG = ("哈哈","你好", "在吗", "谢谢", "辛苦", "早上好", "晚上好", "晚安",
                       "吃饭了吗", "在干嘛", "生日快乐", "新年好")
    if any(w in text for w in CHITCHAT_STRONG) and not years:
        best_domain = "chitchat"

    if years and best_domain == "general":
        best_domain = "liunian"

    wants_report = any(word in text for word in ("完整报告", "详细报告", "全面分析", "完整分析", "从头到尾"))
    confidence = min(0.95, 0.45 + best_score * 0.18 + (0.15 if years else 0))
    return QuestionIntent(
        domain=best_domain,
        label=DOMAIN_LABELS.get(best_domain, "综合咨询"),
        target_years=years,
        wants_report=wants_report,
        confidence=round(confidence, 2),
    )


def build_chart_context(birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1) -> WorkflowChartContext:
    chart = build_bazi_chart(birth_time, gender, sect=sect, yun_sect=yun_sect, dayun_count=10, liunian_years=8)
    return WorkflowChartContext(
        birth_time=birth_time,
        gender=gender,
        sect=sect,
        yun_sect=yun_sect,
        chart=chart,
    )


class ReviewerWorker:
    """Reviewer 独立审核员：对 Worker 产出做三重交叉校验。

    参考 学习资料/16_多Agent协作/SupervisorWorker协作说明.md 的 Review Worker 角色。
    独立于 Worker，用不同视角审视，避免 Worker 自己的盲区。

    三重校验：
    1. 事实校验：四柱/大运/流年/起运是否与系统排盘一致（复用 check_facts）
    2. 古籍真实性：回答中「《XXX》原文：」标注的古籍是否真的在检索结果中出现（防杜撰）
    3. 合规校验：扫描生死/赌博/符咒/堕胎等红线关键词

    不通过 → 触发 Reflextion 回退修复。
    """

    # 合规红线关键词（命中即需人工提示，不直接拒答）
    COMPLIANCE_RISKS = (
        "死期", "寿命", "何时死", "什么时候死", "堕胎择时", "择日堕胎",
        "符咒", "改运", "改命", "诅咒", "下蛊", "邪术",
        "买彩票", "赌博必赢", "包赚", "稳赚不赔",
    )

    # 古籍真实性校验：抽取回答中「《XXX》原文：...」标注
    ANCIENT_CITATION_RE = re.compile(r"《[^》]{1,12}》[^。；;\n]{0,6}原文[：:]")

    def review(self, answer: str, chart: BaziChart, knowledge: str, fact_checker) -> FactCheckResult:
        """对 Worker 产出做三重校验。

        Args:
            answer: Worker 生成的回答
            chart: 系统排盘事实
            knowledge: Worker 检索到的知识片段（用于古籍真实性比对）
            fact_checker: 复用 XianzhiWorkflow.check_facts 方法
        """
        issues: list[str] = []

        # 1) 事实校验（四柱/大运/流年）
        fact_result = fact_checker(answer, chart)
        issues.extend(fact_result.issues)

        # 2) 古籍真实性校验：标注了「《XXX》原文」的引用必须在检索知识中出现
        citations = self.ANCIENT_CITATION_RE.findall(answer)
        if citations and knowledge and "未检索到相关知识" not in knowledge and "闲聊场景" not in knowledge:
            # 提取检索知识里的书名（粗粒度比对）
            cited_books = set()
            for m in re.finditer(r"《([^》]{1,12})》", knowledge):
                cited_books.add(m.group(1))
            # 比对回答中标注的书是否在检索结果里
            for citation in citations:
                book_match = re.match(r"《([^》]{1,12})》", citation)
                if book_match:
                    book = book_match.group(1)
                    # 允许常见经典古籍直接通过（知识库已收录，检索可能未命中但属合理引用）
                    classic_books = {"渊海子平", "子平真诠", "滴天髓", "穷通宝鉴", "三命通会", "神峰通考", "千里命稿"}
                    if book not in cited_books and book not in classic_books:
                        issues.append(f"引用《{book}》原文未在检索结果中出现，疑似杜撰古籍")

        # 3) 合规红线扫描
        risks_found = [kw for kw in self.COMPLIANCE_RISKS if kw in answer]
        if risks_found:
            issues.append(f"命中合规红线关键词：{','.join(risks_found)}；若涉及凶险断言需劝导寻求专业帮助")

        return FactCheckResult(ok=not issues, issues=issues)


class XianzhiWorkflow:
    """Supervisor：意图分类 → 分派专业 Worker → Reviewer 审核 → Reflextion 修复。

    架构参考 学习资料/智能体开发笔记/16_多Agent协作：
    - Supervisor（本类）：决策、分派、验收、合并结果
    - 专业 Worker（WORKERS 注册表）：按领域专注单一断法
    - Reviewer（ReviewerWorker）：独立交叉校验
    """

    def __init__(self, chat_model: BaseChatModel):
        self.chat_model = chat_model
        self._reviewer = ReviewerWorker()
        self._graph = None
        try:
            from app.agent.xianzhi_langgraph import create_xianzhi_graph

            self._graph = create_xianzhi_graph(self)
        except Exception as e:
            log.debug("LangGraph workflow unavailable: {}", e)

    def answer(
        self,
        user_prompt: str,
        chart_context: WorkflowChartContext,
        history: list[BaseMessage] | None = None,
    ) -> str:
        intent = classify_question(user_prompt)
        if self._graph is not None:
            result = self._graph.invoke({
                "user_prompt": user_prompt,
                "chart_context": chart_context,
                "history": history or [],
                "intent": intent,
            })
            final = (result.get("final_answer") or "").strip()
            if final:
                return final

        # ===== Supervisor 分派阶段 =====
        worker = WORKERS.get(intent.domain, WORKERS["general"])
        log.info("[Supervisor] 意图={} 置信度={} → 分派给 {} Worker",
                 intent.label, intent.confidence, worker.label)

        chart_context = self._extend_chart_if_needed(chart_context, intent)

        # ===== Worker 执行阶段 =====
        knowledge = self._retrieve_rules(intent, chart_context, worker)
        messages = self._build_messages(user_prompt, intent, chart_context, knowledge, history or [], worker)
        raw_answer = self._invoke(messages)

        # ===== Reviewer 审核阶段（三重校验：事实+古籍真实性+合规） =====
        review = self._reviewer.review(raw_answer, chart_context.chart, knowledge, self.check_facts)
        if review.ok:
            log.info("[Reviewer] {} Worker 产出通过三重校验", worker.label)
            return raw_answer
        log.warning("[Reviewer] {} Worker 产出未通过校验，触发 Reflextion 修复: {}",
                    worker.label, review.issues)

        # ===== Reflextion 回退修复 =====
        repair_messages = self._build_repair_messages(
            raw_answer, review, user_prompt, intent, chart_context, knowledge, worker
        )
        repaired = self._invoke(repair_messages)
        repaired_review = self._reviewer.review(repaired, chart_context.chart, knowledge, self.check_facts)
        if repaired_review.ok:
            log.info("[Reflextion] {} Worker 修复后通过校验", worker.label)
            return repaired
        log.warning("[Reflextion] {} Worker 修复后仍未通过，附加口径说明", worker.label)
        return repaired.rstrip() + "\n\n口径校验：本次回答以系统排盘为准；" + "；".join(repaired_review.issues)

    def _extend_chart_if_needed(self, ctx: WorkflowChartContext, intent: QuestionIntent) -> WorkflowChartContext:
        if not intent.target_years:
            return ctx
        known_years = {item.year for item in ctx.chart.liunian}
        if all(year in known_years for year in intent.target_years):
            return ctx
        start = min(min(intent.target_years), _dt.date.today().year)
        end = max(max(intent.target_years), _dt.date.today().year)
        chart = build_bazi_chart(
            ctx.birth_time,
            ctx.gender,
            sect=ctx.sect,
            yun_sect=ctx.yun_sect,
            dayun_count=12,
            liunian_start_year=start,
            liunian_years=max(1, end - start + 1),
        )
        return WorkflowChartContext(ctx.birth_time, ctx.gender, ctx.sect, ctx.yun_sect, chart)

    def _retrieve_rules(self, intent: QuestionIntent, ctx: WorkflowChartContext, worker: DomainWorker | None = None) -> str:
        # 闲聊场景：最优先短路，不依赖知识库，让 LLM 自然回应
        if intent.domain == "chitchat":
            return "（闲聊场景，无需命理知识检索）"
        if not knowledge_base.ready:
            return "（知识库未就绪，本轮只使用结构化排盘事实与内置命理口径。）"
        # 1) 领域规则 query（来自 DOMAIN_RULE_QUERIES）
        queries = list(DOMAIN_RULE_QUERIES.get(intent.domain, DOMAIN_RULE_QUERIES["general"]))
        # 1.5) Worker 专属额外检索 query（叠加在领域规则之后，提升专业深度）
        if worker and worker.extra_queries:
            queries.extend(worker.extra_queries)
        # 2) 日主 + 强弱个性化 query
        day_master = ctx.chart.wuxing.day_master or ""
        strength = ctx.chart.wuxing.strength or ""
        queries.append(f"{intent.label} {day_master}日主 {strength} 大运流年")
        # 3) 命例查相似结构：根据日主强弱和十神倾向构造
        if day_master and strength:
            if "旺" in strength or "强" in strength:
                queries.append(f"{day_master}日主身旺 命例 典型命局 古籍")
            elif "弱" in strength or "衰" in strength:
                queries.append(f"{day_master}日主身弱 命例 典型命局 古籍")
        # 4) 按领域补古籍检索 query
        ancient_query_map = {
            "career": "渊海子平 论官杀 事业 官星",
            "wealth": "渊海子平 论财 财星 食伤生财",
            "marriage": "滴天髓 论婚姻 配偶宫 古籍",
            "health": "三命通会 论疾病 五行 健康古籍",
            "love": "子平真诠 论桃花 感情 古籍",
        }
        ancient_q = ancient_query_map.get(intent.domain)
        if ancient_q:
            queries.append(ancient_q)
        # 5) 断法体系 query（针对具体断事方向）
        duanfa_query_map = {
            "health": "健康伤病 断法 五行失衡 疾病",
            "wealth": "贫富层次 财星 断法 命理",
            "career": "事业财运 官星 印星 断法",
            "marriage": "婚恋关系 配偶宫 断法 命理",
            "love": "婚恋关系 桃花 断法 命理",
        }
        duanfa_q = duanfa_query_map.get(intent.domain)
        if duanfa_q:
            queries.append(duanfa_q)

        # 上限提到 5 条 query（原本 3 条太少，覆盖不到命例/古籍/断法）
        final_queries = queries[:5]
        log.info("[workflow检索] 领域={} 命主={}{} 构造query数={}",
                 intent.domain, day_master, strength, len(final_queries))
        parts: list[str] = []
        for idx, query in enumerate(final_queries, 1):
            text = knowledge_base.search_as_text(query)
            preview = (text[:200] + "…") if text and len(text) > 200 else (text or "（无匹配）")
            log.info("[workflow检索] [{}/{}] query={}\n  返回={}", idx, len(final_queries), query, preview)
            if text and text not in parts:
                parts.append(f"【检索问题】{query}\n{text}")
        if not parts:
            log.info("[workflow检索] 全部query无匹配结果")
        return "\n\n".join(parts) if parts else "（未检索到相关知识）"

    def _build_messages(
        self,
        user_prompt: str,
        intent: QuestionIntent,
        ctx: WorkflowChartContext,
        knowledge: str,
        history: list[BaseMessage],
        worker: DomainWorker | None = None,
    ) -> list[BaseMessage]:
        # Worker 配置优先（专业 Worker 提供 length_rule 和 skip_facts）
        if worker is None:
            worker = WORKERS.get(intent.domain, WORKERS["general"])
        facts = "" if worker.skip_facts else self._compact_facts(ctx.chart, intent)
        recent_history = self._compact_history(history)
        # 篇幅规则：详批优先 → Worker 专属规则
        if intent.wants_report:
            length_rule = "可以分段深入，但仍要围绕用户问题，不要堆砌全盘。"
        else:
            length_rule = worker.length_rule
        system = (
            "你是先知，拥有数十年实战经验的八字命理师傅，气质通透沉稳，像阅历丰富的老友。"
            "精通四柱八字、五行十神、大运流年、合婚择日；熟读渊海子平、子平真诠、滴天髓、穷通宝鉴、三命通会，论命引经据典但不堆砌古文。\n"
            "硬性规则：四柱、大运、流年、起运时间等事实只能使用【系统排盘事实】，不能自行改算或编造。\n"
            "知识库规则：\n"
            "1. 解释命理术语（空亡、桃花、羊刃、华盖、七杀等）时，必须参考【命理规则检索】中的内容，不得自行编造\n"
            "2. 引用古籍原文必须来自检索结果，格式：「《典籍名》原文：XXX」，简短自然嵌入，不单独大段摘抄\n"
            "3. 知识库取用优先级：调候参考《穷通宝鉴》、格局以《子平真诠》为准、基础理论取自《渊海子平》、神煞杂断参考《三命通会》；多流派冲突时以调候+扶抑格局折中\n"
            "4. 纳音、神煞仅作辅助，核心吉凶以正五行、十神、格局、用神为根基\n"
            "5. 检索无匹配古籍时，如实说明暂无古法论断，仅以五行十神基础逻辑分析，不杜撰古文\n"
            "合规红线：不推断生死、不指导赌博投机、不宣扬符咒改运、不提供堕胎择时；涉及重病、牢狱等凶险信息，优先劝导寻求医院、律师等现实专业帮助，不放大恐慌。\n"
            "说话风格：真人聊天感，不用表格、多层标题、emoji。不同问题回答重点不同，不重复论述，详略得当，一针见血。\n"
            "闲聊场景：用户不问命理问题时，回复不围绕命盘，根据心境适当回应，可参杂人生哲理、处世良言，引发情感共鸣。\n"
            "篇幅规范：闲聊1-3句≤150字；简单问题≤200字；常规分析2-3段≤350字；用户主动要求完整详批可放宽。\n"
            "该幽默幽默（调侃桃花旺、财来财去等），该严肃严肃（健康、刑冲等）。用'你'不用'您'，口语化，可适当用语气词。不确定直说'这个要看具体情况'，不绝对化。\n"
            "避免AI腔：不要'总结一下''需要注意的是''好消息/需要注意'这种模板。不要输出ReAct过程，不要机械倾倒完整报告，不要恐吓。"
        )
        # 追加 Worker 专属断法规则（专业 Worker 的领域知识）
        if worker.expertise_prompt:
            system += "\n" + worker.expertise_prompt
        human = (
            f"【用户问题】\n{user_prompt}\n\n"
            f"【识别意图】\n领域={intent.label}; 目标年份={intent.target_years or '未指定'}; 置信度={intent.confidence}\n\n"
            f"【最近对话摘要】\n{recent_history}\n\n"
        )
        if facts:
            human += f"【系统排盘事实】\n{facts}\n\n"
        human += (
            f"【命理规则检索】\n{knowledge}\n\n"
            f"【输出要求】\n{length_rule}\n"
            "如果提到具体年份，必须同时核对该年流年干支和所在大运。"
        )
        return [SystemMessage(content=system), HumanMessage(content=human)]

    def _build_repair_messages(
        self,
        raw_answer: str,
        checked: FactCheckResult,
        user_prompt: str,
        intent: QuestionIntent,
        ctx: WorkflowChartContext,
        knowledge: str,
        worker: DomainWorker | None = None,
    ) -> list[BaseMessage]:
        if worker is None:
            worker = WORKERS.get(intent.domain, WORKERS["general"])
        facts = "" if worker.skip_facts else self._compact_facts(ctx.chart, intent)
        # Reflextion 改写器：带上 Worker 专属断法，确保修复后仍符合领域规范
        sys_content = "你是事实校验后的改写器。只修正事实错误，保持自然命理师口吻，不要解释校验过程。"
        if worker.expertise_prompt:
            sys_content += "\n" + worker.expertise_prompt
        return [
            SystemMessage(content=sys_content),
            HumanMessage(content=(
                f"【用户问题】\n{user_prompt}\n\n"
                f"【原回答】\n{raw_answer}\n\n"
                f"【发现的问题】\n" + "\n".join(f"- {issue}" for issue in checked.issues) + "\n\n"
                + (f"【正确排盘事实】\n{facts}\n\n" if facts else "")
                + f"【可用规则】\n{knowledge}\n\n"
                "请输出修正后的最终回答。"
            )),
        ]

    def _invoke(self, messages: list[BaseMessage]) -> str:
        response = self.chat_model.invoke(messages)
        content = (getattr(response, "content", "") or "").strip()
        # 过滤 reasoning model 的 <think>...</think> 推理过程，避免重复显示
        content = re.sub(r"<think>[\s\S]*?</think>\s*", "", content, flags=re.IGNORECASE)
        # 处理未闭合的 <think> 标签（流式中断等场景）
        content = re.sub(r"<think>[\s\S]*$", "", content, flags=re.IGNORECASE)
        content = content.strip()
        if not content:
            return "我先看盘面，当前信息足够排盘，但模型没有生成有效解读。你可以换一个更具体的问题继续问。"
        return _dedupe_content(content)

    def _compact_history(self, history: list[BaseMessage]) -> str:
        if not history:
            return "（无）"
        chunks = []
        for msg in history[-6:]:
            role = msg.__class__.__name__.replace("Message", "")
            content = str(getattr(msg, "content", "")).strip()
            if content:
                chunks.append(f"{role}: {content[:180]}")
        return "\n".join(chunks) if chunks else "（无）"

    def _compact_facts(self, chart: BaziChart, intent: QuestionIntent) -> str:
        today = _dt.date.today()
        pillars = " ".join(f"{p.name}:{p.ganzhi}({p.nayin})" for p in chart.pillars)
        dayun_lines = [
            f"{item.ganzhi} {item.start_year}-{item.end_year} {item.start_age}-{item.end_age}岁"
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
            f"{item.year}年:{item.ganzhi} {item.age}虚岁 所在大运:{item.dayun_ganzhi or '-'}"
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
            f"日主: {chart.wuxing.day_master}({chart.wuxing.day_master_wuxing}); 强弱: {chart.wuxing.strength}; 分数: {chart.wuxing.strength_score}",
            f"五行权重: {chart.wuxing.counts}; 最旺: {chart.wuxing.strongest}; 最弱: {chart.wuxing.weakest}",
            f"用神提示: {chart.wuxing.useful_hint}",
            f"十神结构: {chart.analysis.ten_gods}; 透干: {chart.analysis.exposed_stems or '-'}; 通根: {chart.analysis.rooted_stems or '-'}",
            f"地支关系: 合={chart.analysis.combinations or '-'}; 冲={chart.analysis.clashes or '-'}; 害={chart.analysis.harms or '-'}; 刑={chart.analysis.punishments or '-'}",
            f"调候: 月令{chart.analysis.season}; {chart.analysis.adjustment}",
            f"格局提示: {chart.analysis.pattern_hint}; 判断置信度: {chart.analysis.confidence}",
            f"起运: {chart.start_yun['startDate']} 起; {chart.start_yun['direction']}; 起运年龄 {chart.start_yun['startYear']}年{chart.start_yun['startMonth']}月{chart.start_yun['startDay']}日",
            "大运: " + "；".join(dayun_lines),
            "相关流年: " + ("；".join(liunian_lines) if liunian_lines else "未指定"),
            "口径: " + "；".join(chart.warnings),
        ])

    def check_facts(self, answer: str, chart: BaziChart) -> FactCheckResult:
        issues: list[str] = []
        year_to_gz = {item.year: item.ganzhi for item in chart.liunian}
        for match in YEAR_GANZHI_RE.finditer(answer):
            year = int(match.group("year"))
            stated = match.group("ganzhi")
            expected = year_to_gz.get(year)
            if expected and stated != expected:
                issues.append(f"{year}年流年应为{expected}，回答写成了{stated}")

        pillar_names = {p.name: p.ganzhi for p in chart.pillars}
        for name, expected in pillar_names.items():
            pattern = re.compile(rf"{name}[^。；;，,、\n]{{0,8}}(?P<ganzhi>{GANZHI_RE.pattern})")
            for match in pattern.finditer(answer):
                stated = match.group("ganzhi")
                if stated != expected:
                    issues.append(f"{name}应为{expected}，回答写成了{stated}")

        return FactCheckResult(ok=not issues, issues=issues)


def render_full_fact_context(ctx: WorkflowChartContext) -> str:
    return format_fact_context(ctx.chart)
