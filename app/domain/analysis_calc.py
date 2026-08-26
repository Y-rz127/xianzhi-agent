"""命局结构分析：五行强弱、专旺/从格判定、十神统计、干支合冲刑害。"""
from __future__ import annotations

from app.domain.models import DomainAnalysis, Pillar, WuxingAnalysis
from app.domain.tables import (
    CONTROLS,
    GAN_CHONG,
    GAN_HE,
    GAN_WUXING,
    GENERATES,
    HIDDEN_STEMS,
    LIU_CHONG,
    LIU_HAI,
    LIU_HE,
    LIU_PO,
    SAN_HE,
    SAN_HUI,
    SAN_XING,
    SEASON_NOTES,
    SELF_XING,
    WUXING_ORDER,
    ZHI_WUXING,
)

# 特殊格局判定阈值
_ZHUANWANG_DOM_RATIO = 0.60       # 主导五行占全局加权比例下限
_ZHUANWANG_PRESSURE_MAX = 2.0     # 克泄耗三行合计加权上限（超过视为破局，不判专旺）
_CONG_ROOT_MIN_HIDDEN = 0.30      # 藏干中日主五行达此权重视为有"根"
_CONG_RESOURCE_MIN_HIDDEN = 0.30  # 藏干中印星五行达此权重视为有"印根"
_CONG_SELF_WX_MAX = 0.50          # 日主自身五行加权超过此值，不从
_CONG_SECOND_RATIO = 0.60         # 从势判定：次旺/最旺 ≥ 此比例视为两行相当 → 从势

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


def _has_root(pillars, day_master: str, day_wx: str, resource: str) -> bool:
    """真假从根气判定：日主有禄/刃/库根、藏干中气以上本气根，或印星/比劫透干 → 不从。

    日干本身即日主，不计入"比劫透干"，否则任何八字都会被判有比劫。
    """
    roots = _root_branches_for_master(day_master)
    hidden_day = 0.0
    hidden_resource = 0.0
    same_stem = False
    resource_stem = False
    for i, p in enumerate(pillars):
        zhi = p[1]
        if zhi in roots:
            return True
        for h, ratio in HIDDEN_STEMS.get(zhi, ()):
            hw = GAN_WUXING.get(h)
            if hw == day_wx:
                hidden_day += ratio
            elif hw == resource:
                hidden_resource += ratio
        if i == 2:  # 日柱天干即日主，跳过比劫/印透干判定
            continue
        gw = GAN_WUXING.get(p[0])
        if gw == day_wx:
            same_stem = True
        elif gw == resource:
            resource_stem = True
    if same_stem:
        return True
    if hidden_day >= _CONG_ROOT_MIN_HIDDEN:
        return True
    if resource_stem or hidden_resource >= _CONG_RESOURCE_MIN_HIDDEN:
        return True
    return False


def _detect_zhuanwang(weighted, day_wx, resource, officer, wealth, output):
    """极旺候选 → 专旺格判定；要求日主五行独旺且克泄耗无破局。返回 (label, hint) 或 None。"""
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
    return name, hint


def _detect_conging(weighted, pillars, day_wx, day_master, resource, officer, wealth, output):
    """极弱候选 → 从格判定（真假从 + 从杀/从财/从儿/从势）。返回 (label, hint) 或 None。"""
    if _has_root(pillars, day_master, day_wx, resource):
        return None  # 有根/有印/有比劫 → 假从或不从
    if weighted.get(day_wx, 0.0) > _CONG_SELF_WX_MAX:
        return None  # 日主自身五行仍有可观权重（藏干本气），不从
    contenders = {
        "官杀": weighted.get(officer, 0.0),
        "财": weighted.get(wealth, 0.0),
        "食伤": weighted.get(output, 0.0),
    }
    best_name = max(contenders, key=contenders.get)
    if contenders[best_name] < 0.5:
        return None  # 没有一行明显独旺，不从
    # 从势：次旺行与最旺行相当（差距不大）
    vals = sorted(contenders.values(), reverse=True)
    if vals[1] >= vals[0] * _CONG_SECOND_RATIO and vals[1] > 0:
        hint = (
            f"日主极弱无依，官杀/财/食伤两三相混、势均力敌，入从势格；"
            f"宜顺势相从，随旺气流转，喜多而从者、忌{resource or '印星'}{day_wx}比劫扶身。"
        )
        return "从势格", hint
    name_map = {
        "官杀": ("从杀格", f"日主极弱从杀，喜{wealth or '财星'}生{officer or '官杀'}、顺势御杀；切忌{resource or '印星'}、{day_wx}比劫抗杀。"),
        "财": ("从财格", f"日主极弱从财，喜{output or '食伤'}生{wealth or '财星'}、{officer or '官杀'}护财；切忌{resource or '印星'}、{day_wx}比劫分财。"),
        "食伤": ("从儿格", f"日主极弱从儿（食伤），喜{wealth or '财星'}流通秀气；切忌{resource or '印星'}制儿、{officer or '官杀'}犯怒。"),
    }
    return name_map[best_name]


def _detect_special_pattern(pillars, weighted, day_wx, day_master, score,
                            resource, output, wealth, officer):
    """在 ±7 极端候选区做特殊格局识别：score ≥ 7 判专旺，score ≤ -7 判从格。

    不落入极端区或判定不自信时返回 is_special=False。
    """
    if score >= 7:
        zw = _detect_zhuanwang(weighted, day_wx, resource, officer, wealth, output)
        if zw:
            label, hint = zw
            return {"is_special": True, "kind": "专旺", "label": label, "useful_hint": hint}
    elif score <= -7:
        cg = _detect_conging(weighted, pillars, day_wx, day_master, resource, officer, wealth, output)
        if cg:
            label, hint = cg
            return {"is_special": True, "kind": "从格", "label": label, "useful_hint": hint}
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


def _branch_relations(zhis: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """归纳一组地支间的合/冲/害/刑关系（两两查六合/六冲/六害，三刑/自刑按集合判定）。"""
    combinations: list[str] = []
    clashes: list[str] = []
    harms: list[str] = []
    punishments: list[str] = []
    for i in range(len(zhis)):
        for j in range(i + 1, len(zhis)):
            pair = frozenset((zhis[i], zhis[j]))
            if pair in LIU_HE:
                combinations.append(LIU_HE[pair])
            if pair in LIU_CHONG:
                clashes.append(LIU_CHONG[pair])
            if pair in LIU_HAI:
                harms.append(LIU_HAI[pair])
    zhi_set = set(zhis)
    for group, label in SAN_XING.items():
        if group.issubset(zhi_set):
            punishments.append(label)
    for zhi in zhi_set:
        if zhis.count(zhi) >= 2 and zhi in SELF_XING:
            punishments.append(SELF_XING[zhi])
    return combinations, clashes, harms, punishments


def _branch_combinations(zhis: list[str]) -> list[str]:
    """识别地支三合局、三会方、六破；只报三支全会的完整局，缺支不识别。"""
    result: list[str] = []
    zhi_set = set(zhis)
    for group, label in SAN_HE.items():
        if group.issubset(zhi_set):
            result.append(label)
    for group, label in SAN_HUI.items():
        if group.issubset(zhi_set):
            result.append(label)
    for i in range(len(zhis)):
        for j in range(i + 1, len(zhis)):
            pair = frozenset((zhis[i], zhis[j]))
            if pair in LIU_PO:
                result.append(LIU_PO[pair])
    return result


def _stem_relations(gans: list[str]) -> tuple[list[str], list[str]]:
    """天干五合与相冲。返回 (合, 冲)。"""
    combos: list[str] = []
    clashes: list[str] = []
    for i in range(len(gans)):
        for j in range(i + 1, len(gans)):
            pair = frozenset((gans[i], gans[j]))
            if pair in GAN_HE:
                combos.append(GAN_HE[pair])
            if pair in GAN_CHONG:
                clashes.append(GAN_CHONG[pair])
    return combos, clashes


def _build_domain_analysis(pillars: list[Pillar], wuxing: WuxingAnalysis) -> DomainAnalysis:
    """汇总十神、透干/根气、地支关系与季节调候，组装领域层分析对象。

    天干五合/相冲以「(干合)」「(干冲)」前缀并入合/冲列表以便区分；
    pattern_hint 保留空串维持 dataclass 契约（根气/合冲等已由结构化字段承载）。
    """
    day_master = wuxing.day_master
    visible_gans = [p.gan for p in pillars if p.gan]
    hidden_stems = [stem for p in pillars for stem in p.hidden_stems]
    exposed = [gan for gan in visible_gans if gan != day_master]
    rooted = sorted({day_master for stem in hidden_stems if stem == day_master})
    zhis = [p.zhi for p in pillars if p.zhi]
    combinations, clashes, harms, punishments = _branch_relations(zhis)
    three_assemblies = _branch_combinations(zhis)
    gan_he, gan_chong = _stem_relations(visible_gans)
    combinations = [f"{g}(干合)" for g in gan_he] + combinations
    clashes = [f"{c}(干冲)" for c in gan_chong] + clashes
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
        punishments=punishments,
        three_assemblies=three_assemblies,
        season=month_zhi,
        adjustment=adjustment,
        pattern_hint=pattern_hint,
        confidence=round(min(confidence, 0.9), 2),
    )
