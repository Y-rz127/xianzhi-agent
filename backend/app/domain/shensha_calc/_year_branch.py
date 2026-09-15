"""三、四、以年支（或年支+日支）查的神煞。

覆盖：
- `collect_year_day_branch`（年支/日支双查，**排除自身柱位**）：
  华盖 / 桃花 / 驿马 / 将星 / 劫煞 / 亡神。
  年支查时排除年柱（idx 0），日支查时排除日柱（idx 2）—— 否则每柱都会自我命中。
- `collect_year_branch`（只以年支查，**排除年柱**）：
  灾煞 / 吊客 / 病符 / 红鸾 / 天喜 / 孤辰 / 寡宿 / 丧门 / 披麻 / 血刃 /
  勾绞煞 / 元辰 / 天罗地网。

口径要点：
- **"跳过发源柱"里的 `if i == 0: continue` 是刻意的**：这些神煞的口诀是
  "以年支查**余三支**"，返源柱本身不算。但注意血刃是反例 —— 它以**月支**查四柱
  且含月柱自身（"亥月→亥"自映射），故血刃不跳过任何柱，见 `collect_year_branch` 内注释。
- 勾绞煞 / 元辰 依"年干阴阳 + 性别"定向：阳男阴女顺推、阴男阳女逆推。
"""

from __future__ import annotations

from collections.abc import Iterator

from app.domain.shensha_calc._context import ShenshaContext, adv as _adv
from app.domain.tables import (
    BING_FU,
    CHONG_ZHI,
    DIAO_KE,
    GU_CHEN,
    GUA_SU,
    HONG_LUAN,
    HUA_GAI,
    JIANG_XING,
    JIE_SHA,
    PI_MA,
    SANG_MEN,
    TAO_HUA,
    TIAN_XI,
    WANG_SHEN,
    XUE_REN,
    YI_MA,
    ZAI_SHA,
)

_ZHI_LOOKUPS = (
    ("华盖", HUA_GAI, "聪明孤僻，近艺术宗教"),
    ("桃花", TAO_HUA, "人缘感情，异性缘佳"),
    ("驿马", YI_MA, "迁动出行，奔波变化"),
    ("将星", JIANG_XING, "掌权威望，领导力强"),
    ("劫煞", JIE_SHA, "破财伤身之兆"),
    ("亡神", WANG_SHEN, "心思深沉，暗耗多端"),
)

# 只以年支查、排除年柱自身的一批（口诀均为"以年支查余三支"）
_YEAR_BRANCH_LOOKUPS = (
    ("灾煞", ZAI_SHA, "灾厄不顺，需防意外"),
    ("吊客", DIAO_KE, "孝服丧事之兆"),
    ("病符", BING_FU, "身体小恙，注意健康"),
    ("红鸾", HONG_LUAN, "喜庆婚恋之事"),
    ("天喜", TIAN_XI, "喜事临门，感情顺遂"),
    ("孤辰", GU_CHEN, "性格孤独，亲情淡薄"),
    ("寡宿", GUA_SU, "内心寂寞，晚景清冷"),
    ("丧门", SANG_MEN, "孝服丧事之应，主忧郁悲伤"),
)


def collect_year_day_branch(ctx: ShenshaContext) -> Iterator[tuple[str, str, str]]:
    """以年支与日支分别查，各自排除发源柱。"""
    pillars = ctx.pillars
    for key_zhi, skip_idx in ((ctx.year_zhi, 0), (ctx.day_zhi, 2)):
        for name, table, desc in _ZHI_LOOKUPS:
            target = table.get(key_zhi)
            if not target:
                continue
            for i, p in enumerate(pillars):
                if i == skip_idx:
                    continue
                if p.zhi == target:
                    yield (name, desc, p.name)


def collect_year_branch(ctx: ShenshaContext) -> Iterator[tuple[str, str, str]]:
    """只以年支查（排除年柱），另含血刃、勾绞煞、元辰、天罗地网。"""
    pillars = ctx.pillars

    for name, table, desc in _YEAR_BRANCH_LOOKUPS:
        target = table.get(ctx.year_zhi)
        if not target:
            continue
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == target:
                yield (name, desc, p.name)

    # 披麻（年支查余三支，表值为多元素集合）
    for z in PI_MA.get(ctx.year_zhi, ()):
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == z:
                yield ("披麻", "孝服六亲有损，大运流年遇之主意外伤病", p.name)

    # 血刃（以月支查四柱，含月柱自身）："亥月→亥"自映射，不能像余三支那样跳过月柱
    xr = XUE_REN.get(ctx.month_zhi)
    if xr:
        for p in pillars:
            if p.zhi == xr:
                yield ("血刃", "血光之灾、外伤手术，岁运冲激尤忌", p.name)

    # 勾绞煞（年支查余三支，依年干阴阳+性别：阳男阴女勾前绞后，阴男阳女勾后绞前）
    is_yang, is_male = ctx.is_yang_year, ctx.is_male
    forward = (is_yang and is_male) or (not is_yang and not is_male)
    gou = _adv(ctx.year_zhi, 3 if forward else -3)
    jiao = _adv(ctx.year_zhi, -3 if forward else 3)
    for target in (gou, jiao):
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == target:
                yield ("勾绞煞", "牵连羁绊、易有官非纠纷", p.name)

    # 元辰（年支查对冲前/后一位，依年干阴阳+性别）
    chong = CHONG_ZHI.get(ctx.year_zhi)
    if chong:
        yuan = _adv(chong, 1 if forward else -1)
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == yuan:
                yield ("元辰", "别而不合、诸事不顺", p.name)

    # 天罗地网（戌亥为天罗、辰巳为地网；需戌亥互见 / 辰巳互见）
    # 标注到具体柱：天罗标含"戌"的柱，地网标含"辰"的柱
    all_zhi = ctx.all_zhi
    if "戌" in all_zhi and "亥" in all_zhi:
        p_xu = next((p for p in pillars if p.zhi == "戌"), None)
        yield ("天罗", "困顿羁绊、难挣脱", p_xu.name if p_xu else "")
    if "辰" in all_zhi and "巳" in all_zhi:
        p_chen = next((p for p in pillars if p.zhi == "辰"), None)
        yield ("地网", "困顿羁绊、事业受阻", p_chen.name if p_chen else "")
