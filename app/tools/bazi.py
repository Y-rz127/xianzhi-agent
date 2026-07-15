"""八字排盘工具（基于 lunar-python 纯算法实现）。

提供四柱排盘、五行分析、十神、纳音、大运流年、空亡等完整命理计算。
支持公历、农历、传统时辰、八字干支等多种输入格式。
"""
from __future__ import annotations
import re
from langchain_core.tools import tool
from lunar_python import Solar, Lunar, EightChar
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


# 传统时辰（地支）→ 小时映射，子时跨 23-1 点按早子时处理
_ZHI_HOUR = {
    "子": 0, "丑": 2, "寅": 4, "卯": 6, "辰": 8, "巳": 10,
    "午": 12, "未": 14, "申": 16, "酉": 18, "戌": 20, "亥": 22,
}
# 农历日中文数字 → 阿拉伯数字
_CN_DAY = {"初一": 1, "初二": 2, "初三": 3, "初四": 4, "初五": 5, "初六": 6, "初七": 7, "初八": 8, "初九": 9, "初十": 10,
           "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
           "廿一": 21, "廿二": 22, "廿三": 23, "廿四": 24, "廿五": 25, "廿六": 26, "廿七": 27, "廿八": 28, "廿九": 29, "三十": 30}
_CN_MONTH = {"正": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}


def _parse_zhi_hour(text: str) -> int | None:
    """从文本中识别传统时辰（如"辰时""午时"），返回对应小时（取该时辰正刻）。"""
    for zhi, h in _ZHI_HOUR.items():
        if zhi + "时" in text:
            return h
    return None


def _parse_cn_day(text: str) -> int | None:
    """识别农历中文日（初一、廿三等）。"""
    for cn, n in _CN_DAY.items():
        if cn in text:
            return n
    return None


def _parse_cn_month(text: str) -> int | None:
    """识别农历中文月（正月、五月等），支持"闰"前缀。"""
    # 优先匹配 "X月"
    m = re.search(r"([正一二三四五六七八九十]+)月", text)
    if m:
        return _CN_MONTH.get(m.group(1))
    return None


def _parse_birth_smart(birth_time: str) -> tuple:
    """智能解析出生时间，支持公历、农历、传统时辰、八字干支等多种格式。

    返回 (solar, lunar, ec, hour, minute, source_label)。
    source_label 标识输入类型，便于排盘结果中提示用户。

    支持格式：
    - 公历："1990-05-20 14:30"
    - 公历+时辰："1990-05-20 辰时"
    - 农历："农历1990年四月廿六 8:00" 或 "1990年农历五月初五 辰时"
    - 节日："端午节辰时" 等（需配合 year 一起，如 "2004年端午节 辰时"）
    """
    s = (birth_time or "").strip()
    if not s:
        raise ValueError("出生时间为空")

    # 提取时辰：先尝试 HH:MM，再尝试传统时辰
    hour, minute = 0, 0
    time_label = ""

    # 1) 优先识别 HH:MM
    m = re.search(r"(\d{1,2})[:：](\d{1,2})", s)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("时辰必须在 00:00-23:59")
        time_label = f"{hour:02d}:{minute:02d}"
    else:
        # 2) 尝试传统时辰
        zhi_h = _parse_zhi_hour(s)
        if zhi_h is not None:
            hour = zhi_h
            minute = 0
            time_label = f"传统时辰"

    # 判断农历：含"农历"或"农历"相关字眼，或含中文日（初一/廿三等）
    is_lunar = ("农历" in s or "阴历" in s or
                _parse_cn_day(s) is not None)

    # 农历排盘
    if is_lunar:
        # 提取年
        ym = re.search(r"(\d{4})年", s)
        if not ym:
            raise ValueError("农历输入需提供年份，如 农历2004年五月初五")
        year = int(ym.group(1))
        month = _parse_cn_month(s)
        day = _parse_cn_day(s)
        # 数字日兜底
        if day is None:
            dm = re.search(r"月(\d{1,2})", s)
            if dm:
                day = int(dm.group(1))
        if month is None or day is None:
            raise ValueError("农历输入需提供月日，如 农历2004年五月初五")
        lunar = Lunar.fromYmdHms(year, month, day, hour, minute, 0)
        solar = lunar.getSolar()
        ec = lunar.getEightChar()
        return solar, lunar, ec, hour, minute, f"农历({s})→公历{solar.toYmd()}"

    # 公历排盘
    # 若检测到传统时辰（无 HH:MM），只从字符串提取日期，时辰用已识别的小时
    if time_label == "传统时辰":
        dm = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", s)
        if dm:
            y, mo, d = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
            solar = Solar.fromYmdHms(y, mo, d, hour, minute, 0)
            lunar = solar.getLunar()
            ec = lunar.getEightChar()
            return solar, lunar, ec, hour, minute, "公历+时辰"
    # 沿用原 parse_birth 处理纯公历
    y, mo, d, h, mi = parse_birth(birth_time)
    solar = Solar.fromYmdHms(y, mo, d, h, mi, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    return solar, lunar, ec, h, mi, "公历"


def _parse_gender(gender):
    return parse_gender(gender)


def _normalize_birth_time(birth_time: str) -> str:
    """将农历/节日/时辰等格式标准化为公历字符串 YYYY-MM-DD HH:MM。

    供所有 bazi_* 工具入口调用，确保 build_bazi_chart 拿到的是公历。
    如果输入已是公历，原样返回。
    """
    s = (birth_time or "").strip()
    if not s:
        raise ValueError("出生时间为空")
    # 公历快速识别：纯数字 YYYY-MM-DD HH:MM 格式
    if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}[\sT]+\d{1,2}[:：]\d{1,2}", s):
        return s.replace("/", "-").replace("：", ":")
    # 用智能解析转公历
    solar, lunar, ec, h, mi, source = _parse_birth_smart(s)
    return "{}-{:02d}-{:02d} {:02d}:{:02d}".format(
        solar.getYear(), solar.getMonth(), solar.getDay(), h, mi
    )


def _get_eight_char(birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1):
    """排盘并应用流派参数，返回 (solar, lunar, eight_char, yun, gender_int)。

    使用 _parse_birth_smart 智能识别公历/农历/传统时辰。
    """
    solar, lunar, ec, h, mi, source = _parse_birth_smart(birth_time)
    g = _parse_gender(gender)
    if sect != 2:
        ec.setSect(sect)
    yun = ec.getYun(g, yun_sect)
    return solar, lunar, ec, yun, g


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
                # 普通节日：构造农历表达式
                cn_month_str = mo + "月"
                cn_day_str = day + ("日" if not day.startswith("初") else "")
                # 构造完整农历时间，提取时辰
                lunar_str = f"农历{year}年{cn_month_str}{day}"
                # 提取时辰
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
        birth_time = _normalize_birth_time(birth_time)
        y, m, d, h, mi = parse_birth(birth_time)
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

        birth_time_a = _normalize_birth_time(birth_time_a)
        birth_time_b = _normalize_birth_time(birth_time_b)
        y_a, m_a, d_a, h_a, mi_a = parse_birth(birth_time_a)
        g_a = _parse_gender(gender_a)
        solar_a = Solar.fromYmdHms(y_a, m_a, d_a, h_a, mi_a, 0)
        ec_a = solar_a.getLunar().getEightChar()
        if sect != 2:
            ec_a.setSect(sect)

        y_b, m_b, d_b, h_b, mi_b = parse_birth(birth_time_b)
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


bazi_tools = [lunar_to_solar, bazi_chart, bazi_analysis, bazi_dayun, bazi_liunian, bazi_liuyue, bazi_liuri, bazi_hehun, bazi_full]
