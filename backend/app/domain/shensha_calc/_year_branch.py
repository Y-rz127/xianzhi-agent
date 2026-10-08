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
- 勾绞煞只取命前三辰一位（问真查法单表：子见卯、丑见辰…亥见寅），命后三辰之绞不另计；
  元辰依"年干阴阳 + 性别"定向：阳男阴女顺推、阴男阳女逆推。
- **天罗地网走问真查法一**（以年支+日支查余三支），且**记录在触发柱**而非参照柱；
  天罗/地网保持两个独立名字，不合并（用户要求）。
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
    """只以年支查（排除年柱），另含血刃、勾绞煞、元辰、天罗地网。

    天罗地网例外：**以年支+日支双查余三支**（问真查法一），记录在触发柱，
    见函数内注释。
    """
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

    # 勾绞煞（以年支查余三支，只取命前三辰一位为勾：子见卯、丑见辰…亥见寅）
    # 问真口径的查法表即此单表，命后三辰之绞不另计，故不再依阴阳男女定向
    gou = _adv(ctx.year_zhi, 3)
    for i, p in enumerate(pillars):
        if i == 0:
            continue
        if p.zhi == gou:
            yield ("勾绞煞", "牵连羁绊、易有官非纠纷", p.name)

    # 元辰（年支查对冲前/后一位，依年干阴阳+性别）
    is_yang, is_male = ctx.is_yang_year, ctx.is_male
    forward = (is_yang and is_male) or (not is_yang and not is_male)
    chong = CHONG_ZHI.get(ctx.year_zhi)
    if chong:
        yuan = _adv(chong, 1 if forward else -1)
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == yuan:
                yield ("元辰", "别而不合、诸事不顺", p.name)

    # 天罗地网（问真查法一：以**年支、日支**查余三支）
    #   戌见亥 / 亥见戌 → 天罗；辰见巳 / 巳见辰 → 地网。
    # 记录到**触发柱**（"被见到的那个字"所在柱），而非参照柱 ——
    # 旧实现全盘扫"戌亥/辰巳"同时出现、并把字标在含"辰"/"戌"的柱上，
    # 导致 庚辰 甲申 辛酉 癸巳 的"地网"标到年柱（问真标时柱，2026-10-08 现场）。
    # 两字互见（如年支辰+日支巳）时，各参照点各标一次，按柱名去重。
    # 注：yield 的神煞名必须写字面量 —— tests/bazi_golden.py 的 AST 名册守卫按字面量提取。
    _LW_TARGET = {"戌": "亥", "亥": "戌", "辰": "巳", "巳": "辰"}
    seen_lw: set[str] = set()
    for key_zhi, skip_idx in ((ctx.year_zhi, 0), (ctx.day_zhi, 2)):
        target = _LW_TARGET.get(key_zhi)
        if not target:
            continue
        for i, p in enumerate(pillars):
            if i == skip_idx or p.name in seen_lw:
                continue
            if p.zhi == target:
                seen_lw.add(p.name)
                if key_zhi in ("戌", "亥"):
                    yield ("天罗", "困顿羁绊、难挣脱，男命尤忌", p.name)
                else:
                    yield ("地网", "困顿羁绊、事业受阻，女命尤忌", p.name)
