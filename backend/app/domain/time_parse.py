"""出生时间解析（领域层公共工具）。

将公历/农历/节日/传统时辰等多种输入统一解析为标准公历时间；
供工具层与记忆层（app.memory.postgres_memory）共用。
"""
from __future__ import annotations

import re

from lunar_python import Lunar, Solar

from app.domain.chart_builder import parse_birth

# 传统时辰（地支）→ 小时映射，子时跨 23-1 点按早子时处理
_ZHI_HOUR = {
    "子": 0, "丑": 2, "寅": 4, "卯": 6, "辰": 8, "巳": 10,
    "午": 12, "未": 14, "申": 16, "酉": 18, "戌": 20, "亥": 22,
}
_CN_DAY = {"初一": 1, "初二": 2, "初三": 3, "初四": 4, "初五": 5, "初六": 6, "初七": 7, "初八": 8, "初九": 9, "初十": 10,
           "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
           "廿一": 21, "廿二": 22, "廿三": 23, "廿四": 24, "廿五": 25, "廿六": 26, "廿七": 27, "廿八": 28, "廿九": 29, "三十": 30}
_CN_MONTH = {"正": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}


def _parse_zhi_hour(text: str) -> int | None:
    """识别传统时辰（如"辰时""午时"），返回该时辰正刻小时。"""
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
    m = re.search(r"([正一二三四五六七八九十]+)月", text)
    if m:
        return _CN_MONTH.get(m.group(1))
    return None


def _parse_birth_smart(birth_time: str) -> tuple:
    """智能解析出生时间，返回 (solar, lunar, ec, hour, minute, source_label)。

    支持公历、农历、传统时辰、节日等格式；source_label 标识输入类型。
    """
    s = (birth_time or "").strip()
    if not s:
        raise ValueError("出生时间为空")

    # 节日预处理：将"春节/端午/中秋"等替换为农历日期
    FESTIVAL_MAP = {
        "春节": ("正", "初一"), "元旦": ("正", "初一"),
        "端午": ("五", "初五"), "端午日": ("五", "初五"),
        "中秋": ("八", "十五"), "中秋日": ("八", "十五"),
        "重阳": ("九", "初九"), "重阳节": ("九", "初九"),
        "元宵": ("正", "十五"), "元宵节": ("正", "十五"),
        "七夕": ("七", "初七"), "七夕节": ("七", "初七"),
        "中元": ("七", "十五"), "中元节": ("七", "十五"),
        "腊八": ("十二", "初八"), "腊八节": ("十二", "初八"),
    }
    ym = re.search(r"(\d{4})年", s)
    year = int(ym.group(1)) if ym else None
    for festival, (mo, day) in FESTIVAL_MAP.items():
        if festival in s and year:
            s = re.sub(re.escape(festival), f"农历{year}年{mo}月{day}", s)
            break

    # 识别时辰：优先 HH:MM，其次传统时辰
    hour, minute = 0, 0
    time_label = ""
    m = re.search(r"(\d{1,2})[:：](\d{1,2})", s)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("时辰必须在 00:00-23:59")
        time_label = f"{hour:02d}:{minute:02d}"
    else:
        zhi_h = _parse_zhi_hour(s)
        if zhi_h is not None:
            hour = zhi_h
            minute = 0
            time_label = "传统时辰"

    # 含"农历/阴历"字眼或中文日 → 按农历解析
    is_lunar = ("农历" in s or "阴历" in s or _parse_cn_day(s) is not None)

    if is_lunar:
        ym = re.search(r"(\d{4})年", s)
        if not ym:
            raise ValueError("农历输入需提供年份，如 农历2004年五月初五")
        year = int(ym.group(1))
        month = _parse_cn_month(s)
        day = _parse_cn_day(s)
        if day is None:  # 数字日兜底
            dm = re.search(r"月(\d{1,2})", s)
            if dm:
                day = int(dm.group(1))
        if month is None or day is None:
            raise ValueError("农历输入需提供月日，如 农历2004年五月初五")
        lunar = Lunar.fromYmdHms(year, month, day, hour, minute, 0)
        solar = lunar.getSolar()
        ec = lunar.getEightChar()
        return solar, lunar, ec, hour, minute, f"农历({s})→公历{solar.toYmd()}"

    # 公历 + 传统时辰：从字符串提取日期，时辰用已识别小时
    if time_label == "传统时辰":
        dm = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", s)
        if dm:
            y, mo, d = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
            solar = Solar.fromYmdHms(y, mo, d, hour, minute, 0)
            lunar = solar.getLunar()
            ec = lunar.getEightChar()
            return solar, lunar, ec, hour, minute, "公历+时辰"

    # 纯公历
    y, mo, d, h, mi = parse_birth(birth_time)
    solar = Solar.fromYmdHms(y, mo, d, h, mi, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    return solar, lunar, ec, h, mi, "公历"


def _normalize_birth_time(birth_time: str) -> str:
    """将农历/节日/时辰等格式标准化为公历字符串 YYYY-MM-DD HH:MM。

    供 bazi_* 工具入口调用，确保 build_bazi_chart 拿到的是公历。
    """
    s = (birth_time or "").strip()
    if not s:
        raise ValueError("出生时间为空")
    # 公历快速识别：纯数字 YYYY-MM-DD HH:MM 格式
    if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}[\sT]+\d{1,2}[:：]\d{1,2}", s):
        return s.replace("/", "-").replace("：", ":")
    solar, lunar, ec, h, mi, source = _parse_birth_smart(s)
    return "{}-{:02d}-{:02d} {:02d}:{:02d}".format(
        solar.getYear(), solar.getMonth(), solar.getDay(), h, mi
    )
