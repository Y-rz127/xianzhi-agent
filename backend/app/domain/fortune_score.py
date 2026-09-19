"""岁运运势评分（纯函数，无 IO、无 LLM、无随机）。

定位
----
「命理 K 线」的确定性底座：把每个岁运柱对原局的顺逆换算成 0-100 分，
使年 K 线的 open/close/high/low 每一个值都有出处，可黄金快照回归。

与 `analysis_calc.strength_score` 的分工（**刻意不合并**）
------------------------------------------------------
- `strength_score` = 原局四柱对日主的「扶助 − 压制」，被 36 个黄金盘锚定，是
  **原局静态**量。本模块只读不改。
- 本模块的 `delta` = 岁运柱（大运/流年/流月）五行加权 与 原局喜忌方向 的点乘，
  是**时间轴上的动态**量。

两者量纲不同、用途不同。历史上「干支关系两套口径」曾让 36 个黄金盘里 34 个
结论不一致（见 `analysis_calc` 文件末尾注释），此处刻意不重演：合冲刑害一律委托
`yun_relations.relations_for`，本模块**不自行判定关系**，也不复制五行生克表。

确定性边界
----------
本模块的所有输出只由 `BaziChart` 决定，不含时间、随机、LLM 输入。因此同一命盘
任意次调用结果全等，可直接进黄金快照。大模型只允许在**批注文本**层出现，且
不参与此处任何数值。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.analysis_calc import _controller_of, _producer_of
from app.domain.chart_builder import _find_dayun_for_year, parse_birth, parse_gender
from app.domain.ganzhi_relations import branch_relations
from app.domain.models import BaziChart
from app.domain.tables import CONTROLS, GAN_WUXING, GENERATES, HIDDEN_STEMS, WUXING_ORDER, ZHI_WUXING
from app.domain.xipan import _MONTH_ZHI, _month_ganzhi, _year_ganzhi
from app.domain.yun_relations import relations_for

# ---------------- 喜忌基准系数 ----------------
# 沿用 analysis_calc 的扶助/压制系数，保证「原局强弱」与「岁运顺逆」两套量纲可比。
SAME_COEF = 1.0  # 比劫
RESOURCE_COEF = 0.85  # 印枭
OUTPUT_COEF = 0.55  # 食伤
WEALTH_COEF = 0.7  # 财
OFFICER_COEF = 0.8  # 官杀

# ---------------- 岁运柱权重 ----------------
# 大运为纲（管十年）、流年为目、流月为最小刻度。三者归一后合成一个 delta，
# 故「大运定基调、流年定年份差异、流月定年内波动」——这正是 K 线的宏观/微观分层。
W_DAYUN = 0.5
W_LIUNIAN = 0.3
W_LIUYUE = 0.2

# ---------------- 分数映射 ----------------
# delta ∈ [-1, 1] → 50 ± K_SCORE。
# K_SCORE=40 由 36 个黄金盘 / 2776 个年份实测标定，不是拍脑袋：
#   全局 close 分位 1/5/25/50/75/95/99 = 22.4 / 30.9 / 43.9 / 52.0 / 60.1 / 70.4 / 76.7，
#   触及 0/100 硬边界 0 次，单盘年内跨度 24-54、标准差 6.0-14.5。
# 即：既不饱和（无一味贴顶贴底），也不压缩在 50 附近。
# 改这里必须重跑标定并重生成 kline_golden 快照。
K_SCORE = 40.0
SCORE_MIN = 0.0
SCORE_MAX = 100.0

# 中和档的倾斜下限：tilt 为 0 时也要给出方向，否则全盘 50 分、无区分度。
BALANCED_FLOOR = 0.4
# 中和档 tilt 的归一尺度（与 analysis_calc 的「偏旺」阈值同值，口径对齐）
BALANCED_TILT_SPAN = 2.2

# 印重判据：印权重 ≥ 比劫 × 该倍数，且印为五行之最重者。见 `_resource_dominant`。
RESOURCE_DOMINANT_RATIO = 1.5

# 杀重判据（两条成立其一，均要求官杀为五行之最重）：
#   ① 官杀 ≥ 比劫 × OFFICER_DOMINANT_RATIO；
#   ② 比劫之根被原局六冲伤及 —— 根气虚浮，纯计数高估了比劫一党的抗杀之力。
OFFICER_DOMINANT_RATIO = 1.15
# 制化通道门槛：印（化杀）或食伤（制杀）≥ 官杀 × 该倍数即视为「有制有化」——
# 杀印相生、食神制杀都是成格而不为病，不得进病药路径。
OFFICER_MEDICINE_RATIO = 0.5

# ---------------- 维度（十神侧重） ----------------
# 「维度」不是换一套算法，而是**换一组十神侧重**：喜忌方向仍由原局决定（偏弱喜比印、
# 偏旺喜食财官、从格顺势），变的只是「哪一路十神对这条曲线更敏感」。
# 后者是命理上早就成立的取象（论事业看官杀、论财看财星、男以财为妻女以官杀为夫），
# 所以维度增强的是**同一套确定性口径的取象能力**，不是引入新的不确定来源。
#
# key 与 `agent.workflow.workflow_models.DOMAIN_LABELS` 对齐（career/wealth/love/health/study），
# 以便将来 K 线维度与对话领域共用一套命名；comprehensive 是额外加的总纲维度。
DIM_COMPREHENSIVE = "comprehensive"
DIMENSIONS = ("comprehensive", "career", "wealth", "love", "health", "study")
DIMENSION_LABELS = {
    "comprehensive": "综合",
    "career": "事业",
    "wealth": "财运",
    "love": "感情",
    "health": "健康",
    "study": "学业",
}
# 给前端做维度副标题的一句话取象说明。放后端是为了单一事实源 ——
# 前端只显示，不解释命理口径。
DIMENSION_NOTES = {
    "comprehensive": "总纲：日主得扶助则升、受克泄则降",
    "career": "侧重官杀与印枭：论事业地位、权柄与资历",
    "wealth": "侧重财星与食伤：论财源与生财之力",
    "love": "男重财星、女重官杀：论感情缘分之向背",
    "health": "侧重比劫与官杀：论元气与攻身之病",
    "study": "侧重印枭与食伤：论学业文书、聪慧与考试发挥",
}

# 相对侧重（未归一，1.0 = 与综合维度同等敏感）。数值表达的是十神在对应人事上的份量，
# 精确性由 `dimension_emphasis` 的均值归一 + `scripts/kline_diagnose.py` 逐维度体检兜住。
_DIM_EMPHASIS = {
    DIM_COMPREHENSIVE: {"比劫": 1.0, "印枭": 1.0, "食伤": 1.0, "财": 1.0, "官杀": 1.0},
    # 官杀为事业之本、印为权柄资历；财耗身、比劫夺权，权重下调
    "career": {"比劫": 0.8, "印枭": 1.3, "食伤": 0.8, "财": 0.7, "官杀": 1.6},
    # 财为财源、食伤生财；印夺食伤之源、官杀泄财之气，权重下调
    "wealth": {"比劫": 0.9, "印枭": 0.7, "食伤": 1.4, "财": 1.8, "官杀": 0.7},
    # 比劫为自身元气、印为养护、官杀为攻身之病；财耗身
    "health": {"比劫": 1.5, "印枭": 1.3, "食伤": 1.1, "财": 0.8, "官杀": 1.4},
    # 印为学业文书之本（学堂词馆皆印）、食伤为聪慧与临场发挥；
    # 财坏印夺志（读书人最忌分心于财）、比劫为同窗之争；官杀主功名属事业维度，取基线
    "study": {"比劫": 0.7, "印枭": 1.8, "食伤": 1.3, "财": 0.6, "官杀": 1.0},
}
# 感情维度男女取用相反：男以财为妻（比劫夺财则争），女以官杀为夫（食伤克官则阻）
_DIM_EMPHASIS_LOVE_MALE = {"比劫": 0.7, "印枭": 1.1, "食伤": 0.9, "财": 1.7, "官杀": 0.8}
_DIM_EMPHASIS_LOVE_FEMALE = {"比劫": 0.9, "印枭": 1.1, "食伤": 0.7, "财": 0.9, "官杀": 1.7}

# ---------------- 关系修正 ----------------
# 对「分数」的修正：正 = 加分。冲刻意记 0.0 —— 冲定波动不定吉凶，见 REL_VOL。
REL_SCORE_ADJ = {"合": 2.0, "冲": 0.0, "刑": -2.0, "害": -1.5, "破": -1.0}
# 伏吟/反吟/天克地冲/岁运并临：按词命中，不走 _classify
ZHU_SCORE_ADJ = {"伏吟": -1.0, "反吟": -2.0}
TKD_CHONG_ADJ = -3.0  # 天克地冲
BING_LIN_ADJ = 2.0  # 岁运并临
# 对「波动」（影线长度）的放大：冲主变动，必然放大振幅，与所冲之神喜忌无关。
REL_VOL = {"冲": 1.6, "刑": 0.8, "害": 0.6, "破": 0.4, "合": -0.3}

_REL_KINDS = ("合", "冲", "刑", "害", "破")

# 全部干支字符，用于判断一条关系串是否真的牵扯岁运柱
_GANZHI_CHARS = frozenset(GAN_WUXING) | frozenset(ZHI_WUXING)


@dataclass(frozen=True)
class Candle:
    """一根年 K 线。每个字段都可追溯到月分数或关系计数。"""

    year: int
    age: int  # 虚岁，与 LiunianItem.age 同口径
    ganzhi: str  # 流年干支（立春换岁）
    dayun: str  # 所在大运干支；童限期为空
    open: float
    close: float
    high: float
    low: float
    volume: float  # 年内相邻月分数变化绝对值之和
    month_scores: list[float]
    relations: list[str] = field(default_factory=list)
    relation_adj: float = 0.0
    volatility: float = 0.0
    is_dayun_start: bool = False

    @property
    def is_up(self) -> bool:
        """收 > 开。前端按国内习惯「涨红跌绿」着色。"""
        return self.close >= self.open


# ---------------- 喜忌方向 ----------------


def _conging_signs(
    strength: str, same: str, resource: str, output: str, wealth: str, officer: str
) -> dict[str, float]:
    """从格/假从的喜忌：顺势为喜，印比扶身反成羁绊。

    所从之神由格名给出（从财/从杀/从儿/从势）。「假从」与「真从」方向一致、
    力度不打折——真假之别在成格牢固度，不在喜忌方向。
    """
    kind = strength.replace("假从", "").replace("从", "").replace("格", "")
    if kind == "财":
        return {wealth: 1.0, output: 0.6, officer: 0.3, same: -1.0, resource: -1.0}
    if kind == "杀":
        # 食伤制杀为破格之神，忌得最重
        return {officer: 1.0, wealth: 0.6, output: -0.8, same: -1.0, resource: -1.0}
    if kind == "儿":
        return {output: 1.0, wealth: 0.6, same: 0.2, resource: -1.0, officer: -0.5}
    if kind == "势":
        # 财官两行相当（黄金盘的从势格定义）
        return {wealth: 0.9, officer: 0.9, output: 0.4, same: -1.0, resource: -1.0}
    # 未知子格：退化为「顺势忌扶身」，宁可方向保守，也不给错方向
    return {same: -1.0, resource: -1.0}


def _resource_dominant(counts: dict[str, float], same: str, resource: str) -> bool:
    """印重：印为五行之最重者，且显著重于比劫。

    两个条件缺一不可，各自负责一件事：
    - 「印为最重」说明病神所在（五行偏枯在印，见 04 文档 §三.1「五行偏枯」）。
    - 「显著重于比劫」把「旺由印致」与「比劫党众致旺」分开。后者本就该用官杀制身，
      不属印多之病，套病药论反而错。
    """
    if not counts or resource not in WUXING_ORDER or counts.get(resource, 0.0) <= 0:
        return False
    if max(WUXING_ORDER, key=lambda k: counts.get(k, 0.0)) != resource:
        return False
    return counts.get(resource, 0.0) >= counts.get(same, 0.0) * RESOURCE_DOMINANT_RATIO


def _same_root_clashed(zhis: list[str], same: str) -> bool:
    """比劫之根（主气属比劫的地支）是否被原局六冲伤及。

    六冲判定委托 `ganzhi_relations.branch_relations`（原局内部关系的单一事实源，
    与 `analysis_calc` 同一入口）。藏干余气之根不计 —— 那是「有根」而非「有强根」，
    折算进判据会让门槛失真。
    """
    roots = {z for z in zhis if ZHI_WUXING.get(z) == same}
    if not roots:
        return False
    return any(any(root in rel for root in roots) for rel in branch_relations(zhis).chong)


def _officer_dominant(
    counts: dict[str, float],
    zhis: list[str],
    same: str,
    resource: str,
    output: str,
    officer: str,
) -> bool:
    """杀重：官杀为五行之最重、且原局无制无化，克身成病。

    与印重互斥（两者都要求自己是「最重」）。三个先决条件各自负责一件事：
    - 「官杀为最重」说明病神所在（五行偏枯在官杀，04 文档 §三.1「官杀太重」）；
    - 「印、食伤皆 ≤ 官杀 × OFFICER_MEDICINE_RATIO」把「杀重无制」与
      「杀印相生 / 食神制杀」分开 —— 后两者是成格，官杀是被用的对象，不是病，
      套病药论反而会把「印夺食 / 伤用神」说成吉；
    - 「官杀显著重于比劫，或比劫之根被冲」回应的是：比劫党众硬抗能把 score 顶进
      中和正侧，数值上「补平」了官杀的压制，但硬抗不等于制化（见 `_officer_ailment_signs`）。
    """
    if not counts or officer not in WUXING_ORDER or counts.get(officer, 0.0) <= 0:
        return False
    if max(WUXING_ORDER, key=lambda k: counts.get(k, 0.0)) != officer:
        return False
    if counts.get(resource, 0.0) > counts.get(officer, 0.0) * OFFICER_MEDICINE_RATIO:
        return False
    if counts.get(output, 0.0) > counts.get(officer, 0.0) * OFFICER_MEDICINE_RATIO:
        return False
    if counts.get(officer, 0.0) >= counts.get(same, 0.0) * OFFICER_DOMINANT_RATIO:
        return True
    return _same_root_clashed(zhis, same)


def _ailment_signs(same: str, resource: str, output: str, wealth: str, officer: str) -> dict[str, float]:
    """印多之病 → 药：以财制印、以比劫泄印（04 文档 §三.2）；官杀生印，是给病神添柴。

    **术语**：印为忌时财去克印是「财制印」（用药）；印为用时被财克才叫「财坏印」（破格）。
    二者字面相近而吉凶相反，此处必须写「制印」。

    食伤为病神（印）所克，是这场病里最受伤的一路，故同列喜神。
    印为病神本身，忌得比其余任何一路都重（1.2 > 1.0），
    否则「最忌」会被基准系数截胡，落不到病神头上。
    """
    return {same: 0.8, resource: -1.2, output: 0.7, wealth: 1.0, officer: -0.9}


def _officer_ailment_signs(
    same: str, resource: str, output: str, wealth: str, officer: str
) -> dict[str, float]:
    """杀重之病 → 药：食伤制杀、印化杀（04 文档 §三.2）；财滋杀，是给病神添柴。

    **术语**：杀为病时食伤克杀是「制杀」（用药）；杀为用（从杀格、杀印相生）时
    食伤克杀才是「破格」。字面相近而吉凶相反，与印重路径的「制印/坏印」辨析同构。

    食伤 sign 取 1.6：× OUTPUT_COEF(0.55) = 0.88，方能压过印 ×RESOURCE_COEF(0.85) = 0.85，
    保住「有杀先论杀、制杀为先」的次序 —— 金木交战等贴局亦以食伤通关制杀为急务，
    印化杀为辅，比劫硬抗再次（能分力但制不了病）。
    官杀为病神本身，忌得最重（1.2），否则「最忌」会被基准系数截胡。
    """
    return {same: 0.8, resource: 1.0, output: 1.6, wealth: -0.9, officer: -1.2}


def _balanced_signs(
    score: float, same: str, resource: str, output: str, wealth: str, officer: str
) -> dict[str, float]:
    """中和档：喜忌本不显著，以 strength_score 的符号定方向并压低强度。

    严格说明：中和应「取格局用神」，而格局取用尚未量化。此处以强弱符号作近似，
    方向可靠性弱于偏旺/偏弱档，故强度封在 [BALANCED_FLOOR, 1.0]；
    下限的存在是为了保证有区分度，而不是为了数值好看。
    """
    tilt = max(-1.0, min(1.0, score / BALANCED_TILT_SPAN))
    m = BALANCED_FLOOR + (1.0 - BALANCED_FLOOR) * abs(tilt)
    if tilt >= 0:  # 略偏旺 → 走偏旺侧（喜泄耗制衡）
        return {same: -m, resource: -0.8 * m, output: m, wealth: m, officer: m}
    return {same: m, resource: m, output: -0.6 * m, wealth: -m, officer: -m}


def favor_vector(chart: BaziChart) -> dict[str, float]:
    """原局喜忌方向：五行 → 带系数的倾向（正=喜，负=忌）。

    先由 `special_pattern` 分流（专旺/从格的取用与正格相反），再按 `strength` 五档定向。
    """
    w = chart.wuxing
    day_wx = w.day_master_wuxing
    if day_wx not in WUXING_ORDER:
        return {}
    same = day_wx
    resource = _producer_of(day_wx)
    output = GENERATES.get(day_wx, "")
    wealth = CONTROLS.get(day_wx, "")
    officer = _controller_of(day_wx)
    coef = {
        same: SAME_COEF,
        resource: RESOURCE_COEF,
        output: OUTPUT_COEF,
        wealth: WEALTH_COEF,
        officer: OFFICER_COEF,
    }
    zhis = [p.zhi for p in chart.pillars]

    if w.special_pattern == "专旺":
        # 顺其旺势：比劫/印/食伤泄秀为喜；官杀逆克激怒旺神，忌得最重
        signs = {same: 1.0, resource: 0.6, output: 0.5, wealth: -1.0, officer: -1.2}
    elif w.special_pattern in ("从格", "假从"):
        signs = _conging_signs(w.strength, same, resource, output, wealth, officer)
    elif w.strength in ("偏弱", "极弱"):
        signs = {same: 1.0, resource: 1.0, output: -0.6, wealth: -1.0, officer: -1.0}
    elif (
        w.strength != "极旺"
        and w.strength_score > 0
        and _resource_dominant(w.counts, same, resource)
    ):
        # 印重之病。扶抑档位只回答「日主强不强」，回答不了「强从何来」：
        # 印撑起来的身旺，若仍按偏旺取用，会得出「忌印却喜官杀」——官杀生印，
        # 是给病神添柴。此病按病药论改向（见 04 文档 §三.2）。
        # 三个排除条件：专旺/从格已在前分流；偏弱档印是日主靠山，不作病论；
        # 极旺近专旺，仍以顺其旺势为口径，不在此处改向。
        signs = _ailment_signs(same, resource, output, wealth, officer)
    elif (
        w.strength != "极旺"
        and w.strength_score > 0
        and _officer_dominant(w.counts, zhis, same, resource, output, officer)
    ):
        # 杀重之病。档位同样回答不了「克从何来」：比劫党众硬抗能把 score 顶进
        # 中和/偏旺正侧，方向表随之给出「最喜官杀」——给病神添柴。典型事故盘：
        # 乙酉×3 乙卯（三酉冲一卯），天干四乙把 +0.44 的贴零分补成正侧。
        # 排除条件与印重同构，另加「有制有化不为病」（杀印相生/食神制杀是成格）。
        signs = _officer_ailment_signs(same, resource, output, wealth, officer)
    elif w.strength in ("偏旺", "极旺"):
        signs = {same: -1.0, resource: -0.8, output: 1.0, wealth: 1.0, officer: 1.0}
    else:
        signs = _balanced_signs(w.strength_score, same, resource, output, wealth, officer)

    return {wx: round(signs.get(wx, 0.0) * coef.get(wx, 0.0), 4) for wx in WUXING_ORDER}


# ---------------- 维度侧重 ----------------


def _shishen_of_wuxing(day_wx: str) -> dict[str, str]:
    """相对日主，五行 → 十神组名。五个键必然互不相同（五行同构置换）。"""
    return {
        "比劫": day_wx,
        "印枭": _producer_of(day_wx),
        "食伤": GENERATES.get(day_wx, ""),
        "财": CONTROLS.get(day_wx, ""),
        "官杀": _controller_of(day_wx),
    }


def dimension_emphasis(chart: BaziChart, dimension: str = DIM_COMPREHENSIVE) -> dict[str, float]:
    """维度 → {五行: 侧重系数}；综合维度返回空表（表示「不偏」）。

    **均值归一到 1.0**：若不归一，事业维度的官杀×1.6 会把整条曲线整体抬高，
    切维度就变成换量纲，`K_SCORE=40` 的标定随之失效。归一后各维度总量级一致、
    只有形状不同 —— 这正是「切维度只换取象、不换刻度」。
    """
    if dimension == DIM_COMPREHENSIVE or dimension not in DIMENSIONS:
        return {}
    if dimension == "love":
        raw = _DIM_EMPHASIS_LOVE_MALE if parse_gender(chart.birth.gender) == 1 else _DIM_EMPHASIS_LOVE_FEMALE
    else:
        raw = _DIM_EMPHASIS[dimension]

    day_wx = chart.wuxing.day_master_wuxing
    if day_wx not in WUXING_ORDER:
        return {}
    mean = sum(raw.values()) / len(raw)
    if mean <= 0:
        return {}
    by_wx: dict[str, float] = {}
    for name, mul in raw.items():
        wx = _shishen_of_wuxing(day_wx).get(name, "")
        if wx in WUXING_ORDER:
            by_wx[wx] = round(mul / mean, 4)
    return by_wx


def effective_favor(chart: BaziChart, dimension: str = DIM_COMPREHENSIVE) -> dict[str, float]:
    """维度下的实际喜忌权重：原局喜忌 × 该维度的十神侧重。"""
    favor = favor_vector(chart)
    empha = dimension_emphasis(chart, dimension)
    if not empha:
        return favor
    return {k: round(v * empha.get(k, 1.0), 4) for k, v in favor.items()}


# ---------------- 岁运柱 → delta ----------------


def pillar_weights(ganzhi: str) -> dict[str, float]:
    """单柱五行权重（天干 1.0、地支 1.0、藏干按比例），归一到 1.0。

    岁运柱不像原局有「月令」，故不设 1.6 加权 —— 原局那个加权属于
    `analysis_calc` 的静态口径，不搬到时间轴上。
    """
    if not ganzhi or len(ganzhi) != 2:
        return {}
    out = dict.fromkeys(WUXING_ORDER, 0.0)
    total = 0.0
    gwx = GAN_WUXING.get(ganzhi[0])
    if gwx:
        out[gwx] += 1.0
        total += 1.0
    zwx = ZHI_WUXING.get(ganzhi[1])
    if zwx:
        out[zwx] += 1.0
        total += 1.0
    for hidden, ratio in HIDDEN_STEMS.get(ganzhi[1], ()):
        hwx = GAN_WUXING.get(hidden)
        if hwx:
            out[hwx] += ratio
            total += ratio
    if total <= 0:
        return {}
    return {k: v / total for k, v in out.items()}


def pillar_delta(favor: dict[str, float], ganzhi: str) -> float:
    """一个岁运柱与喜忌方向的点乘。"""
    weights = pillar_weights(ganzhi)
    if not weights or not favor:
        return 0.0
    return sum(favor.get(k, 0.0) * v for k, v in weights.items())


def score_delta(
    chart: BaziChart,
    *,
    dayun: str = "",
    liunian: str = "",
    liuyue: str = "",
    dimension: str = DIM_COMPREHENSIVE,
) -> float:
    """大运/流年/流月加权合成 delta（按实际存在者重新归一）。

    童限期无大运可论，权重自动落到流年与流月，而非留空拉低分数。
    喜忌用 `effective_favor`（含维度侧重），故换维度即换曲线形状。
    """
    parts = [(W_DAYUN, dayun), (W_LIUNIAN, liunian), (W_LIUYUE, liuyue)]
    used = [(w, gz) for w, gz in parts if len(gz) == 2]
    if not used:
        return 0.0
    favor = effective_favor(chart, dimension)
    if not favor:
        return 0.0
    total_w = sum(w for w, _ in used)
    return sum(w * pillar_delta(favor, gz) for w, gz in used) / total_w


def delta_to_score(delta: float) -> float:
    """delta → 0-100 分。截断在两端，避免极端盘越界。"""
    bounded = max(-1.0, min(1.0, delta))
    return round(max(SCORE_MIN, min(SCORE_MAX, 50.0 + K_SCORE * bounded)), 1)


# ---------------- 关系修正 ----------------


def _involves_sui(rel: str, sui_chars: frozenset[str]) -> bool:
    """关系串是否真的牵扯到岁运柱。

    `_build_relations` 的岁运栏会把「岁运 + 原局」**合并后**判三合/三刑，因此
    可能返回纯原局内部的组合（实测：stem_jia 原局为 甲子/丙子/甲辰/甲子，
    其 子辰半合水 逐年恒定、与流年无关）。这类条目若计入关系修正，会给出一个
    与岁运无关的固定加减分，并在前端被误读成"今年的合/破"。

    此处只做**筛选**，不改任何判定口径——关系怎么判仍由 `_build_relations` 说了算。
    筛选方向偏保守：只要串里出现任一岁运字符就保留。
    """
    return bool((_GANZHI_CHARS & set(rel)) & sui_chars)


def _zhi_rel_of_sui(zhi_rel: list[str], *ganzhis: str) -> list[str]:
    """从岁运栏地支关系中剔除纯原局内部的条目（详见 `_involves_sui`）。

    只用于地支：`gan_rel`（仅 岁运×原局 / 岁运×岁运）与 `zhu_rel`（仅 岁运×原局）
    本就不含原局内部组合，无需过滤。
    """
    sui_chars = frozenset(ch for gz in ganzhis if len(gz) == 2 for ch in gz)
    if not sui_chars:
        return list(zhi_rel)
    return [rel for rel in zhi_rel if _involves_sui(rel, sui_chars)]


def classify_relations(rels: list[str]) -> dict[str, int]:
    """按关键词把关系串归到 合/冲/刑/害/破 五类。

    同一对地支可同时成立（如「巳申合水」与「巳申破」并存），故各类分别计数、
    不做互斥，这与 `ganzhi_relations` 的「六破独立成类」口径一致。

    「天克地冲」跳过归类：它已由 `relation_adjust` 单独按 `TKD_CHONG_ADJ` 计，
    若再被当作一个「冲」会重复计一次，等于把同一件事罚两遍。
    """
    counts = dict.fromkeys(_REL_KINDS, 0)
    for rel in rels:
        if "天克地冲" in rel:
            continue
        for kind in _REL_KINDS:
            if kind in rel:
                counts[kind] += 1
                break
    return counts


def relation_adjust(counts: dict[str, int], rels: list[str]) -> float:
    """关系对分数的修正。冲记 0 —— 吉凶取决于所冲之神，不在此处判。"""
    adj = sum(REL_SCORE_ADJ[kind] * n for kind, n in counts.items())
    if any("天克地冲" in r for r in rels):
        adj += TKD_CHONG_ADJ
    if any("岁运并临" in r for r in rels):
        adj += BING_LIN_ADJ
    for word, delta in ZHU_SCORE_ADJ.items():
        if any(word in r for r in rels):
            adj += delta
    return round(adj, 1)


def relation_volatility(counts: dict[str, int]) -> float:
    """关系对波动（影线）的放大。合会压缩振幅，冲刑害破放大振幅。"""
    return round(max(0.0, sum(REL_VOL[kind] * n for kind, n in counts.items())), 1)


# ---------------- 年份装配 ----------------


def _dayun_ganzhi_for_year(chart: BaziChart, year: int) -> str:
    """该年所在大运干支；童限期（起运前）返回空串。"""
    item = _find_dayun_for_year(chart.dayun, year)
    if item is None or len(item.ganzhi) != 2 or item.ganzhi[0] not in GAN_WUXING:
        return ""
    return item.ganzhi


def birth_year_of(chart: BaziChart) -> int:
    """出生公历年。`BirthInfo` 只存 solar 字符串，年份由此解析（与排盘同一入口）。"""
    return parse_birth(chart.birth.solar)[0]


def _month_ganzhis(year: int) -> list[str]:
    """该命理年（立春起）的 12 个节气月干支，寅月起。

    直接复用 xipan 的五虎遁，不走 `_build_liuyue_list` —— 后者顺带算 12 柱神煞，
    而评分与神煞无关，不该让 500 行的神煞逻辑进入这条路径。
    """
    year_gan = _year_ganzhi(year)[0]
    return [_month_ganzhi(year_gan, i) for i in range(len(_MONTH_ZHI))]


def year_relations(chart: BaziChart, year: int) -> list[str]:
    """该流年 ×（所在大运 + 原局）的关系串（含天克地冲/岁运并临）。

    刻意直接调 `relations_for` 传干支，**不经 `chart.liunian`**：后者按
    `liunian_years` 只覆盖 5 年（默认 2026-2030），而 K 线要跨 80 年，
    走那条路会让绝大多数年份的关系串为空、影线全为 0。

    已知继承特性：`_build_relations` 的岁运栏会把「岁运+原局」合并后判三合/半合，
    因此结果里可能夹带纯原局内部的组合（该部分逐年恒定，只造成一个常量偏移）。
    这是细盘岁运栏的既有口径，本模块**不另起一套**——历史上两套干支关系口径
    曾让 36 个黄金盘里 34 个结论不一致。
    """
    ganzhi = _year_ganzhi(year)
    dayun = _dayun_ganzhi_for_year(chart, year)
    it = relations_for(
        chart,
        dayun_ganzhi=dayun,
        liunian_ganzhi=ganzhi,
        label=f"{year}{ganzhi}",
    )
    rels = [*it.gan_rel, *_zhi_rel_of_sui(it.zhi_rel, dayun, ganzhi), *it.zhu_rel]
    if it.tian_ke_di_chong and "天克地冲" not in rels:
        rels.append("天克地冲")
    if it.sui_yun_bing_lin and "岁运并临" not in rels:
        rels.append("岁运并临")
    return rels


def month_scores(chart: BaziChart, year: int, *, dimension: str = DIM_COMPREHENSIVE) -> list[float]:
    """该年 12 个节气月的原始分数（未叠关系修正）。"""
    dayun = _dayun_ganzhi_for_year(chart, year)
    liunian = _year_ganzhi(year)
    return [
        delta_to_score(score_delta(chart, dayun=dayun, liunian=liunian, liuyue=gz, dimension=dimension))
        for gz in _month_ganzhis(year)
    ]


def build_candle(
    chart: BaziChart,
    year: int,
    *,
    prev_close: float | None = None,
    dimension: str = DIM_COMPREHENSIVE,
) -> Candle:
    """年 K 线：由该年 12 个节气月分数聚合，再叠关系修正。

    开 = **上年收盘**（首年无上年，取寅月立春分数）、收 = 丑月小寒分数、
    高/低 = 12 月极值 ± 波动（并包络开收，保证高≥开收≥低），
    量 = 年内相邻月分数变化绝对值之和 + 年初跳空。四个价格值每一个都能追到月分数。

    为什么开取上年收盘而不是寅月分数
    --------------------------------
    寅月属木、丑月属土，两者只差 `W_LIUYUE` 的流月项，而这两个地支的**固定五行差**
    远大于随年份波动的月干差，于是实体方向被"该盘喜木还是喜土"永久锁死。实测 36 个
    黄金盘：寅月/丑月口径下**没有任何一个命盘同时出现阳线与阴线**（各自全阳或全阴），
    实体方向零信息量；改取上年收盘后 36/36 盘都有阳有阴、阳线率 50.0%，
    且实体/振幅由 0.401 升至 0.425（反而更饱满）。

    该口径下实体 = 同比运势升降（阳线=比上年好），与 `dayunBands`（十年均线带）
    天然咬合；影线 = 年内波动，仍由 12 个节气月与关系波动量决定。
    """
    raw = month_scores(chart, year, dimension=dimension)
    rels = year_relations(chart, year)
    counts = classify_relations(rels)
    adj = relation_adjust(counts, rels)
    series = [round(max(SCORE_MIN, min(SCORE_MAX, s + adj)), 1) for s in raw]
    vol = relation_volatility(counts)

    open_ = series[0] if prev_close is None else round(prev_close, 1)
    close = series[-1]
    dayun = _dayun_ganzhi_for_year(chart, year)
    birth_year = birth_year_of(chart)
    return Candle(
        year=year,
        age=year - birth_year + 1,
        ganzhi=_year_ganzhi(year),
        dayun=dayun,
        open=open_,
        close=close,
        high=round(min(SCORE_MAX, max(max(series), open_, close) + vol), 1),
        low=round(max(SCORE_MIN, min(min(series), open_, close) - vol), 1),
        volume=round(
            abs(series[0] - open_)
            + sum(abs(series[i] - series[i - 1]) for i in range(1, len(series))),
            1,
        ),
        month_scores=series,
        relations=rels,
        relation_adj=adj,
        volatility=vol,
        is_dayun_start=bool(dayun) and any(
            d.start_year == year and d.ganzhi == dayun for d in chart.dayun
        ),
    )


def kline_years(chart: BaziChart, *, max_age: int = 80) -> list[int]:
    """K 线年份范围：**起运年** → 出生年 + max_age − 1（即覆盖到 max_age 虚岁）。

    起点取起运年而非出生年：童限期无大运可论，命理上不以大运刻度衡量。
    童限期补线（以当年小运代大运）留待后续单独处理，不在本阶段混入口径。

    终点用 `− 1`：虚岁 = 年 − 出生年 + 1，故"覆盖到 N 岁"对应最后一年 = 出生年 + N − 1。
    """
    if not chart.dayun:
        return []
    start = chart.dayun[0].start_year
    end = birth_year_of(chart) + max_age - 1
    return [y for y in range(start, end + 1)]


def build_kline(
    chart: BaziChart, *, max_age: int = 80, dimension: str = DIM_COMPREHENSIVE
) -> list[dict[str, Any]]:
    """整条人生 K 线（list[dict]，可直接序列化进快照/API）。

    逐年串联：每根蜡烛的 `open` = 上一根 `close`，首根取寅月分数。
    因此蜡烛首尾相接，不会出现无来由的跳空之外的价格断裂。
    `dimension` 只影响分数、不影响关系判定，故换维度不会改变 relations 字段。
    """
    out: list[dict[str, Any]] = []
    prev_close: float | None = None
    for year in kline_years(chart, max_age=max_age):
        candle = build_candle(chart, year, prev_close=prev_close, dimension=dimension)
        out.append(_candle_to_dict(candle))
        prev_close = candle.close
    return out


def _candle_to_dict(c: Candle) -> dict[str, Any]:
    return {
        "year": c.year,
        "age": c.age,
        "ganzhi": c.ganzhi,
        "dayun": c.dayun,
        "open": c.open,
        "close": c.close,
        "high": c.high,
        "low": c.low,
        "volume": c.volume,
        "monthScores": c.month_scores,
        "relations": c.relations,
        "relationAdj": c.relation_adj,
        "volatility": c.volatility,
        "isDayunStart": c.is_dayun_start,
        "isUp": c.is_up,
    }


def detect_ailment(chart: BaziChart) -> str:
    """原局病神代号；无病（或不在本引擎判据内）返回空串。

    目前识别两种能由五行权重 + 原局六冲确定性判定的病：
    - **印重**（resource_dominant）：旺由印撑，官杀生印反助病；
    - **杀重**（officer_dominant）：官杀最重且无制无化。比劫党众硬抗会把 score
      顶进中和/偏旺正侧，方向表随之误判「最喜官杀」，故须按病药论改向。
    其余病种（财多身弱 / 食伤泄身太过等）在 `strength` 五档里已被
    「偏弱喜印比、忌克泄耗」覆盖，不需另立分支。
    """
    w = chart.wuxing
    if w.special_pattern or w.strength in ("偏弱", "极弱", "极旺") or w.strength_score <= 0:
        return ""
    day_wx = w.day_master_wuxing
    if day_wx not in WUXING_ORDER:
        return ""
    if _resource_dominant(w.counts, day_wx, _producer_of(day_wx)):
        return "resource_dominant"
    if _officer_dominant(
        w.counts,
        [p.zhi for p in chart.pillars],
        day_wx,
        _producer_of(day_wx),
        GENERATES.get(day_wx, ""),
        _controller_of(day_wx),
    ):
        return "officer_dominant"
    return ""


# 病神 → 一句话依据。放在后端是为了单一事实源：前端只显示，不解释命理口径。
AILMENT_NOTES = {
    "resource_dominant": "病在印重：印为五行之最重、日主之旺独由印撑。以财制印、比劫泄印为药，官杀生印反助病。",
    "officer_dominant": "病在杀重：官杀为五行之最重、原局无制无化而攻身。以食伤制杀、印星化杀为药，财滋杀反助病。",
}


def chart_favor_summary(chart: BaziChart) -> dict[str, Any]:
    """喜忌方向的可读摘要（供 API/前端图例与调试使用）。"""
    favor = favor_vector(chart)
    ailment = detect_ailment(chart)
    return {
        "dayMaster": chart.wuxing.day_master,
        "dayMasterWuxing": chart.wuxing.day_master_wuxing,
        "strength": chart.wuxing.strength,
        "specialPattern": chart.wuxing.special_pattern,
        "favor": favor,
        "mostFavored": max(favor, key=favor.get) if favor else "",
        "mostOpposed": min(favor, key=favor.get) if favor else "",
        "ailment": ailment,
        "ailmentNote": AILMENT_NOTES.get(ailment, ""),
    }


def gender_int_of(chart: BaziChart) -> int:
    """命盘性别 → int（1 男 / 0 女），与 lunar-python 口径一致。"""
    return parse_gender(chart.birth.gender)
