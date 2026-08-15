"""八字排盘工具（基于 lunar-python 纯算法实现）。

提供四柱排盘、五行分析、十神、纳音、大运流年、空亡等完整命理计算。
支持公历、农历、传统时辰、八字干支等多种输入格式。
"""
from __future__ import annotations

import re

from langchain_core.tools import tool
from lunar_python import Lunar, Solar

from app.domain.bazi_engine import (
    GZ_WUXING,
    build_bazi_chart,
    format_analysis_text,
    format_chart_text,
    format_dayun_text,
    format_fact_context,
    format_liunian_text,
    parse_birth,
    parse_gender,
)

# 时间解析（农历/节日/时辰智能解析与出生时间标准化）已下沉到领域层
# app/domain/time_parse.py（消除记忆层对工具层的反向依赖）；此处重导入以保持本模块引用不变
from app.domain.time_parse import (
    _CN_DAY,
    _CN_MONTH,
    _normalize_birth_time,
    _parse_birth_smart,
    _parse_cn_day,
    _parse_zhi_hour,
)
from app.tools.cache import bazi_cache


def _parse_gender(gender):
    return parse_gender(gender)


def _apply_solar_time(y: int, m: int, d: int, h: int, mi: int, longitude: float | None) -> tuple:
    """真太阳时校正：基准经度 120°E（北京时间），每度差 4 分钟。返回校正后的 (y, m, d, h, mi)。"""
    import datetime as _dt
    corr = 0
    if longitude and 60 <= longitude <= 140:
        corr = round((120 - longitude) * 4)
    if corr == 0:
        return y, m, d, h, mi
    corrected = _dt.datetime(y, m, d, h, mi) + _dt.timedelta(minutes=corr)
    return corrected.year, corrected.month, corrected.day, corrected.hour, corrected.minute


@tool
def lunar_to_solar(query: str) -> str:
    """农历日期、传统节日、传统时辰转公历工具。

    当用户用农历、节日、时辰表达时间时，调用本工具转换为公历日期+具体时辰，
    避免手动换算错误。

    Args:
        query: 农历或节日表达式，如：
            - "农历2004年五月初五" → 返回公历 2004-06-22
            - "2004年端午节" → 返回公历 2004-06-22
            - "辰时" → 返回 08:00
            - "2004年农历五月初五 辰时" → 返回公历 2004-06-22 08:00

    Returns:
        转换后的公历日期+时辰，以及对应的八字四柱（如可用）
    """
    try:
        # 节日映射：把"春节/端午/中秋/重阳"等转为该年农历日期
        FESTIVAL_MAP = {
            "春节": ("正", "初一"), "元旦": ("正", "初一"),
            "端午": ("五", "初五"), "端午日": ("五", "初五"),
            "中秋": ("八", "十五"), "中秋日": ("八", "十五"),
            "重阳": ("九", "初九"), "重阳节": ("九", "初九"),
            "元宵": ("正", "十五"), "元宵节": ("正", "十五"),
            "七夕": ("七", "初七"), "七夕节": ("七", "初七"),
            "中元": ("七", "十五"), "中元节": ("七", "十五"),
            "腊八": ("十二", "初八"), "腊八节": ("十二", "初八"),
            "冬至": ("十一", "初"),  # 冬至按节气，简化处理
        }
        s = query.strip()
        # 提取年份
        ym = re.search(r"(\d{4})年", s)
        year = int(ym.group(1)) if ym else None

        # 节日替换：把节日名转成"X月初X"
        for festival, (mo, day) in FESTIVAL_MAP.items():
            if festival in s and year:
                # 冬至特殊处理（按节气，这里用近似日期）
                if festival == "冬至":
                    # 冬至在公历12月21-23日之间，用 lunar-python 查节气
                    solar_test = Solar.fromYmdHms(year, 12, 22, 12, 0, 0)
                    lunar_test = solar_test.getLunar()
                    jieqi = lunar_test.getJieQiTable()
                    dongzhi_date = jieqi.get("冬至")
                    if dongzhi_date:
                        return f"{festival}({year}年) → 公历 {dongzhi_date.getYear()}-{dongzhi_date.getMonth():02d}-{dongzhi_date.getDay():02d}"
                # 普通节日：按农历月/日构造，提取时辰
                zhi_h = _parse_zhi_hour(s)
                hh = zhi_h if zhi_h is not None else 8
                mm = 0
                lunar_obj = Lunar.fromYmdHms(year, _CN_MONTH.get(mo, 5), _CN_DAY.get(day, 5), hh, mm, 0)
                solar_obj = lunar_obj.getSolar()
                return f"{s} → 公历 {solar_obj.getYear()}-{solar_obj.getMonth():02d}-{solar_obj.getDay():02d} {hh:02d}:{mm:02d}"

        # 不是节日，尝试直接解析为农历
        # 1) 含农历字眼
        if "农历" in s or "阴历" in s or _parse_cn_day(s) is not None:
            # 用 _parse_birth_smart 处理
            solar, lunar, ec, h, mi, source = _parse_birth_smart(s)
            return f"{s} → 公历 {solar.getYear()}-{solar.getMonth():02d}-{solar.getDay():02d} {h:02d}:{mi:02d}"

        # 2) 仅时辰
        zhi_h = _parse_zhi_hour(s)
        if zhi_h is not None and not ym:
            return f"传统时辰 {s} → {zhi_h:02d}:00（{zhi_h}点-{zhi_h+2 if zhi_h<22 else 0}点之间）"

        return f"无法识别的格式: {query}"
    except Exception as e:
        return f"转换失败: {e}"


@tool
def bazi_chart(birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1) -> str:
    """根据出生时间排八字四柱。支持公历、农历、传统时辰、节日等多种输入。

    Args:
        birth_time: 出生时间，支持以下格式：
            - 公历: "1990-05-20 14:30"
            - 公历+时辰: "1990-05-20 辰时"
            - 农历: "农历1990年四月廿六 8:00" 或 "1990年农历五月初五 辰时"
            - 农历中文日: "农历2004年五月初五 辰时"
        gender: 性别，男 或 女（影响大运起运方向，请务必提供）
        sect: 日柱计算流派，1=按日期精确，2=按日期精确2（默认）。影响早晚子时日柱归属
        yun_sect: 大运计算流派，1=按天数和时辰数（默认，3天1年），2=按分钟数

    Returns:
        年柱/月柱/日柱/时柱、生肖、农历、纳音、空亡等信息
    """
    try:
        birth_time = _normalize_birth_time(birth_time)
        cached = bazi_cache.get(birth_time, gender, sect, yun_sect, "chart")
        if cached:
            return cached
        chart = build_bazi_chart(birth_time, gender, sect=sect, yun_sect=yun_sect)
        result = format_chart_text(chart)
        bazi_cache.set(birth_time, gender, result, sect, yun_sect, "chart")
        return result
    except Exception as e:
        return "排盘失败: {}".format(e)


@tool
def bazi_analysis(birth_time: str, gender: str, question: str = "整体运势", sect: int = 2) -> str:
    """对八字进行基础五行与十神分析。

    Args:
        birth_time: 同 bazi_chart
        gender: 同 bazi_chart
        question: 分析方向，如事业、感情、财运、健康
        sect: 日柱计算流派，1=按日期精确，2=按日期精确2（默认）

    Returns:
        五行分布、日主强弱、十神关系、用神建议
    """
    try:
        birth_time = _normalize_birth_time(birth_time)
        cache_tool = "analysis:{}".format(question or "整体运势")
        cached = bazi_cache.get(birth_time, gender, sect, 1, cache_tool)
        if cached:
            return cached
        chart = build_bazi_chart(birth_time, gender, sect=sect, yun_sect=1)
        result = format_analysis_text(chart, question)
        bazi_cache.set(birth_time, gender, result, sect, 1, cache_tool)
        return result
    except Exception as e:
        return "分析失败: {}".format(e)


@tool
def bazi_dayun(birth_time: str, gender: str, count: int = 8, yun_sect: int = 1) -> str:
    """推算大运（每10年一柱）。

    Args:
        birth_time: 同 bazi_chart
        gender: 同 bazi_chart（决定大运顺逆排）
        count: 推算多少柱大运，默认8柱（80年）
        yun_sect: 大运计算流派，1=按天数和时辰数（默认，3天1年），2=按分钟数

    Returns:
        起运信息 + 每柱大运的干支、年份区间、岁数
    """
    try:
        birth_time = _normalize_birth_time(birth_time)
        cached = bazi_cache.get(birth_time, gender, 2, yun_sect, "dayun")
        if cached:
            return cached
        chart = build_bazi_chart(birth_time, gender, yun_sect=yun_sect, dayun_count=count)
        result = format_dayun_text(chart)
        bazi_cache.set(birth_time, gender, result, 2, yun_sect, "dayun")
        return result
    except Exception as e:
        return "大运推算失败: {}".format(e)


@tool
def bazi_liunian(birth_time: str, gender: str, years: int = 10, yun_sect: int = 1) -> str:
    """推算流年（逐年干支）。

    Args:
        birth_time: 同 bazi_chart
        gender: 同 bazi_chart
        years: 推算多少年，默认10年（从当前年份开始往后）
        yun_sect: 大运计算流派，1=按天数和时辰数（默认），2=按分钟数

    Returns:
        每年的干支、年份、虚岁
    """
    try:
        import datetime
        birth_time = _normalize_birth_time(birth_time)
        current_year = datetime.date.today().year
        # 缓存 key 含 years 与起始年，避免跨年后命中旧流年
        cache_tool = "liunian:{}:{}".format(years, current_year)
        cached = bazi_cache.get(birth_time, gender, 2, yun_sect, cache_tool)
        if cached:
            return cached
        chart = build_bazi_chart(
            birth_time,
            gender,
            yun_sect=yun_sect,
            dayun_count=12,
            liunian_years=years,
            liunian_start_year=current_year,
        )
        result = format_liunian_text(chart)
        bazi_cache.set(birth_time, gender, result, 2, yun_sect, cache_tool)
        return result
    except Exception as e:
        return "流年推算失败: {}".format(e)


@tool
def bazi_liuyue(birth_time: str, gender: str, year: int = None, sect: int = 2, yun_sect: int = 1) -> str:
    """推算流月（某一年的12个月干支）。

    Args:
        birth_time: 同 bazi_chart
        gender: 同 bazi_chart
        year: 目标年份，默认当前年份
        sect: 日柱计算流派
        yun_sect: 大运计算流派

    Returns:
        指定年份每个月的干支、节气信息
    """
    try:
        import datetime
        birth_time = _normalize_birth_time(birth_time)
        y, m, d, h, mi = parse_birth(birth_time)
        target_year = year or datetime.date.today().year
        # 缓存 key 含目标年份，避免不同年份互相污染
        cache_tool = "liuyue:{}".format(target_year)
        cached = bazi_cache.get(birth_time, gender, sect, yun_sect, cache_tool)
        if cached:
            return cached

        lines = ["【流月推算】{} 年".format(target_year), ""]

        for month in range(1, 13):
            solar = Solar.fromYmdHms(target_year, month, 1, 0, 0, 0)
            lunar = solar.getLunar()
            month_gz = lunar.getMonthInGanZhi()
            jieqi = lunar.getJieQi() or "无"
            lines.append("  {}月: {} | 节气: {}".format(month, month_gz, jieqi))

        lines.append("")
        lines.append("注: 流月按节气分界，非公历月份")
        result = "\n".join(lines)
        bazi_cache.set(birth_time, gender, result, sect, yun_sect, cache_tool)
        return result
    except Exception as e:
        return "流月推算失败: {}".format(e)


@tool
def bazi_liuri(birth_time: str, gender: str, year: int = None, month: int = None, sect: int = 2, yun_sect: int = 1) -> str:
    """推算流日（某一年某一月的每日干支）。

    Args:
        birth_time: 同 bazi_chart
        gender: 同 bazi_chart
        year: 目标年份，默认当前年份
        month: 目标月份，默认当前月份
        sect: 日柱计算流派
        yun_sect: 大运计算流派

    Returns:
        指定年月每日的干支、农历日期
    """
    try:
        import datetime
        today = datetime.date.today()
        target_year = year or today.year
        target_month = month or today.month
        # 流日与出生时间无关（纯日历推算），缓存 key 用固定占位
        cache_tool = "liuri:{}-{:02d}".format(target_year, target_month)
        cached = bazi_cache.get("calendar", "all", sect, yun_sect, cache_tool)
        if cached:
            return cached

        lines = ["【流日推算】{}年{}月".format(target_year, target_month), ""]

        from calendar import monthrange
        days_in_month = monthrange(target_year, target_month)[1]

        for day in range(1, days_in_month + 1):
            solar = Solar.fromYmdHms(target_year, target_month, day, 0, 0, 0)
            lunar = solar.getLunar()
            day_gz = lunar.getDayInGanZhi()
            lunar_day = lunar.getDayInChinese()
            lines.append("  {}日: {} | 农历: {}".format(day, day_gz, lunar_day))

        lines.append("")
        lines.append("注: 显示当月所有日期的干支")
        result = "\n".join(lines)
        bazi_cache.set("calendar", "all", result, sect, yun_sect, cache_tool)
        return result
    except Exception as e:
        return "流日推算失败: {}".format(e)


@tool
def bazi_hehun(birth_time_a: str, gender_a: str, birth_time_b: str, gender_b: str, sect: int = 2, longitude_a: float | None = None, longitude_b: float | None = None) -> str:
    """合婚分析：对比两个人的八字。

    Args:
        birth_time_a: 男方出生时间
        gender_a: 男方性别（男）
        birth_time_b: 女方出生时间
        gender_b: 女方性别（女）
        sect: 日柱计算流派，1=早子时（子时换日），2=晚子时（默认，子正换日）
        longitude_a: 男方出生地经度（°E，用于真太阳时校正，可选）
        longitude_b: 女方出生地经度（°E，用于真太阳时校正，可选）

    Returns:
        双方命盘对比、五行互补分析、合婚建议
    """
    try:
        birth_time_a = _normalize_birth_time(birth_time_a)
        birth_time_b = _normalize_birth_time(birth_time_b)
        # 合婚结果对双方输入确定，走缓存（双方时间+性别+流派+经度组合为 key）
        cache_key_a = "{}|{}|{}|{}".format(birth_time_a, gender_a, sect, longitude_a)
        cache_key_b = "{}|{}|{}|{}".format(birth_time_b, gender_b, sect, longitude_b)
        cached = bazi_cache.get(cache_key_a, cache_key_b, sect, 1, "hehun")
        if cached:
            return cached

        y_a, m_a, d_a, h_a, mi_a = parse_birth(birth_time_a)
        y_a, m_a, d_a, h_a, mi_a = _apply_solar_time(y_a, m_a, d_a, h_a, mi_a, longitude_a)
        g_a = _parse_gender(gender_a)
        solar_a = Solar.fromYmdHms(y_a, m_a, d_a, h_a, mi_a, 0)
        ec_a = solar_a.getLunar().getEightChar()
        if sect != 2:
            ec_a.setSect(sect)

        y_b, m_b, d_b, h_b, mi_b = parse_birth(birth_time_b)
        y_b, m_b, d_b, h_b, mi_b = _apply_solar_time(y_b, m_b, d_b, h_b, mi_b, longitude_b)
        g_b = _parse_gender(gender_b)
        solar_b = Solar.fromYmdHms(y_b, m_b, d_b, h_b, mi_b, 0)
        ec_b = solar_b.getLunar().getEightChar()
        if sect != 2:
            ec_b.setSect(sect)

        pillars_a = [ec_a.getYear(), ec_a.getMonth(), ec_a.getDay(), ec_a.getTime()]
        pillars_b = [ec_b.getYear(), ec_b.getMonth(), ec_b.getDay(), ec_b.getTime()]

        wx_a = {"金": 0, "木": 0, "水": 0, "火": 0, "土": 0}
        wx_b = {"金": 0, "木": 0, "水": 0, "火": 0, "土": 0}
        for p in pillars_a:
            for ch in p:
                if ch in GZ_WUXING:
                    wx_a[GZ_WUXING[ch]] += 1
        for p in pillars_b:
            for ch in p:
                if ch in GZ_WUXING:
                    wx_b[GZ_WUXING[ch]] += 1

        day_gan_a = ec_a.getDayGan()
        day_wx_a = GZ_WUXING.get(day_gan_a, "未知")
        day_gan_b = ec_b.getDayGan()
        day_wx_b = GZ_WUXING.get(day_gan_b, "未知")

        strongest_a = max(wx_a, key=wx_a.get)
        weakest_a = min(wx_a, key=wx_a.get)
        strongest_b = max(wx_b, key=wx_b.get)
        weakest_b = min(wx_b, key=wx_b.get)

        complement_score = 0
        complement_reasons = []
        if wx_a[weakest_a] < wx_b[weakest_a]:
            complement_score += 20
            complement_reasons.append("{}的最弱五行{}，{}相对较强，可互补".format(
                "男方" if g_a == 1 else "女方", weakest_a, "女方" if g_b == 0 else "男方"))
        if wx_b[weakest_b] < wx_a[weakest_b]:
            complement_score += 20
            complement_reasons.append("{}的最弱五行{}，{}相对较强，可互补".format(
                "女方" if g_b == 0 else "男方", weakest_b, "男方" if g_a == 1 else "女方"))
        if day_wx_a != day_wx_b:
            complement_score += 15
            complement_reasons.append("日主五行不同，相互生克更有活力")
        else:
            complement_score += 10
            complement_reasons.append("日主五行相同，心性相投")

        if len(complement_reasons) == 0:
            complement_reasons.append("五行分布较为均衡")

        lines = [
            "【合婚分析】",
            "",
            "【{}】".format("男方" if g_a == 1 else "女方"),
            "出生: {}-{:02d}-{:02d} {:02d}:{:02d}".format(y_a, m_a, d_a, h_a, mi_a),
            "四柱: {}".format(" ".join(pillars_a)),
            "日主: {}({})".format(day_gan_a, day_wx_a),
            "五行: {}".format(wx_a),
            "最强/最弱: {}/{}".format(strongest_a, weakest_a),
            "",
            "【{}】".format("女方" if g_b == 0 else "男方"),
            "出生: {}-{:02d}-{:02d} {:02d}:{:02d}".format(y_b, m_b, d_b, h_b, mi_b),
            "四柱: {}".format(" ".join(pillars_b)),
            "日主: {}({})".format(day_gan_b, day_wx_b),
            "五行: {}".format(wx_b),
            "最强/最弱: {}/{}".format(strongest_b, weakest_b),
            "",
            "【五行互补评分】{}分".format(min(complement_score, 100)),
        ] + ["  - " + r for r in complement_reasons]
        if longitude_a and 60 <= longitude_a <= 140:
            corr_a = round((120 - longitude_a) * 4)
            if corr_a != 0:
                lines.append("注: 男方出生地经度 {}°E，真太阳时校正 {:+d} 分钟".format(longitude_a, corr_a))
        if longitude_b and 60 <= longitude_b <= 140:
            corr_b = round((120 - longitude_b) * 4)
            if corr_b != 0:
                lines.append("注: 女方出生地经度 {}°E，真太阳时校正 {:+d} 分钟".format(longitude_b, corr_b))
        lines.append("注: 此为基础合婚分析，完整合婚需结合大运流年，由 LLM 综合判断")

        result = "\n".join(lines)
        bazi_cache.set(cache_key_a, cache_key_b, result, sect, 1, "hehun")
        return result
    except Exception as e:
        return "合婚分析失败: {}".format(e)


@tool
def bazi_full(birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1) -> str:
    """完整排盘：四柱 + 五行 + 十神 + 纳音 + 神煞 + 大运 + 流年。

    一次性输出全部命理基础数据，适合需要全面分析时调用。

    Args:
        birth_time: 同 bazi_chart
        gender: 同 bazi_chart
        sect: 日柱计算流派，1=按日期精确，2=按日期精确2（默认）
        yun_sect: 大运计算流派，1=按天数和时辰数（默认），2=按分钟数

    Returns:
        完整的八字命盘信息
    """
    try:
        birth_time = _normalize_birth_time(birth_time)
        chart = build_bazi_chart(birth_time, gender, sect=sect, yun_sect=yun_sect)
        return format_fact_context(chart)
    except Exception as e:
        return "完整排盘失败: {}".format(e)


@tool
def bazi_infer_dates(pillars: str, gender: str, top_n: int = 3) -> str:
    """根据八字反推可能的出生日期。

    当用户只提供八字（如"我的八字是甲申庚午壬申甲辰，我是男命"）而不知精确出生时间时调用。
    返回若干候选出生日期，请向用户展示并请其确认实际出生日期（可回复序号或具体日期），
    确认后用对应 birth_time 调用 bazi_full 等工具排盘。

    Args:
        pillars: 八字四柱连续干支，如 "甲申庚午壬申甲辰"
        gender: 男/女
        top_n: 最多返回候选数（默认 3）

    Returns:
        候选出生日期列表与选择指引
    """
    try:
        from app.domain.bazi_engine import find_birth_dates_from_pillars
        candidates = find_birth_dates_from_pillars(pillars, gender, top_n=top_n)
    except ValueError as e:
        return "八字解析失败: {}".format(e)
    except Exception as e:
        return "反推出生日期失败: {}".format(e)
    if not candidates:
        return "未能根据八字 {}（{}）反推出候选出生日期，请确认八字是否正确。".format(pillars, gender)
    lines = ["根据你提供的八字 {}（{}），反推可能的出生日期如下：".format(pillars, gender)]
    for i, c in enumerate(candidates, 1):
        lines.append("  {}. {}（{}，{}）".format(i, c["birth_time"], c["ganzhi"], c["shi_chen"]))
    lines.append("请回复序号或具体日期确认你的实际出生日期，我再用该日期为你完整排盘。")
    return "\n".join(lines)


bazi_tools = [lunar_to_solar, bazi_chart, bazi_analysis, bazi_dayun, bazi_liunian, bazi_liuyue, bazi_liuri, bazi_hehun, bazi_full, bazi_infer_dates]
