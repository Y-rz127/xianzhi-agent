"""八字排盘工具（基于 lunar-python 纯算法实现）。

提供四柱排盘、五行分析、十神、纳音、大运流年、空亡等完整命理计算。
"""
from __future__ import annotations
from langchain_core.tools import tool
from lunar_python import Solar
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
from app.tools.cache import bazi_cache


def _parse_birth(birth_time):
    return parse_birth(birth_time)


def _parse_gender(gender):
    return parse_gender(gender)


def _get_eight_char(birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1):
    """排盘并应用流派参数，返回 (solar, lunar, eight_char, yun, gender_int)。"""
    y, m, d, h, mi = _parse_birth(birth_time)
    g = _parse_gender(gender)
    solar = Solar.fromYmdHms(y, m, d, h, mi, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    if sect != 2:
        ec.setSect(sect)
    yun = ec.getYun(g, yun_sect)
    return solar, lunar, ec, yun, g


@tool
def bazi_chart(birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1) -> str:
    """根据出生时间排八字四柱。

    Args:
        birth_time: 出生时间，格式 YYYY-MM-DD HH:MM，例如 1990-05-20 14:30
        gender: 性别，男 或 女（影响大运起运方向，请务必提供）
        sect: 日柱计算流派，1=按日期精确，2=按日期精确2（默认）。影响早晚子时日柱归属
        yun_sect: 大运计算流派，1=按天数和时辰数（默认，3天1年），2=按分钟数

    Returns:
        年柱/月柱/日柱/时柱、生肖、农历、纳音、空亡等信息
    """
    try:
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
        current_year = datetime.date.today().year
        chart = build_bazi_chart(
            birth_time,
            gender,
            yun_sect=yun_sect,
            dayun_count=12,
            liunian_years=years,
            liunian_start_year=current_year,
        )
        return format_liunian_text(chart)
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
        y, m, d, h, mi = _parse_birth(birth_time)
        target_year = year or datetime.date.today().year

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
        bazi_cache.set(birth_time, gender, result, 2, yun_sect, "liuyue")
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
        return "\n".join(lines)
    except Exception as e:
        return "流日推算失败: {}".format(e)


@tool
def bazi_hehun(birth_time_a: str, gender_a: str, birth_time_b: str, gender_b: str, sect: int = 2) -> str:
    """合婚分析：对比两个人的八字。

    Args:
        birth_time_a: 男方出生时间
        gender_a: 男方性别（男）
        birth_time_b: 女方出生时间
        gender_b: 女方性别（女）
        sect: 日柱计算流派

    Returns:
        双方命盘对比、五行互补分析、合婚建议
    """
    try:
        from collections import Counter

        y_a, m_a, d_a, h_a, mi_a = _parse_birth(birth_time_a)
        g_a = _parse_gender(gender_a)
        solar_a = Solar.fromYmdHms(y_a, m_a, d_a, h_a, mi_a, 0)
        ec_a = solar_a.getLunar().getEightChar()
        if sect != 2:
            ec_a.setSect(sect)

        y_b, m_b, d_b, h_b, mi_b = _parse_birth(birth_time_b)
        g_b = _parse_gender(gender_b)
        solar_b = Solar.fromYmdHms(y_b, m_b, d_b, h_b, mi_b, 0)
        ec_b = solar_b.getLunar().getEightChar()

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
        lines += ["", "注: 此为基础合婚分析，完整合婚需结合大运流年，由 LLM 综合判断"]

        return "\n".join(lines)
    except Exception as e:
        return "合婚分析失败: {}".format(e)


@tool
def bazi_full(birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1) -> str:
    """完整排盘：四柱 + 五行 + 十神 + 纳音 + 空亡 + 大运 + 流年。

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
        chart = build_bazi_chart(birth_time, gender, sect=sect, yun_sect=yun_sect)
        return format_fact_context(chart)
    except Exception as e:
        return "完整排盘失败: {}".format(e)


bazi_tools = [bazi_chart, bazi_analysis, bazi_dayun, bazi_liunian, bazi_liuyue, bazi_liuri, bazi_hehun, bazi_full]
