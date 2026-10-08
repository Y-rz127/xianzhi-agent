"""命局结构分析：五行强弱、专旺/从格判定、十神统计、干支合冲刑害。"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.ganzhi_relations import branch_relations, stem_relations
from app.domain.models import DomainAnalysis, Pillar, WuxingAnalysis
from app.domain.tables import (
    CONTROLS,
    GAN_WUXING,
    GENERATES,
    HIDDEN_STEMS,
    SEASON_NOTES,
    WUXING_ORDER,
    ZHI_WUXING,
)

# 特殊格局判定阈值
_ZHUANWANG_DOM_RATIO = 0.60       # 主导五行占全局加权比例下限
_ZHUANWANG_PRESSURE_MAX = 2.0     # 克泄耗三行合计加权上限（超过视为破局，不判专旺）
_CONG_ROOT_MIN_HIDDEN = 0.30      # 藏干中某五行达此权重视为"本气级"（判透干印比是否有地支支撑）
_CONG_RESOURCE_MIN_HIDDEN = 0.30  # 同上，用于印星
_CONG_SECOND_RATIO = 0.80         # 从势判定：次旺/最旺 ≥ 此比例视为两行相当 → 从势

# 原 _CONG_SELF_WX_MAX = 0.50 已删除（2026-09-15）。
# 它比较的是"日主五行**绝对**权重"，而日干自身必然贡献 1.0，
# 该量最小值恒为 1.0（6 万样本实测 min=1.0）→ 守卫恒真、从格永不成立（死代码）。
# 同文件专旺侧用的是**占比**（_ZHUANWANG_DOM_RATIO），从格侧却用绝对量，量纲本就不一致。
# 日主无根/无印/无比劫的判定已由 _root_profile 完整承担，无需再设权重阈值。

_LU = {"甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳", "己": "午",
       "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}  # 日主禄地
_REN = {"甲": "卯", "乙": "辰", "丙": "午", "丁": "未", "戊": "午", "己": "未",
        "庚": "酉", "辛": "戌", "壬": "子", "癸": "丑"}  # 日主羊刃地
_KU = {"木": "未", "火": "戌", "金": "丑", "水": "辰"}  # 墓库；土寄四季，单独处理


def _producer_of(element: str) -> str:
    for src, dst in GENERATES.items():
        if dst == element:
            return src
    return ""


def _controller_of(element: str) -> str:
    for src, dst in CONTROLS.items():
        if dst == element:
            return src
    return ""


def _round_counts(counts: dict[str, float]) -> dict[str, float]:
    return {k: round(v, 2) for k, v in counts.items()}


def _root_branches_for_master(day_master: str) -> set[str]:
    """日主的根气地支集合 = 禄（_LU）+ 刃（_REN）；土并入四库，其余并入墓库。"""
    wx = GAN_WUXING.get(day_master, "")
    s = {_LU.get(day_master, ""), _REN.get(day_master, "")}
    s.discard("")
    if wx == "土":
        s.update(["辰", "戌", "丑", "未"])
    else:
        ku = _KU.get(wx)
        if ku:
            s.add(ku)
    return s


_ZHUANWANG_NAME = {"水": "润下格", "火": "炎上格", "木": "曲直格", "金": "从革格", "土": "稼穑格"}


# ---------------- 日主根气画像（真从 / 假从 / 正格 三档的分档依据） ----------------
#
# 口径来源：`knowledge_docs/33_从格专旺化气体系.md`
#   §一.2「关键判定」：'地支藏干中只要有日主微根（如甲木见辰中乙木、亥中甲木），
#                       即不为真从，为假从。天干虚浮一比一印，亦为假从。'
#   §八.3「假从假化与正格的边界」：根极弱 → 假从；根有力 → 正格；印比有力 → 正格。
#   §八.1「现实」：假从居多，真从极少。
#
# 注意"微根"的门槛是**有一丝**，不是本气级 —— 故不能用 _CONG_ROOT_MIN_HIDDEN 当根气门槛。
# 该常量现在只用于判断"透干的印比在地支有没有本气级支撑"（虚浮 vs 有力）。

_VERDICT_SOLID = "有力"
_VERDICT_WEAK = "微根"
_VERDICT_NONE = "无根"


@dataclass(frozen=True)
class _RootProfile:
    """日主根气画像。`verdict` 是三档判定的唯一入口。"""

    lu_ren_ku: bool                    # 地支见禄/刃/墓库根
    hidden_day: float                  # 藏干中日主五行权重合计（含余气）
    hidden_resource: float             # 藏干中印星五行权重合计
    solid_support: tuple[str, ...]     # 印比透干且地支有本气级支撑
    floating_support: tuple[str, ...]  # 印比透干但地支无支撑（虚浮）

    @property
    def verdict(self) -> str:
        if self.lu_ren_ku or self.solid_support:
            return _VERDICT_SOLID
        if self.hidden_day > 0 or self.hidden_resource > 0 or self.floating_support:
            return _VERDICT_WEAK
        return _VERDICT_NONE


def _root_profile(pillars, day_master: str, day_wx: str, resource: str) -> _RootProfile:
    """采集日主根气画像。

    `pillars` 为四柱干支字符串（如 "甲子"）：`p[0]` 天干、`p[1]` 地支。
    日干本身即日主，不计入"比劫透干"，否则任何八字都会被判有比劫。
    """
    roots = _root_branches_for_master(day_master)
    lu_ren_ku = False
    hidden_day = 0.0
    hidden_resource = 0.0
    for p in pillars:
        if p[1] in roots:
            lu_ren_ku = True
        for h, ratio in HIDDEN_STEMS.get(p[1], ()):
            hw = GAN_WUXING.get(h)
            if hw == day_wx:
                hidden_day += ratio
            elif hw == resource:
                hidden_resource += ratio

    solid: list[str] = []
    floating: list[str] = []
    for i, p in enumerate(pillars):
        if i == 2:  # 日柱天干即日主
            continue
        gw = GAN_WUXING.get(p[0])
        if gw not in (day_wx, resource):
            continue
        # 透干五行在地支有无支撑：地支本气即该五行，或藏干累计达本气级
        supported = any(ZHI_WUXING.get(q[1]) == gw for q in pillars) or (
            sum(
                r for q in pillars for h, r in HIDDEN_STEMS.get(q[1], ()) if GAN_WUXING.get(h) == gw
            )
            >= _CONG_ROOT_MIN_HIDDEN
        )
        (solid if supported else floating).append(p[0])

    return _RootProfile(lu_ren_ku, hidden_day, hidden_resource, tuple(solid), tuple(floating))


def _detect_zhuanwang(weighted, day_wx, resource, officer, wealth, output):
    """极旺候选 → 专旺格判定；要求日主五行独旺且克泄耗无破局。返回 (kind, label, hint) 或 None。"""
    total = sum(weighted.values())
    if total <= 0:
        return None
    strongest = max(weighted, key=weighted.get)
    if strongest != day_wx:
        return None
    dom_ratio = weighted[strongest] / total
    pressure = weighted.get(officer, 0.0) + weighted.get(wealth, 0.0) + weighted.get(output, 0.0)
    if dom_ratio < _ZHUANWANG_DOM_RATIO:
        return None
    if pressure > _ZHUANWANG_PRESSURE_MAX:
        return None
    name = _ZHUANWANG_NAME.get(strongest)
    if not name:
        return None
    hint = (
        f"日主入{name}（一行独旺，候选专旺），宜顺其旺势，喜{resource or '印星'}、{day_wx}比劫相扶；"
        f"切忌{wealth or '财星'}、{officer or '官杀'}逆克激怒旺神。"
    )
    return "专旺", name, hint


# 从格：所从之神 → (格名, 用神提示)
_CONG_LABELS = {
    "官杀": ("从杀格", "日主无依从杀，喜{wealth}生{officer}、顺势御杀；切忌{resource}、{day_wx}比劫抗杀。"),
    "财": ("从财格", "日主无依从财，喜{output}生{wealth}、{officer}护财；切忌{resource}、{day_wx}比劫分财。"),
    "食伤": ("从儿格", "日主无依从儿（食伤），喜{wealth}流通秀气；切忌{resource}制儿、{officer}犯怒。"),
}
_CONG_SHISHI = ("从势格", "日主无依、官杀/财/食伤两三相混而势均力敌，入从势格；"
                           "宜顺势相从、随旺气流转，忌{resource}{day_wx}比劫扶身。")

# 假从的额外告诫（知识库 §八.1：「行顺从运可发，行帮身运即破败，根基不稳」）
_FAKE_TAIL = "行顺从运可发，行帮身运即破败，根基不稳，须先按正格参考。"

# 子格的破格之神（知识库 §二.1 / §三.1 / §四.1 第 4 条）：
#   从财格 — 无官杀泄财气（官杀虽克身但泄财，见官杀则不纯）
#   从杀格 — 无食伤制杀（食伤制杀则破从局）
#   从儿格 — 无印星克食伤（印克食伤则破从局）；该条已被"无根无印"前置条件覆盖，故恒满足
#   从势格 — 无（财官食伤皆旺，无一定之从）
_BREAKER_OF = {"财": "官杀", "官杀": "食伤", "食伤": "印星"}


def _breaker_element(follow: str, resource: str, officer: str, output: str) -> str:
    """取该子格破格之神的五行；未知子格返回空串。"""
    return {"财": officer, "官杀": output, "食伤": resource}.get(follow, "")


def _breaker_is_potent(pillars, breaker_wx: str) -> bool:
    """破格之神是否有力：**透干，或地支见其本气**。

    仅藏干余气/中气不算 —— 如土月丑/戌中藏的一点辛金（金为官杀），
    库中之气不足以泄财，不构成破格。判据与本文件 `_root_profile` 的
    "有力/虚浮"同一套机制，避免到处新造阈值。
    """
    if not breaker_wx:
        return False
    for i, p in enumerate(pillars):
        if i != 2 and GAN_WUXING.get(p[0]) == breaker_wx:
            return True
        if ZHI_WUXING.get(p[1]) == breaker_wx:
            return True
    return False


def _detect_conging(weighted, pillars, day_wx, day_master, resource, officer, wealth, output):
    """极弱候选 → 从格判定。返回 (kind, label, hint) 或 None。

    kind ∈ {"从格"(真从), "假从"}。四条判据对齐 `knowledge_docs/33_从格专旺化气体系.md`：
    1. 根气三档（`_RootProfile.verdict`）：有力 → 正格不论从；微根 → 假从；无根 → 真从候选。
    2. 全局气势专一：克泄耗中须有一行明显独旺，否则无从。
    3. 月令须为所从之神当令（§一.2 第 4 条）。
    4. **无破格之神**（§二.1/§三.1/§四.1 第 4 条）：该子格的破格之神有力则格局不纯。
    任一条不满足即降为假从，并在提示里写明降级之由（供 LLM 区分真假从的岁运断法）。
    """
    month_zhi = pillars[1][1]
    profile = _root_profile(pillars, day_master, day_wx, resource)
    if profile.verdict == _VERDICT_SOLID:
        return None  # 禄/刃/库根，或印比透干且有地支支撑 → 正格，不论从

    contenders = {
        "官杀": weighted.get(officer, 0.0),
        "财": weighted.get(wealth, 0.0),
        "食伤": weighted.get(output, 0.0),
    }
    best_name = max(contenders, key=contenders.get)
    if contenders[best_name] < 0.5:
        return None  # 没有一行明显独旺，无从

    vals = sorted(contenders.values(), reverse=True)
    is_shishi = vals[1] >= vals[0] * _CONG_SECOND_RATIO and vals[1] > 0
    follow_wx = {"官杀": officer, "财": wealth, "食伤": output}

    if is_shishi:
        # 从势无一定之从：月令落在克泄耗任一行即算当令；亦无破格之神
        label, template = _CONG_SHISHI
        month_ok = ZHI_WUXING.get(month_zhi, "") in (officer, wealth, output)
        impure = False
    else:
        label, template = _CONG_LABELS[best_name]
        month_ok = ZHI_WUXING.get(month_zhi, "") == follow_wx[best_name]
        breaker_wx = _breaker_element(best_name, resource, officer, output)
        impure = _breaker_is_potent(pillars, breaker_wx)

    hint = template.format(
        resource=resource or "印星", day_wx=day_wx,
        officer=officer or "官杀", wealth=wealth or "财星", output=output or "食伤",
    )
    if profile.verdict == _VERDICT_NONE and month_ok and not impure:
        return "从格", label, hint

    reasons = []
    if profile.verdict != _VERDICT_NONE:
        reasons.append("日主尚存微根或虚浮印比")
    if not month_ok:
        reasons.append("月令非所从之神当令")
    if impure:
        reasons.append(f"{_BREAKER_OF[best_name]}有力，泄耗所从之气，格局不纯")
    return "假从", f"假{label}", f"{hint}（假从之由：{'；'.join(reasons)}。{_FAKE_TAIL}）"


def _detect_special_pattern(pillars, weighted, day_wx, day_master, score,
                            resource, output, wealth, officer):
    """在 ±7 极端候选区做特殊格局识别：score ≥ 7 判专旺，score ≤ -7 判从格。

    返回 `kind` ∈ {"专旺", "从格"(真从), "假从", ""}。真假从的区分见 `_detect_conging`
    与 `knowledge_docs/33_从格专旺化气体系.md` §八：假从仍按所从之神取用，但行帮身运即破局。
    不落入极端区或判定不自信时返回 is_special=False。
    """
    if score >= 7:
        zw = _detect_zhuanwang(weighted, day_wx, resource, officer, wealth, output)
        if zw:
            kind, label, hint = zw
            return {"is_special": True, "kind": kind, "label": label, "useful_hint": hint}
    elif score <= -7:
        cg = _detect_conging(weighted, pillars, day_wx, day_master, resource, officer, wealth, output)
        if cg:
            kind, label, hint = cg
            return {"is_special": True, "kind": kind, "label": label, "useful_hint": hint}
    return {"is_special": False, "kind": "", "label": "", "useful_hint": ""}


def _classify_strength(
    score: float,
    day_wx: str,
    resource: str,
    same: str,
    output: str,
    wealth: str,
    officer: str,
) -> tuple[str, str]:
    """日主强弱五档分档（方案A），返回 (strength, useful_hint)。

    |score| ≥ 7 候选特殊格局；≥ 2.2 偏旺；≤ -1.2 偏弱；其余中和。
    极旺/极弱用神走顺势，与偏旺/偏弱的制衡/扶助方向相反。
    """
    if score >= 7:
        strength = "极旺"
        useful_hint = (
            f"日主极旺（候选专旺格），宜顺其旺势，喜{resource or '印星'}、{same or '比劫'}相扶；"
            f"若有{output or '食伤'}亦可泄秀，切忌{wealth or '财星'}、{officer or '官杀'}逆克激怒旺神。"
        )
    elif score >= 2.2:
        strength = "偏旺"
        useful_hint = f"日主偏旺，宜取泄耗制衡之气，优先关注{output or '食伤'}、{wealth or '财星'}、{officer or '官杀'}的配合。"
    elif score <= -7:
        strength = "极弱"
        useful_hint = (
            f"日主极弱（候选从格），宜顺势相从，不喜{resource or '印星'}、{same or '比劫'}扶身反成羁绊；"
            f"具体用神需结合所从五行（从{wealth or '财'} / 从{officer or '官'} / 从{output or '儿'} 等）判定。"
        )
    elif score <= -1.2:
        strength = "偏弱"
        useful_hint = f"日主偏弱，宜先扶助日主，重点看{resource or '印星'}与{same or '比劫'}是否得地。"
    else:
        strength = "中和"
        useful_hint = "格局接近平衡，喜忌需要结合大运流年触发点细看。"
    return strength, useful_hint


def _build_wuxing_analysis(ec) -> WuxingAnalysis:
    """基于四柱（含藏干）计算五行权重与日主强弱，并做特殊格局初判。

    权重：天干计 1.0、月令天干 1.2；地支计 1.0、月令地支 1.6；藏干按比例累加。
    强弱分 = 扶助（比劫 + 印枭×0.85）- 压制（食伤×0.55 + 财×0.7 + 官杀×0.8）。
    """
    pillars = [ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime()]
    visible_counts = {k: 0 for k in WUXING_ORDER}
    weighted = {k: 0.0 for k in WUXING_ORDER}

    for index, pillar in enumerate(pillars):
        gan, zhi = pillar[0], pillar[1]
        gan_wx = GAN_WUXING.get(gan)
        zhi_wx = ZHI_WUXING.get(zhi)
        stem_weight = 1.2 if index == 1 else 1.0
        branch_weight = 1.6 if index == 1 else 1.0
        if gan_wx:
            visible_counts[gan_wx] += 1
            weighted[gan_wx] += stem_weight
        if zhi_wx:
            visible_counts[zhi_wx] += 1
            weighted[zhi_wx] += branch_weight
        for hidden, ratio in HIDDEN_STEMS.get(zhi, ()):
            wx = GAN_WUXING.get(hidden)
            if wx:
                weighted[wx] += ratio * branch_weight

    day_master = ec.getDayGan()
    day_wx = GAN_WUXING.get(day_master, "未知")
    same = day_wx
    resource = _producer_of(day_wx)
    output = GENERATES.get(day_wx, "")
    wealth = CONTROLS.get(day_wx, "")
    officer = _controller_of(day_wx)

    support = weighted.get(same, 0.0) + weighted.get(resource, 0.0) * 0.85
    pressure = (
        weighted.get(output, 0.0) * 0.55
        + weighted.get(wealth, 0.0) * 0.7
        + weighted.get(officer, 0.0) * 0.8
    )
    strength_score = round(support - pressure, 2)
    strength, useful_hint = _classify_strength(
        strength_score, day_wx, resource, same, output, wealth, officer
    )
    # 仅在 ±7 极端候选区做特殊格局识别（专旺/从格）
    special_pattern = ""
    if abs(strength_score) >= 7:
        sp = _detect_special_pattern(
            pillars, weighted, day_wx, day_master, strength_score,
            resource, output, wealth, officer,
        )
        if sp["is_special"]:
            strength = sp["label"]
            useful_hint = sp["useful_hint"]
            special_pattern = sp["kind"]

    strongest = max(weighted, key=weighted.get)
    weakest = min(weighted, key=weighted.get)
    notes = [
        "五行权重已纳入天干、地支、藏干，并对月令加权；比单纯统计八个字更稳。",
        "强弱为工程化初判，最终用神仍需结合格局、调候、合冲刑害与大运流年校验。",
    ]
    return WuxingAnalysis(
        counts=_round_counts(weighted),
        visible_counts=visible_counts,
        strongest=strongest,
        weakest=weakest,
        day_master=day_master,
        day_master_wuxing=day_wx,
        strength=strength,
        strength_score=strength_score,
        useful_hint=useful_hint,
        special_pattern=special_pattern,
        notes=notes,
    )


def _count_ten_gods(pillars: list[Pillar]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pillar in pillars:
        if pillar.shishen_gan and pillar.shishen_gan != "日主":
            counts[pillar.shishen_gan] = counts.get(pillar.shishen_gan, 0) + 1
        for item in pillar.shishen_zhi:
            if item:
                counts[item] = counts.get(item, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


# 干支关系的实现已收敛到 `app.domain.ganzhi_relations`（单一事实源）：
# 原 `_branch_relations` / `_branch_combinations` / `_stem_relations` 三个私有函数
# 与 `xipan` 里的另一套并存，导致 36 个黄金命盘里 34 个两套结论不一致，已删除。
# 统一口径：半合/拱合纳入、三刑用「两支半刑」、六破独立成「破」、自刑统一命名。


def _build_domain_analysis(pillars: list[Pillar], wuxing: WuxingAnalysis) -> DomainAnalysis:
    """汇总十神、透干/根气、地支关系与季节调候，组装领域层分析对象。

    关系口径见 `app.domain.ganzhi_relations`（单一事实源）；本函数只做**视图映射**：
      合 = 干合(加前缀区分) + 六合 + 半合 + 拱合（合局力量：六合＞半合＞拱合）
      冲 = 干冲(加前缀区分) + 六冲
      害 = 六害
      破 = 六破            ← 独立成栏（原先被错放进「三合/三会」栏）
      刑 = 三刑 + 半刑 + 自刑
      三合/三会 = 完整三合局 + 三会方
    天干以「(干合)」「(干冲)」前缀并入，便于与地支关系区分；
    pattern_hint 保留空串维持 dataclass 契约（根气/合冲等已由结构化字段承载）。
    """
    day_master = wuxing.day_master
    visible_gans = [p.gan for p in pillars if p.gan]
    hidden_stems = [stem for p in pillars for stem in p.hidden_stems]
    exposed = [gan for gan in visible_gans if gan != day_master]
    rooted = sorted({day_master for stem in hidden_stems if stem == day_master})
    zhis = [p.zhi for p in pillars if p.zhi]

    rel = branch_relations(zhis)
    gan_he, gan_chong = stem_relations(visible_gans)

    combinations = [f"{g}(干合)" for g in gan_he] + [*rel.liu_he, *rel.ban_he, *rel.gong_he]
    clashes = [f"{c}(干冲)" for c in gan_chong] + list(rel.chong)
    harms = list(rel.hai)
    breaks = list(rel.po)
    punishments = [*rel.san_xing, *rel.ban_xing, *rel.zi_xing]
    three_assemblies = [*rel.hui, *rel.san_he]

    month_zhi = pillars[1].zhi if len(pillars) > 1 else ""
    adjustment = SEASON_NOTES.get(month_zhi, "调候需结合月令、寒暖燥湿与全局五行再定。")

    ten_gods = _count_ten_gods(pillars)
    pattern_hint = ""
    confidence = 0.72
    if month_zhi:
        confidence += 0.08
    if combinations or clashes or harms or punishments:
        confidence += 0.05

    return DomainAnalysis(
        ten_gods=ten_gods,
        exposed_stems=exposed,
        rooted_stems=rooted,
        combinations=combinations,
        clashes=clashes,
        harms=harms,
        breaks=breaks,
        punishments=punishments,
        three_assemblies=three_assemblies,
        season=month_zhi,
        adjustment=adjustment,
        pattern_hint=pattern_hint,
        confidence=round(min(confidence, 0.9), 2),
    )
