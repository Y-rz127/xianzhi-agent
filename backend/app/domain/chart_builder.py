"""排盘构建：出生时间解析、四柱/大运/流年构建、命盘组装与 API 序列化。"""

from __future__ import annotations

import datetime
import re
from dataclasses import asdict
from typing import Any

from lunar_python import Solar

from app.domain.analysis_calc import (
    _build_domain_analysis,
    _build_wuxing_analysis,
)
from app.domain.models import (
    BaziChart,
    BirthInfo,
    DayunItem,
    LiunianItem,
    Pillar,
)
from app.domain.shensha_calc import _compute_shensha
from app.domain.tables import (
    _YANG_GAN,
    _ZHI_SEQ,
    GAN_WUXING,
    HIDDEN_STEMS,
    WUXING_ORDER,
    ZHI_WUXING,
)
from app.domain.xipan import build_xipan, ten_god, zizuo


def parse_birth(birth_time: str) -> tuple[int, int, int, int, int]:
    """将多种格式的出生时间字符串解析为 (年, 月, 日, 时, 分)。"""
    s = birth_time.strip()
    s = s.replace("：", ":").replace("．", ".").replace("。", ".")
    s = s.replace("年", "-").replace("月", "-").replace("日", " ").replace("号", " ")
    s = s.replace("时", ":").replace("点", ":").replace("分", "").replace("T", " ")
    s = s.replace("/", "-").replace(".", "-")
    s = re.sub(r"\s+", " ", s).strip()
    parts = s.replace(":", " ").replace("-", " ").split()
    if len(parts) < 3:
        raise ValueError("请提供完整的出生时间，格式: YYYY-MM-DD HH:MM")
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    hour = int(parts[3]) if len(parts) > 3 else 0
    minute = int(parts[4]) if len(parts) > 4 else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("出生时辰必须在 00:00-23:59 之间")
    return year, month, day, hour, minute


def parse_gender(gender: str) -> int:
    """解析性别为内部编码：男=1，女=0；支持 男/女/male/female/m/f/1/0/公/母。"""
    g = (gender or "").strip().lower()
    if g in ("男", "male", "m", "1", "公"):
        return 1
    if g in ("女", "female", "f", "0", "母"):
        return 0
    raise ValueError("gender 必须是 男 或 女")


def _gender_label(gender_int: int) -> str:
    return "男" if gender_int == 1 else "女"


def _tai_yuan(month_pillar: str) -> tuple[str, str]:
    """按月柱推胎元：月干进一位、月支进三位。"""
    gan_seq = "甲乙丙丁戊己庚辛壬癸"
    nayin_names = [
        "海中金",
        "炉中火",
        "大林木",
        "路旁土",
        "剑锋金",
        "山头火",
        "涧下水",
        "城头土",
        "白蜡金",
        "杨柳木",
        "泉中水",
        "屋上土",
        "霹雳火",
        "松柏木",
        "长流水",
        "沙中金",
        "山下火",
        "平地木",
        "壁上土",
        "金箔金",
        "覆灯火",
        "天河水",
        "大驿土",
        "钗钏金",
        "桑柘木",
        "大溪水",
        "沙中土",
        "天上火",
        "石榴木",
        "大海水",
    ]
    if len(month_pillar) < 2 or month_pillar[0] not in gan_seq or month_pillar[1] not in _ZHI_SEQ:
        return "", ""
    gan = gan_seq[(gan_seq.index(month_pillar[0]) + 1) % 10]
    zhi = _ZHI_SEQ[(_ZHI_SEQ.index(month_pillar[1]) + 3) % 12]
    ganzhi = gan + zhi
    sexagenary = [gan_seq[i % 10] + _ZHI_SEQ[i % 12] for i in range(60)]
    index = sexagenary.index(ganzhi)
    return ganzhi, nayin_names[index // 2]


def _ganzhi_detail(
    ganzhi: str, day_master_gan: str, pillars: list[Pillar], gender_int: int
) -> dict[str, Any]:
    """为大运/流年干支计算详细字段：主星、藏干、副星、星运、神煞。"""
    if not ganzhi or len(ganzhi) < 2:
        return {}
    gan = ganzhi[0]
    zhi = ganzhi[1]
    shishen_gan = ten_god(day_master_gan, gan)
    hidden = [s for s, _ in HIDDEN_STEMS.get(zhi, ())]
    shishen_zhi = [ten_god(day_master_gan, s) for s in hidden]
    changsheng = zizuo(day_master_gan, zhi)
    # 临时 Pillar 并入四柱计算神煞，再筛出该柱神煞
    temp_name = "运柱"
    temp_pillar = Pillar(
        name=temp_name,
        ganzhi=ganzhi,
        gan=gan,
        zhi=zhi,
        gan_wuxing=GAN_WUXING.get(gan, ""),
        zhi_wuxing=ZHI_WUXING.get(zhi, ""),
        nayin="",
        xunkong="",
        hidden_stems=hidden,
        shishen_gan=shishen_gan,
        shishen_zhi=shishen_zhi,
        changsheng=changsheng,
        zizuo="",
    )
    all_shensha = _compute_shensha(pillars + [temp_pillar], gender_int)
    shensha = [
        {"name": s["name"], "description": s["description"]}
        for s in all_shensha
        if s.get("pillar") == temp_name
    ]
    return {
        "shishen_gan": shishen_gan,
        "gan": gan,
        "zhi": zhi,
        "hidden_stems": hidden,
        "shishen_zhi": shishen_zhi,
        "changsheng": changsheng,
        "shensha": shensha,
    }


def _pillar(
    name: str,
    ganzhi: str,
    nayin: str,
    xunkong: str,
    hidden: str,
    shishen_gan: str,
    shishen_zhi: Any,
    changsheng: str = "",
    zizuo: str = "",
) -> Pillar:
    """由 lunar_python 排盘产物构造单柱 Pillar（解析天干/地支/五行/十神/藏干）。"""
    gan = ganzhi[0] if ganzhi else ""
    zhi = ganzhi[1] if len(ganzhi) > 1 else ""
    if isinstance(shishen_zhi, str):
        zhi_shishen = [
            s for s in shishen_zhi.replace("[", "").replace("]", "").replace("'", "").split(",") if s.strip()
        ]
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
        hidden_stems=[
            s.strip()
            for s in str(hidden).replace("[", "").replace("]", "").replace("'", "").split(",")
            if s.strip()
        ],
        shishen_gan=shishen_gan,
        shishen_zhi=[s.strip() for s in zhi_shishen],
        changsheng=changsheng,
        zizuo=zizuo,
    )


def _build_dayun(
    yun, count: int, day_master_gan: str = "", pillars: list[Pillar] | None = None, gender_int: int = 1
) -> list[DayunItem]:
    """构建大运序列（起止年/龄、旬空与按日主标注的十神/神煞等）。"""
    items: list[DayunItem] = []
    for d_yun in yun.getDaYun(count + 1):
        gz = d_yun.getGanZhi()
        if not gz:
            continue
        detail = _ganzhi_detail(gz, day_master_gan, pillars or [], gender_int) if day_master_gan else {}
        items.append(
            DayunItem(
                index=d_yun.getIndex(),
                ganzhi=gz,
                start_year=d_yun.getStartYear(),
                end_year=d_yun.getEndYear(),
                start_age=d_yun.getStartAge(),
                end_age=d_yun.getEndAge(),
                xunkong=d_yun.getXunKong(),
                shishen_gan=detail.get("shishen_gan", ""),
                gan=detail.get("gan", ""),
                zhi=detail.get("zhi", ""),
                hidden_stems=detail.get("hidden_stems", []),
                shishen_zhi=detail.get("shishen_zhi", []),
                changsheng=detail.get("changsheng", ""),
                shensha=detail.get("shensha", []),
            )
        )
        if len(items) >= count:
            break
    return items


def _find_dayun_for_year(dayun: list[DayunItem], year: int) -> DayunItem | None:
    for item in dayun:
        if item.start_year <= year <= item.end_year:
            return item
    return None


def _build_liunian(
    yun,
    dayun: list[DayunItem],
    start_year: int,
    years: int,
    day_master_gan: str = "",
    pillars: list[Pillar] | None = None,
    gender_int: int = 1,
) -> list[LiunianItem]:
    """构建流年序列，并关联每年所处大运与十神/神煞明细。

    优先用 lunar_python 的 LiuNian 查表；缺漏年份以「立春换岁」口径手工推算，
    再反查每年所属大运区间。
    """
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
        detail = _ganzhi_detail(ganzhi, day_master_gan, pillars or [], gender_int) if day_master_gan else {}
        result.append(
            LiunianItem(
                year=year,
                ganzhi=ganzhi,
                age=age,
                dayun_ganzhi=active_dayun.ganzhi if active_dayun else "",
                dayun_start_year=active_dayun.start_year if active_dayun else None,
                dayun_end_year=active_dayun.end_year if active_dayun else None,
                xunkong=xunkong,
                shishen_gan=detail.get("shishen_gan", ""),
                gan=detail.get("gan", ""),
                zhi=detail.get("zhi", ""),
                hidden_stems=detail.get("hidden_stems", []),
                shishen_zhi=detail.get("shishen_zhi", []),
                changsheng=detail.get("changsheng", ""),
                shensha=detail.get("shensha", []),
            )
        )
    return result


def build_bazi_chart(
    birth_time: str,
    gender: str,
    sect: int = 2,
    yun_sect: int = 1,
    dayun_count: int = 12,
    liunian_years: int = 5,
    liunian_start_year: int | None = None,
    longitude: float | None = None,
    liunian_cover_dayun: bool = False,
    today: datetime.date | None = None,
) -> BaziChart:
    """构建完整八字命盘（BaziChart）。

    sect: 日柱计算流派；yun_sect: 大运计算流派；
    longitude: 出生地经度，用于真太阳时校正（基准 120°E，每度差 4 分钟）；
    liunian_cover_dayun: 流年范围自动扩展到覆盖当前大运起止（前端流年神煞需整运十年）；
    today: 基准日（默认取系统当天），会透传给细盘用于定位"当前岁运"。
           不传时行为与历史一致；黄金命盘快照必须传固定值，否则快照随日期漂移。
    """
    y, m, d, h, mi = parse_birth(birth_time)
    gender_int = parse_gender(gender)

    # 真太阳时校正：按出生地经度修正时钟时间
    solar_correction_min = 0
    if longitude and 60 <= longitude <= 140:
        solar_correction_min = round((120 - longitude) * 4)
    if solar_correction_min != 0:
        corrected = datetime.datetime(y, m, d, h, mi) + datetime.timedelta(minutes=solar_correction_min)
        h, mi = corrected.hour, corrected.minute
        if corrected.date() != datetime.date(y, m, d):
            y, m, d = corrected.year, corrected.month, corrected.day

    solar = Solar.fromYmdHms(y, m, d, h, mi, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    if sect != 2:
        ec.setSect(sect)

    # 大运顺逆 = 年干阴阳与性别是否相同（阳年男/阴年女顺排，与《渊海子平》古法一致）
    year_gan = ec.getYearGan()
    year_is_yang = year_gan in _YANG_GAN
    yun = ec.getYun(gender_int, yun_sect)
    start_solar = yun.getStartSolar()
    dayun_direction = "顺排" if (year_is_yang == (gender_int == 1)) else "逆排"

    pillars = [
        _pillar(
            "年柱",
            ec.getYear(),
            ec.getYearNaYin(),
            ec.getYearXunKong(),
            ec.getYearHideGan(),
            ec.getYearShiShenGan(),
            ec.getYearShiShenZhi(),
            changsheng=ec.getYearDiShi(),
            zizuo=zizuo(ec.getYearGan(), ec.getYearZhi()),
        ),
        _pillar(
            "月柱",
            ec.getMonth(),
            ec.getMonthNaYin(),
            ec.getMonthXunKong(),
            ec.getMonthHideGan(),
            ec.getMonthShiShenGan(),
            ec.getMonthShiShenZhi(),
            changsheng=ec.getMonthDiShi(),
            zizuo=zizuo(ec.getMonthGan(), ec.getMonthZhi()),
        ),
        _pillar(
            "日柱",
            ec.getDay(),
            ec.getDayNaYin(),
            ec.getDayXunKong(),
            ec.getDayHideGan(),
            "日主",
            ec.getDayShiShenZhi(),
            changsheng=ec.getDayDiShi(),
            zizuo=zizuo(ec.getDayGan(), ec.getDayZhi()),
        ),
        _pillar(
            "时柱",
            ec.getTime(),
            ec.getTimeNaYin(),
            ec.getTimeXunKong(),
            ec.getTimeHideGan(),
            ec.getTimeShiShenGan(),
            ec.getTimeShiShenZhi(),
            changsheng=ec.getTimeDiShi(),
            zizuo=zizuo(ec.getTimeGan(), ec.getTimeZhi()),
        ),
    ]
    wuxing = _build_wuxing_analysis(ec)
    analysis = _build_domain_analysis(pillars, wuxing)
    day_master_gan = ec.getDayGan()
    tai_yuan, tai_yuan_nayin = _tai_yuan(ec.getMonth())
    dayun = _build_dayun(yun, dayun_count, day_master_gan, pillars, gender_int)
    start_year = liunian_start_year or datetime.date.today().year
    liunian_end = start_year + liunian_years - 1
    if liunian_cover_dayun:
        # 流年范围扩展到覆盖当前大运起止（含大运起始年可能早于今年的情形）
        cur_dyun = _find_dayun_for_year(dayun, start_year)
        if cur_dyun:
            start_year = min(start_year, cur_dyun.start_year)
            liunian_end = max(liunian_end, cur_dyun.end_year)
    liunian = _build_liunian(
        yun, dayun, start_year, liunian_end - start_year + 1, day_master_gan, pillars, gender_int
    )
    xipan = build_xipan(
        yun, pillars, gender_int, day_master_gan, dayun_direction, today=today, dayun_count=dayun_count
    )


    warnings = [
        "流年干支采用立春口径；具体到立春前后的事件判断，应结合准确日期时刻。",
    ]
    if solar_correction_min != 0:
        sign = "+" if solar_correction_min > 0 else ""
        warnings.append(f"已根据出生地经度（{longitude}°E）校正真太阳时：{sign}{solar_correction_min}分钟。")
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
        wuxing=wuxing,
        analysis=analysis,
        dayun=dayun,
        liunian=liunian,
        xipan=xipan,
        ming_gong=ec.getMingGong(),
        ming_gong_nayin=ec.getMingGongNaYin(),
        shen_gong=ec.getShenGong(),
        shen_gong_nayin=ec.getShenGongNaYin(),
        tai_yuan=tai_yuan,
        tai_yuan_nayin=tai_yuan_nayin,
        start_yun={
            "startYear": yun.getStartYear(),
            "startSolarYear": start_solar.getYear(),
            "startMonth": yun.getStartMonth(),
            "startDay": yun.getStartDay(),
            "startHour": yun.getStartHour(),
            "startDate": f"{start_solar.getYear():04d}-{start_solar.getMonth():02d}-{start_solar.getDay():02d}",
            "forward": year_is_yang == (gender_int == 1),
            "direction": dayun_direction,
        },
        warnings=warnings,
    )


def _yun_detail(item) -> dict[str, Any]:
    """大运/流年共用的干支细节段。"""
    return {
        "xunkong": item.xunkong,
        "shishenGan": item.shishen_gan,
        "gan": item.gan,
        "zhi": item.zhi,
        "hiddenStems": item.hidden_stems,
        "shishenZhi": item.shishen_zhi,
        "changsheng": item.changsheng,
        "shensha": item.shensha,
    }


def chart_to_api_dict(chart: BaziChart) -> dict[str, Any]:
    """将 BaziChart 转为前端友好的 dict（含五行配色、柱/五行/大运/流年结构）。"""
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
                "changsheng": p.changsheng,
                "zizuo": p.zizuo,
            }
            for p in chart.pillars
        ],
        "wuxing": [
            {"name": name, "count": chart.wuxing.counts.get(name, 0), "color": colors[name]}
            for name in WUXING_ORDER
        ],
        "analysis": {
            **asdict(chart.wuxing),
            "tenGods": chart.analysis.ten_gods,
            "exposedStems": chart.analysis.exposed_stems,
            "rootedStems": chart.analysis.rooted_stems,
            "combinations": chart.analysis.combinations,
            "clashes": chart.analysis.clashes,
            "harms": chart.analysis.harms,
            "breaks": chart.analysis.breaks,
            "punishments": chart.analysis.punishments,
            "threeAssemblies": chart.analysis.three_assemblies,
            "season": chart.analysis.season,
            "adjustment": chart.analysis.adjustment,
            "patternHint": chart.analysis.pattern_hint,
            "confidence": chart.analysis.confidence,
        },
        "dayun": [
            {
                "index": item.index,
                "year": item.ganzhi,
                "ganzhi": item.ganzhi,
                "startYear": item.start_year,
                "endYear": item.end_year,
                "startAge": item.start_age,
                "endAge": item.end_age,
                **_yun_detail(item),
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
                **_yun_detail(item),
            }
            for item in chart.liunian
        ],
        "shensha": _compute_shensha(chart.pillars, parse_gender(chart.birth.gender)),
        "mingGong": f"{chart.ming_gong}（{chart.ming_gong_nayin}）",
        "shenGong": f"{chart.shen_gong}（{chart.shen_gong_nayin}）",
        "taiYuan": f"{chart.tai_yuan}（{chart.tai_yuan_nayin}）",
        "startYun": chart.start_yun,
        "warnings": chart.warnings,
        "xipan": chart.xipan,
    }
