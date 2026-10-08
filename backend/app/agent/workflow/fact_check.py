"""命盘事实审核（纯函数，无 LLM / 无 IO）。

从 `workflow_messages.check_facts` 抽出的单一事实源：原实现是 451 行单体函数，
内部嵌套 7 个闭包、共享 `issues/chart/answer/needs_chart/actual_shishen/...` 一整套状态。
现拆为：模块级常量 + 模块级辅助函数 + 7 个维度校验函数 + `check_facts` 编排器，
共享状态收口到 `_FactCheckCtx`。

口径依据与历史事故见各维度块内注释；行为须与黄金样本 `tests/fixtures/fact_check_cases.json`
（22 条）逐字一致——改动后用 `scripts/fact_check_golden.py --diff` 核对，禁止「刷快照放行违规」。

高维坐标：`knowledge_docs` 知识库「审核红线」相关条目；`tests/test_fact_check_golden.py` 49 测试兜底。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.agent.workflow.workflow_models import FactCheckResult
from app.agent.workflow.workflow_support import (
    _DAYUN_GANZHI_RE,
    GANZHI_RE,
    YEAR_GANZHI_RE,
)
from app.domain.chart_builder import (
    BaziChart,
    _compute_shensha,
    parse_gender,
)

# ───────────────────────── 模块级常量（原闭包/局部常量上提） ─────────────────────────

SHISHEN_NAMES = (
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
)

SHENSHA_NAMES = (
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
)

# 流年干支校验：年份→干支之间或干支之后若出现大运词，则该干支在讲大运，不算流年错误
_DAYUN_MARKER_RE = re.compile(r"大运|交运|起运|运柱|行运|步入|迈入|走入|交入|走|交|运")

# 大运干支校验：流年干支只在「年份紧跟干支」时放行（近义写法）
_YEAR_BEFORE_RE = re.compile(r"(?:\d{4}年?|流年|岁运|年运|当年|本年|今年|明年|后年)$")

# 归属断言锚点：「你命盘/命中/八字/四柱/原局/年柱/日支…」+ 紧随的十神/神煞名，即视为对命盘做归属断言
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

# 句切分（归属断言按句判定）
_SENT_SPLIT = re.compile(r"[。；;！!？?\n\r]")

# 多字否定词：直接命中即视为否定
_NEG_TOKENS = (
    "没见",
    "没有",
    "不带",
    "不含",
    "未见",
    "并无",
    "毫无",
    "不存在",
    "不曾",
    "并未",
    "并非",
    "而非",
    "未有",
    "未带",
    "未含",
    "无此",
    "没带",
    "无关",
    "不算",
    "谈不上",
    "算不上",
    "见不到",
    "看不到",
)

# 单字否定字符
_NEG_CHARS = "不未无没非否莫"
# 单字否定须后接谓语才算否定
_NEG_PREDICATES = "是带含见有存在落坐透现遇属会具犯逢临"

# 动态岁运语境标识：出现即认为在讲外部流年/大运，而非原盘静态断言
_DYNAMIC_CTX = re.compile(r"\d{4}|大运|流年|岁运|年运|运上|流月|流日")
# 「桃花年」「红鸾运」等约定俗成 → 目标词后紧接年/运/月 视为动态流年讨论
_DYNA_SUFFIX = re.compile(r"[年运月令日限]")

# 正向归属暗示词：只有这些词在目标词附近，才认为是在「断言命盘拥有 X」
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

# 纯理论定义/区别解释标记（句中无锚点时，命中即非命盘断言）
_THEORY_MARKERS = (
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

# 十神组合断言（短语 → 需同时存在的两个十神）
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

# 神煞柱位归属校验的小句切分（比句更细，避免跨小句误配）
_CLAUSE_SPLIT = re.compile(r"[。；;！!？?\n\r，,、]")


# ───────────────────────── 共享状态 ─────────────────────────

@dataclass
class _FactCheckCtx:
    """一次审核所需的共享状态（替代原闭包捕获的局部变量集合）。"""

    chart: BaziChart
    other_chart: BaziChart | None
    answer: str
    needs_chart: bool
    facts_text: str
    year_to_gz: dict[int, str] = field(default_factory=dict)
    dayun_gz: set[str] = field(default_factory=set)
    valid: dict[str, set[str]] = field(default_factory=dict)
    primary: dict[str, str] = field(default_factory=dict)
    pillar_names: list[str] = field(default_factory=list)
    actual_shishen: set[str] = field(default_factory=set)
    actual_shensha_all: set[str] = field(default_factory=set)
    actual_shensha_by_pillar: dict[str, set[str]] = field(default_factory=dict)
    dynamic_shensha: set[str] = field(default_factory=set)


# ───────────────────────── 辅助函数（原嵌套闭包，参数化后上提） ─────────────────────────

def _sentence_has_negative_between(
    sent: str, a_pos: int, b_pos: int, target_word: str = ""
) -> bool:
    """判断 sent 中 a_pos 与 b_pos 之间（含边界附近±2）是否存在否定词。

    多字否定词直接命中；单字否定（不/未/无/没/非/否）只在后接谓语（是/带/含/见/有…）
    或紧邻 target_word 时才算否定，避免「不错/无论/非常」把肯定断言当否定放行。
    """
    lo, hi = sorted([a_pos, b_pos])
    lo = max(0, lo - 2)
    hi = min(len(sent), hi + 2)
    seg = sent[lo:hi]
    if any(tok in seg for tok in _NEG_TOKENS):
        return True
    for i, ch in enumerate(seg):
        if ch not in _NEG_CHARS:
            continue
        nxt = seg[i + 1 : i + 2]
        if nxt and nxt in _NEG_PREDICATES:
            return True
        if target_word and seg[i + 1 : i + 1 + len(target_word)] == target_word:
            return True
    return False


def _sentence_is_theory_definition(sent: str, target_word: str) -> bool:
    """判断该句是否是在做纯理论定义/区别解释，而非命盘断言。"""
    for anchor in _ASSERT_ANCHORS:
        if anchor in sent:
            return False
    t_pos = sent.find(target_word)
    tail = sent[t_pos:]
    return any(m in tail for m in _THEORY_MARKERS)


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
    """目标词附近是否有「有/带/含/透/藏…」等归属暗示。"""
    win = sent[max(0, t_pos - 8) : min(len(sent), t_pos + len(target_word) + 8)]
    return any(h in win for h in _OWNERSHIP_HINTS)


def _sentence_asserts_positive(sent: str, target_word: str, needs_chart: bool) -> bool:
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
        # 锚点与目标词之间若插入了年份/大运/流年（如"你日柱壬申，2045年拱禄入命"），
        # 目标词是绑在岁运上的，不构成原局归属断言 → 换下一个锚点（避免误报"排盘事实中无X"）
        _lo, _hi = sorted([a_pos, t_pos])
        if _DYNAMIC_CTX.search(sent[_lo:_hi]):
            continue
        if not _sentence_has_negative_between(sent, a_pos, t_pos, target_word):
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


def _answer_makes_binding_assertion(
    target_word: str, answer: str, needs_chart: bool, text: str | None = None
) -> bool:
    """判断回答是否在**肯定地断言**命盘事实层面带有 target_word（十神/神煞）。

    必须排除：
    - 否定句（没见/没有/不带/无/未/非 等，锚点与目标词之间出现）
    - 纯理论定义句（XX主XX/XX代表XX，且句中无锚点）

    text: 校验用文本（默认 answer）；调用方可传子串消歧后的文本。
    """
    scan_text = answer if text is None else text
    if target_word not in scan_text:
        return False
    for sent in _SENT_SPLIT.split(scan_text):
        if target_word not in sent:
            continue
        if _sentence_asserts_positive(sent, target_word, needs_chart):
            return True
    return False


def _scan_text_for(answer: str, name: str) -> str:
    """返回校验 name 用的文本：把「更长且包含 name」的神煞名（如 正学堂 中的 学堂、
    正词馆 中的 词馆）就地替换为等长圆点，避免子串误配（"正学堂"被当作"学堂"判柱位）。
    替换等长 → 位置/小句边界与 answer 完全一致，可直接复用。
    """
    text = answer
    for longer in SHENSHA_NAMES:
        if len(longer) > len(name) and name in longer and longer in text:
            text = text.replace(longer, "○" * len(longer))
    return text


# ───────────────────────── 7 个维度校验块 ─────────────────────────

def _check_liunian_ganzhi(ctx: _FactCheckCtx, issues: list[str]) -> None:
    """流年干支校验：回答里的「YYYY年+干支」须与系统流年一致。

    大运豁免：该干支确实是本盘某步大运的干支，且年份→干支之间(≤6字)或干支之后紧随大运词，
    则判为在讲大运（"2028年走壬申大运"），不算流年干支错误。
    """
    answer = ctx.answer
    for match in YEAR_GANZHI_RE.finditer(answer):
        year = int(match.group("year"))
        stated = match.group("ganzhi")
        expected = ctx.year_to_gz.get(year)
        if not expected or stated == expected:
            continue
        if stated in ctx.dayun_gz:
            gap = match.group("gap") or ""
            tail = answer[match.end() : match.end() + 3]
            if _DAYUN_MARKER_RE.search(gap) or re.match(r"(?:大)?运", tail):
                continue  # 该干支在讲大运，不算流年干支错误
        issues.append(f"{year}年流年应为{expected}，回答写成了{stated}")


def _check_dayun_ganzhi(ctx: _FactCheckCtx, issues: list[str]) -> None:
    """大运干支校验：回答提到的「XX运/XX大运」须是本盘（含合婚对方盘）真实存在的大运干支。

    流年干支只在「年份紧跟干支」时才放行——旧版无条件放行流年干支，导致编造的大运只要撞上
    某个流年干支（如"己酉运"）就拦不住；现在只容忍"2032壬子运"/"流年壬子运"这类明确带
    年份语境的近义写法。"财运/桃花运"无干支不匹配，"小运""流月"也不匹配。
    """
    answer = ctx.answer
    _liunian_gz = set(ctx.year_to_gz.values())
    for match in _DAYUN_GANZHI_RE.finditer(answer):
        stated_dy = match.group(1)
        if stated_dy in ctx.dayun_gz:
            continue
        if stated_dy in _liunian_gz:
            pre = answer[max(0, match.start() - 8) : match.start()]
            if _YEAR_BEFORE_RE.search(pre):
                continue  # "2032壬子运"：把流年称作"运"，但紧邻年份，属近义写法
        issues.append(f"排盘事实无「{stated_dy}」这步大运，回答却提到{stated_dy}运，与大运事实不符")


def _check_pillar_ganzhi(ctx: _FactCheckCtx, issues: list[str]) -> None:
    """柱位干支校验：回答里的「年柱X/日支Y」须与本盘（含合婚对方盘）该柱干支一致。"""
    answer = ctx.answer
    for name, expected_set in ctx.valid.items():
        pattern = re.compile(rf"{name}[^。；;，,、\n]{{0,8}}(?P<ganzhi>{GANZHI_RE.pattern})")
        for match in pattern.finditer(answer):
            stated = match.group("ganzhi")
            if stated not in expected_set:
                issues.append(f"{name}应为{ctx.primary[name]}，回答写成了{stated}")


def _check_shishen_pairs(ctx: _FactCheckCtx, issues: list[str]) -> None:
    """十神：组合断言校验（如「偏正财都有」须两个十神都在排盘事实中）。"""
    for phrase, need_a, need_b in _SHISHEN_PAIRS:
        if _answer_makes_binding_assertion(phrase, ctx.answer, ctx.needs_chart):
            has_a = need_a in ctx.actual_shishen
            has_b = need_b in ctx.actual_shishen
            if not (has_a and has_b):
                missing = need_a if not has_a else need_b
                issues.append(f"排盘事实中无{missing}，回答却说「{phrase}」，与十神事实不符")


def _check_shishen_single(ctx: _FactCheckCtx, issues: list[str]) -> None:
    """十神：单个归属断言校验（断言命盘带某十神，须其确实在排盘事实中）。"""
    for name in SHISHEN_NAMES:
        if name == "日主":
            continue
        if _answer_makes_binding_assertion(name, ctx.answer, ctx.needs_chart) and name not in ctx.actual_shishen:
            issues.append(f"排盘事实中无「{name}」，回答却断言命盘带有，与十神事实不符")


def _check_shensha_existence(ctx: _FactCheckCtx, issues: list[str]) -> None:
    """神煞：存在性断言校验（断言命盘带某神煞，须其确实在排盘事实中）。"""
    for name in SHENSHA_NAMES:
        if (
            _answer_makes_binding_assertion(name, ctx.answer, ctx.needs_chart, _scan_text_for(ctx.answer, name))
            and name not in ctx.actual_shensha_all
        ):
            issues.append(f"排盘事实中无「{name}」，回答却断言命盘带有，与神煞事实不符")


def _check_shensha_pillar(ctx: _FactCheckCtx, issues: list[str]) -> None:
    """神煞：柱位归属断言校验。

    配对口径（2026-09-11 修：旧版"同句共现即判错"会造成系统性误报）：
      1) 以「小句」为单位配对，按 。；;！!？? 换行 与 ，,、 切分；
      2) 小句内出现多个柱名时取离目标神煞最近者；最近距离并列的柱名只要有一个是该神煞
         的合法归属柱即放行（宁可不误杀）；
      3) 纯岁运神煞（原局四柱没有、只在大运/流年行出现）不按原局柱位判错：
         只有回答在小句里把它绑到某原局柱、且该小句无岁运语境时才记问题。
    """
    answer = ctx.answer
    for name in ctx.actual_shensha_all:
        if name not in answer:
            continue
        owners = [pn for pn in ctx.pillar_names if name in ctx.actual_shensha_by_pillar.get(pn, set())]
        is_dynamic = name in ctx.dynamic_shensha
        if not owners and not is_dynamic:
            continue  # 归属不明（全局项或流年窗口外的神煞）→ 不做柱位校验
        # 子串消歧后的文本（等长替换，"正学堂"不再被当作"学堂"）
        for clause in _CLAUSE_SPLIT.split(_scan_text_for(answer, name)):
            if name not in clause:
                continue
            anchors = [pn for pn in ctx.pillar_names if pn in clause]
            if not anchors:
                continue
            t_pos = clause.find(name)
            dist = {pn: abs(clause.find(pn) - t_pos) for pn in anchors}
            nearest_d = min(dist.values())
            nearest = [pn for pn in anchors if dist[pn] == nearest_d]
            if any(pn in owners for pn in nearest):
                continue  # 最近柱名即合法归属柱 → 通过
            if _DYNAMIC_CTX.search(clause):
                continue  # 该小句在讲流年/大运 → 不是原盘柱位断言
            a_pos = clause.find(nearest[0])
            # 排除否定：如"日柱没有金舆"不算错误归属断言
            if _sentence_has_negative_between(clause, a_pos, t_pos, name):
                continue
            if owners:
                issues.append(
                    f"「{name}」属于{'、'.join(owners)}，回答却关联到{nearest[0]}，与神煞事实不符"
                )
            else:
                issues.append(
                    f"「{name}」只出现在大运/流年（原局无此神煞），回答却关联到{nearest[0]}，与神煞事实不符"
                )
            break


# ───────────────────────── 编排器 ─────────────────────────

def check_facts(
    answer: str,
    chart: BaziChart,
    other_chart: BaziChart | None = None,
    needs_chart: bool = True,
    facts_text: str = "",
) -> FactCheckResult:
    """校验回答中的四柱/大运/流年/十神/神煞是否与系统排盘一致。

    Args:
        other_chart: 合婚双盘时的对方命盘，同一干支若出现在任一张合法盘上即视为正确。
        needs_chart: 当前回答是否属于"绑定命盘分析"场景（命盘分析/合婚/流年大运推演等）。
            - True（默认）：严格校验十神/神煞的存在性与柱位归属，禁止凭空捏造
            - False（理论/术语解释场景）：仅校验**归属断言**（"你命盘有X""年柱X"等绑定命盘的表述），
              纯术语解释（"红鸾主喜庆""正财代表求财"）不受限，避免误杀理论问答。
        facts_text: 发给 LLM 的命盘事实文本（compact_facts 输出）。
            审核员从中提取 LLM 可见的十神/神煞，确保与 LLM 看到的一致，
            避免流年/大运神煞被误判为"排盘事实中无"。
    """
    # 流年/大运干支映射（含合婚双盘）
    year_to_gz: dict[int, str] = {item.year: item.ganzhi for item in chart.liunian}
    dayun_gz: set[str] = {d.ganzhi for d in chart.dayun}
    if other_chart is not None:
        for item in other_chart.liunian:
            year_to_gz.setdefault(item.year, item.ganzhi)
        dayun_gz |= {d.ganzhi for d in other_chart.dayun}

    # 每个柱名下，两张盘各自合法的干支都算正确
    valid: dict[str, set[str]] = {}
    for p in chart.pillars:
        valid.setdefault(p.name, set()).add(p.ganzhi)
    if other_chart is not None:
        for p in other_chart.pillars:
            valid.setdefault(p.name, set()).add(p.ganzhi)
    primary = {p.name: p.ganzhi for p in chart.pillars}

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

    # 从 LLM 可见的事实文本中补充十神/神煞（流年/大运/岁运关系中的），
    # 确保审核员与 LLM 看到一致的命盘信息，避免流年神煞被误判为"排盘事实中无"
    if facts_text:
        for ss in SHISHEN_NAMES:
            if ss in facts_text:
                actual_shishen.add(ss)
        for name in SHENSHA_NAMES:
            if name in facts_text:
                actual_shensha_all.add(name)

    # 纯岁运神煞（原局四柱没有、只在大运/流年行出现）= 结构化神煞 - 原局静态神煞
    pillar_names = [p.name for p in chart.pillars]
    static_shensha_all: set[str] = set()
    for _names in actual_shensha_by_pillar.values():
        static_shensha_all |= _names
    dynamic_shensha: set[str] = set()
    for _src in [chart] + ([other_chart] if other_chart else []):
        for _item in list(_src.dayun) + list(_src.liunian):
            for _s in getattr(_item, "shensha", None) or []:
                if isinstance(_s, dict) and _s.get("name"):
                    dynamic_shensha.add(_s["name"])
    dynamic_shensha -= static_shensha_all

    ctx = _FactCheckCtx(
        chart=chart,
        other_chart=other_chart,
        answer=answer,
        needs_chart=needs_chart,
        facts_text=facts_text,
        year_to_gz=year_to_gz,
        dayun_gz=dayun_gz,
        valid=valid,
        primary=primary,
        pillar_names=pillar_names,
        actual_shishen=actual_shishen,
        actual_shensha_all=actual_shensha_all,
        actual_shensha_by_pillar=actual_shensha_by_pillar,
        dynamic_shensha=dynamic_shensha,
    )

    issues: list[str] = []
    _check_liunian_ganzhi(ctx, issues)
    _check_dayun_ganzhi(ctx, issues)
    _check_pillar_ganzhi(ctx, issues)
    _check_shishen_pairs(ctx, issues)
    _check_shishen_single(ctx, issues)
    _check_shensha_existence(ctx, issues)
    _check_shensha_pillar(ctx, issues)

    return FactCheckResult(ok=not issues, issues=issues)
