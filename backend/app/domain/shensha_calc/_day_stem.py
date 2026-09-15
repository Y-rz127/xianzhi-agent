"""一、以日干/年干查的神煞（贵人系）。

覆盖：天乙贵人 / 太极贵人 / 文昌贵人 / 禄神 / 羊刃 / 学堂·词馆（含"正"位）/
金舆 / 福星贵人 / 天厨贵人 / 国印贵人 / 流霞 / 红艳煞。

口径要点（改动前请先核对 `knowledge_docs/07_神煞初探.md` 对应条目）：
- 学堂/词馆以**年柱纳音**查月日时三柱（不含年柱自身）。
- 正学堂/正词馆为精确位（干支全配），同柱命中"正X"时不再报"X" ——
  故必须先标"正X"并记住命中柱，再标"X"时跳过。这个"先精后粗"的顺序是刻意的。
"""

from __future__ import annotations

from collections.abc import Iterator

from app.domain.shensha_calc._context import ShenshaContext
from app.domain.tables import (
    CI_GUAN,
    FU_XING,
    GUO_YIN,
    HONG_YAN,
    JIN_YU,
    LIU_XIA,
    LU_SHEN,
    TAI_JI,
    TIAN_CHU,
    TIAN_YI,
    WEN_CHANG,
    XUE_TANG,
    YANG_REN,
    ZHENG_CI_GUAN,
    ZHENG_XUE_TANG,
)


def yang_ren_zhi(ctx: ShenshaContext) -> str | None:
    """日干羊刃位（飞刃 = 其冲位，见 `_combinations`）。"""
    return YANG_REN.get(ctx.day_gan)


def collect(ctx: ShenshaContext) -> Iterator[tuple[str, str, str]]:
    """按固定顺序产出本族命中。"""
    day_gan, year_gan = ctx.day_gan, ctx.year_gan
    pillars = ctx.pillars

    # 天乙贵人（日干或年干）
    for g in (day_gan, year_gan):
        for z in TIAN_YI.get(g, ()):
            for p in pillars:
                if p.zhi == z:
                    yield ("天乙贵人", "遇事有人帮、临难有人解，逢凶化吉", p.name)

    # 太极贵人（日干或年干）
    for g in (day_gan, year_gan):
        for z in TAI_JI.get(g, ()):
            for p in pillars:
                if p.zhi == z:
                    yield ("太极贵人", "聪明好学，喜文史哲宗教，做事有始有终", p.name)

    # 文昌贵人（日干或年干）
    for g in (day_gan, year_gan):
        w = WEN_CHANG.get(g)
        if w:
            for p in pillars:
                if p.zhi == w:
                    yield ("文昌贵人", "聪明雅秀、有上进心，利考试功名", p.name)

    # 禄神（日干）
    lu = LU_SHEN.get(day_gan)
    if lu:
        for p in pillars:
            if p.zhi == lu:
                yield ("禄神", "身体健康、勤劳致富，一生少闲", p.name)

    # 羊刃（日干，取帝旺位；丁己在巳）
    yangren = YANG_REN.get(day_gan)
    if yangren:
        for p in pillars:
            if p.zhi == yangren:
                yield ("羊刃", "刚烈勇猛、有勇有谋；得制化为武贵，失制化易招灾", p.name)

    # 学堂/词馆：按年柱纳音查月日时三柱（不含年柱自身）
    other_three = ctx.other_three
    xt = XUE_TANG.get(ctx.year_nayin_wx)
    zxt = ZHENG_XUE_TANG.get(ctx.year_nayin_wx)
    cg = CI_GUAN.get(ctx.year_nayin_wx)
    zcg = ZHENG_CI_GUAN.get(ctx.year_nayin_wx)

    # 先标"正X"：记录命中柱，避免同一柱重复报"X"
    zheng_xt_pillars: set[str] = set()
    if zxt:
        for p in other_three:
            if p.ganzhi == zxt:
                zheng_xt_pillars.add(p.name)
                yield ("正学堂", "纳音长生正位，学问正统、贵气十足", p.name)
    zheng_cg_pillars: set[str] = set()
    if zcg:
        for p in other_three:
            if p.ganzhi == zcg:
                zheng_cg_pillars.add(p.name)
                yield ("正词馆", "纳音临官正位，文章锦绣、文采斐然", p.name)

    # 再标"X"：跳过已被"正X"标记的柱
    if xt:
        for p in other_three:
            if p.zhi == xt and p.name not in zheng_xt_pillars:
                yield ("学堂", "纳音长生，聪明好学、文才出众、功名显达", p.name)
    if cg:
        for p in other_three:
            if p.zhi in cg and p.name not in zheng_cg_pillars:
                yield ("词馆", "纳音临官，文章出类、学业精专", p.name)

    # 金舆（日干或年干）
    for g in (day_gan, year_gan):
        y = JIN_YU.get(g)
        if y:
            for p in pillars:
                if p.zhi == y:
                    yield ("金舆", "贵气显赫、得权贵相助，具领导气质", p.name)

    # 福星贵人（年干或日干）
    for g in (year_gan, day_gan):
        for z in FU_XING.get(g, ()):
            for p in pillars:
                if p.zhi == z:
                    yield ("福星贵人", "福德深厚、一生多得贵人，福寿双全", p.name)

    # 天厨贵人（年干或日干）
    for g in (year_gan, day_gan):
        t = TIAN_CHU.get(g)
        if t:
            for p in pillars:
                if p.zhi == t:
                    yield ("天厨贵人", "食神建禄，衣食无忧、财帛丰足，善理财", p.name)

    # 国印贵人（年干或日干）
    for g in (year_gan, day_gan):
        y = GUO_YIN.get(g)
        if y:
            for p in pillars:
                if p.zhi == y:
                    yield ("国印贵人", "权威正直、有责任感，宜公职权力岗", p.name)

    # 流霞（日干）
    lx = LIU_XIA.get(day_gan)
    if lx:
        for p in pillars:
            if p.zhi == lx:
                yield ("流霞", "主血光之灾、外伤疾病，需防意外", p.name)

    # 红艳煞（日干）
    hy = HONG_YAN.get(day_gan)
    if hy:
        for p in pillars:
            if p.zhi == hy:
                yield ("红艳煞", "异性缘过旺、易陷复杂感情纠葛，女命尤忌", p.name)
