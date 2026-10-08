"""紫微斗数排盘引擎（纯函数领域层，零运行时依赖，逐组对齐 iztro 2.6.0 默认配置）。

派别与规则（模块头声明，与 tables.py 一致）
--------------------------------------------
- 安星法：《紫微斗数全书》通行法（= iztro ``algorithm='default'``）。
- 四化：三合通用四化表（:data:`app.domain.ziwei.tables.MUTAGEN_BY_STEM`，可替换常量）。
- 年分界：正月初一（= iztro ``yearDivide='normal'``，对应 lunar-python ``getYearInGanZhi()``）。
- 闰月：闰月十五（含）前算本月、之后算下月（``fix_leap=True``，中州/通行一致规则）。
- 晚子时：``time_index=12``（23:00–24:00）起紫微星按次日农历日计，其余历法原语不因小时进日。

宫位索引统一以「寅宫=0，顺时针至丑宫=11」。
"""
from __future__ import annotations

import datetime

from lunar_python import Solar

from app.domain.ziwei import tables as T
from app.domain.ziwei.models import Chart, Decadal, Palace, Star

MIN_YEAR = 1900
MAX_YEAR = 2100
ZODIAC = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")


# --------------------------------------------------------------------------- #
# 索引工具
# --------------------------------------------------------------------------- #
def _fix(index: int, mod: int = 12) -> int:
    """把任意整数折回 [0, mod)（等价 iztro fixIndex，Python 取模天然处理负数）。"""
    return index % mod


def _febi(branch: str) -> int:
    """地支 → 以寅为 0 的宫位索引（= iztro fixEarthlyBranchIndex）。"""
    return _fix(T.EARTHLY_BRANCHES.index(branch) - T.YIN_BRANCH_INDEX)


# --------------------------------------------------------------------------- #
# 历法原语（lunar-python 桥接）
# --------------------------------------------------------------------------- #
def _solar_from_lunar(year: int, month: int, day: int, leap: bool) -> datetime.date:
    """农历 → 阳历；校验农历日期真实存在（闰月须该年确有、日不超出该月天数）。"""
    from lunar_python import Lunar

    try:
        lunar = Lunar.fromYmd(year, -month if leap else month, day)
        solar = lunar.getSolar()
    except Exception as e:  # lunar-python 对超范围农历日抛通用 Exception，统一转成 ValueError
        raise ValueError(f"农历日期不存在：{year}{'闰' if leap else ''}{month}月{day}日") from e
    # 回读校验：lunar-python 会把非法日向前/向后夹取，比对月/日/闰性是否一致
    back = solar.getLunar()
    if abs(back.getMonth()) != month or back.getDay() != day or (back.getMonth() < 0) != leap:
        raise ValueError(f"农历日期不存在：{year}{'闰' if leap else ''}{month}月{day}日")
    return datetime.date(solar.getYear(), solar.getMonth(), solar.getDay())


def _resolve_calendar(solar: datetime.date, time_index: int, fix_leap: bool) -> dict:
    """由阳历日 + 时辰序号解析排盘所需历法原语。"""
    lunar = Solar.fromYmd(solar.year, solar.month, solar.day).getLunar()
    raw_month = lunar.getMonth()  # 闰月为负
    is_leap = raw_month < 0
    lunar_month = abs(raw_month)
    lunar_day = lunar.getDay()
    year_gz = lunar.getYearInGanZhi()  # 正月初一分界
    year_stem, year_branch = year_gz[0], year_gz[1]
    hour_branch_index = time_index % 12

    need_to_add = is_leap and fix_leap and lunar_day > 15 and time_index != 12
    month_index = _fix(lunar_month - 1 + (1 if need_to_add else 0))
    soul_index = _fix(month_index - hour_branch_index)
    body_index = _fix(month_index + hour_branch_index)

    start_stem = T.TIGER_RULE[year_stem]
    soul_stem_index = _fix(T.HEAVENLY_STEMS.index(start_stem) + soul_index, 10)
    heavenly_stem_of_soul = T.HEAVENLY_STEMS[soul_stem_index]
    earthly_branch_of_soul = T.EARTHLY_BRANCHES[_fix(soul_index + T.YIN_BRANCH_INDEX)]
    five_class = _five_elements(heavenly_stem_of_soul, earthly_branch_of_soul)

    # 晚子时起紫微用次日农历日（等价 iztro 的 lunarDay+1 跨月夹取）
    if time_index == 12:
        ziwei_day = Solar.fromYmd(solar.year, solar.month, solar.day).next(1).getLunar().getDay()
    else:
        ziwei_day = lunar_day

    return {
        "lunar": lunar,
        "lunar_month": lunar_month,
        "lunar_day": lunar_day,
        "is_leap": is_leap,
        "year_stem": year_stem,
        "year_branch": year_branch,
        "hour_branch_index": hour_branch_index,
        "month_index": month_index,
        "soul_index": soul_index,
        "body_index": body_index,
        "heavenly_stem_of_soul": heavenly_stem_of_soul,
        "earthly_branch_of_soul": earthly_branch_of_soul,
        "five_class": five_class,
        "ziwei_day": ziwei_day,
    }


def _five_elements(stem: str, branch: str) -> str:
    """定五行局（纳音取数巧记）。"""
    table = ("木三局", "金四局", "水二局", "火六局", "土五局")
    stem_num = T.HEAVENLY_STEMS.index(stem) // 2 + 1
    branch_num = _fix(T.EARTHLY_BRANCHES.index(branch), 6) // 2 + 1
    idx = stem_num + branch_num
    while idx > 5:
        idx -= 5
    return table[idx - 1]


# --------------------------------------------------------------------------- #
# 星曜属性
# --------------------------------------------------------------------------- #
def _brightness(star: str, palace_index: int) -> str:
    arr = T.BRIGHTNESS.get(star)
    return arr[_fix(palace_index)] if arr else ""


def _mutagen(star: str, year_stem: str) -> str:
    lu, quan, ke, ji = T.MUTAGEN_BY_STEM[year_stem]
    if star == lu:
        return "禄"
    if star == quan:
        return "权"
    if star == ke:
        return "科"
    if star == ji:
        return "忌"
    return ""


# --------------------------------------------------------------------------- #
# 定位函数（逐项誊录 iztro star/location.js）
# --------------------------------------------------------------------------- #
def _start_index(res: dict) -> tuple[int, int]:
    """起紫微、天府宫位索引。"""
    five_value = T.FIVE_ELEMENTS_VALUE[res["five_class"]]
    day = res["ziwei_day"]
    offset = 0
    while True:
        divisor = day + offset
        if divisor % five_value == 0:
            break
        offset += 1
    quotient = (divisor // five_value) % 12
    ziwei = quotient - 1
    ziwei = ziwei + offset if offset % 2 == 0 else ziwei - offset
    ziwei = _fix(ziwei)
    tianfu = _fix(12 - ziwei)
    return ziwei, tianfu


def _lu_yang_tuo_ma(year_stem: str, year_branch: str) -> dict:
    ma_map = {"寅": "申", "午": "申", "戌": "申", "申": "寅", "子": "寅", "辰": "寅",
              "巳": "亥", "酉": "亥", "丑": "亥", "亥": "巳", "卯": "巳", "未": "巳"}
    lu_map = {"甲": "寅", "乙": "卯", "丙": "巳", "戊": "巳", "丁": "午", "己": "午",
              "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}
    lu = _febi(lu_map[year_stem])
    ma = _febi(ma_map[year_branch])
    return {"lu": lu, "ma": ma, "yang": _fix(lu + 1), "tuo": _fix(lu - 1)}


def _kui_yue(year_stem: str) -> tuple[int, int]:
    m = {"甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
         "乙": ("子", "申"), "己": ("子", "申"), "辛": ("午", "寅"),
         "丙": ("亥", "酉"), "丁": ("亥", "酉"), "壬": ("卯", "巳"), "癸": ("卯", "巳")}
    k, y = m[year_stem]
    return _febi(k), _febi(y)


def _zuo_you(lunar_month: int) -> tuple[int, int]:
    return _fix(_febi("辰") + (lunar_month - 1)), _fix(_febi("戌") - (lunar_month - 1))


def _chang_qu(time_index: int) -> tuple[int, int]:
    ti = _fix(time_index)
    return _fix(_febi("戌") - ti), _fix(_febi("辰") + ti)


def _kong_jie(time_index: int) -> tuple[int, int]:
    ti = _fix(time_index)
    hai = _febi("亥")
    return _fix(hai - ti), _fix(hai + ti)  # (地空, 地劫)


def _huo_ling(year_branch: str, time_index: int) -> tuple[int, int]:
    m = {"寅": ("丑", "卯"), "午": ("丑", "卯"), "戌": ("丑", "卯"),
         "申": ("寅", "戌"), "子": ("寅", "戌"), "辰": ("寅", "戌"),
         "巳": ("卯", "戌"), "酉": ("卯", "戌"), "丑": ("卯", "戌"),
         "亥": ("酉", "戌"), "未": ("酉", "戌"), "卯": ("酉", "戌")}
    huo0, ling0 = m[year_branch]
    ti = _fix(time_index)
    return _fix(_febi(huo0) + ti), _fix(_febi(ling0) + ti)


def _luan_xi(year_branch: str) -> tuple[int, int]:
    hongluan = _fix(_febi("卯") - T.EARTHLY_BRANCHES.index(year_branch))
    return hongluan, _fix(hongluan + 6)


def _huagai_xianchi(year_branch: str) -> tuple[int, int]:
    m = {"寅": ("戌", "卯"), "午": ("戌", "卯"), "戌": ("戌", "卯"),
         "申": ("辰", "酉"), "子": ("辰", "酉"), "辰": ("辰", "酉"),
         "巳": ("丑", "午"), "酉": ("丑", "午"), "丑": ("丑", "午"),
         "亥": ("未", "子"), "未": ("未", "子"), "卯": ("未", "子")}
    hg, xc = m[year_branch]
    return _febi(hg), _febi(xc)


def _gu_gua(year_branch: str) -> tuple[int, int]:
    m = {"寅": ("巳", "丑"), "卯": ("巳", "丑"), "辰": ("巳", "丑"),
         "巳": ("申", "辰"), "午": ("申", "辰"), "未": ("申", "辰"),
         "申": ("亥", "未"), "酉": ("亥", "未"), "戌": ("亥", "未"),
         "亥": ("寅", "戌"), "子": ("寅", "戌"), "丑": ("寅", "戌")}
    gu, gua = m[year_branch]
    return _febi(gu), _febi(gua)


def _nian_jie(year_branch: str) -> int:
    order = ("戌", "酉", "申", "未", "午", "巳", "辰", "卯", "寅", "丑", "子", "亥")
    return _febi(order[T.EARTHLY_BRANCHES.index(year_branch)])


def _tian_shi_tian_shang(gender: str, year_branch: str, soul_index: int) -> tuple[int, int]:
    """天使、天伤（通行派：天伤=命宫+5，天使=命宫+7）。"""
    tianshang = _fix(5 + soul_index)
    tianshi = _fix(7 + soul_index)
    return tianshi, tianshang


def _yearly_star_index(res: dict, gender: str) -> dict:
    ys, yb = res["year_stem"], res["year_branch"]
    soul, body = res["soul_index"], res["body_index"]
    bi = T.EARTHLY_BRANCHES.index(yb)
    si = T.HEAVENLY_STEMS.index(ys)
    hg, xc = _huagai_xianchi(yb)
    gu, gua = _gu_gua(yb)
    tianshi, tianshang = _tian_shi_tian_shang(gender, yb, soul)
    yinyang = bi % 2
    jielu = _fix(_febi(("申", "午", "辰", "寅", "子")[si % 5]))
    kongwang = _fix(_febi(("酉", "未", "巳", "卯", "丑")[si % 5]))
    xunkong = _fix(_febi(yb) + 10 - si)
    if yinyang != xunkong % 2:
        xunkong = _fix(xunkong + 1)
    return {
        "xianchi": xc, "huagai": hg, "guchen": gu, "guasu": gua,
        "tiancai": _fix(soul + bi), "tianshou": _fix(body + bi),
        "tianchu": _fix(_febi(("巳", "午", "子", "巳", "午", "申", "寅", "午", "酉", "亥")[si])),
        "posui": _fix(_febi(("巳", "丑", "酉")[bi % 3])),
        "feilian": _fix(_febi(("申", "酉", "戌", "巳", "午", "未", "寅", "卯", "辰", "亥", "子", "丑")[bi])),
        "longchi": _fix(_febi("辰") + bi), "fengge": _fix(_febi("戌") - bi),
        "tianku": _fix(_febi("午") - bi), "tianxu": _fix(_febi("午") + bi),
        "tianguan": _fix(_febi(("未", "辰", "巳", "寅", "卯", "酉", "亥", "酉", "戌", "午")[si])),
        "tianfu": _fix(_febi(("酉", "申", "子", "亥", "卯", "寅", "午", "巳", "午", "巳")[si])),
        "tiande": _fix(_febi("酉") + bi), "yuede": _fix(_febi("巳") + bi),
        "tiankong": _fix(_febi(yb) + 1),
        "jielu": jielu, "kongwang": kongwang, "xunkong": xunkong,
        "tianshang": tianshang, "tianshi": tianshi, "nianjie": _nian_jie(yb),
    }


def _monthly_star_index(res: dict, time_index: int) -> dict:
    mi = res["month_index"]
    return {
        "jieshen": _fix(_febi(("申", "戌", "子", "寅", "辰", "午")[mi // 2])),
        "tianyao": _fix(_febi("丑") + mi), "tianxing": _fix(_febi("酉") + mi),
        "yinsha": _fix(_febi(("寅", "子", "戌", "申", "午", "辰")[mi % 6])),
        "tianyue": _fix(_febi(("戌", "巳", "辰", "寅", "未", "卯", "亥", "未", "寅", "午", "戌", "寅")[mi])),
        "tianwu": _fix(_febi(("巳", "申", "寅", "亥")[mi % 4])),
    }


def _daily_star_index(res: dict, time_index: int) -> dict:
    mi = res["month_index"]
    lunar_day = res["lunar_day"]
    zuo, you = _zuo_you(mi + 1)
    chang, qu = _chang_qu(time_index)
    day_index = lunar_day if time_index >= 12 else lunar_day - 1
    return {
        "santai": _fix(zuo + day_index), "bazuo": _fix(you - day_index),
        "enguang": _fix(chang + day_index - 1), "tiangui": _fix(qu + day_index - 1),
    }


def _timely_star_index(time_index: int) -> dict:
    ti = _fix(time_index)
    return {"taifu": _fix(_febi("午") + ti), "fenggao": _fix(_febi("寅") + ti)}


# --------------------------------------------------------------------------- #
# 十二神组
# --------------------------------------------------------------------------- #
def _same_yinyang(gender: str, year_branch: str) -> bool:
    """阳男阴女为顺行组（True）。"""
    return ("阳" if gender == "男" else "阴") == T.branch_yinyang(year_branch)


def _changsheng12(res: dict, gender: str) -> list[str]:
    start = _febi(T.CHANGSHENG_START_BRANCH[res["five_class"]])
    forward = _same_yinyang(gender, res["year_branch"])
    out = [""] * 12
    for i, name in enumerate(T.CHANGSHENG_12):
        out[_fix(start + i if forward else start - i)] = name
    return out


def _boshi12(res: dict, gender: str) -> list[str]:
    lu = _lu_yang_tuo_ma(res["year_stem"], res["year_branch"])["lu"]
    forward = _same_yinyang(gender, res["year_branch"])
    out = [""] * 12
    for i, name in enumerate(T.BOSHI_12):
        out[_fix(lu + i if forward else lu - i)] = name
    return out


def _jiangqian12(res: dict) -> list[str]:
    start = _febi(T.JIANGXING_START_BRANCH[res["year_branch"]])
    out = [""] * 12
    for i, name in enumerate(T.JIANGQIAN_12):
        out[_fix(start + i)] = name
    return out


def _suiqian12(res: dict) -> list[str]:
    start = _febi(res["year_branch"])
    out = [""] * 12
    for i, name in enumerate(T.SUIQIAN_12):
        out[_fix(start + i)] = name
    return out


# --------------------------------------------------------------------------- #
# 大限 / 小限
# --------------------------------------------------------------------------- #
def _decadals(res: dict, gender: str) -> list[Decadal | None]:
    soul = res["soul_index"]
    five_value = T.FIVE_ELEMENTS_VALUE[res["five_class"]]
    start_stem = T.TIGER_RULE[res["year_stem"]]
    forward = _same_yinyang(gender, res["year_branch"])
    out: list[Decadal | None] = [None] * 12
    for i in range(12):
        idx = _fix(soul + i) if forward else _fix(soul - i)
        start = five_value + 10 * i
        stem_idx = _fix(T.HEAVENLY_STEMS.index(start_stem) + idx, 10)
        branch_idx = _fix(T.YIN_BRANCH_INDEX + idx)
        out[idx] = Decadal([start, start + 9], T.HEAVENLY_STEMS[stem_idx], T.EARTHLY_BRANCHES[branch_idx])
    return out


def _age_index(year_branch: str) -> int:
    if year_branch in ("寅", "午", "戌"):
        return _febi("辰")
    if year_branch in ("申", "子", "辰"):
        return _febi("戌")
    if year_branch in ("巳", "酉", "丑"):
        return _febi("未")
    return _febi("丑")  # 亥卯未


def _ages(res: dict, gender: str) -> list[list[int]]:
    age_idx = _age_index(res["year_branch"])
    out: list[list[int]] = [[] for _ in range(12)]
    for i in range(12):
        age = [12 * j + i + 1 for j in range(10)]
        idx = _fix(age_idx + i) if gender == "男" else _fix(age_idx - i)
        out[idx] = age
    return out


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
def cast_chart(
    *,
    solar_date: str | None = None,
    lunar_date: str | None = None,
    leap: bool = False,
    time_index: int,
    gender: str,
    calendar: str = "solar",
    fix_leap: bool = True,
) -> Chart:
    """排一张紫微斗数命盘。

    Args:
        solar_date: 阳历 'YYYY-MM-DD'（calendar='solar' 时必填）。
        lunar_date: 农历 'YYYY-M-D'（calendar='lunar' 时必填），leap 指示是否闰月。
        time_index: 时辰序号 0~12（0=早子，12=晚子）。
        gender: '男' 或 '女'。
        calendar: 'solar' | 'lunar'。
        fix_leap: 是否按闰月上/下半月规则调整（默认 True）。

    Returns:
        Chart 对象。非法参数抛 ValueError。
    """
    if gender not in ("男", "女"):
        raise ValueError("性别须为「男」或「女」")
    if not isinstance(time_index, int) or not 0 <= time_index <= 12:
        raise ValueError("时辰序号须在 0~12 之间")
    if calendar not in ("solar", "lunar"):
        raise ValueError("calendar 仅支持 solar 或 lunar")

    if calendar == "solar":
        if not solar_date:
            raise ValueError("阳历模式需提供 solar_date")
        y, m, d = _parse_ymd(solar_date)
        solar = datetime.date(y, m, d)
    else:
        if not lunar_date:
            raise ValueError("农历模式需提供 lunar_date")
        y, m, d = _parse_ymd(lunar_date)
        solar = _solar_from_lunar(y, m, d, leap)

    if not MIN_YEAR <= solar.year <= MAX_YEAR:
        raise ValueError(f"日期须在 {MIN_YEAR}~{MAX_YEAR} 年之间")

    res = _resolve_calendar(solar, time_index, fix_leap)
    ys = res["year_stem"]

    # 建 12 宫
    palace_names = [T.PALACE_NAMES[_fix(i - res["soul_index"])] for i in range(12)]
    palaces = [
        Palace(
            index=i,
            name=palace_names[i],
            heavenly_stem=T.HEAVENLY_STEMS[_fix(T.HEAVENLY_STEMS.index(res["heavenly_stem_of_soul"]) - res["soul_index"] + i, 10)],
            earthly_branch=T.EARTHLY_BRANCHES[_fix(T.YIN_BRANCH_INDEX + i)],
            is_body=(i == res["body_index"]),
        )
        for i in range(12)
    ]

    # 主星
    ziwei, tianfu = _start_index(res)
    for i, name in enumerate(T.ZIWEI_GROUP):
        if name:
            _add_major(palaces, _fix(ziwei - i), name, ys)
    for i, name in enumerate(T.TIANFU_GROUP):
        if name:
            _add_major(palaces, _fix(tianfu + i), name, ys)

    # 辅煞星
    _place_minor(palaces, res, time_index, ys)
    # 杂曜
    _place_adjective(palaces, res, time_index, gender)

    # 十二神组
    cs, bo, jq, sq = _changsheng12(res, gender), _boshi12(res, gender), _jiangqian12(res), _suiqian12(res)
    decadal = _decadals(res, gender)
    ages = _ages(res, gender)
    for i in range(12):
        palaces[i].changsheng12 = cs[i]
        palaces[i].boshi12 = bo[i]
        palaces[i].jiangqian12 = jq[i]
        palaces[i].suiqian12 = sq[i]
        palaces[i].decadal = decadal[i]
        palaces[i].ages = ages[i]

    soul_branch = res["earthly_branch_of_soul"]
    lunar = res["lunar"]
    chart = Chart(
        gender=gender,
        solar_date=solar.isoformat(),
        lunar_date=f"{lunar.getYearInGanZhi()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
        time_index=time_index,
        time_name=T.CHINESE_TIME[time_index],
        time_range=T.TIME_RANGE[time_index],
        zodiac=ZODIAC[T.EARTHLY_BRANCHES.index(res["year_branch"])],
        earthly_branch_of_soul=soul_branch,
        earthly_branch_of_body=T.EARTHLY_BRANCHES[_fix(res["body_index"] + T.YIN_BRANCH_INDEX)],
        soul_star=T.SOUL_STAR_BY_BRANCH[soul_branch],
        body_star=T.BODY_STAR_BY_BRANCH[res["year_branch"]],
        five_elements_class=res["five_class"],
        palaces=palaces,
    )
    _fill_four_pillars(chart, solar, time_index)
    return chart


def _add_major(palaces: list[Palace], idx: int, name: str, year_stem: str) -> None:
    palaces[idx].major_stars.append(
        Star(name, "major", _brightness(name, idx), _mutagen(name, year_stem))
    )


def _place_minor(palaces: list[Palace], res: dict, time_index: int, year_stem: str) -> None:
    ys, yb = res["year_stem"], res["year_branch"]
    mi = res["month_index"]
    zuo, you = _zuo_you(mi + 1)
    chang, qu = _chang_qu(time_index)
    kui, yue = _kui_yue(ys)
    huo, ling = _huo_ling(yb, time_index)
    kong, jie = _kong_jie(time_index)
    lym = _lu_yang_tuo_ma(ys, yb)
    placements = [
        ("左辅", zuo), ("右弼", you), ("文昌", chang), ("文曲", qu),
        ("天魁", kui), ("天钺", yue), ("禄存", lym["lu"]), ("天马", lym["ma"]),
        ("地空", kong), ("地劫", jie), ("火星", huo), ("铃星", ling),
        ("擎羊", lym["yang"]), ("陀罗", lym["tuo"]),
    ]
    for name, idx in placements:
        idx = _fix(idx)
        palaces[idx].minor_stars.append(
            Star(name, T.MINOR_STAR_TYPES[name], _brightness(name, idx), _mutagen(name, year_stem))
        )


def _place_adjective(palaces: list[Palace], res: dict, time_index: int, gender: str) -> None:
    y = _yearly_star_index(res, gender)
    mo = _monthly_star_index(res, time_index)
    da = _daily_star_index(res, time_index)
    ti = _timely_star_index(time_index)
    hongluan, tianxi = _luan_xi(res["year_branch"])
    placements = [
        ("红鸾", hongluan), ("天喜", tianxi), ("天姚", mo["tianyao"]), ("咸池", y["xianchi"]),
        ("解神", mo["jieshen"]), ("三台", da["santai"]), ("八座", da["bazuo"]),
        ("恩光", da["enguang"]), ("天贵", da["tiangui"]), ("龙池", y["longchi"]),
        ("凤阁", y["fengge"]), ("天才", y["tiancai"]), ("天寿", y["tianshou"]),
        ("台辅", ti["taifu"]), ("封诰", ti["fenggao"]), ("天巫", mo["tianwu"]),
        ("华盖", y["huagai"]), ("天官", y["tianguan"]), ("天福", y["tianfu"]),
        ("天厨", y["tianchu"]), ("天月", mo["tianyue"]), ("天德", y["tiande"]),
        ("月德", y["yuede"]), ("天空", y["tiankong"]), ("旬空", y["xunkong"]),
        ("截路", y["jielu"]), ("空亡", y["kongwang"]),
        ("孤辰", y["guchen"]), ("寡宿", y["guasu"]), ("蜚廉", y["feilian"]),
        ("破碎", y["posui"]), ("天刑", mo["tianxing"]), ("阴煞", mo["yinsha"]),
        ("天哭", y["tianku"]), ("天虚", y["tianxu"]), ("天使", y["tianshi"]),
        ("天伤", y["tianshang"]), ("年解", y["nianjie"]),
    ]
    for name, idx in placements:
        idx = _fix(idx)
        palaces[idx].adjective_stars.append(Star(name, T.ADJECTIVE_STAR_TYPES[name]))


def _parse_ymd(s: str) -> tuple[int, int, int]:
    parts = s.strip().replace("/", "-").split("-")
    if len(parts) != 3:
        raise ValueError(f"日期格式应为 YYYY-M-D，收到「{s}」")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as e:
        raise ValueError(f"日期无法解析：{s}") from e


def _fill_four_pillars(chart: Chart, solar: datetime.date, time_index: int) -> None:
    """四柱（干支）——展示用，非 oracle 校验项；异常不外泄。"""
    try:
        if time_index == 12:
            hour = 23
        elif time_index == 0:
            hour = 0
        else:
            hour = 2 * time_index - 1
        lunar = Solar.fromYmdHms(solar.year, solar.month, solar.day, hour, 0, 0).getLunar()
        ec = lunar.getEightChar()
        chart.yearly_ganzhi = ec.getYear()
        chart.monthly_ganzhi = ec.getMonth()
        chart.daily_ganzhi = ec.getDay()
        chart.hourly_ganzhi = ec.getTime()
    except Exception:  # noqa: BLE001  展示字段，失败不影响命盘主体
        pass
