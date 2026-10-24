"""命局结构分析：五行强弱、专旺/从格判定、十神统计、干支合冲刑害。"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.ganzhi_relations import branch_relations, stem_relations
from app.domain.models import DomainAnalysis, Pillar, WuxingAnalysis
from app.domain.tables import (
    CONTROLS,
    GAN_HE,
    GAN_WUXING,
    GENERATES,
    HIDDEN_STEMS,
    SEASON_NOTES,
    WUXING_ORDER,
    ZHI_WUXING,
    element_state,
)

# 特殊格局判定阈值
# 引擎版本：位置权重/阈值/关系修正任一变动都必须 bump —— chart_verdicts 缓存表
# 把它并进主键，bump 后老裁决自然失效、新裁决另起一行（历史留档可对比）。
ENGINE_VERSION = "20261024.1"  # 真太阳时方向修正（经度差 + 均时差），排盘结果与旧版不同

_ZHUANWANG_DOM_RATIO = 0.35       # 主导五行占「对日干影响」加权比例下限
_ZHUANWANG_PRESSURE_MAX = 2.8     # 克泄耗三行合计加权上限（超过视为破局，不判专旺）
_CONG_ROOT_MIN_HIDDEN = 0.25      # 藏干中某五行达此权重视为"中气级"（判透干印比是否有地支支撑）；
                                  # 与藏干比中气 0.25 对齐（2026-10-11 藏干比 30/10→25/15 时同步，
                                  # 保持"单中气支撑即有力"的原标定语义）
_CONG_SECOND_RATIO = 0.70         # 从势判定：次旺/最旺 ≥ 此比例视为两行相当 → 从势
_CONG_DOMINANT_MIN = 0.6          # 从格候选门槛：克泄耗中最旺一行须达此权重，否则无从

# 强弱档位门槛（2026-10-11 随位置权重重标定；正负不对称——日干不计入后
# 扶助力整体下移，且地支只按藏干比分配一次，分数整体约为旧口径的 55%）
_RU = 1.0                         # 偏旺
_RUAN = -1.4                      # 偏弱
_EXTREME_HIGH = 3.6               # 极旺（同时为专旺候选区门槛）
_EXTREME_LOW = -4.4               # 极弱（同时为从格候选区门槛）

# 四柱位置权重：各干支「对日干的影响力量」占比（2026-10-11 重标定）。
# 年干7% 年支5%｜月干15% 月支35%｜日干0% 日支18%｜时干8% 时支12%；
# 天干合计 30%、地支合计 70%（传统「天干三分、地支七分」），月柱 50% 为提纲。
# 日干是**被评估对象**，不参与「对日干影响」的计算（其本气即日主本身）；
# 全局五行分布的 visible_counts 仍含日干，两个口径勿混用。
# 实际权重 = 占比 × _TOTAL_WEIGHT（8.8，与历史口径同量纲，按需调整）。
# 藏干 = 藏干比 × 本柱地支权重，月令藏干随之放大，体现「得令者旺」。
_TOTAL_WEIGHT = 8.8
_POSITION_RATIOS = {
    0: (0.07, 0.05),   # 年干 7% / 年支 5% —— 距日主最远，须合冲刑害方显
    1: (0.15, 0.35),   # 月干 15% / 月支 35% —— 提纲，旺衰之源
    2: (0.00, 0.18),   # 日干 0%（不计）/ 日支 18% —— 日主之坐，贴身之根
    3: (0.08, 0.12),   # 时干 8% / 时支 12% —— 归宿之地
}
_POSITION_WEIGHTS = {
    i: (round(gan * _TOTAL_WEIGHT, 4), round(zhi * _TOTAL_WEIGHT, 4))
    for i, (gan, zhi) in _POSITION_RATIOS.items()
}
# 日干本气在**全局**五行分布里的权重：日干是八字之一，展示口径必须计回，
# 否则「日干是木而木显示 0」。取值 1.0（一个天干字符的本气），与三天干权重
# （0.616/1.32/0.704）同量级；只进 global_counts，不进 counts（影响口径）。
_DAY_MASTER_GLOBAL_WEIGHT = 1.0

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

# ---------------- 原局合冲刑害的五行力量修正（确定性共识，非 LLM 裁决） ----------------
#
# 知识库口径：12_合冲刑害规则卡 §一「合局力量：三会＞三合＞六合＞半合＞拱合」、
# §二「冲则根动」；33_从格专旺化气体系 §七 化气须「化神当令、地支成方局」。
# 这里只做**力学归并**（谁的力量并给谁、打几折），不做格局成败裁决 —— 那是
# 专旺/从格/化气判定与后续 LLM 裁决的事。
_CHART_SANHE_SHIFT = 1.0    # 三合局/三会方：参与支力量全部并入局五行（化气成局）
_CHART_LIUHE_SHIFT = 0.5    # 六合：参与支各折半并入合化五行（合而未化，倾向性修正）
_CHART_GANHE_SHIFT = 0.5    # 干合：两干各折半并入合化五行（合绊）
_CHART_CHONG_FACTOR = 0.75  # 六冲：被冲支藏干力量保留率（冲则根动，折损 25% 散失）


def _wu_of_relation(name: str) -> str:
    """从关系名尾字取五行：'申子辰合水局'→水、'子丑合土'→土、'卯戌合火'→火。"""
    for wx in WUXING_ORDER:
        if name.endswith(wx + "局") or name.endswith(wx):
            return wx
    return ""


def _chart_relation_adjust(pillars: list[str], weighted: dict[str, float]) -> tuple[dict[str, float], list[str], set[int]]:
    """原局合冲刑害对五行力量的修正，返回 (修正后 weighted, 修正说明, 被冲支索引集)。

    只做确定性共识的力学归并：
    - 三会方：参与支力量**全部**并入局五行（三支齐全即当季方气聚，无条件）；
    - 三合局：化神在月令**旺或相**（得时）才整支并入；休/囚/死一律**合而不化、
      各归本位**（不并入——自然之泄已含在藏干权重里。判据与 `xipan._wuxing_state`
      同源：申子辰生于辰月为「辰库收水」，不化。2026-10-12 用户裁决）；
    - 六合/干合：参与干支各折半并入合化五行（合而未化）；
    - 六冲：被冲支的藏干力量 ×0.75（冲则根动）。
    三刑/自刑/害/破不进强弱分 —— 它们主应事与伤病，不改变旺衰力学，
    编进来只会让阈值漂移（知识库 §四：刑害「助力应事，不改旺衰」）。

    注意与 `_build_domain_analysis` 的视图口径解耦：那里是展示映射（关系名列表），
    这里是力学归并；两处都调 `ganzhi_relations`（单一事实源），判定口径不分叉。
    """
    notes: list[str] = []
    w = dict(weighted)
    zhis = [p[1] for p in pillars]
    rel = branch_relations(zhis)

    consumed: set[int] = set()  # 已成局的支（整支并入局五行）
    merges: list[tuple[str, str]] = []  # 实际成局的 (关系名, 局五行)，供第 5 步归并

    # 1) 三会方 > 三合局：整支并入局五行
    #    三会无条件（三支齐全即当季方气聚）；三合须化神得时（月令旺/相）才化，
    #    否则合而不化、各归本位（辰月申子辰=辰库收水不化，2026-10-12 用户裁决）
    for is_san_he, names in ((False, rel.hui), (True, rel.san_he)):
        for name in names:
            wx = _wu_of_relation(name)
            if not wx:
                continue
            if is_san_he and element_state(pillars[1][1], wx) not in ("旺", "相"):
                notes.append(f"{name}：{wx}不当令，合而不化，各归本位")
                continue
            members = [c for c in name if c in zhis]
            for i, p in enumerate(pillars):
                if p[1] in members and i not in consumed:
                    consumed.add(i)
            notes.append(f"{name}：参与支力量并入{wx}")
            merges.append((name, wx))

    # 2) 六合：参与支各折半并入合化五行（参与支未被三合吞掉的部分）
    for name in rel.liu_he:
        wx = _wu_of_relation(name)
        if not wx:
            continue
        members = [c for c in name if c in zhis]
        for i, p in enumerate(pillars):
            if p[1] in members or i in consumed:
                continue
            _, zw = _POSITION_WEIGHTS[i]
            take = round(zw * _CHART_LIUHE_SHIFT, 4)
            # 折半量从该支藏干按比抽走，并入合化五行
            for h, r in HIDDEN_STEMS.get(p[1], ()):
                hw = GAN_WUXING.get(h)
                if hw and hw in w:
                    move = round(r * take, 4)
                    w[hw] = round(w[hw] - move, 4)
                    w[wx] = round(w[wx] + move, 4)
            notes.append(f"{name}：半力并入{wx}")

    # 3) 干合：两干各折半并入合化五行
    gans = [p[0] for p in pillars]
    gan_he, _ = stem_relations(gans)
    for gan in gan_he:
        for name in GAN_HE.values():
            if gan in name:
                wx = _wu_of_relation(name)
                if not wx:
                    continue
                pair = [g for g in name if g in gans and GAN_WUXING.get(g)]
                for g in pair:
                    i = gans.index(g)
                    gw, _ = _POSITION_WEIGHTS[i]
                    move = round(gw * _CHART_GANHE_SHIFT, 4)
                    hw = GAN_WUXING.get(g)
                    if hw in w:
                        w[hw] = round(w[hw] - move, 4)
                        w[wx] = round(w[wx] + move, 4)
                notes.append(f"{name}(干合)：半力并入{wx}")
                break

    # 4) 六冲：被冲支藏干力量折损（冲则根动）；被三合吞掉的支不再打折。
    # 成对去重：每支只折一次 —— 三酉遇一卯时，三个酉各折一次、卯只折一次
    # （群劫冲一，不是 6×3 笛卡尔积）。折损的 (1-factor) **散失不转移**：
    # 根摇之力泄于全局，总量不守恒是特性 —— 与六合/干合的「转移」语义不同。
    chong_hit: set[int] = set()
    for name in rel.chong:
        members = [c for c in name if c in zhis]
        hit_any = False
        for i, p in enumerate(pillars):
            if p[1] in members and i not in consumed:
                chong_hit.add(i)
                hit_any = True
        if hit_any:
            notes.append(f"{name}：根摇，被冲支藏干力×{_CHART_CHONG_FACTOR}（折损散失）")
    for i in chong_hit:
        _, zw = _POSITION_WEIGHTS[i]
        for h, r in HIDDEN_STEMS.get(pillars[i][1], ()):
            hw = GAN_WUXING.get(h)
            if hw and hw in w:
                lose = round(r * zw * (1 - _CHART_CHONG_FACTOR), 4)
                w[hw] = round(w[hw] - lose, 4)

    # 5) 成局整支归并（放在冲之后：局成则局内支不因冲再折损；合而不化者不在此列）
    for i, p in enumerate(pillars):
        if i not in consumed:
            continue
        _, zw = _POSITION_WEIGHTS[i]
        for h, r in HIDDEN_STEMS.get(p[1], ()):
            hw = GAN_WUXING.get(h)
            if hw and hw in w:
                move = round(r * zw, 4)
                w[hw] = round(w[hw] - move, 4)
    for name, wx in merges:
        members = [c for c in name if c in zhis]
        for i, p in enumerate(pillars):
            if p[1] in members:
                _, zw = _POSITION_WEIGHTS[i]
                w[wx] = round(w[wx] + zw, 4)

    return w, notes, chong_hit


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
#
# 2026-10-11 修正：原实现把"透干虚浮比劫"也算作微根（假从），依据是对 §一.2 成立条件
# 第 2 条"天干无印比帮扶"的从宽解读。但同篇更具体的两处（§一.2 关键判定、§八.1 定义）
# 列举的假从触发条件只有「地支微根」与「天干虚浮印」，均未含虚浮**比劫**；典籍实例亦站此说：
#   - 韦千里《千里命稿·外格篇》从杀例 戊戌辛酉乙酉乙酉：「乙木全无生气，岂能任之，
#     只得从杀，是即从杀格也」——时干一乙虚浮无根，仍判真从；
#   - 任铁樵《滴天髓·从象章》辛巳辛丑乙酉乙酉：「干透两辛，从杀斯真」——同为虚浮比劫。
# 故虚浮比劫不碍真从，虚浮印仍碍（印能生身，比劫无根则无力）。
# 连带地，强弱分中虚浮印比的扶助力打对折（见 _FLOATING_STEM_FACTOR）。

_VERDICT_SOLID = "有力"
_VERDICT_WEAK = "微根"
_VERDICT_NONE = "无根"

_FLOATING_STEM_FACTOR = 0.5  # 透干虚浮印比的扶助力折扣：无根则虚浮，力量打对折


@dataclass(frozen=True)
class _RootProfile:
    """日主根气画像。`verdict` 是三档判定的唯一入口。"""

    lu_ren_ku: bool                     # 地支见禄/刃/墓库根
    hidden_day: float                   # 藏干中日主五行权重合计（含余气）
    hidden_resource: float              # 藏干中印星五行权重合计
    solid_support: tuple[str, ...]      # 印比透干且地支有本气级支撑
    floating_support: tuple[tuple[int, str], ...]   # (柱位, 天干) 透干但地支无支撑
    floating_resource: tuple[tuple[int, str], ...]  # 上者中属印星者：印碍真从，比劫不碍

    @property
    def verdict(self) -> str:
        if self.lu_ren_ku or self.solid_support:
            return _VERDICT_SOLID
        if self.hidden_day > 0 or self.hidden_resource > 0 or self.floating_resource:
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
    floating: list[tuple[int, str]] = []
    floating_resource: list[tuple[int, str]] = []
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
        if supported:
            solid.append(p[0])
        else:
            floating.append((i, p[0]))
            if gw == resource:
                floating_resource.append((i, p[0]))

    return _RootProfile(lu_ren_ku, hidden_day, hidden_resource, tuple(solid),
                        tuple(floating), tuple(floating_resource))


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
    if contenders[best_name] < _CONG_DOMINANT_MIN:
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
    """在极端候选区做特殊格局识别：score ≥ _EXTREME_HIGH 判专旺，≤ _EXTREME_LOW 判从格。

    返回 `kind` ∈ {"专旺", "从格"(真从), "假从", ""}。真假从的区分见 `_detect_conging`
    与 `knowledge_docs/33_从格专旺化气体系.md` §八：假从仍按所从之神取用，但行帮身运即破局。
    不落入极端区或判定不自信时返回 is_special=False。
    门槛与 `_classify_strength` 的档位门同源（_EXTREME_HIGH/_EXTREME_LOW），
    调用方 `_build_wuxing_analysis` 已按同门过滤，此处再判一次只作防御。
    """
    if score >= _EXTREME_HIGH:
        zw = _detect_zhuanwang(weighted, day_wx, resource, officer, wealth, output)
        if zw:
            kind, label, hint = zw
            return {"is_special": True, "kind": kind, "label": label, "useful_hint": hint}
    elif score <= _EXTREME_LOW:
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

    档位门槛见 _RU/_RUAN/_EXTREME_HIGH/_EXTREME_LOW：
    score ≥ 3.6 极旺（候选专旺格）；≥ 1.0 偏旺；≤ -1.4 偏弱；≤ -4.4 极弱（候选从格）；其余中和。
    极旺/极弱用神走顺势，与偏旺/偏弱的制衡/扶助方向相反。
    """
    if score >= _EXTREME_HIGH:
        strength = "极旺"
        useful_hint = (
            f"日主极旺（候选专旺格），宜顺其旺势，喜{resource or '印星'}、{same or '比劫'}相扶；"
            f"若有{output or '食伤'}亦可泄秀，切忌{wealth or '财星'}、{officer or '官杀'}逆克激怒旺神。"
        )
    elif score >= _RU:
        strength = "偏旺"
        useful_hint = f"日主偏旺，宜取泄耗制衡之气，优先关注{output or '食伤'}、{wealth or '财星'}、{officer or '官杀'}的配合。"
    elif score <= _EXTREME_LOW:
        strength = "极弱"
        useful_hint = (
            f"日主极弱（候选从格），宜顺势相从，不喜{resource or '印星'}、{same or '比劫'}扶身反成羁绊；"
            f"具体用神需结合所从五行（从{wealth or '财'} / 从{officer or '官'} / 从{output or '儿'} 等）判定。"
        )
    elif score <= _RUAN:
        strength = "偏弱"
        useful_hint = f"日主偏弱，宜先扶助日主，重点看{resource or '印星'}与{same or '比劫'}是否得地。"
    else:
        strength = "中和"
        useful_hint = "格局接近平衡，喜忌需要结合大运流年触发点细看。"
    return strength, useful_hint


def _build_wuxing_analysis(ec) -> WuxingAnalysis:
    """基于四柱（含藏干）计算五行权重与日主强弱，并做特殊格局初判。

    权重：四柱位置加权（见 _POSITION_WEIGHTS，月令 35% 为提纲；日干为被评估对象不计），
    藏干按比例累加。counts 是「各干支对日干的影响力量」分布，不含日干自身；
    全局五行分布（含日干）看 visible_counts。
    强弱分 = 扶助（比劫 + 印枭×0.85 − 虚浮印比折扣）- 压制（食伤×0.55 + 财×0.7 + 官杀×0.8）。
    """
    pillars = [ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime()]
    visible_counts = {k: 0 for k in WUXING_ORDER}
    weighted = {k: 0.0 for k in WUXING_ORDER}

    for index, pillar in enumerate(pillars):
        gan, zhi = pillar[0], pillar[1]
        gan_wx = GAN_WUXING.get(gan)
        zhi_wx = ZHI_WUXING.get(zhi)
        stem_weight, branch_weight = _POSITION_WEIGHTS[index]
        if gan_wx:
            visible_counts[gan_wx] += 1
            weighted[gan_wx] += stem_weight
        if zhi_wx:
            visible_counts[zhi_wx] += 1
        # 地支力量只按藏干比分配一次（本气/中气/余气），不再另计主气全重 ——
        # 否则本气被算两遍（酉=辛 1.0 时地支贡献翻倍），总权重从 8.8 涨到 17.6，
        # 「天干30%+地支70%=100%」的会计不成立。2026-10-11 修正。
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

    # 透干虚浮印比：地支无根则虚浮，扶助力按位置权重折半。
    # 韦千里评从杀例「乙木全无生气，岂能任之」即此意 —— 无根天干不构成有效帮扶。
    prof = _root_profile(pillars, day_master, day_wx, resource)
    floating_discount = sum(
        _POSITION_WEIGHTS[i][0]
        * (0.85 if GAN_WUXING.get(gan) == resource else 1.0)
        * _FLOATING_STEM_FACTOR
        for i, gan in prof.floating_support
    )
    # 原局合冲刑害的力学修正（三合成局/六合半化/干合绊/冲根摇）——
    # 修正后的 weighted 只进强弱分，不回写 counts（counts 是原始影响分布）。
    adjusted, relation_notes, chong_hit = _chart_relation_adjust(pillars, weighted)

    # 印星受生条件（土重金埋）：日元须有一定力量方能受重印所生 ——
    # 日主**完全无根**（禄刃库根与余气微根皆无）时，重印生不动身，
    # 印星扶助系数 0.85 → 0.5。
    # 只对无根生效、微根不动：微根印重盘（水多木漂家族）的 score 若被拉负，
    # 会退出病药路径的 score>0 前提，方向反而变错 —— 其方向纠偏由
    # resource_dominant 病药路径承担，档位标签的分歧交给 LLM 终审。
    resource_coef = 0.85 if prof.verdict != _VERDICT_NONE else 0.5

    # 比劫根损打折（有根有比则不从的前提是根还站着）：透干比劫的根
    # 全部落在被冲支上时，根摇比劫折半 —— 三酉冲一卯盘的三乙不构成抗杀铁壁。
    day_roots_hit = {
        i for i, p in enumerate(pillars)
        if ZHI_WUXING.get(p[1]) == day_wx and i in chong_hit
    }
    same_discount = 0.0
    if day_roots_hit:
        solid_day_roots = any(
            i not in chong_hit for i, p in enumerate(pillars)
            if ZHI_WUXING.get(p[1]) == day_wx
        )
        if not solid_day_roots:
            same_discount = sum(
                _POSITION_WEIGHTS[i][0] * _FLOATING_STEM_FACTOR
                for i, p in enumerate(pillars)
                if GAN_WUXING.get(p[0]) == day_wx and i != 2
            )
            if same_discount > 0:
                relation_notes.append("比劫之根全被冲：透干比劫扶助力折半")

    support = (
        adjusted.get(same, 0.0) - same_discount
        + adjusted.get(resource, 0.0) * resource_coef
        - floating_discount
    )
    pressure = (
        adjusted.get(output, 0.0) * 0.55
        + adjusted.get(wealth, 0.0) * 0.7
        + adjusted.get(officer, 0.0) * 0.8
    )
    strength_score = round(support - pressure, 2)
    strength, useful_hint = _classify_strength(
        strength_score, day_wx, resource, same, output, wealth, officer
    )
    # 仅在极端候选区做特殊格局识别（专旺/从格），门槛与强弱档位同源
    special_pattern = ""
    if strength_score >= _EXTREME_HIGH or strength_score <= _EXTREME_LOW:
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
    # 全局分布 = 影响分布 + 日干本气（展示口径，日干是八字之一必须计回）
    global_counts = dict(weighted)
    if day_wx in global_counts:
        global_counts[day_wx] = round(global_counts[day_wx] + _DAY_MASTER_GLOBAL_WEIGHT, 2)
    notes = [
        "五行权重已纳入天干、地支、藏干，并对月令加权；比单纯统计八个字更稳。",
        "counts 为「各干支对日干的影响」分布（日干不计，供强弱/格局判定）；"
        "global_counts 为全局分布（加回日干本气，供五行分布图展示）。",
        "强弱为工程化初判，最终用神仍需结合格局、调候、合冲刑害与大运流年校验。",
        *relation_notes,
    ]
    return WuxingAnalysis(
        counts=_round_counts(weighted),
        global_counts=_round_counts(global_counts),
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
        root_verdict=prof.verdict,
        # 强弱分构成透出（合冲修正后的值）：LLM 裁决要"点名引擎错在哪一步"，
        # 必须能看到分数怎么来的，否则只能泛泛猜
        strength_detail={
            "support": {
                "比劫": round(adjusted.get(same, 0.0), 2),
                "印星": round(adjusted.get(resource, 0.0), 2),
                "印系数": resource_coef,
                "虚浮折扣": round(floating_discount, 2),
                "根损折扣": round(same_discount, 2),
            },
            "pressure": {
                "食伤": round(adjusted.get(output, 0.0), 2),
                "财": round(adjusted.get(wealth, 0.0), 2),
                "官杀": round(adjusted.get(officer, 0.0), 2),
            },
        },
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
