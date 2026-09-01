"""命盘文本格式化与出生日期反推。"""
from __future__ import annotations

import datetime
import re
from typing import Any

from lunar_python import Lunar, Solar

from app.domain.chart_builder import parse_gender
from app.domain.models import BaziChart
from app.domain.shensha_calc import _compute_shensha


def _shensha_by_pillar(chart: BaziChart) -> dict[str, list[str]]:
    """按柱分组神煞名称，供文本格式化复用。"""
    ss = _compute_shensha(chart.pillars, parse_gender(chart.birth.gender))
    grouped: dict[str, list[str]] = {}
    for s in ss:
        grouped.setdefault(s.get("pillar") or "全局", []).append(s["name"])
    return grouped


def format_chart_text(chart: BaziChart) -> str:
    """格式化四柱排盘文本（基本信息/四柱/空亡/命宫身宫/神煞/校验提示）。"""
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
        lines.append(
            f"    藏干: {', '.join(p.hidden_stems) or '-'} | "
            f"副星: {', '.join(p.shishen_zhi) or '-'} | "
            f"星运: {p.changsheng or '-'} | 自坐: {p.zizuo or '-'} | 旬空: {p.xunkong or '-'}"
        )
    lines += ["", "【旬空口诀】"]
    for p in chart.pillars:
        lines.append(f"  {p.name[0]}柱旬空: {p.xunkong}")
    lines.append("  注: 旬空口诀为本柱干支所在旬的空亡字，不等于本柱落空；哪柱当真落空以【神煞（按柱）】的空亡标记为准")
    lines += [
        "",
        "【命宫/身宫】",
        f"  命宫: {chart.ming_gong} ({chart.ming_gong_nayin})",
        f"  身宫: {chart.shen_gong} ({chart.shen_gong_nayin})",
    ]
    shensha_by_pillar = _shensha_by_pillar(chart)
    if shensha_by_pillar:
        lines += ["", "【神煞（按柱）】"]
        for p in chart.pillars:
            names = shensha_by_pillar.get(p.name, [])
            lines.append(f"  {p.name}: {'、'.join(names) if names else '—'}")
    if chart.warnings:
        lines += ["", "【校验提示】"] + [f"  - {w}" for w in chart.warnings]
    return "\n".join(lines)


def format_analysis_text(chart: BaziChart, question: str = "整体运势") -> str:
    """格式化五行十神分析文本（四柱/日主强弱/用神/十神/藏干/结构判断）。"""
    wx = chart.wuxing
    lines = [
        f"【四柱】 {' '.join(p.ganzhi for p in chart.pillars)}",
        f"【日主】 {wx.day_master}({wx.day_master_wuxing})",
        f"【五行权重】 {wx.counts}",
        f"【显性五行】 {wx.visible_counts}",
        f"【最旺/最弱】 {wx.strongest}({wx.counts[wx.strongest]}) / {wx.weakest}({wx.counts[wx.weakest]})",
        f"【日主强弱】 {wx.strength} (score={wx.strength_score})",
        f"【特殊格局】 {wx.special_pattern or '无（普通正格/未达极端候选）'}",
        f"【用神提示】 {wx.useful_hint}",
        "",
        "【十神（天干对日主）】",
    ]
    for p in chart.pillars:
        lines.append(f"  {p.name}{p.gan}: {p.shishen_gan}")
    lines += ["", "【藏干】"]
    for p in chart.pillars:
        lines.append(f"  {p.name}{p.zhi}: {', '.join(p.hidden_stems) or '-'}")
    lines += [
        "",
        "【结构判断】",
        f"  十神分布: {chart.analysis.ten_gods}",
        f"  透干: {', '.join(chart.analysis.exposed_stems) or '-'}",
        f"  通根: {', '.join(chart.analysis.rooted_stems) or '-'}",
        f"  合: {', '.join(chart.analysis.combinations) or '-'}",
        f"  冲: {', '.join(chart.analysis.clashes) or '-'}",
        f"  害: {', '.join(chart.analysis.harms) or '-'}",
        f"  刑: {', '.join(chart.analysis.punishments) or '-'}",
        f"  调候: {chart.analysis.adjustment}",
        f"  判断置信度: {chart.analysis.confidence}",
        "",
        f"【分析方向】 {question}",
        "【口径说明】",
    ]
    lines += [f"  - {note}" for note in wx.notes]
    shensha_by_pillar = _shensha_by_pillar(chart)
    lines += ["", "【神煞（按柱）】"]
    for p in chart.pillars:
        names = shensha_by_pillar.get(p.name, [])
        lines.append(f"  {p.name}: {'、'.join(names) if names else '—'}")
    return "\n".join(lines)


def _yun_extra_text(item) -> str:
    """藏干/副星/星运/神煞 明细段（大运、流年共用）。"""
    return (
        f"藏干[{'、'.join(item.hidden_stems) or '—'}] "
        f"副星[{'、'.join(item.shishen_zhi) or '—'}] "
        f"星运[{item.changsheng or '—'}] "
        f"神煞[{'、'.join(s['name'] for s in item.shensha) or '—'}]"
    )


def format_dayun_text(chart: BaziChart) -> str:
    """格式化大运文本（起运信息 + 每柱大运的干支/年份区间/年龄）。"""
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
        lines.append(
            f"  {item.ganzhi}({item.shishen_gan}) | {item.start_year}-{item.end_year} | {item.start_age}-{item.end_age}岁 "
            f"{_yun_extra_text(item)}"
        )
    lines += ["", "注: 大运由 lunar-python 起运算法生成，顺逆与起运时间已结构化保存。"]
    return "\n".join(lines)


def format_liunian_text(chart: BaziChart) -> str:
    """格式化流年文本（逐年干支/虚岁，并绑定所在大运）。"""
    start_year = chart.liunian[0].year if chart.liunian else datetime.date.today().year
    lines = [f"【流年推算】从 {start_year} 年起往后 {len(chart.liunian)} 年", ""]
    for item in chart.liunian:
        dy = f" | 所在大运: {item.dayun_ganzhi}" if item.dayun_ganzhi else ""
        lines.append(
            f"  {item.year}年: {item.ganzhi}({item.shishen_gan}) | {item.age}虚岁{dy} "
            f"{_yun_extra_text(item)}"
        )
    lines += ["", "注: 流年干支采用立春口径，并逐年绑定所在大运。"]
    return "\n".join(lines)


_GAN_SEQ = "甲乙丙丁戊己庚辛壬癸"
_ZHI_SEQ2 = "子丑寅卯辰巳午未申酉戌亥"
_ZHI_MID_HOUR = {
    "子": 0, "丑": 2, "寅": 4, "卯": 6, "辰": 8, "巳": 10,
    "午": 12, "未": 14, "申": 16, "酉": 18, "戌": 20, "亥": 22,
}


def _parse_pillars(pillars: str) -> tuple[str, str, str, str]:
    """把 '甲申庚午壬申甲辰' / '甲申 庚午 壬申 甲辰' / '甲申年庚午月...' 统一拆成四柱。"""
    s = (pillars or "").strip()
    s = re.sub(r"[\s/、，,年日月时\-]", "", s)
    chars = [c for c in s if c in _GAN_SEQ or c in _ZHI_SEQ2]
    seq = "".join(chars)
    if len(seq) < 8:
        raise ValueError("八字应为 4 个干支共 8 字，如 甲申庚午壬申甲辰")
    seq = seq[:8]
    out = []
    for i in range(4):
        gz = seq[i * 2: i * 2 + 2]
        if gz[0] not in _GAN_SEQ or gz[1] not in _ZHI_SEQ2:
            raise ValueError(f"非法干支: {gz}")
        out.append(gz)
    return tuple(out)


def _jdn(y: int, m: int, d: int) -> int:
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def _day_gz_from_jdn(j: int) -> str:
    """日柱快速公式（与 lunar 标定一致）。"""
    return _GAN_SEQ[(j + _DAY_OFF_G) % 10] + _ZHI_SEQ2[(j + _DAY_OFF_Z) % 12]


_REF = _jdn(2000, 1, 1)
_REF_EC = Lunar.fromSolar(Solar.fromYmd(2000, 1, 1)).getEightChar().getDay()
_DAY_OFF_G = (_GAN_SEQ.index(_REF_EC[0]) - _REF) % 10
_DAY_OFF_Z = (_ZHI_SEQ2.index(_REF_EC[1]) - _REF) % 12


def find_birth_dates_from_pillars(
    pillars: str,
    gender: str = "男",
    max_years_back: int = 120,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """根据四柱反推候选出生日期（日柱 60 天周期 + 年/月/时柱逐层过滤）。

    返回 [{"birth_time", "ganzhi", "shi_chen"}, ...] 按日期倒序，最多 top_n 个。
    """
    y_gz, m_gz, d_gz, t_gz = _parse_pillars(pillars)
    today = datetime.date.today()
    today_jdn = _jdn(*today.timetuple()[:3])
    min_jdn = _jdn(today.year - max_years_back, 1, 1)

    t_zhi = t_gz[1]
    results: list[dict[str, Any]] = []
    seen_dates: set[str] = set()

    j = today_jdn
    while j >= min_jdn:
        if _day_gz_from_jdn(j) == d_gz:
            y, mo, d = _date_from_jdn(j)
            key = f"{y}-{mo:02d}-{d:02d}"
            if key not in seen_dates:
                hour = _ZHI_MID_HOUR[t_zhi]
                solar = Solar.fromYmdHms(y, mo, d, hour, 0, 0)
                ec = solar.getLunar().getEightChar()
                if ec.getYear() == y_gz and ec.getMonth() == m_gz and ec.getTime() == t_gz:
                    seen_dates.add(key)
                    results.append({
                        "birth_time": f"{y}-{mo:02d}-{d:02d} {hour:02d}:00",
                        "ganzhi": f"{ec.getYear()} {ec.getMonth()} {ec.getDay()} {t_gz}",
                        "shi_chen": f"{t_zhi}时",
                    })
        j -= 1

    results.sort(key=lambda r: r["birth_time"], reverse=True)
    return results[:top_n]


def _date_from_jdn(j: int) -> tuple[int, int, int]:
    a = j + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


def format_fact_context(chart: BaziChart) -> str:
    """汇总格式化命盘事实（排盘+分析+大运+流年），用于事实校验锚点。"""
    return "\n\n".join([
        format_chart_text(chart),
        format_analysis_text(chart),
        format_dayun_text(chart),
        format_liunian_text(chart),
    ])


def extract_bazi_brief(chart_data: Any) -> str | None:
    """从命盘 JSON（chart_data）中提取四柱干支摘要，如 '辛卯 丁酉 庚午 丙子'。"""
    try:
        pillars = chart_data.get("pillars")
        if isinstance(pillars, list) and len(pillars) >= 4:
            parts = []
            for p in pillars:
                gz = p.get("ganzhi") if isinstance(p, dict) else None
                if isinstance(gz, list) and len(gz) >= 2:
                    parts.append(f"{gz[0]}{gz[1]}")
                elif isinstance(gz, str):
                    parts.append(gz)
            if len(parts) >= 4:
                return " ".join(parts[:4])
    except Exception:
        pass
    return None
