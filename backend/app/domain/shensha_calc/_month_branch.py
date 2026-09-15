"""二、以月支查的神煞。

覆盖：天德贵人 / 月德贵人 / 天德合 / 月德合 / 德秀贵人 / 天医。

口径要点（改动前请先核对 `knowledge_docs/07_神煞初探.md` 对应条目）：
- **天德是"干支混搭"字典，必须分两支**：`TIAN_DE_MONTH` 给出的字，
  在卯/午/酉/子 4 个月令（`TIAN_DE_IS_BRANCH`）本身是**地支**，查 `p.zhi`；
  其余月令是**天干**，查 `p.gan`（并额外查藏干，暗藏力弱需引动）。
  天德合同理走同一分支判断。
- **月德只查四柱天干**，不查藏干 —— 口诀"亥卯未月甲干栖"的"干"即天干；
  查藏干会把三合木局误报成月德。
- 德秀贵人是"德干优先、无德才看秀干"的 for/else 结构，顺序不能颠倒。
"""

from __future__ import annotations

from collections.abc import Iterator

from app.domain.shensha_calc._context import ShenshaContext
from app.domain.tables import (
    DE_XIU,
    TIAN_DE_HE,
    TIAN_DE_IS_BRANCH,
    TIAN_DE_MONTH,
    TIAN_YI_MED,
    YUE_DE_HE,
    YUE_DE_MONTH,
)


def collect(ctx: ShenshaContext) -> Iterator[tuple[str, str, str]]:
    """按固定顺序产出本族命中。"""
    month_zhi = ctx.month_zhi
    month_idx = ctx.month_idx
    pillars = ctx.pillars

    # 天德贵人：查天干（透出，力显）或地支，取决于该月令天德的本来属性
    tiande_chars = TIAN_DE_MONTH.get(month_idx)
    if tiande_chars:
        is_branch_target = month_idx in TIAN_DE_IS_BRANCH
        for c in tiande_chars:
            for p in pillars:
                if is_branch_target:
                    # 天德是地支（2月申、5月亥、8月寅），查地支
                    if p.zhi == c:
                        yield ("天德贵人", "逢凶化吉", p.name)
                else:
                    # 天德是天干，查天干（透出，力显）和藏干（暗藏，力弱需引动）
                    if p.gan == c:
                        yield ("天德贵人", "逢凶化吉", p.name)
                    elif any(hs == c for hs in p.hidden_stems):
                        yield ("天德贵人", "逢凶化吉", p.name)

    # 月德贵人只查四柱天干
    yuede_chars = YUE_DE_MONTH.get(month_idx)
    if yuede_chars:
        for c in yuede_chars:
            for p in pillars:
                if p.gan == c:
                    yield ("月德贵人", "天干见{}，化煞解厄".format(c), p.name)

    # 天德合：卯/午/酉/子月天德是地支，查 p.zhi；其余月天德是天干，查 p.gan
    tian_de_he = TIAN_DE_HE.get(month_zhi)
    if tian_de_he:
        is_branch_target = month_idx in TIAN_DE_IS_BRANCH
        for p in pillars:
            if is_branch_target:
                if p.zhi == tian_de_he:
                    yield ("天德合", "与天德相配、逢凶化吉", p.name)
            else:
                if p.gan == tian_de_he:
                    yield ("天德合", "与天德相配、逢凶化吉", p.name)

    yue_de_he = YUE_DE_HE.get(month_zhi)
    if yue_de_he:
        for p in pillars:
            if p.gan == yue_de_he:
                yield ("月德合", "化解灾难、福禄双全", p.name)

    # 德秀贵人（月令查天干：德干优先，无德干才看秀干）
    de_xiu = DE_XIU.get(month_zhi)
    if de_xiu:
        de_set, xiu_set = de_xiu
        for p in pillars:
            if p.gan in de_set:
                yield ("德秀贵人", "温厚聪慧、才华横溢", p.name)
                break
        else:
            for p in pillars:
                if p.gan in xiu_set:
                    yield ("德秀贵人", "清秀之气、多才多艺", p.name)
                    break

    # 天医（月支查，对齐 07_神煞初探.md）
    tianyi_med = TIAN_YI_MED.get(month_zhi)
    if tianyi_med:
        for p in pillars:
            if p.zhi == tianyi_med:
                yield ("天医", "医药有缘、善疗病痛，宜医护保健", p.name)
