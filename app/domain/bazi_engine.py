"""Structured Bazi chart engine.

The public tools still return readable text, but this module is the factual
source of truth for chart data used by APIs, chart cases and agent context.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass
from typing import Any

from lunar_python import Solar


GAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}

ZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
    "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
    "戌": "土", "亥": "水",
}

GZ_WUXING = {**GAN_WUXING, **ZHI_WUXING}

HIDDEN_STEMS = {
    "子": (("癸", 1.0),),
    "丑": (("己", 0.6), ("癸", 0.3), ("辛", 0.1)),
    "寅": (("甲", 0.6), ("丙", 0.3), ("戊", 0.1)),
    "卯": (("乙", 1.0),),
    "辰": (("戊", 0.6), ("乙", 0.3), ("癸", 0.1)),
    "巳": (("丙", 0.6), ("戊", 0.3), ("庚", 0.1)),
    "午": (("丁", 0.7), ("己", 0.3)),
    "未": (("己", 0.6), ("丁", 0.3), ("乙", 0.1)),
    "申": (("庚", 0.6), ("壬", 0.3), ("戊", 0.1)),
    "酉": (("辛", 1.0),),
    "戌": (("戊", 0.6), ("辛", 0.3), ("丁", 0.1)),
    "亥": (("壬", 0.7), ("甲", 0.3)),
}

GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
WUXING_ORDER = ("金", "木", "水", "火", "土")


@dataclass(frozen=True)
class BirthInfo:
    solar: str
    lunar: str
    gender: str
    shengxiao: str
    sect: int
    yun_sect: int


@dataclass(frozen=True)
class Pillar:
    name: str
    ganzhi: str
    gan: str
    zhi: str
    gan_wuxing: str
    zhi_wuxing: str
    nayin: str
    xunkong: str
    hidden_stems: list[str]
    shishen_gan: str
    shishen_zhi: list[str]


@dataclass(frozen=True)
class DayunItem:
    index: int
    ganzhi: str
    start_year: int
    end_year: int
    start_age: int
    end_age: int
    xunkong: str


@dataclass(frozen=True)
class LiunianItem:
    year: int
    ganzhi: str
    age: int
    dayun_ganzhi: str
    dayun_start_year: int | None
    dayun_end_year: int | None
    xunkong: str


@dataclass(frozen=True)
class WuxingAnalysis:
    counts: dict[str, float]
    visible_counts: dict[str, int]
    strongest: str
    weakest: str
    day_master: str
    day_master_wuxing: str
    strength: str
    strength_score: float
    useful_hint: str
    notes: list[str]


@dataclass(frozen=True)
class BaziChart:
    birth: BirthInfo
    pillars: list[Pillar]
    wuxing: WuxingAnalysis
    dayun: list[DayunItem]
    liunian: list[LiunianItem]
    ming_gong: str
    ming_gong_nayin: str
    shen_gong: str
    shen_gong_nayin: str
    start_yun: dict[str, Any]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_birth(birth_time: str) -> tuple[int, int, int, int, int]:
    parts = birth_time.strip().replace("-", " ").replace("/", " ").replace(":", " ").split()
    if len(parts) < 3:
        raise ValueError("请提供完整的出生时间，格式: YYYY-MM-DD HH:MM")
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    hour = int(parts[3]) if len(parts) > 3 else 0
    minute = int(parts[4]) if len(parts) > 4 else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("出生时辰必须在 00:00-23:59 之间")
    return year, month, day, hour, minute


def parse_gender(gender: str) -> int:
    g = (gender or "").strip().lower()
    if g in ("男", "male", "m", "1", "公"):
        return 1
    if g in ("女", "female", "f", "0", "母"):
        return 0
    raise ValueError("gender 必须是 男 或 女")


def _gender_label(gender_int: int) -> str:
    return "男" if gender_int == 1 else "女"


def _producer_of(element: str) -> str:
    for src, dst in GENERATES.items():
        if dst == element:
            return src
    return ""


def _controller_of(element: str) -> str:
    for src, dst in CONTROLS.items():
        if dst == element:
            return src
    return ""


def _round_counts(counts: dict[str, float]) -> dict[str, float]:
    return {k: round(v, 2) for k, v in counts.items()}


def _build_wuxing_analysis(ec) -> WuxingAnalysis:
    pillars = [ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime()]
    visible_counts = {k: 0 for k in WUXING_ORDER}
    weighted = {k: 0.0 for k in WUXING_ORDER}

    for index, pillar in enumerate(pillars):
        gan, zhi = pillar[0], pillar[1]
        gan_wx = GAN_WUXING.get(gan)
        zhi_wx = ZHI_WUXING.get(zhi)
        stem_weight = 1.2 if index == 1 else 1.0
        branch_weight = 1.6 if index == 1 else 1.0
        if gan_wx:
            visible_counts[gan_wx] += 1
            weighted[gan_wx] += stem_weight
        if zhi_wx:
            visible_counts[zhi_wx] += 1
            weighted[zhi_wx] += branch_weight
        for hidden, ratio in HIDDEN_STEMS.get(zhi, ()):
            wx = GAN_WUXING.get(hidden)
            if wx:
                weighted[wx] += ratio * branch_weight

    day_master = ec.getDayGan()
    day_wx = GAN_WUXING.get(day_master, "未知")
    same = day_wx
    resource = _producer_of(day_wx)
    output = GENERATES.get(day_wx, "")
    wealth = CONTROLS.get(day_wx, "")
    officer = _controller_of(day_wx)

    support = weighted.get(same, 0.0) + weighted.get(resource, 0.0) * 0.85
    pressure = (
        weighted.get(output, 0.0) * 0.55
        + weighted.get(wealth, 0.0) * 0.7
        + weighted.get(officer, 0.0) * 0.8
    )
    strength_score = round(support - pressure, 2)
    if strength_score >= 2.2:
        strength = "偏强"
        useful_hint = f"宜取泄耗制衡之气，优先关注{output or '食伤'}、{wealth or '财星'}、{officer or '官杀'}的配合。"
    elif strength_score <= -1.2:
        strength = "偏弱"
        useful_hint = f"宜先扶助日主，重点看{resource or '印星'}与{same or '比劫'}是否得地。"
    else:
        strength = "中和"
        useful_hint = "格局接近平衡，喜忌需要结合大运流年触发点细看。"

    strongest = max(weighted, key=weighted.get)
    weakest = min(weighted, key=weighted.get)
    notes = [
        "五行权重已纳入天干、地支、藏干，并对月令加权；比单纯统计八个字更稳。",
        "强弱为工程化初判，最终用神仍需结合格局、调候、合冲刑害与大运流年校验。",
    ]
    return WuxingAnalysis(
        counts=_round_counts(weighted),
        visible_counts=visible_counts,
        strongest=strongest,
        weakest=weakest,
        day_master=day_master,
        day_master_wuxing=day_wx,
        strength=strength,
        strength_score=strength_score,
        useful_hint=useful_hint,
        notes=notes,
    )


def _pillar(name: str, ganzhi: str, nayin: str, xunkong: str, hidden: str, shishen_gan: str, shishen_zhi: Any) -> Pillar:
    gan = ganzhi[0] if ganzhi else ""
    zhi = ganzhi[1] if len(ganzhi) > 1 else ""
    if isinstance(shishen_zhi, str):
        zhi_shishen = [s for s in shishen_zhi.replace("[", "").replace("]", "").replace("'", "").split(",") if s.strip()]
    else:
        zhi_shishen = list(shishen_zhi or [])
    return Pillar(
        name=name,
        ganzhi=ganzhi,
        gan=gan,
        zhi=zhi,
        gan_wuxing=GAN_WUXING.get(gan, ""),
        zhi_wuxing=ZHI_WUXING.get(zhi, ""),
        nayin=nayin,
        xunkong=xunkong,
        hidden_stems=[s.strip() for s in str(hidden).replace("[", "").replace("]", "").replace("'", "").split(",") if s.strip()],
        shishen_gan=shishen_gan,
        shishen_zhi=[s.strip() for s in zhi_shishen],
    )


def _build_dayun(yun, count: int) -> list[DayunItem]:
    items: list[DayunItem] = []
    for d_yun in yun.getDaYun(count):
        gz = d_yun.getGanZhi()
        if not gz:
            continue
        items.append(DayunItem(
            index=d_yun.getIndex(),
            ganzhi=gz,
            start_year=d_yun.getStartYear(),
            end_year=d_yun.getEndYear(),
            start_age=d_yun.getStartAge(),
            end_age=d_yun.getEndAge(),
            xunkong=d_yun.getXunKong(),
        ))
    return items


def _find_dayun_for_year(dayun: list[DayunItem], year: int) -> DayunItem | None:
    for item in dayun:
        if item.start_year <= year <= item.end_year:
            return item
    return None


def _build_liunian(yun, dayun: list[DayunItem], start_year: int, years: int) -> list[LiunianItem]:
    lookup: dict[int, Any] = {}
    for d_yun in yun.getDaYun(14):
        for liu_nian in d_yun.getLiuNian(10):
            lookup[liu_nian.getYear()] = liu_nian

    result: list[LiunianItem] = []
    for offset in range(years):
        year = start_year + offset
        liu_nian = lookup.get(year)
        active_dayun = _find_dayun_for_year(dayun, year)
        if liu_nian is not None:
            ganzhi = liu_nian.getGanZhi()
            age = liu_nian.getAge()
            xunkong = liu_nian.getXunKong()
        else:
            lunar = Solar.fromYmdHms(year, 2, 4, 12, 0, 0).getLunar()
            ganzhi = lunar.getYearInGanZhiByLiChun()
            birth_year = yun.getLunar().getSolar().getYear()
            age = year - birth_year + 1
            xunkong = lunar.getYearXunKongByLiChun()
        result.append(LiunianItem(
            year=year,
            ganzhi=ganzhi,
            age=age,
            dayun_ganzhi=active_dayun.ganzhi if active_dayun else "",
            dayun_start_year=active_dayun.start_year if active_dayun else None,
            dayun_end_year=active_dayun.end_year if active_dayun else None,
            xunkong=xunkong,
        ))
    return result


def build_bazi_chart(
    birth_time: str,
    gender: str,
    sect: int = 2,
    yun_sect: int = 1,
    dayun_count: int = 8,
    liunian_years: int = 5,
    liunian_start_year: int | None = None,
) -> BaziChart:
    y, m, d, h, mi = parse_birth(birth_time)
    gender_int = parse_gender(gender)
    solar = Solar.fromYmdHms(y, m, d, h, mi, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    if sect != 2:
        ec.setSect(sect)
    yun = ec.getYun(gender_int, yun_sect)
    start_solar = yun.getStartSolar()

    pillars = [
        _pillar("年柱", ec.getYear(), ec.getYearNaYin(), ec.getYearXunKong(), ec.getYearHideGan(), ec.getYearShiShenGan(), ec.getYearShiShenZhi()),
        _pillar("月柱", ec.getMonth(), ec.getMonthNaYin(), ec.getMonthXunKong(), ec.getMonthHideGan(), ec.getMonthShiShenGan(), ec.getMonthShiShenZhi()),
        _pillar("日柱", ec.getDay(), ec.getDayNaYin(), ec.getDayXunKong(), ec.getDayHideGan(), "日主", ec.getDayShiShenZhi()),
        _pillar("时柱", ec.getTime(), ec.getTimeNaYin(), ec.getTimeXunKong(), ec.getTimeHideGan(), ec.getTimeShiShenGan(), ec.getTimeShiShenZhi()),
    ]
    dayun = _build_dayun(yun, dayun_count)
    start_year = liunian_start_year or _dt.date.today().year
    liunian = _build_liunian(yun, dayun, start_year, liunian_years)

    warnings = [
        "流年干支采用立春口径；具体到立春前后的事件判断，应结合准确日期时刻。",
    ]
    if h == 23 or h == 0:
        warnings.append("出生时间接近子时，日柱可能受 sect 流派影响，建议保留早晚子时口径。")

    return BaziChart(
        birth=BirthInfo(
            solar=f"{y:04d}-{m:02d}-{d:02d} {h:02d}:{mi:02d}",
            lunar=lunar.toString(),
            gender=_gender_label(gender_int),
            shengxiao=lunar.getYearShengXiao(),
            sect=sect,
            yun_sect=yun_sect,
        ),
        pillars=pillars,
        wuxing=_build_wuxing_analysis(ec),
        dayun=dayun,
        liunian=liunian,
        ming_gong=ec.getMingGong(),
        ming_gong_nayin=ec.getMingGongNaYin(),
        shen_gong=ec.getShenGong(),
        shen_gong_nayin=ec.getShenGongNaYin(),
        start_yun={
            "startYear": yun.getStartYear(),
            "startSolarYear": start_solar.getYear(),
            "startMonth": yun.getStartMonth(),
            "startDay": yun.getStartDay(),
            "startHour": yun.getStartHour(),
            "startDate": f"{start_solar.getYear():04d}-{start_solar.getMonth():02d}-{start_solar.getDay():02d}",
            "forward": yun.isForward(),
            "direction": "顺排" if yun.isForward() else "逆排",
        },
        warnings=warnings,
    )


def chart_to_api_dict(chart: BaziChart) -> dict[str, Any]:
    colors = {"金": "#d4af37", "木": "#4a7c3a", "水": "#3a6ea5", "火": "#c0392b", "土": "#8b6f47"}
    return {
        "birth": asdict(chart.birth),
        "pillars": [
            {
                "name": p.name,
                "ganzhi": p.ganzhi,
                "nayin": p.nayin,
                "gan": p.gan,
                "zhi": p.zhi,
                "ganWuxing": p.gan_wuxing,
                "zhiWuxing": p.zhi_wuxing,
                "xunkong": p.xunkong,
                "hiddenStems": p.hidden_stems,
                "shishenGan": p.shishen_gan,
                "shishenZhi": p.shishen_zhi,
            }
            for p in chart.pillars
        ],
        "wuxing": [
            {"name": name, "count": chart.wuxing.counts.get(name, 0), "color": colors[name]}
            for name in WUXING_ORDER
        ],
        "analysis": asdict(chart.wuxing),
        "dayun": [
            {
                "year": item.ganzhi,
                "ganzhi": item.ganzhi,
                "startYear": item.start_year,
                "endYear": item.end_year,
                "startAge": item.start_age,
                "endAge": item.end_age,
                "xunkong": item.xunkong,
            }
            for item in chart.dayun
        ],
        "liunian": [
            {
                "year": str(item.year),
                "ganzhi": item.ganzhi,
                "age": item.age,
                "dayun": item.dayun_ganzhi,
                "dayunStartYear": item.dayun_start_year,
                "dayunEndYear": item.dayun_end_year,
                "xunkong": item.xunkong,
            }
            for item in chart.liunian
        ],
        "shensha": [
            {"name": "命宫", "description": f"{chart.ming_gong}（{chart.ming_gong_nayin}）"},
            {"name": "身宫", "description": f"{chart.shen_gong}（{chart.shen_gong_nayin}）"},
        ],
        "startYun": chart.start_yun,
        "warnings": chart.warnings,
    }


def format_chart_text(chart: BaziChart) -> str:
    lines = [
        "【基本信息】",
        f"出生(公历): {chart.birth.solar}",
        f"出生(农历): {chart.birth.lunar}",
        f"生肖: {chart.birth.shengxiao}",
        f"性别: {chart.birth.gender}",
        "",
        "【四柱】",
    ]
    for p in chart.pillars:
        mark = "  ← 日主" if p.name == "日柱" else ""
        lines.append(f"  {p.name}: {p.ganzhi} ({p.nayin}){mark}")
    lines += [
        "",
        "【空亡】",
    ]
    for p in chart.pillars:
        lines.append(f"  {p.name[0]}空: {p.xunkong}")
    lines += [
        "",
        "【命宫/身宫】",
        f"  命宫: {chart.ming_gong} ({chart.ming_gong_nayin})",
        f"  身宫: {chart.shen_gong} ({chart.shen_gong_nayin})",
    ]
    if chart.warnings:
        lines += ["", "【校验提示】"] + [f"  - {w}" for w in chart.warnings]
    return "\n".join(lines)


def format_analysis_text(chart: BaziChart, question: str = "整体运势") -> str:
    wx = chart.wuxing
    lines = [
        f"【四柱】 {' '.join(p.ganzhi for p in chart.pillars)}",
        f"【日主】 {wx.day_master}({wx.day_master_wuxing})",
        f"【五行权重】 {wx.counts}",
        f"【显性五行】 {wx.visible_counts}",
        f"【最旺/最弱】 {wx.strongest}({wx.counts[wx.strongest]}) / {wx.weakest}({wx.counts[wx.weakest]})",
        f"【日主强弱】 {wx.strength} (score={wx.strength_score})",
        f"【用神提示】 {wx.useful_hint}",
        "",
        "【十神（天干对日主）】",
    ]
    for p in chart.pillars:
        lines.append(f"  {p.name}{p.gan}: {p.shishen_gan}")
    lines += ["", "【藏干】"]
    for p in chart.pillars:
        lines.append(f"  {p.name}{p.zhi}: {', '.join(p.hidden_stems) or '-'}")
    lines += ["", f"【分析方向】 {question}", "【口径说明】"]
    lines += [f"  - {note}" for note in wx.notes]
    return "\n".join(lines)


def format_dayun_text(chart: BaziChart) -> str:
    lines = [
        "【起运信息】",
        f"起运年龄: {chart.start_yun['startYear']}年 {chart.start_yun['startMonth']}月 {chart.start_yun['startDay']}日 {chart.start_yun['startHour']}时",
        f"起运日期: {chart.start_yun['startDate']}",
        f"起运公历年: {chart.start_yun['startSolarYear']} 年",
        f"大运方向: {chart.start_yun['direction']}",
        "",
        f"【大运列表】(共 {len(chart.dayun)} 柱)",
    ]
    for item in chart.dayun:
        lines.append(f"  {item.ganzhi} | {item.start_year}-{item.end_year} | {item.start_age}-{item.end_age}岁")
    lines += ["", "注: 大运由 lunar-python 起运算法生成，顺逆与起运时间已结构化保存。"]
    return "\n".join(lines)


def format_liunian_text(chart: BaziChart) -> str:
    if chart.liunian:
        start_year = chart.liunian[0].year
    else:
        start_year = _dt.date.today().year
    lines = [f"【流年推算】从 {start_year} 年起往后 {len(chart.liunian)} 年", ""]
    for item in chart.liunian:
        dy = f" | 所在大运: {item.dayun_ganzhi}" if item.dayun_ganzhi else ""
        lines.append(f"  {item.year}年: {item.ganzhi} | {item.age}虚岁{dy}")
    lines += ["", "注: 流年干支采用立春口径，并逐年绑定所在大运。"]
    return "\n".join(lines)


def format_fact_context(chart: BaziChart) -> str:
    return "\n\n".join([
        format_chart_text(chart),
        format_analysis_text(chart),
        format_dayun_text(chart),
        format_liunian_text(chart),
    ])
