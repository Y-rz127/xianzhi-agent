"""基于先知图表的确定性工作流。

这是一个轻量级的状态机式编排层。它将复杂的图表信息保留在LLM之外，让模型专注于解读和自然对话。
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.domain.bazi_engine import BaziChart, build_bazi_chart, format_fact_context
from app.logger import log
# 检索策略（领域关键词/领域检索词/理论术语检索词/术语识别）统一由 app.rag.retrieval 提供，
# 与 ReAct 工具路径（app/tools/rag_search.py）共用一套体系
from app.rag.retrieval import (
    DOMAIN_KEYWORDS,
    DOMAIN_RULE_QUERIES,
    detect_domain,
    detect_theory_topic,
)
from app.rag.vector_store import knowledge_base
from app.tools.text_clean import clean_think_tags, dedupe_content as _dedupe_content_impl


def _parse_json(text: str) -> Any:
    """容错 JSON 解析：处理 LLM 输出的各种格式问题。"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试提取第一个 {...} 块
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _dedupe_content(content: str) -> str:
    """检测并移除完全重复的内容（推理模型 think 块泄漏的兜底）。
    
    委托给 app.utils.text_clean.dedupe_content 统一实现。
    """
    return _dedupe_content_impl(content)


GANZHI_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")
YEAR_GANZHI_RE = re.compile(r"(?P<year>\d{4})年[^。；;，,、\n]{0,12}(?P<ganzhi>[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])")

# 从用户问题里抽取「对方」出生信息（合婚场景）：支持 男/女 在数字前后两种顺序，时分可缺省
# 注意：不允许在「性别→日期」之间跨过另一个 男/女，否则会把用户自己的性别误配给对方日期
_OTHER_BIRTH_RE1 = re.compile(
    r"(?P<gender>男|女)(?:(?!男|女)[^\d])*?(?P<year>\d{4})[-年/](?P<month>\d{1,2})[-月/](?P<day>\d{1,2})"
    r"(?:[日\s]*(?P<hour>\d{1,2})[:：]?(?P<minute>\d{1,2})?)?"
)
_OTHER_BIRTH_RE2 = re.compile(
    r"(?P<year>\d{4})[-年/](?P<month>\d{1,2})[-月/](?P<day>\d{1,2})"
    r"(?:[日\s]*(?P<hour>\d{1,2})[:：]?(?P<minute>\d{1,2})?)?[^\d]*?(?P<gender>男|女)"
)


DOMAIN_LABELS = {
    "career": "事业工作",
    "wealth": "财运收入",
    "love": "恋爱感情",
    "marriage": "婚姻关系",
    "health": "健康状态",
    "liunian": "大运流年",
    "study": "学习考试",
    "social": "社交人际",
    "family": "六亲关系",
    "personality": "性格心性",
    "migration": "方位迁移",
    "naming": "起名改名",
    "auspicious": "择吉择日",
    "match": "合婚配对",
    "children": "子女生育",
    "theory": "术语理论",
    "chitchat": "闲聊问候",
    "general": "综合咨询",
}

@dataclass(frozen=True)
class QuestionIntent:
    """用户问题意图分类结果。

    Supervisor 用它决定分派哪个专业 Worker，以及检索哪些知识。
    合婚(match)场景下额外携带对方出生信息/命盘/规则基础数据。
    """
    domain: str
    label: str
    target_years: list[int] = field(default_factory=list)
    wants_report: bool = False
    confidence: float = 0.5
    needs_chart: bool = False  # 用户是否在问自己命盘的具体判断（如"我是不是枭神夺食"）
    queries: tuple[str, ...] = ()  # LLM 拆解出的精准检索词（空=走硬编码 fallback）
    other_birth_time: str = ""  # match 合婚：用户问题中提供的「对方」出生时间
    other_gender: str = ""      # match 合婚：对方的性别（男/女）
    second_chart: Any = None    # match 合婚：解析出的对方命盘（WorkflowChartContext）
    match_basis: str = ""       # match 合婚：系统规则合婚基础数据（bazi_hehun 产出）


@dataclass
class WorkflowChartContext:
    """工作流用的命盘上下文容器。

    保存原始输入（birth_time/gender/sect/yun_sect）与已排好的 BaziChart，
    供 Supervisor/Worker/Reviewer 共享同一排盘事实，避免重复计算。
    """
    birth_time: str
    gender: str
    sect: int
    yun_sect: int
    chart: BaziChart


@dataclass(frozen=True)
class FactCheckResult:
    """事实校验结果：ok 表示通过全部校验，issues 为发现的问题列表。"""
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
    "social": DomainWorker(
        domain="social",
        label="社交人际",
        expertise_prompt=(
            "【社交人际专项断法】\n"
            "- 比肩劫财主朋友同辈：比肩为同性相助、劫财为异性相助；比劫为用则朋友得力，为忌则受朋友连累\n"
            "- 贵人星（天乙贵人、天德贵人、月德贵人）入命，主社交有贵人提携\n"
            "- 七杀无制主小人：七杀攻身无食伤制化，易招小人嫉妒、背后使坏\n"
            "- 日支合他柱：日支被合走，主身边人缘变化（合入为得助，合走为疏远）\n"
            "- 比劫夺财兼社交：比劫旺而夺财，不仅破财，也主朋友争利、合伙生隙\n"
            "- 大运流年走比劫旺地，主社交活跃、人脉变动；走官杀旺地，主遇贵人或受压制\n"
            "- 社交层次看格局清浊：清格主贵人层次高、交往圈子优质；浊格主交际复杂、是非多"
        ),
        extra_queries=("比肩 劫财 朋友 贵人 小人 人际 断法", "天乙贵人 社交 合伙 八字 命理"),
    ),
    "family": DomainWorker(
        domain="family",
        label="六亲关系",
        expertise_prompt=(
            "【六亲关系专项断法】\n"
            "- 六亲对应十神：年柱为祖上/父母宫，月柱为父母/兄弟宫，日柱为自身/配偶宫，时柱为子女宫\n"
            "- 印星为母：正印为母，偏印为继母/养母；印星为用神且有力，主与母亲缘深得力\n"
            "- 财星为父：正财为父（也有以偏财为父的流派）；财星为用神且有力，主与父亲缘深得力\n"
            "- 比肩劫财为兄弟姐妹：比肩为同性手足，劫财为异性手足；为用则手足得力，为忌则受手足连累\n"
            "- 食神伤官为子女（女命）：食神为女，伤官为子；食伤为用神且有力，主子女出息\n"
            "- 正官七杀为子女（男命）：正官为女，七杀为子；官杀为用神且有力，主子女有成\n"
            "- 宫位受冲刑害：对应宫位逢冲刑害，主该六亲关系动荡、缘分浅薄\n"
            "- 大运流年引动六亲宫位或星位，多主该六亲当年有重大变化（婚丧嫁娶、升迁变动）"
        ),
        extra_queries=("六亲 十神 宫位 父母 子女 断法", "印星 财星 比劫 食伤 官杀 六亲 八字"),
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
            "- 如果提供了【系统排盘事实】，用户问'是不是XX'时，需结合命盘事实做判断：先解释术语成立条件，再对照命盘给出结论"
        ),
        length_rule="术语解释≤200字；结合命盘判断时≤350字，先给结论，后给依据。",
        skip_facts=True,
    ),
    "chitchat": DomainWorker(
        domain="chitchat",
        label="闲聊问候",
        expertise_prompt="",
        length_rule="闲聊1-3句，≤150字，像朋友聊天自然回应。",
        skip_facts=True,
    ),
    "personality": DomainWorker(
        domain="personality",
        label="性格心性",
        expertise_prompt=(
            "【性格心性专项断法】\n"
            "- 日主定底色：日主五行（甲乙木/丙丁火等）决定基本气质与行事风格\n"
            "- 十神组合定性格：比劫主果敢仗义、食伤主聪慧外露、正印主沉稳仁厚、偏印主孤僻机巧、"
            "正官主规矩自律、七杀主果决狠劲、正财主务实、偏财主慷慨\n"
            "- 强弱看精神面貌：身旺者主动外放、身弱者内敛保守；日主得令得地者自信，失令者易怯\n"
            "- 格局看层次：伤官佩印主才华内敛、杀印相生主谋略、食神制杀主魄力、官印相生主稳重\n"
            "- 适合什么人：看夫妻星/配偶宫十神与日主生克，以及桃花星、贵人星，给出互补型人格建议\n"
            "- 避免贴标签式下定论，结合用神喜忌说明性格的可成长方向"
        ),
        extra_queries=("日主 十神 性格 心性 断法", "用神 性格 天赋 为人 命理"),
    ),
    "migration": DomainWorker(
        domain="migration",
        label="方位迁移",
        expertise_prompt=(
            "【方位迁移专项断法】\n"
            "- 用神定吉方：用神五行对应方位（木东、火南、金西、水北、土中/本地），宜向用神方位发展\n"
            "- 驿马定动象：驿马星（寅午戌见申、申子辰见寅、巳酉丑见亥、亥卯未见巳）主奔波动迁，逢冲更明显\n"
            "- 大运流年引动：走驿马运、向外地之运，或流年冲动日支/驿马，多为外出发展之期\n"
            "- 本地 vs 外地：日主强、驿马旺、用神在他方者宜外出；日主弱、用神在本地者宜守\n"
            "- 合规提示：迁移仅为命理趋势参考，实际决策结合现实条件（工作、家庭、政策）"
        ),
        extra_queries=("用神方位 驿马 迁移 出行 断法", "外地发展 本地 大运 流年 命理"),
    ),
    "naming": DomainWorker(
        domain="naming",
        label="起名改名",
        expertise_prompt=(
            "【起名改名专项断法】\n"
            "- 以用神喜忌为核心：名字五行宜补用神、喜神所缺，忌神之五行尽量回避\n"
            "- 日主强弱定补法：身弱补印比（生扶日主），身强宜泄耗（食伤财官）\n"
            "- 字形字义为辅：在五行补益前提下选寓意积极、音律和谐的字，不与长辈重字\n"
            "- 调候优先：寒命（冬生水旺）喜火调候、燥命（夏生火旺）喜水润局\n"
            "- 合规提示：起名改名仅为文化民俗参考，不保证改运；最终以家长与户籍规定为准"
        ),
        extra_queries=("喜用神 起名 改名 五行补缺 命理", "八字命名 用神 古籍"),
    ),
    "auspicious": DomainWorker(
        domain="auspicious",
        label="择吉择日",
        expertise_prompt=(
            "【择吉择日专项断法】\n"
            "- 以用事人八字喜用神为择日根基：所选日课干支五行宜助旺用神、避开忌神\n"
            "- 事项定用神侧重：开业重财官、嫁娶重合婚、搬迁重印比安稳、动土重印星护身\n"
            "- 避凶煞：避开与用事人年命刑冲、三煞、月破、四离四绝等凶日\n"
            "- 选吉神当值：天德、月德、天赦、三合、六合等吉神值日优先\n"
            "- 合规提示：择日为传统民俗参考，重大事宜（医疗、法律）务必以专业意见为准"
        ),
        extra_queries=("择日 择吉 黄道吉日 用事 命理", "开业 嫁娶 搬迁 择日 古籍"),
    ),
    "match": DomainWorker(
        domain="match",
        label="合婚配对",
        expertise_prompt=(
            "【合婚配对专项断法】（已提供双方命盘：用户命盘 + 对方命盘）\n"
            "- 双盘对比：年柱生肖/纳音生克、日柱干支生克（男命看财星、女命看官星是否得力）、双方用神是否互补\n"
            "- 配偶宫（日支）十神、夫妻星状态、桃花/红鸾天喜/孤辰寡宿等神煞，两盘分别看再对比\n"
            "- 刑冲合害：两盘地支有无冲克（子午冲、卯酉冲、寅申冲等）、有无三合六合化解\n"
            "- 五行互补：双方最旺/最弱五行能否互济（参考【合婚基础数据（系统规则）】的互补评分）\n"
            "- 大运流年引动：双方当前及近年的婚恋应期是否同步\n"
            "- 若【合婚基础数据（系统规则）】已给出五行互补评分，作为参考锚点，结合十神格局做综合判断\n"
            "- 结论风格：讲清'合'与'需磨合'的维度，不绝对断吉凶；提醒婚姻经营重于命数\n"
            "- 若【对方命盘事实】缺失（用户未提供对方出生时间），说明需要对方出生年月日时+性别才能合婚，"
            "并先用单盘讲清本方配偶宫/夫妻星维度"
        ),
        extra_queries=("八字合婚 配偶宫 夫妻星 双盘 命理", "生肖 纳音 刑冲 合婚 古籍"),
    ),
    "children": DomainWorker(
        domain="children",
        label="子女生育",
        expertise_prompt=(
            "【子女生育专项断法】\n"
            "- 子女星看男女：男命以官杀为子女（官为女、杀为子），女命以食伤为子女（食为女、伤为子）\n"
            "- 子女宫看时柱：时柱干支与子女星状态定子女缘分厚薄、得力与否\n"
            "- 生育时机：大运流年引动子女星、子女宫（透出/得生/逢合），多为生育之机\n"
            "- 子女星受克（被冲合、入墓、空亡）多主缘分较浅或迟得，需结合大运看应期\n"
            "- 合规提示：生育规划仅为命理参考，健康与医学建议以医院为准"
        ),
        extra_queries=("子女星 子女宫 食伤 官杀 生育 断法", "何年生子 大运流年 子女 命理"),
    ),
    "general": DomainWorker(
        domain="general",
        label="综合咨询",
        expertise_prompt="",
    ),
}


def classify_question(text: str, today: _dt.date | None = None) -> QuestionIntent:
    """基于关键词/年份/闲聊信号的轻量意图分类（LLM 拆解的兜底）。

    Args:
        text: 用户问题
        today: 基准日期（默认今天，用于"今年/明年"年份推算）
    Returns:
        含 domain/label/target_years 等的 QuestionIntent
    """
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
    """根据出生时间/性别/流派构造 WorkflowChartContext（大运 10 柱、流年 8 年）。

    Args:
        birth_time: 出生时间（公历/农历/时辰/节日格式均可）
        gender: 性别（男/女）
        sect: 日柱计算流派（默认 2）
        yun_sect: 大运计算流派（默认 1）
    Returns:
        已排盘完成的 WorkflowChartContext
    """
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

    def review(self, answer: str, chart: BaziChart, knowledge: str, fact_checker, second_chart: Any = None) -> FactCheckResult:
        """对 Worker 产出做三重校验。

        Args:
            answer: Worker 生成的回答
            chart: 系统排盘事实
            knowledge: Worker 检索到的知识片段（用于古籍真实性比对）
            fact_checker: 复用 XianzhiWorkflow.check_facts 方法
            second_chart: 合婚双盘时的对方命盘（可选，同样做事实校验）
        """
        issues: list[str] = []

        # 1) 事实校验（四柱/大运/流年）
        # 双盘场景：两张盘的合法干支互为「容错集」，避免把对方盘的正确陈述误判为本盘错误
        fact_result = fact_checker(answer, chart, second_chart)
        issues.extend(fact_result.issues)
        if second_chart is not None:
            fact_result2 = fact_checker(answer, second_chart, chart)
            issues.extend(fact_result2.issues)

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
        self._graph_error: str | None = None
        try:
            from app.agent.xianzhi_langgraph import create_xianzhi_graph

            self._graph = create_xianzhi_graph(self)
            log.info("[workflow] LangGraph 编排已启用（backend=langgraph）")
        except Exception as e:
            self._graph_error = str(e)
            log.warning("[workflow] LangGraph 编排不可用，降级为内置 Supervisor 流水线（backend=builtin）: {}", e)

    @property
    def graph_enabled(self) -> bool:
        """LangGraph 编排是否真正启用。"""
        return self._graph is not None

    @property
    def backend(self) -> str:
        """当前生效的编排后端：langgraph / builtin。"""
        return "langgraph" if self._graph is not None else "builtin"

    # ===== LLM 意图拆解 =====
    _DECOMPOSE_SYSTEM = (
        "你是命理问答系统的意图分析模块。分析用户问题，输出JSON：\n"
        '{"domain":"...","queries":["...","..."],"needs_chart":true/false}\n\n'
        "domain 取值：theory=术语/概念/格局解释与判断, career=事业工作, wealth=财运, "
        "love=恋爱, marriage=婚姻, health=健康, liunian=大运流年, study=学习考试, "
        "social=社交人际/朋友/贵人/小人, family=六亲关系/父母/子女/兄弟姐妹, "
        "personality=性格心性/天赋为人/适合什么人, migration=方位迁移/去哪发展/本地外地, "
        "naming=起名改名/用神取名, auspicious=择吉择日/开业搬家结婚选日, "
        "match=合婚配对/两人八字合不合, children=子女生育时机/何年生子, "
        "chitchat=闲聊问候, general=综合咨询\n"
        "queries：1-3条精准检索词，用于知识库语义检索，每条≤30字，紧密围绕用户核心问题。"
        "不要泛化，不要堆砌无关概念。例如用户问'枭神夺食'就只给枭神夺食相关的词。\n"
        "needs_chart：用户是否在问自己命盘的具体判断（如'我是不是XX''我命盘XX'）。\n"
        "若 domain=match 且用户问题中给出了对方出生时间，请额外返回 other_birth_time"
        "（格式 YYYY-MM-DD HH:MM 或含时辰，如'1990-05-20 14:30'/'男1990年五月初五辰时'）和 "
        "other_gender（男/女）；只填'对方/另一半'的出生时间，不要填用户自己的。没有则留空字符串。\n"
        "只输出JSON，不要解释，不要markdown代码块。"
    )

    def _decompose_query(self, user_prompt: str) -> QuestionIntent | None:
        """用 LLM 拆解用户问题 → 意图分类 + 精准检索词。

        失败时返回 None，调用方 fallback 到 classify_question。
        """
        if not self.chat_model:
            return None
        try:
            messages = [
                SystemMessage(content=self._DECOMPOSE_SYSTEM),
                HumanMessage(content=user_prompt),
            ]
            resp = self.chat_model.invoke(messages)
            raw = (getattr(resp, "content", "") or "").strip()
            # 去除可能存在的 markdown 代码块包裹
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            data = _parse_json(raw)
            if not data or not isinstance(data, dict):
                return None
            domain = str(data.get("domain", "")).strip()
            if domain not in DOMAIN_LABELS:
                domain = "general"
            queries_raw = data.get("queries", [])
            if not isinstance(queries_raw, list):
                return None
            queries = tuple(str(q).strip() for q in queries_raw if str(q).strip())[:3]
            if not queries:
                return None
            needs_chart = bool(data.get("needs_chart", False))
            other_birth_time = str(data.get("other_birth_time", "") or "").strip()
            other_gender = str(data.get("other_gender", "") or "").strip()
            # 年份提取复用原逻辑
            years = sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", user_prompt)})
            today = _dt.date.today()
            if "今年" in user_prompt:
                years.append(today.year)
            if "明年" in user_prompt:
                years.append(today.year + 1)
            years = sorted(set(years))
            wants_report = any(w in user_prompt for w in ("完整报告", "详细报告", "全面分析", "完整分析", "从头到尾"))
            intent = QuestionIntent(
                domain=domain,
                label=DOMAIN_LABELS.get(domain, "综合咨询"),
                target_years=years,
                wants_report=wants_report,
                confidence=0.9,
                needs_chart=needs_chart,
                queries=queries,
                other_birth_time=other_birth_time,
                other_gender=other_gender,
            )
            log.info("[LLM拆解] domain={} needs_chart={} queries={}", domain, needs_chart, list(queries))
            return intent
        except Exception as e:
            log.warning("[LLM拆解] 失败，fallback到关键词分类: {}", e)
            return None

    def answer(
        self,
        user_prompt: str,
        chart_context: WorkflowChartContext,
        history: list[BaseMessage] | None = None,
    ) -> str:
        # 闲聊短路：关键词命中 chitchat 时直接走分类，不调用 LLM 拆解（节省 API 调用+时间）
        _chitchat_kw = detect_domain(user_prompt)
        if _chitchat_kw == "chitchat":
            intent = classify_question(user_prompt)
            log.info("[LLM拆解] 闲聊识别，跳过 LLM 拆解 → domain={}", intent.domain)
        else:
            intent = self._decompose_query(user_prompt) or classify_question(user_prompt)
        # ===== 合婚双盘：解析对方命盘（用户已挂载自己的盘，问题中给出对方盘）=====
        # 必须在 LangGraph 调用之前完成，否则图内节点读取不到 second_chart/match_basis
        if intent.domain == "match":
            ob, og = self._parse_other_birth(user_prompt)
            # LLM 拆解出的优先，正则兜底
            if not (ob and og) and intent.other_birth_time and intent.other_gender:
                ob, og = intent.other_birth_time, intent.other_gender
            if ob and og:
                try:
                    from app.tools.bazi import _normalize_birth_time
                    ob_n = _normalize_birth_time(ob)
                    # 避免把用户自己的盘当成对方盘
                    if ob_n != chart_context.birth_time:
                        other_ctx = build_chart_context(ob_n, og, chart_context.sect, chart_context.yun_sect)
                        basis = self._build_match_basis(chart_context, other_ctx)
                        intent = replace(intent, second_chart=other_ctx, match_basis=basis)
                        log.info("[match] 已解析对方命盘 {} {}，合婚基础数据{}字",
                                 ob_n, og, len(basis))
                    else:
                        log.info("[match] 解析出的对方命盘与用户自身盘相同，跳过")
                except Exception as e:
                    log.warning("[match] 解析对方命盘失败: {}", e)

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
            log.warning("[workflow] LangGraph 未产出最终答案，回退内置 Supervisor 流水线")

        # ===== Supervisor 分派阶段 =====
        worker = WORKERS.get(intent.domain, WORKERS["general"])
        log.info("[Supervisor] 意图={} 置信度={} → 分派给 {} Worker",
                 intent.label, intent.confidence, worker.label)

        chart_context = self._extend_chart_if_needed(chart_context, intent)

        # ===== Worker 执行阶段 =====
        knowledge = self._retrieve_rules(intent, chart_context, worker, user_prompt)
        messages = self._build_messages(user_prompt, intent, chart_context, knowledge, history or [], worker)
        raw_answer = self._invoke(messages)
        log.info("[Worker] {} 生成回答 {}字", worker.label, len(raw_answer))

        # ===== Reviewer 审核阶段（三重校验：事实+古籍真实性+合规） =====
        log.info("[Reviewer] 开始审核 {} Worker 产出 ({}字)...", worker.label, len(raw_answer))
        review = self._reviewer.review(raw_answer, chart_context.chart, knowledge, self.check_facts,
                                       getattr(intent, "second_chart", None).chart if getattr(intent, "second_chart", None) else None)
        if review.ok:
            log.info("[Reviewer] {} Worker 产出通过三重校验 ✓", worker.label)
            return raw_answer
        log.warning("[Reviewer] {} Worker 产出未通过校验 ✗，触发 Reflextion 修复", worker.label)
        for i, issue in enumerate(review.issues, 1):
            log.warning("[Reviewer]   issue[{}]: {}", i, issue)

        # ===== Reflextion 回退修复 =====
        repair_messages = self._build_repair_messages(
            raw_answer, review, user_prompt, intent, chart_context, knowledge, worker
        )
        repaired = self._invoke(repair_messages)
        repaired_review = self._reviewer.review(repaired, chart_context.chart, knowledge, self.check_facts,
                                                getattr(intent, "second_chart", None).chart if getattr(intent, "second_chart", None) else None)
        if repaired_review.ok:
            log.info("[Reflextion] {} Worker 修复后通过校验 ✓", worker.label)
            return repaired
        log.warning("[Reflextion] {} Worker 修复后仍未通过 ✗", worker.label)
        for i, issue in enumerate(repaired_review.issues, 1):
            log.warning("[Reflextion]   残留issue[{}]: {}", i, issue)
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

    def _parse_other_birth(self, text: str) -> tuple[str, str]:
        """从用户问题中正则抽取「对方」出生信息（合婚兜底）。

        返回 (birth_time, gender)，无匹配返回 ("", "")。
        birth_time 标准化为 YYYY-MM-DD HH:MM（时分缺省补 00:00）。
        """
        for pattern in (_OTHER_BIRTH_RE1, _OTHER_BIRTH_RE2):
            m = pattern.search(text)
            if m:
                d = m.groupdict()
                year, month, day = int(d["year"]), int(d["month"]), int(d["day"])
                hour = int(d["hour"]) if d.get("hour") else 0
                minute = int(d["minute"]) if d.get("minute") else 0
                birth_time = "{}-{:02d}-{:02d} {:02d}:{:02d}".format(year, month, day, hour, minute)
                return birth_time, d["gender"]
        return "", ""

    def _build_match_basis(self, self_ctx: WorkflowChartContext, other_ctx: WorkflowChartContext) -> str:
        """复用规则合婚工具 bazi_hehun，生成双盘基础数据，作为 LLM 综合判断的锚点。"""
        try:
            from app.tools.bazi import bazi_hehun
            # bazi_hehun 是 @tool 装饰的 StructuredTool，需用 .func 取底层函数直接调用
            base = bazi_hehun.func(
                self_ctx.birth_time, self_ctx.gender,
                other_ctx.birth_time, other_ctx.gender,
                self_ctx.sect,
            )
            if base and not base.startswith("合婚分析失败"):
                return base
        except Exception as e:
            log.warning("[match] 规则合婚基础数据生成失败: {}", e)
        return ""

    # 单 query 检索结果最大字符数（避免单次拉爆 token；≈ 2-3 个 chunk）
    _MAX_TEXT_PER_QUERY = 1000
    # 累计送入 prompt 的总检索字符上限（截断兜底）
    _MAX_KNOWLEDGE_TOTAL = 3500

    def _retrieve_rules(
        self,
        intent: QuestionIntent,
        ctx: WorkflowChartContext,
        worker: DomainWorker | None = None,
        user_text: str = "",
    ) -> str:
        # 闲聊场景：最优先短路，不依赖知识库，让 LLM 自然回应
        if intent.domain == "chitchat":
            return "（闲聊场景，无需命理知识检索）"
        if not knowledge_base.ready:
            return "（知识库未就绪，本轮只使用结构化排盘事实与内置命理口径。）"

        day_master = ctx.chart.wuxing.day_master or ""
        strength = ctx.chart.wuxing.strength or ""

        # ===== LLM 拆解的 queries 优先（精准、自适应） =====
        if intent.queries:
            # 限制最多 2 条 query，避免过多检索导致 token 浪费
            queries = list(intent.queries[:2])
            log.info("[workflow检索] LLM拆解路径 queries={} (原{}条,取前2条)",
                     queries, len(intent.queries))
        elif intent.domain == "theory":
            queries, log_meta = self._build_theory_queries(user_text)
            log.info("[workflow检索] 理论路径 meta={} 构造query数={}", log_meta, len(queries))
        else:
            queries, log_meta = self._build_duxing_queries(intent, ctx, worker)
            log.info("[workflow检索] 断事路径 meta={} 构造query数={}", log_meta, len(queries))

        log.info("[workflow检索] 领域={} 命主={}{} 构造query数={}",
                 intent.domain, day_master, strength, len(queries))

        parts: list[str] = []
        total_chars = 0
        seen_prefixes: set[str] = set()  # 跨 query 去重：相同片段不重复送入 prompt
        dedup_count = 0
        for idx, query in enumerate(queries, 1):
            text = knowledge_base.search_as_text(query)
            # 单 query 结果截断，防止长片段（古籍原文）吃光预算
            if text and len(text) > self._MAX_TEXT_PER_QUERY:
                text = text[:self._MAX_TEXT_PER_QUERY] + "…"
            # 跨 query 去重：取前 120 字符作为指纹，避免语义相近的 query 返回相同片段
            if text:
                prefix = text[:120]
                if prefix in seen_prefixes:
                    dedup_count += 1
                    log.debug("[workflow检索] [{}/{}] query={} 结果与前面重复，跳过", idx, len(queries), query)
                    continue
                seen_prefixes.add(prefix)
            log.info("[workflow检索] [{}/{}] query={} 命中={}字",
                     idx, len(queries), query, len(text) if text else 0)
            # 打印检索内容前 200 字符，方便排查
            if text:
                preview = text.replace("\n", " ")[:200]
                log.info("[workflow检索] [{}/{}] 内容预览: {}", idx, len(queries), preview)
            if not text:
                continue
            block = f"【检索问题】{query}\n{text}"
            # 总字符截断兜底
            if total_chars + len(block) > self._MAX_KNOWLEDGE_TOTAL:
                remain = self._MAX_KNOWLEDGE_TOTAL - total_chars
                if remain > 200:
                    block = block[:remain] + "…"
                    parts.append(block)
                    total_chars += len(block)
                log.info("[workflow检索] 累计字符已达上限，截断后续结果")
                break
            parts.append(block)
            total_chars += len(block)
        if not parts:
            log.info("[workflow检索] 全部query无匹配结果")
        else:
            log.info("[workflow检索] 汇总: {}条query → {}条有效结果, 去重跳过{}条, 总{}字",
                     len(queries), len(parts), dedup_count, total_chars)
        return "\n\n".join(parts) if parts else "（未检索到相关知识）"

    def _build_theory_queries(self, user_text: str) -> tuple[list[str], str]:
        """理论问题 query 构造：精准单概念，规避泛化检索。

        1) 命中具体术语 → 单条精准 query
        2) 未命中 → 走兜底 query
        3) 严格限制 1-2 条 query，不叠加个性化/命例/古籍/断法
        """
        match = detect_theory_topic(user_text)
        if match:
            topic, query = match
            return [query], f"topic={topic}"
        return ["命理 术语 概念 解释"], "fallback"

    def _build_duxing_queries(
        self,
        intent: QuestionIntent,
        ctx: WorkflowChartContext,
        worker: DomainWorker | None,
    ) -> tuple[list[str], str]:
        """断事问题 query 构造：领域规则 + 个性化 + 命例 + 古籍 + 断法。"""
        queries: list[str] = list(DOMAIN_RULE_QUERIES.get(intent.domain, DOMAIN_RULE_QUERIES["general"]))
        # 1) Worker 专属额外检索 query
        if worker and worker.extra_queries:
            queries.extend(worker.extra_queries)
        day_master = ctx.chart.wuxing.day_master or ""
        strength = ctx.chart.wuxing.strength or ""
        # 2) 日主 + 强弱个性化 query
        queries.append(f"{intent.label} {day_master}日主 {strength} 大运流年")
        # 3) 命例查相似结构
        if day_master and strength:
            if "旺" in strength or "强" in strength:
                queries.append(f"{day_master}日主身旺 命例 典型命局 古籍")
            elif "弱" in strength or "衰" in strength:
                queries.append(f"{day_master}日主身弱 命例 典型命局 古籍")
        # 4) 按领域补古籍检索
        ancient_query_map = {
            "career": "渊海子平 论官杀 事业 官星",
            "wealth": "渊海子平 论财 财星 食伤生财",
            "marriage": "滴天髓 论婚姻 配偶宫 古籍",
            "health": "三命通会 论疾病 五行 健康古籍",
            "love": "子平真诠 论桃花 感情 古籍",
            "personality": "滴天髓 论性情 日主 十神 性格 古籍",
            "migration": "滴天髓 论迁移 驿马 方位 古籍",
            "naming": "渊海子平 论命名 用神 起名 古籍",
            "auspicious": "星命 择日 择吉 用事 古籍",
            "match": "三命通会 论合婚 夫妻宫 合婚 古籍",
            "children": "三命通会 论子息 子女 食伤 古籍",
        }
        ancient_q = ancient_query_map.get(intent.domain)
        if ancient_q:
            queries.append(ancient_q)
        # 5) 断法体系 query
        duanfa_query_map = {
            "health": "健康伤病 断法 五行失衡 疾病",
            "wealth": "贫富层次 财星 断法 命理",
            "career": "事业财运 官星 印星 断法",
            "marriage": "婚恋关系 配偶宫 断法 命理",
            "love": "婚恋关系 桃花 断法 命理",
            "personality": "性格心性 十神 日主 为人 断法",
            "migration": "方位迁移 用神方位 驿马 断法",
            "naming": "起名改名 喜用神 五行 断法",
            "auspicious": "择吉择日 用事 黄道 断法",
            "match": "合婚 夫妻宫 刑冲合害 断法",
            "children": "子女生育 食伤 子女宫 时机 断法",
        }
        duanfa_q = duanfa_query_map.get(intent.domain)
        if duanfa_q:
            queries.append(duanfa_q)
        # 上限 3 条（领域规则 + 个性化 + 古籍/断法择一）
        return queries[:3], "duxing"

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
        # needs_chart 覆盖 skip_facts：用户问"我命盘是不是XX"时需要注入命盘事实
        skip = worker.skip_facts and not intent.needs_chart
        facts = "" if skip else self._compact_facts(ctx.chart, intent)
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
            "篇幅规范：闲聊1-3句≤120字；简单问题≤250字；常规分析2-3段≤400字；用户主动要求完整详批可放宽。\n"
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
        match_basis = getattr(intent, "match_basis", "")
        if match_basis:
            human += f"【合婚基础数据（系统规则）】\n{match_basis}\n\n"
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
                + (f"【合婚基础数据（系统规则）】\n{getattr(intent, 'match_basis', '')}\n\n"
                   if getattr(intent, "match_basis", "") else "")
                + f"【可用规则】\n{knowledge}\n\n"
                "请输出修正后的最终回答。"
            )),
        ]

    def _invoke(self, messages: list[BaseMessage]) -> str:
        response = self.chat_model.invoke(messages)
        content = (getattr(response, "content", "") or "").strip()
        # 过滤 reasoning model 的 <think>...</think> 推理过程，避免重复显示
        content = clean_think_tags(content)
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

    def _fact_block(self, chart: BaziChart, intent: QuestionIntent) -> str:
        """单张命盘的紧凑事实块（不含对方盘逻辑，供 _compact_facts 复用）。"""
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

    def _compact_facts(self, chart: BaziChart, intent: QuestionIntent) -> str:
        facts = self._fact_block(chart, intent)
        # 合婚双盘：追加对方命盘事实
        second = getattr(intent, "second_chart", None)
        if second is not None:
            facts += "\n\n【对方命盘事实】\n" + self._fact_block(second.chart, intent)
        return facts

    def check_facts(self, answer: str, chart: BaziChart, other_chart: BaziChart | None = None) -> FactCheckResult:
        """校验回答中的四柱/大运/流年是否与系统排盘一致。

        other_chart 为合婚双盘时的对方命盘：同一干支若出现在任一张合法盘上即视为正确，
        避免把回答中对「对方/自己」各自正确的陈述误判为对方盘错误。
        """
        issues: list[str] = []
        year_to_gz: dict[int, str] = {item.year: item.ganzhi for item in chart.liunian}
        if other_chart is not None:
            for item in other_chart.liunian:
                year_to_gz.setdefault(item.year, item.ganzhi)
        for match in YEAR_GANZHI_RE.finditer(answer):
            year = int(match.group("year"))
            stated = match.group("ganzhi")
            expected = year_to_gz.get(year)
            if expected and stated != expected:
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


def render_full_fact_context(ctx: WorkflowChartContext) -> str:
    return format_fact_context(ctx.chart)
