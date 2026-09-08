"""细盘：时间层级排盘（起运→大运→流年→流月）+ 当前叠加快照 + 月令旺衰/司令。

对齐专业排盘软件形态：
- 起运文案与交运节气（逢X年 立X后X天交运）
- 全量大运（干支/年龄/年份/十神/空亡/藏干）
- 全量流年（出生年起，带所属大运与小运）
- 全量流月（每年 12 节气月：节名+公历日期+干支+十神）
- 当前流年+当前大运叠加四柱的六列快照
- 月令五行旺相休囚死 + 人元司令分野（渊海子平口径）

纯查表与 lunar-python 排盘产物，无 IO 无 LLM，可直接单测。
"""

from __future__ import annotations

import datetime
from typing import Any

from lunar_python import Solar
from lunar_python.util import LunarUtil

from app.domain.models import Pillar
from app.domain.shensha_calc import _compute_shensha
from app.domain.tables import (
    _GAN_CHANGSHENG_ZHI,
    _YANG_GAN,
    _ZHI_SEQ,
    CONTROLS,
    GAN_HE,
    GAN_WUXING,
    GENERATES,
    GZ_WUXING,
    HIDDEN_STEMS,
    LIU_CHONG,
    LIU_HAI,
    LIU_HE,
    LIU_PO,
    SAN_HUI,
    SAN_XING,
    SELF_XING,
    WUXING_ORDER,
    ZHI_WUXING,
)

_GAN_SEQ = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
# 节气月支序：寅月起（立春）
_MONTH_ZHI = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]
_JIE_OF_MONTH = {
    "寅": "立春",
    "卯": "惊蛰",
    "辰": "清明",
    "巳": "立夏",
    "午": "芒种",
    "未": "小暑",
    "申": "立秋",
    "酉": "白露",
    "戌": "寒露",
    "亥": "立冬",
    "子": "大雪",
    "丑": "小寒",
}
_ZHI_OF_JIE = {v: k for k, v in _JIE_OF_MONTH.items()}
# 五虎遁：年干 → 寅月起运之干
_WUHU_START = {
    "甲": "丙",
    "己": "丙",
    "乙": "戊",
    "庚": "戊",
    "丙": "庚",
    "辛": "庚",
    "丁": "壬",
    "壬": "壬",
    "戊": "甲",
    "癸": "甲",
}

# 人元司令分野（渊海子平口径）：月支 → [(用事天干, 天数)]
_FENYE = {
    "寅": [("戊", 7), ("丙", 7), ("甲", 16)],
    "卯": [("甲", 10), ("乙", 20)],
    "辰": [("乙", 9), ("癸", 3), ("戊", 18)],
    "巳": [("戊", 7), ("庚", 7), ("丙", 16)],
    "午": [("丙", 10), ("己", 9), ("丁", 11)],
    "未": [("丁", 9), ("乙", 3), ("己", 18)],
    "申": [("戊", 7), ("壬", 7), ("庚", 16)],
    "酉": [("庚", 10), ("辛", 20)],
    "戌": [("辛", 9), ("丁", 3), ("戊", 18)],
    "亥": [("戊", 7), ("甲", 7), ("壬", 16)],
    "子": [("壬", 10), ("癸", 20)],
    "丑": [("癸", 9), ("辛", 3), ("己", 18)],
}


def ten_god(day_master: str, target_gan: str) -> str:
    """计算 target_gan 相对 day_master 的十神（主星）。"""
    if not day_master or not target_gan:
        return ""
    dm_wx = GAN_WUXING.get(day_master, "")
    tg_wx = GAN_WUXING.get(target_gan, "")
    if not dm_wx or not tg_wx:
        return ""
    same_polarity = (day_master in _YANG_GAN) == (target_gan in _YANG_GAN)
    if dm_wx == tg_wx:
        return "比肩" if same_polarity else "劫财"
    if GENERATES[dm_wx] == tg_wx:
        return "食神" if same_polarity else "伤官"
    if CONTROLS[dm_wx] == tg_wx:
        return "偏财" if same_polarity else "正财"
    if GENERATES[tg_wx] == dm_wx:
        return "偏印" if same_polarity else "正印"
    if CONTROLS[tg_wx] == dm_wx:
        return "七杀" if same_polarity else "正官"
    return ""


def zizuo(gan: str, zhi: str) -> str:
    """天干 gan 在地支 zhi 的十二长生状态（阳顺阴逆）。"""
    if not gan or not zhi:
        return ""
    base = _GAN_CHANGSHENG_ZHI.get(gan)
    if not base or base not in _ZHI_SEQ or zhi not in _ZHI_SEQ:
        return ""
    i_base = _ZHI_SEQ.index(base)
    i_zhi = _ZHI_SEQ.index(zhi)
    offset = (i_zhi - i_base) % 12 if gan in _YANG_GAN else (i_base - i_zhi) % 12
    return ("长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养")[offset]


_JIE_QI_CACHE: dict[int, dict[str, Any]] = {}
_JIE_QI_CACHE_MAX = 600  # 约六个世纪，够常驻进程用；超了就整表清空（条目很小，不值得做 LRU）


def _year_jie_qi(year: int) -> dict[str, Any]:
    """某公历年的二十四节气表，按年缓存。

    节气时刻只与年份有关、与命主无关，所以可安全进程级复用。锚点取年中：实测 1/20 与 6/1
    两个锚点取到的节气完全一致，故一年只需 getLunar() 一次——它是本模块的耗时大头
    （约 2.7ms/次），旧实现对每年要算两遍（本年 + 次年小寒）。
    """
    table = _JIE_QI_CACHE.get(year)
    if table is None:
        if len(_JIE_QI_CACHE) >= _JIE_QI_CACHE_MAX:
            _JIE_QI_CACHE.clear()
        table = Solar.fromYmdHms(year, 6, 1, 12, 0, 0).getLunar().getJieQiTable()
        _JIE_QI_CACHE[year] = table
    return table


def _jie_table(year: int) -> dict[str, Any]:
    """取某节气年（立春起）12 节的精确时刻；丑月小寒落在次年公历 1 月，取次年表。"""
    table = _year_jie_qi(year)
    result = {name: table[name] for name in _JIE_OF_MONTH.values() if name in table}
    result["小寒"] = _year_jie_qi(year + 1)["小寒"]
    return result


def _solar_date(s: Any) -> datetime.date:
    return datetime.date(s.getYear(), s.getMonth(), s.getDay())


def _month_ganzhi(year_gan: str, month_index: int) -> str:
    """五虎遁：年由年干定寅月干，顺推 month_index（寅=0）。"""
    gan = _GAN_SEQ[(_GAN_SEQ.index(_WUHU_START[year_gan]) + month_index) % 10]
    return gan + _MONTH_ZHI[month_index]


def _year_ganzhi(year: int) -> str:
    """流年干支（立春换岁口径，1984 甲子起算）。"""
    return _GAN_SEQ[(year - 4) % 10] + _ZHI_SEQ[(year - 4) % 12]


# 六十甲子按旬（每 10 位一旬）的旬空地支
_XUN_KONG = ("戌亥", "申酉", "午未", "辰巳", "寅卯", "子丑")


def _xunkong(ganzhi: str) -> str:
    """干支所属旬的空亡（甲子旬空戌亥 … 甲寅旬空子丑）。"""
    if len(ganzhi) != 2 or ganzhi[0] not in _GAN_SEQ or ganzhi[1] not in _ZHI_SEQ:
        return ""
    index = (6 * _GAN_SEQ.index(ganzhi[0]) - 5 * _ZHI_SEQ.index(ganzhi[1])) % 60
    return _XUN_KONG[index // 10]


def _qiyun(yun: Any, direction: str) -> dict[str, Any]:
    y, m, d, h = yun.getStartYear(), yun.getStartMonth(), yun.getStartDay(), yun.getStartHour()
    parts = [f"{y}年", f"{m}月"]
    if d or h:
        parts.append(f"{d}天")
    if h:
        parts.append(f"{h}时")
    start_solar = yun.getStartSolar()
    start_date = datetime.date(start_solar.getYear(), start_solar.getMonth(), start_solar.getDay())
    prev_jie = (
        Solar.fromYmdHms(
            start_solar.getYear(), start_solar.getMonth(), start_solar.getDay(), start_solar.getHour(), 0, 0
        )
        .getLunar()
        .getPrevJie()
    )
    return {
        "after": "出生后" + "".join(parts),
        "startDate": start_solar.toYmdHms()[:16],
        "gan": _GAN_SEQ[(start_solar.getYear() - 4) % 10],
        "jieqi": prev_jie.getName(),
        "daysAfterJieqi": (start_date - _solar_date(prev_jie.getSolar())).days,
        "direction": direction,
    }


def _build_dayun_list(yun: Any, day_master: str, count: int = 12) -> list[dict[str, Any]]:
    """大运列表，含 index=0 童限段（起运前，干支显示为「童限」）。

    count=12 即排满十二步，地支顺/逆排满一轮。
    """
    items: list[dict[str, Any]] = []
    for d in yun.getDaYun(count + 1):
        gz = d.getGanZhi()
        index = d.getIndex()
        if not gz and index != 0:
            continue
        zhi = gz[1] if gz else ""
        items.append(
            {
                "index": index,
                "ganzhi": gz or "童限",
                "shishen": ten_god(day_master, gz[0]) if gz else "",
                "startAge": d.getStartAge(),
                "endAge": d.getEndAge(),
                "startYear": d.getStartYear(),
                "endYear": d.getEndYear(),
                "xunkong": d.getXunKong(),
                "hiddenStems": [s for s, _ in HIDDEN_STEMS.get(zhi, ())] if gz else [],
                "shishenZhi": [ten_god(day_master, s) for s, _ in HIDDEN_STEMS.get(zhi, ())] if gz else [],
                "changsheng": zizuo(day_master, zhi) if gz else "",
            }
        )
        if len(items) >= count + 1:
            break
    return items


def _build_liunian_list(
    yun: Any, day_master: str, max_year: int, segments: int = 13
) -> tuple[list[dict[str, Any]], dict[int, int], dict[int, str]]:
    """全量流年（封顶 max_year），返回 年→大运index 与 年→小运干支 映射。

    segments = 大运段数（含童限），需覆盖整条大运序列。
    """
    items: list[dict[str, Any]] = []
    year_dayun: dict[int, int] = {}
    xiaoyun: dict[int, str] = {}
    for d in yun.getDaYun(segments):
        for x in d.getXiaoYun():
            xiaoyun[x.getYear()] = x.getGanZhi()
        for ln in d.getLiuNian():
            year = ln.getYear()
            if year > max_year:
                continue
            if year in year_dayun:
                continue
            year_dayun[year] = d.getIndex()
            # 自算流年干支：lunar-python 的 LiuNian.getGanZhi() 在部分年段每条要 ~9ms（125 条即 1.1s），
            # 与立春换岁口径逐项核对过，结果完全一致。
            gz = _year_ganzhi(year)
            hidden = [s for s, _ in HIDDEN_STEMS.get(gz[1], ())] if len(gz) == 2 else []
            items.append(
                {
                    "year": year,
                    "ganzhi": gz,
                    "age": ln.getAge(),
                    "dayunIndex": d.getIndex(),
                    "shishen": ten_god(day_master, gz[0]),
                    "shishenZhi": [ten_god(day_master, s) for s in hidden],
                    "changsheng": zizuo(day_master, gz[1]) if len(gz) == 2 else "",
                    "xunkong": _xunkong(gz),
                    "xiaoyun": xiaoyun.get(year, ""),
                }
            )
    return items, year_dayun, xiaoyun


def _yunzhu_shensha(
    ganzhi: str, pillars: list[Pillar], day_master: str, gender_int: int
) -> list[dict[str, str]]:
    """运柱神煞（大运/流年/流月同一口径）：把该干支当临时运柱并入四柱算神煞，再按柱筛出。"""
    if len(ganzhi) != 2 or ganzhi[0] not in GAN_WUXING or ganzhi[1] not in ZHI_WUXING:
        return []
    gan, zhi = ganzhi
    hidden = [s for s, _ in HIDDEN_STEMS.get(zhi, ())]
    temp = Pillar(
        name="运柱",
        ganzhi=ganzhi,
        gan=gan,
        zhi=zhi,
        gan_wuxing=GAN_WUXING.get(gan, ""),
        zhi_wuxing=ZHI_WUXING.get(zhi, ""),
        nayin="",
        xunkong="",
        hidden_stems=hidden,
        shishen_gan=ten_god(day_master, gan),
        shishen_zhi=[ten_god(day_master, s) for s in hidden],
        changsheng=zizuo(day_master, zhi),
        zizuo="",
    )
    all_shensha = _compute_shensha(pillars + [temp], gender_int)
    return [
        {"name": s["name"], "description": s["description"]} for s in all_shensha if s.get("pillar") == "运柱"
    ]


def _month_meta(day_master: str) -> dict[str, dict[str, Any]]:
    """月支 → 地支十神 / 星运：两者都是月支的纯函数，12 条即可，不必逐月重复。"""
    return {
        zhi: {
            "shishenZhi": [ten_god(day_master, hd) for hd, _ in HIDDEN_STEMS.get(zhi, ())],
            "changsheng": zizuo(day_master, zhi),
        }
        for zhi in _MONTH_ZHI
    }


def _ganzhi_meta(day_master: str) -> dict[str, dict[str, Any]]:
    """全部 60 个干支的命盘列字段（十神/藏干/地支十神/星运/自坐/旬空/纳音）。

    这些都是「干支 + 日主」的纯函数。前端点选任意大运/流年都要就地重拼命盘大表，
    整轮 60 个一次算完下发（约 5KB），比固定按当前时刻只给一列更灵活也不增体积。
    """
    out: dict[str, dict[str, Any]] = {}
    for n in range(60):
        gz = _GAN_SEQ[n % 10] + _ZHI_SEQ[n % 12]
        col = _ganzhi_column("", gz, day_master, _xunkong(gz))
        col.pop("name", None)
        out[gz] = col
    return out


def _liunian_shensha_index(
    liunian_list: list[dict[str, Any]], pillars: list[Pillar], day_master: str, gender_int: int
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """流年干支 → 神煞名，外加 名 → 说明。

    流年神煞只由流年干支决定，60 条即可覆盖全部 125 个流年；此前神煞挂在顶层 chart.liunian
    上且只覆盖当前大运十年，切到别的大运就没有神煞可显示。
    """
    names: dict[str, list[str]] = {}
    desc: dict[str, str] = {}
    for item in liunian_list:
        gz = item["ganzhi"]
        if gz in names:
            continue
        ss = _yunzhu_shensha(gz, pillars, day_master, gender_int)
        names[gz] = [entry["name"] for entry in ss]
        for entry in ss:
            desc.setdefault(entry["name"], entry["description"])
    return names, desc


def _build_liuyue_list(
    start_year: int, end_year: int, day_master: str, pillars: list[Pillar], gender_int: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """节气月列表 + 随附的去重表。

    月干支 60 个一循环、神煞只随干支变，所以既不逐行内嵌说明、也不逐行重复名列表：
    行里只留 year/zhi/jieqi/date/ganzhi/shishen，神煞名收进 liuyueShensha（干支→名列表）、
    说明收进 shenshaDict；地支十神与星运是月支的纯函数，收进 monthMeta（12 条）。
    12 步大运下 1500 条流月曾占 /chart 响应 95% 体积，即由此而来。神煞规则与结果不变。
    """
    items: list[dict[str, Any]] = []
    shensha_cache: dict[str, list[dict[str, str]]] = {}
    shensha_by_gz: dict[str, list[str]] = {}
    shensha_dict: dict[str, str] = {}
    for year in range(start_year, end_year + 1):
        table = _jie_table(year)
        year_gan = _year_ganzhi(year)[0]
        for i, zhi in enumerate(_MONTH_ZHI):
            jie = table[_JIE_OF_MONTH[zhi]]
            s = jie
            gz = _month_ganzhi(year_gan, i)
            # 月干支 60 个一循环，神煞按干支缓存（同一干支神煞不变）
            ss = shensha_cache.get(gz)
            if ss is None:
                ss = _yunzhu_shensha(gz, pillars, day_master, gender_int)
                shensha_cache[gz] = ss
                shensha_by_gz[gz] = [entry["name"] for entry in ss]
                for entry in ss:
                    shensha_dict.setdefault(entry["name"], entry["description"])
            items.append(
                {
                    "year": year,
                    "zhi": zhi,
                    "jieqi": _JIE_OF_MONTH[zhi],
                    "date": f"{s.getMonth()}/{s.getDay()}",
                    "ganzhi": gz,
                    "shishen": ten_god(day_master, gz[0]),
                }
            )
    extras = {
        "liuyueShensha": shensha_by_gz,
        "shenshaDict": shensha_dict,
        "monthMeta": _month_meta(day_master),
    }
    return items, extras


def _current(
    today: datetime.date,
    yun: Any,
    year_dayun: dict[int, int],
    xiaoyun: dict[int, str],
    dayun_list: list[dict[str, Any]],
    day_master: str,
    birth_year: int,
) -> dict[str, Any]:
    lunar = Solar.fromYmdHms(today.year, today.month, today.day, 12, 0, 0).getLunar()
    lichun = _jie_table(today.year)["立春"]
    liunian_year = today.year if today >= _solar_date(lichun) else today.year - 1
    year_gz = _year_ganzhi(liunian_year)
    dy_index = year_dayun.get(liunian_year, 0)
    dy = next((d for d in dayun_list if d["index"] == dy_index), None)
    # 童限期（未交大运）以当年小运代替大运
    tongxian = dy_index == 0
    dy_gz = xiaoyun.get(liunian_year, "") if tongxian else (dy["ganzhi"] if dy else "")
    current_jie = lunar.getCurrentJie()
    month_zhi = (
        _ZHI_OF_JIE[current_jie.getName()] if current_jie else _ZHI_OF_JIE[lunar.getPrevJie().getName()]
    )
    month_index = _MONTH_ZHI.index(month_zhi)
    month_gz = _month_ganzhi(year_gz[0], month_index)
    year_xunkong = Solar.fromYmdHms(liunian_year, 6, 1, 12, 0, 0).getLunar().getYearXunKongByLiChun()
    return {
        "year": liunian_year,
        "age": liunian_year - birth_year + 1,
        "dayunIndex": dy_index,
        "dayun": dy_gz,
        "dayunLabel": "小运" if tongxian else "大运",
        "dayunShishen": ten_god(day_master, dy_gz[0]) if dy_gz and dy_gz != "童限" else "",
        "liunian": year_gz,
        "liunianShishen": ten_god(day_master, year_gz[0]),
        "liunianXunkong": year_xunkong,
        "liuyue": month_gz,
        "liuyueShishen": ten_god(day_master, month_gz[0]),
        "liuyueJieqi": current_jie.getName() if current_jie else lunar.getPrevJie().getName(),
        "liuyueDate": f"{current_jie.getSolar().getMonth()}/{current_jie.getSolar().getDay()}"
        if current_jie
        else f"{lunar.getPrevJie().getSolar().getMonth()}/{lunar.getPrevJie().getSolar().getDay()}",
    }


def _pillar_column(p: Pillar, day_master: str) -> dict[str, Any]:
    return {
        "name": p.name,
        "ganzhi": p.ganzhi,
        "shishen": p.shishen_gan,
        "gan": p.gan,
        "zhi": p.zhi,
        "hiddenStems": p.hidden_stems,
        "shishenZhi": p.shishen_zhi,
        "changsheng": p.changsheng,
        "zizuo": p.zizuo,
        "xunkong": p.xunkong,
        "nayin": p.nayin,
    }


def _ganzhi_column(name: str, ganzhi: str, day_master: str, xunkong: str) -> dict[str, Any]:
    if len(ganzhi) != 2 or ganzhi[0] not in GAN_WUXING or ganzhi[1] not in ZHI_WUXING:
        return {
            "name": name,
            "ganzhi": ganzhi,
            "shishen": "",
            "gan": "",
            "zhi": "",
            "hiddenStems": [],
            "shishenZhi": [],
            "changsheng": "",
            "zizuo": "",
            "xunkong": xunkong,
            "nayin": "",
        }
    gan, zhi = ganzhi[0], ganzhi[1]
    hidden = [s for s, _ in HIDDEN_STEMS.get(zhi, ())]
    return {
        "name": name,
        "ganzhi": ganzhi,
        "shishen": ten_god(day_master, gan),
        "gan": gan,
        "zhi": zhi,
        "hiddenStems": hidden,
        "shishenZhi": [ten_god(day_master, s) for s in hidden],
        "changsheng": zizuo(day_master, zhi),
        "zizuo": zizuo(gan, zhi),
        "xunkong": xunkong,
        "nayin": LunarUtil.NAYIN.get(ganzhi, ""),
    }


def _build_snapshot(
    pillars: list[Pillar],
    cur: dict[str, Any],
    dayun_list: list[dict[str, Any]],
    day_master: str,
    gender_int: int,
) -> dict[str, Any]:
    dy = next((d for d in dayun_list if d["index"] == cur["dayunIndex"]), None)
    columns = [
        _ganzhi_column("流年", cur["liunian"], day_master, cur.get("liunianXunkong", "")),
        _ganzhi_column(cur.get("dayunLabel", "大运"), cur["dayun"], day_master, dy["xunkong"] if dy else ""),
        *[_pillar_column(p, day_master) for p in pillars],
    ]
    return {"columns": columns, "label": f"元{'男' if gender_int == 1 else '女'}"}


def _wuxing_state(month_zhi: str) -> list[dict[str, str]]:
    """月令五行定旺相休囚死：当令旺、令生相、生令休、克令囚、令克死。"""
    ling = ZHI_WUXING.get(month_zhi, "")
    state = {}
    for name in WUXING_ORDER:
        if name == ling:
            state[name] = "旺"
        elif GENERATES[ling] == name:
            state[name] = "相"
        elif GENERATES[name] == ling:
            state[name] = "休"
        elif CONTROLS[name] == ling:
            state[name] = "囚"
        elif CONTROLS[ling] == name:
            state[name] = "死"
    order = {"旺": 0, "相": 1, "休": 2, "囚": 3, "死": 4}
    return [{"name": n, "state": s} for n, s in sorted(state.items(), key=lambda kv: order[kv[1]])]


def _siling(birth_solar: Any, month_zhi: str) -> dict[str, Any]:
    """人元司令分野：出生距月建节第几天 → 分野表用事天干。"""
    prev_jie = (
        Solar.fromYmdHms(
            birth_solar.getYear(), birth_solar.getMonth(), birth_solar.getDay(), birth_solar.getHour(), 0, 0
        )
        .getLunar()
        .getPrevJie()
    )
    days = (_solar_date(birth_solar) - _solar_date(prev_jie.getSolar())).days + 1
    stem = ""
    acc = 0
    for s, span in _FENYE.get(month_zhi, ()):
        acc += span
        if days <= acc:
            stem = s
            break
    return {
        "stem": stem,
        "detail": f"{prev_jie.getName()}后{days}天，{stem}司令" if stem else "",
    }


def _ke(a: str, b: str) -> bool:
    """a 的五行是否克 b 的五行（干支通用）。"""
    wa, wb = GZ_WUXING.get(a, ""), GZ_WUXING.get(b, "")
    return bool(wa) and CONTROLS.get(wa, "") == wb


def _dedup(items: list[str]) -> list[str]:
    """按首次出现顺序去重（同一关系被多柱重复触发时只报一次）。"""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _gan_rel(a: str, b: str) -> str:
    """两天干关系：五合优先，其次相克（克者在前，与专业排盘软件同写法）。"""
    if not a or not b or a == b:
        return ""
    pair = frozenset((a, b))
    if pair in GAN_HE:
        return GAN_HE[pair]
    if _ke(a, b):
        return f"{a}{b}相克"
    if _ke(b, a):
        return f"{b}{a}相克"
    return ""


# 三合局（生-旺-墓）与所属五行：缺中神时两支拱出中神
_SAN_HE_GROUPS = (
    ("申", "子", "辰", "水"),
    ("亥", "卯", "未", "木"),
    ("寅", "午", "戌", "火"),
    ("巳", "酉", "丑", "金"),
)


def _zhi_group_rel(zhis: list[str]) -> list[str]:
    """三合局、半合、拱局（申辰拱子）与会方。"""
    out: list[str] = []
    for a, b, c, wx in _SAN_HE_GROUPS:
        has = (a in zhis, b in zhis, c in zhis)
        if all(has):
            out.append(f"{a}{b}{c}合{wx}局")
        elif has[0] and has[1]:
            out.append(f"{a}{b}半合{wx}")
        elif has[1] and has[2]:
            out.append(f"{b}{c}半合{wx}")
        elif has[0] and has[2]:
            out.append(f"{a}{c}拱合{b}")
    for group, label in SAN_HUI.items():
        if group.issubset(set(zhis)):
            out.append(label)
    return out


def _zhi_pair_rel(x: str, y: str) -> list[str]:
    """两地支的六合/六冲/六害/六破（同支不论）。"""
    if not x or not y or x == y:
        return []
    pair = frozenset((x, y))
    return [table[pair] for table in (LIU_HE, LIU_CHONG, LIU_HAI, LIU_PO) if pair in table]


def _zhi_xing(zhis: list[str]) -> list[str]:
    """三刑（持势/无恩/无礼）与自刑。"""
    out: list[str] = []
    zset = set(zhis)
    for group, label in SAN_XING.items():
        if group.issubset(zset):
            out.append(label)
    for z in zhis:
        if z in SELF_XING and zhis.count(z) >= 2:
            out.append(f"{z}{z}相刑")
    return out


def _pillar_rel(gz: str, ref: str) -> str:
    """两柱之间：干支全同为伏吟，天干相克且地支六冲为反吟。"""
    if len(gz) != 2 or len(ref) != 2:
        return ""
    if gz == ref:
        return f"{gz}伏吟"
    if _ke(gz[0], ref[0]) or _ke(ref[0], gz[0]):
        if frozenset((gz[1], ref[1])) in LIU_CHONG:
            return f"{gz}反吟"
    return ""


def _own_pillar_rel(gz: str) -> str:
    """单柱天干地支关系：干克支为盖头，支克干为截脚。"""
    if len(gz) != 2:
        return ""
    gan, zhi = gz[0], gz[1]
    if _ke(gan, zhi):
        return f"{gz}盖头"
    if _ke(zhi, gan):
        return f"{gz}截脚"
    return ""


def _build_relations(pillars: list[Pillar], sui: list[str]) -> dict[str, Any]:
    """岁运分析（大运·流年·流月 叠加原局）与原局分析，六栏文字与专业排盘软件对齐。"""
    orig_gan = [p.gan for p in pillars]
    orig_zhi = [p.zhi for p in pillars]
    orig_gz = [p.ganzhi for p in pillars]
    sui_gan = [g[0] for g in sui if len(g) == 2]
    sui_zhi = [g[1] for g in sui if len(g) == 2]

    # 岁运：只取「岁运 × 原局」与「岁运 × 岁运」，原局内部留给原局栏
    sui_gan_items = [_gan_rel(a, b) for a in sui_gan for b in orig_gan]
    sui_gan_items += [
        _gan_rel(sui_gan[i], sui_gan[j]) for i in range(len(sui_gan)) for j in range(i + 1, len(sui_gan))
    ]
    all_zhi = sui_zhi + orig_zhi
    sui_zhi_items = _zhi_group_rel(all_zhi)
    for x in sui_zhi:
        for y in orig_zhi:
            sui_zhi_items += _zhi_pair_rel(x, y)
    for i in range(len(sui_zhi)):
        for j in range(i + 1, len(sui_zhi)):
            sui_zhi_items += _zhi_pair_rel(sui_zhi[i], sui_zhi[j])
    sui_zhi_items += _zhi_xing(all_zhi)
    sui_zhu = [_pillar_rel(g, r) for g in sui for r in orig_gz]

    yuan_gan = [
        _gan_rel(orig_gan[i], orig_gan[j]) for i in range(len(orig_gan)) for j in range(i + 1, len(orig_gan))
    ]
    yuan_zhi = _zhi_group_rel(orig_zhi)
    for i in range(len(orig_zhi)):
        for j in range(i + 1, len(orig_zhi)):
            yuan_zhi += _zhi_pair_rel(orig_zhi[i], orig_zhi[j])
    yuan_zhi += _zhi_xing(orig_zhi)
    yuan_zhu = [_own_pillar_rel(gz) for gz in orig_gz]

    return {
        "suiyun": {
            "label": " · ".join(sui),
            "gan": _dedup(sui_gan_items),
            "zhi": _dedup(sui_zhi_items),
            "zhu": _dedup(sui_zhu),
        },
        "yuanju": {
            "label": " ".join(orig_gz),
            "gan": _dedup(yuan_gan),
            "zhi": _dedup(yuan_zhi),
            "zhu": _dedup(yuan_zhu),
        },
    }


def build_xipan(
    yun: Any,
    pillars: list[Pillar],
    gender_int: int,
    day_master: str,
    direction: str,
    today: datetime.date | None = None,
) -> dict[str, Any]:
    """构建时间层级细盘：起运/大运/流年/流月/当前快照/月令旺衰/司令。

    yun 为 lunar_python EightChar.getYun() 产物；today 可注入以便测试。
    """
    today = today or datetime.date.today()
    birth_solar = yun.getLunar().getSolar()
    birth_year = birth_solar.getYear()

    dayun_list = _build_dayun_list(yun, day_master)
    end_year = max((d["endYear"] for d in dayun_list), default=birth_year + 80)
    liunian_list, year_dayun, xiaoyun = _build_liunian_list(yun, day_master, end_year, segments=len(dayun_list))
    liuyue_list, liuyue_extras = _build_liuyue_list(birth_year, end_year, day_master, pillars, gender_int)
    ln_shensha, ln_desc = _liunian_shensha_index(liunian_list, pillars, day_master, gender_int)
    liuyue_extras["liunianShensha"] = ln_shensha
    liuyue_extras["shenshaDict"].update(ln_desc)
    liuyue_extras["ganzhiMeta"] = _ganzhi_meta(day_master)

    cur = _current(today, yun, year_dayun, xiaoyun, dayun_list, day_master, birth_year)
    month_zhi = pillars[1].zhi if pillars else ""

    sui = [g for g in (cur["dayun"], cur["liunian"], cur["liuyue"]) if len(g) == 2]

    return {
        "qiyun": _qiyun(yun, direction),
        "current": cur,
        "dayun": dayun_list,
        "liunian": liunian_list,
        "liuyue": liuyue_list,
        **liuyue_extras,
        "snapshot": _build_snapshot(pillars, cur, dayun_list, day_master, gender_int),
        "relations": _build_relations(pillars, sui),
        "wuxingState": _wuxing_state(month_zhi),
        "siling": _siling(birth_solar, month_zhi),
        "note": "流年以立春换岁、流月以节气换月；大运按出生后折算起运，逢年干循环之年交运。",
    }
