"""领域 Worker 注册表与 Reviewer 审核 Agent。

R9 拆分自 xianzhi_workflow.py。"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.prompts import REVIEWER_SYSTEM
from app.agent.workflow.workflow_models import DomainWorker, FactCheckResult
from app.agent.workflow.workflow_support import _parse_json
from app.core.logger import log
from app.domain.bazi_engine import BaziChart, format_fact_context

_REVIEWER_SYSTEM = REVIEWER_SYSTEM


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
        extra_queries=("事业工作 升职 跳槽 伤官见官 官杀混杂",),
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
        extra_queries=("财运收入 正财 偏财 食伤生财 财库 比劫夺财",),
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
        extra_queries=("婚恋关系 桃花 配偶星 红艳 孤辰寡宿",),
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
        extra_queries=("婚恋关系 配偶宫 夫妻星 离婚 晚婚",),
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
        extra_queries=("健康伤病 五行失衡 疾病 七杀攻身 羊刃",),
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
        extra_queries=("学业功名 考试 印星 食伤 官星 文昌",),
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
        extra_queries=("社交人际 朋友 贵人 小人 比肩 劫财 合伙",),
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
        extra_queries=("六亲完整 父母 子女 印星 财星 比劫 宫位",),
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
        extra_queries=("大运流年 太岁 岁运并临 应期 作用关系",),
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
        length_rule="闲聊1-3句，≤150字；先正面接住用户说的话，有问题直接答、有倾诉先接住；不绕弯子、不铺垫、不靠寒暄和反问凑字数，语气平和稳重。",
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
        extra_queries=("性格 心性 日主 十神 天赋 为人 断法",),
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
        extra_queries=("迁移 出行 驿马 用神方位 外地发展 断法",),
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
        extra_queries=("起名 改名 喜用神 五行补缺 汉字五行 命名 断法",),
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
        extra_queries=("择日 择吉 黄道吉日 开业 嫁娶 搬迁 用事 断法",),
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
        extra_queries=("合婚 配偶宫 夫妻星 生肖 纳音 刑冲 双盘 断法",),
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
        extra_queries=("子女 生育 食伤 官杀 子女宫 大运流年 断法",),
    ),
    "general": DomainWorker(
        domain="general",
        label="综合咨询",
        expertise_prompt=(
            """【综合咨询断法】
            - 用户未指定单一领域（如"整体看看我命盘"）时，按"格局用神 → 强弱喜忌 → 事业财运 → 婚恋健康"顺序做鸟瞰式综述。
            - 先给一句话总评（日主、格局、用神、层次），再分点讲 2-3 个最突出的领域，每点结合盘面依据。
            - 不堆砌全盘，详略得当；提示用户可就某一领域深入追问。
            - 复合问题（如"事业和婚姻怎么选"）先拆维度再综合，避免顾此失彼。"""
        ),
    ),
}


class ReviewerWorker:
    """Reviewer 独立审核 Agent：正则快筛 + LLM 深审。

    两层审核架构：
    1. 正则快筛（<5ms，零 token）：事实校验 + 古籍真实性（书名白名单）+ 合规红线
    2. LLM 深审（3-5s，1 次调用）：逻辑自洽 + 断法准确性 + 知识一致性 + 古籍真实性（伪造古文句子）+ 表达质量 + 事实复查

    古籍真实性由两层双重覆盖：正则查书名是否在检索/白名单，LLM 查伪造的古文句子（正则查不出的）。
    正则发现问题直接返回（省 LLM 调用），正则全通过才调 LLM 做深度审核。
    LLM 不可用时自动降级为纯正则（不影响主流程）。
    """

    # 合规红线关键词（命中即需人工提示，不直接拒答）
    COMPLIANCE_RISKS = (
        "你的死期是",
        "你的寿命很",
        "何时死",
        "什么时候死",
        "堕胎择时",
        "择日堕胎",
        "可以改运",
        "可以改命",
        "下诅咒",
        "下蛊",
        "用邪术",
        "买彩票必中",
        "赌博必赢",
        "包赚",
        "稳赚不赔",
    )

    # 古籍真实性校验：抽取回答中「《XXX》原文：...」标注
    ANCIENT_CITATION_RE = re.compile(r"《[^》]{1,12}》[^。；;\n]{0,6}原文[：:]")

    def __init__(self, chat_model: BaseChatModel | None = None):
        self._chat_model = chat_model

    def review(
        self,
        answer: str,
        chart: BaziChart,
        knowledge: str,
        fact_checker,
        second_chart: Any = None,
        user_prompt: str = "",
        ctx: Any = None,
        skip_llm: bool = False,
        needs_chart: bool = True,
    ) -> FactCheckResult:
        """两层审核：正则快筛 → LLM 深审。

        Args:
            answer: Worker 生成的回答
            chart: 系统排盘事实
            knowledge: Worker 检索到的知识片段
            fact_checker: 复用 XianzhiWorkflow.check_facts 方法
            second_chart: 合婚双盘时的对方命盘
            user_prompt: 原始用户问题（LLM 审核判断是否答非所问）
            ctx: WorkflowChartContext（LLM 审核构建事实上下文用）
            skip_llm: 跳过 LLM 深审，仅依赖正则
            needs_chart: 当前回答是否属于"绑定命盘分析"场景（命盘分析/合婚/流年大运推演等）。
                True 时十神/神煞存在性严格校验；False（理论问答）时仅校验归属断言。
        """
        # === 第1层：正则快筛 ===
        regex_issues = self._regex_review(answer, chart, knowledge, fact_checker, second_chart, needs_chart)
        if regex_issues:
            log.info(
                "[Reviewer] 正则快筛发现问题，跳过 LLM 审核（省 1 次调用）: {} 条 issue", len(regex_issues)
            )
            return FactCheckResult(ok=False, issues=regex_issues, source="regex")

        # === 短路：调用方声明跳过 LLM 深审（闲聊/题外话等无 LLM 深审价值的场景）===
        if skip_llm:
            log.info("[Reviewer] 调用方指定 skip_llm，跳过 LLM 深审，仅依赖正则快筛 ✓")
            return FactCheckResult(ok=True, source="regex")

        # === 第2层：LLM 深审 ===
        if self._chat_model is None:
            return FactCheckResult(ok=True, source="regex")

        return self._llm_review(answer, chart, knowledge, user_prompt, ctx, second_chart)

    def _regex_review(
        self, answer, chart, knowledge, fact_checker, second_chart, needs_chart: bool
    ) -> list[str]:
        """第1层：正则快筛（原有三重校验，零 LLM 调用）。"""
        issues: list[str] = []

        # 1) 事实校验（四柱/大运/流年/十神/神煞）
        fact_result = fact_checker(answer, chart, second_chart, needs_chart)
        issues.extend(fact_result.issues)
        if second_chart is not None:
            fact_result2 = fact_checker(answer, second_chart, chart, needs_chart)
            issues.extend(fact_result2.issues)

        # 2) 古籍真实性校验
        citations = self.ANCIENT_CITATION_RE.findall(answer)
        if citations and knowledge and "未检索到相关知识" not in knowledge and "闲聊场景" not in knowledge:
            cited_books = set()
            for m in re.finditer(r"《([^》]{1,12})》", knowledge):
                cited_books.add(m.group(1))
            for citation in citations:
                book_match = re.match(r"《([^》]{1,12})》", citation)
                if book_match:
                    book = book_match.group(1)
                    classic_books = {
                        "渊海子平",
                        "子平真诠",
                        "滴天髓",
                        "穷通宝鉴",
                        "三命通会",
                        "神峰通考",
                        "千里命稿",
                    }
                    if book not in cited_books and book not in classic_books:
                        issues.append(f"引用《{book}》原文未在检索结果中出现，疑似杜撰古籍")

        # 3) 合规红线扫描
        risks_found = [kw for kw in self.COMPLIANCE_RISKS if kw in answer]
        if risks_found:
            issues.append("回答中出现了不合规的风险断言，请移除相关内容并改为劝导寻求专业帮助")

        return issues

    def _llm_review(self, answer, chart, knowledge, user_prompt, ctx, second_chart) -> FactCheckResult:
        """第2层：LLM 深度审核。"""
        facts = format_fact_context(chart)
        if second_chart is not None:
            facts += "\n\n【对方命盘事实】\n" + format_fact_context(second_chart)

        human_content = (
            f"【系统排盘事实】\n{facts}\n\n"
            f"【命理规则检索】\n{knowledge}\n\n"
            f"【用户问题】\n{user_prompt}\n\n"
            f"【待审核回答】\n{answer}"
        )
        messages = [
            SystemMessage(content=_REVIEWER_SYSTEM),
            HumanMessage(content=human_content),
        ]
        try:
            resp = self._chat_model.invoke(messages)
            raw = (getattr(resp, "content", "") or "").strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            data = _parse_json(raw)
            if not data or not isinstance(data, dict):
                log.warning("[Reviewer] LLM 审核返回非 JSON，降级为通过: {}", raw[:200])
                return FactCheckResult(ok=True, source="regex_fallback")
            passed = bool(data.get("pass", True))
            issues_raw = data.get("issues", [])
            issues = [str(i) for i in issues_raw if str(i).strip()] if isinstance(issues_raw, list) else []
            if not passed:
                log.info("[Reviewer] LLM 深审发现问题: {} 条 issue", len(issues))
            else:
                log.info("[Reviewer] LLM 深审通过 ✓")
            return FactCheckResult(ok=passed, issues=issues, source="llm")
        except Exception as e:
            log.warning("[Reviewer] LLM 审核失败，降级为纯正则通过: {}", e)
            return FactCheckResult(ok=True, source="regex_fallback")
