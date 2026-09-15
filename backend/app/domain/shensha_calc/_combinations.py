"""五、特殊组合类神煞 + 六、空亡。

`collect_combinations` 覆盖：魁罡 / 十恶大败 / 十灵日 / 八专日 / 九丑日 /
阴差阳错 / 孤鸾煞 / 六秀日 / 天赦日 / 金神 / 天转日·地转日 / 四废日 /
拱禄 / 三奇贵人 / 童子煞 / 飞刃。
`collect_xunkong` 覆盖：空亡。

口径要点（改动前请先核对 `knowledge_docs/07_神煞初探.md` 对应条目）：
- **三奇贵人必须"顺次连续、不隔柱"**：只认 年-月-日 与 月-日-时 两个连续窗口，
  用 `window == triple` 精确比较元组，逆序/乱序/隔柱一律不中（"凑齐即算"已废弃）。
- 天赦/天转地转/四废以**出生季节**（月支）查日柱；金神为"日柱优先，否则看时柱"
  的 if/elif —— 二者互斥，不能改成两个独立 if。
- 飞刃 = 羊刃对冲位，其羊刃位来自 `_day_stem.yang_ren_zhi`（与族一同源）。
- 空亡为年柱与日柱旬空的**并集**，任一落空即标记该柱。
"""

from __future__ import annotations

from collections.abc import Iterator

from app.domain.shensha_calc import _day_stem
from app.domain.shensha_calc._context import ShenshaContext
from app.domain.tables import (
    BA_ZHUAN,
    CHONG_ZHI,
    GONG_LU,
    GU_LUAN,
    JIN_SHEN,
    JIU_CHOU,
    KUI_GANG,
    LIU_XIU,
    SAN_QI,
    SHI_E_DA_BAI,
    SHI_LING,
    SI_FEI,
    TIAN_DI_ZHUAN,
    TIAN_SHE,
    YIN_CHA_YANG_CUO,
)

# 日柱直接命中的神煞（表为全集，日柱干支在表内即命中）
_DAY_GZ_LOOKUPS = (
    ("魁罡", KUI_GANG, "刚强果断、文章振发，运行身旺发福百端"),
    ("十恶大败", SHI_E_DA_BAI, "祖业难守、不善理财，财运波折"),
    ("十灵日", SHI_LING, "通灵异常、灵感丰富，宜玄学文学艺术"),
    ("八专日", BA_ZHUAN, "专业专精、禄旺，聪明专一但易固执"),
    ("九丑日", JIU_CHOU, "容貌有魅力、感情易惹纠纷损名；女命主产厄"),
    ("阴差阳错", YIN_CHA_YANG_CUO, "婚姻波折、夫妻不和，需包容理解"),
    ("孤鸾煞", GU_LUAN, "婚姻不顺、感情孤独，易晚婚或婚后不和"),
    ("六秀日", LIU_XIU, "聪明俊秀、多才多艺，文雅秀丽"),
)

_SAN_QI_KIND = {
    ("甲", "戊", "庚"): "天上三奇",
    ("乙", "丙", "丁"): "地下三奇",
    ("壬", "癸", "辛"): "人中三奇",
}


def collect_combinations(ctx: ShenshaContext) -> Iterator[tuple[str, str, str]]:
    """按固定顺序产出特殊组合类命中。"""
    pillars = ctx.pillars
    day_gz = ctx.day_gz
    season = ctx.season

    for name, table, desc in _DAY_GZ_LOOKUPS:
        if day_gz in table:
            yield (name, desc, "日柱")

    # 天赦日（按出生季节查日柱）
    if day_gz == TIAN_SHE.get(season, ""):
        yield ("天赦日", "天恩浩荡、逢凶化吉，一生多得天佑", "日柱")

    # 金神（日柱或时柱，六甲日见乙丑/己巳/癸酉）：日柱优先，二者互斥
    if day_gz in JIN_SHEN:
        yield ("金神", "刚烈果断、具开拓改革精神，危机能当重任", "日柱")
    elif len(pillars) > 3 and pillars[3].ganzhi in JIN_SHEN:
        yield ("金神", "刚烈果断、具开拓改革精神，危机能当重任", "时柱")

    # 天转日 / 地转日（以月支查日柱，二者同表）
    if day_gz in TIAN_DI_ZHUAN.get(season, ()):
        yield ("天转日", "干支纳音俱专、旺于四时，时来运转亦防过旺", "日柱")
        yield ("地转日", "干支纳音俱专、旺于四时，转运改命亦防过旺", "日柱")

    # 四废日（以出生季节查日柱）
    if day_gz in SI_FEI.get(season, ()):
        yield ("四废日", "有始无终、费力少功，需防虎头蛇尾", "日柱")

    # 拱禄（日时柱配合：日支与时支拱夹日干禄位）
    if len(pillars) > 3:
        for d, t, lu_zhi in GONG_LU:
            if pillars[2].zhi == d and pillars[3].zhi == t:
                yield ("拱禄", f"日时拱夹禄位{lu_zhi}，财禄拱护、富贵双全", "日柱")

    # 三奇贵人：天干顺次连续、不可颠倒间隔，仅认 年-月-日 / 月-日-时 两个连续窗口
    windows: list[tuple[str, str, str]] = []
    if len(pillars) > 2:  # 年-月-日
        windows.append((pillars[0].gan, pillars[1].gan, pillars[2].gan))
    if len(pillars) > 3:  # 月-日-时
        windows.append((pillars[1].gan, pillars[2].gan, pillars[3].gan))
    for triple in SAN_QI:
        if any(window == triple for window in windows):  # 精确顺序 + 连续窗口
            kind = _SAN_QI_KIND[triple]
            yield ("三奇贵人", f"{kind}（{' '.join(triple)}），襟怀卓越、博学多能", "日柱")
            break

    # 童子煞：依月令季节 + 年柱纳音
    # 口诀「春秋寅子贵，冬夏卯未辰；金木马卯合，水火鸡犬多；土命逢辰巳」
    def _hit_tongzi(zhi: str) -> bool:
        if season in ("春", "秋") and zhi in ("寅", "子"):
            return True
        if season in ("夏", "冬") and zhi in ("卯", "未", "辰"):
            return True
        if ctx.year_nayin_wx in ("金", "木") and zhi in ("午", "卯"):
            return True
        if ctx.year_nayin_wx in ("水", "火") and zhi in ("酉", "戌"):
            return True
        if ctx.year_nayin_wx == "土" and zhi in ("辰", "巳"):
            return True
        return False

    if _hit_tongzi(ctx.day_zhi):
        yield ("童子煞", "运气多阻、易遇小人，婚姻迟缓，宜修道艺", "日柱")
    if len(pillars) > 3 and _hit_tongzi(pillars[3].zhi):
        yield ("童子煞", "运气多阻、易遇小人，婚姻迟缓，宜修道艺", "时柱")

    # 飞刃（羊刃对冲位）
    yangren = _day_stem.yang_ren_zhi(ctx)
    if yangren:
        feiren_zhi = CHONG_ZHI.get(yangren, "")
        if feiren_zhi:
            for p in pillars:
                if p.zhi == feiren_zhi:
                    yield ("飞刃", f"羊刃{yangren}对冲{feiren_zhi}，刚烈更甚、主突发伤害", p.name)


def collect_xunkong(ctx: ShenshaContext) -> Iterator[tuple[str, str, str]]:
    """空亡：年柱+日柱旬空双查，任一落空即标记。"""
    xunkong_set: set[str] = set()
    for idx in (0, 2):  # 年柱=0, 日柱=2
        if ctx.pillars[idx].xunkong:
            for xk_char in ctx.pillars[idx].xunkong:
                xunkong_set.add(xk_char)
    if xunkong_set:
        for p in ctx.pillars:
            if p.zhi in xunkong_set:
                yield ("空亡", f"旬空{p.zhi}，力减半", p.name)
