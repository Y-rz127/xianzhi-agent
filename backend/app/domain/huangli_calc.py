"""黄历领域计算（纯函数，基于 lunar-python 1.4.8 确定性排历）。

覆盖每日黄历（宜忌/冲煞/吉凶神/彭祖/五神方位/值神/建星/九星/二十八宿/时辰吉凶）、
区间简报与择吉筛选。与 bazi_engine 同为领域层纯计算，不依赖 LLM 与数据库。
"""
from __future__ import annotations

import datetime as _dt

from lunar_python import Solar

MIN_YEAR = 1900
MAX_YEAR = 2100
RANGE_MAX_DAYS = 31
ZEJI_MAX_DAYS = 60

# 吉神星标：命中即加星并优先排序（天德合/月德合按天德/月德前缀命中）
_LUCKY_SHEN_PREFIXES = ("天德", "月德")
_LUCKY_SHEN_EXACT = ("天赦", "四相")

# 宜忌事项词表全集，取自 lunar-python 1.4.8 LunarUtil.__YI_JI（requirements.lock 已锁定版本），
# 与 getDayYi/getDayJi 可返回的词一一对应；"无/诸事不宜/馀事勿取"不作为可检索事项。
_YI_JI_RAW = (
    "祭祀", "祈福", "求嗣", "开光", "塑绘", "齐醮", "斋醮", "沐浴", "酬神", "造庙",
    "祀灶", "焚香", "谢土", "出火", "雕刻", "嫁娶", "订婚", "纳采", "问名", "纳婿",
    "归宁", "安床", "合帐", "冠笄", "订盟", "进人口", "裁衣", "挽面", "开容", "修坟",
    "启钻", "破土", "安葬", "立碑", "成服", "除服", "开生坟", "合寿木", "入殓", "移柩",
    "普渡", "入宅", "安香", "安门", "修造", "起基", "动土", "上梁", "竖柱", "开井开池",
    "作陂放水", "拆卸", "破屋", "坏垣", "补垣", "伐木做梁", "作灶", "解除", "开柱眼",
    "穿屏扇架", "盖屋合脊", "开厕", "造仓", "塞穴", "平治道涂", "造桥", "作厕", "筑堤",
    "开池", "伐木", "开渠", "掘井", "扫舍", "放水", "造屋", "合脊", "造畜稠", "修门",
    "定磉", "作梁", "修饰垣墙", "架马", "开市", "挂匾", "纳财", "求财", "开仓", "买车",
    "置产", "雇佣", "出货财", "安机械", "造车器", "经络", "酝酿", "作染", "鼓铸", "造船",
    "割蜜", "栽种", "取渔", "结网", "牧养", "安碓磑", "习艺", "入学", "理发", "探病",
    "见贵", "乘船", "渡水", "针灸", "出行", "移徙", "分居", "剃头", "整手足甲", "纳畜",
    "捕捉", "畋猎", "教牛马", "会亲友", "赴任", "求医", "治病", "词讼", "起基动土",
    "破屋坏垣", "盖屋", "造仓库", "立券交易", "交易", "立券", "安机", "会友", "求医疗病",
    "诸事不宜", "馀事勿取", "行丧", "断蚁", "归岫", "无",
)
YI_JI_ITEMS: tuple[str, ...] = tuple(
    w for w in _YI_JI_RAW if w not in ("无", "诸事不宜", "馀事勿取")
)

_WEEKDAY_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

# 财神方位（日干）：民历通书派，与主流老黄历 App 一致（甲东北/乙西南/丙丁正西/
# 戊己正北/庚辛正东/壬癸正南）。lunar-python 内置的是《玉匣记》"丙丁向在西南寻"派，
# 两派皆有所本，本项目对齐用户端主流展示，弃用 lunar.getDayPositionCaiDesc()。
_CAI_MINLI = {
    "甲": "东北", "乙": "西南", "丙": "正西", "丁": "正西", "戊": "正北",
    "己": "正北", "庚": "正东", "辛": "正东", "壬": "正南", "癸": "正南",
}

# 五鬼方位（日干）：民历通书派。与主流老黄历 App 连续 12 日对照零例外
# （甲己东南/乙庚辛东北/丙丁正北/戊癸西南/己东南/壬西北；仅壬未经手机实测）。
_WUGUI_GAN = {
    "甲": "东南", "乙": "东北", "丙": "正北", "丁": "正北", "戊": "西南",
    "己": "东南", "庚": "东北", "辛": "东北", "壬": "西北", "癸": "西南",
}

# 六十甲子逐日诸神方位（阳贵/阴贵/生门/死门），渊海子平系《六十甲子诸神方位》全表，
# 与主流老黄历 App 17 日对照 134/136：唯一分歧壬申生门死门，已被同组庚午/辛未的
# 手机数据证伪（手机该行错组），本表按古表+三日组律维持。丙日阳贵例外见 _YANG_GUI_BING_OVERRIDE。
# 注：庚辰日阴贵实测证明此四列须逐日查表，不能按十干简化表折算。
_DAY_GOD_POS = {
    "甲子": ("西南", "东北", "东北", "西南"), "乙丑": ("西南", "正北", "东北", "西南"),
    "丙寅": ("正西", "西北", "东北", "西南"), "丁卯": ("西北", "正西", "正西", "正东"),
    "戊辰": ("东北", "西南", "正西", "正东"), "己巳": ("正北", "西南", "正西", "正东"),  # 己巳生门源表"正南"为讹字，按对冲组律校正
    "庚午": ("东北", "西南", "东南", "西北"), "辛未": ("东北", "正南", "东南", "西北"),
    "壬申": ("正东", "东南", "东南", "西北"), "癸酉": ("东南", "正东", "正南", "正北"),
    "甲戌": ("西南", "东北", "正南", "正北"), "乙亥": ("西南", "正北", "正南", "正北"),
    "丙子": ("正西", "西北", "正北", "正南"), "丁丑": ("西北", "正西", "正北", "正南"),
    "戊寅": ("东北", "西南", "正北", "正南"), "己卯": ("正北", "西南", "西北", "东南"),  # 戊寅生门源表"西北"为讹字，手机实测/组律/对冲三证校正
    "庚辰": ("东北", "西南", "西北", "东南"), "辛巳": ("东北", "正南", "西北", "东南"),
    "壬午": ("正东", "东南", "正东", "正西"), "癸未": ("东南", "正东", "正东", "正西"),
    "甲申": ("西南", "东北", "正东", "正西"), "乙酉": ("西南", "正北", "西南", "东北"),
    "丙戌": ("正西", "西北", "西南", "东北"), "丁亥": ("西北", "正西", "西南", "东北"),
    "戊子": ("东北", "西南", "东北", "西南"), "己丑": ("正北", "西南", "东北", "西南"),
    "庚寅": ("东北", "西南", "东北", "西南"), "辛卯": ("东北", "正南", "正西", "正东"),
    "壬辰": ("正东", "东南", "正西", "正东"), "癸巳": ("东南", "正东", "正西", "正东"),
    "甲午": ("西南", "东北", "东南", "西北"), "乙未": ("西南", "正北", "东南", "西北"),
    "丙申": ("正西", "西北", "东南", "西北"), "丁酉": ("西北", "正西", "正南", "正北"),  # 丁酉生门源表"正东"为讹字，按同组戊戌己亥与对冲律校正
    "戊戌": ("东北", "西南", "正南", "正北"), "己亥": ("正北", "西南", "正南", "正北"),
    "庚子": ("东北", "西南", "正北", "正南"), "辛丑": ("东北", "正南", "正北", "正南"),
    "壬寅": ("正东", "东南", "正北", "正南"), "癸卯": ("东南", "正东", "西北", "东南"),
    "甲辰": ("西南", "东北", "西北", "东南"), "乙巳": ("西南", "正北", "西北", "东南"),
    "丙午": ("正西", "西北", "正东", "正西"), "丁未": ("西北", "正西", "正东", "正西"),
    "戊申": ("东北", "西南", "正东", "正西"), "己酉": ("正北", "西南", "西南", "东北"),
    "庚戌": ("东北", "西南", "西南", "东北"), "辛亥": ("东北", "东南", "西南", "东北"),
    "壬子": ("正东", "正南", "东北", "西南"), "癸丑": ("东南", "正东", "东北", "西南"),
    "甲寅": ("西南", "东北", "东北", "西南"), "乙卯": ("西南", "正北", "正西", "正东"),
    "丙辰": ("正西", "西北", "正西", "正东"), "丁巳": ("西北", "正西", "正西", "正东"),
    "戊午": ("东北", "西南", "东南", "西北"), "己未": ("正北", "西南", "东南", "西北"),
    "庚申": ("东北", "西南", "东南", "西北"), "辛酉": ("东北", "正南", "正南", "正北"),
    "壬戌": ("正东", "东南", "正南", "正北"), "癸亥": ("东南", "正东", "正南", "正北"),
}

# 丙日阳贵：古表作正西，但主流黄历 App 实测丙子/丙戌两日均为正南（丙禄旺之地），
# 按用户"对齐手机"要求覆写为南。如需回到古表口径，置为 None 即可。
_YANG_GUI_BING_OVERRIDE = "正南"


def parse_date(text: str) -> _dt.date:
    """解析 YYYY-MM-DD（兼容 YYYYMMDD），超范围抛 ValueError。"""
    s = (text or "").strip()
    if len(s) == 8 and s.isdigit():
        s = "{}-{}-{}".format(s[:4], s[4:6], s[6:])
    try:
        date = _dt.date.fromisoformat(s)
    except ValueError:
        raise ValueError("日期格式应为 YYYY-MM-DD，如 2026-08-30") from None
    if not (MIN_YEAR <= date.year <= MAX_YEAR):
        raise ValueError("仅支持 {}-{} 年的日期".format(MIN_YEAR, MAX_YEAR))
    return date


def _lucky_shens(jishen: list[str]) -> list[str]:
    return [
        js for js in jishen
        if js in _LUCKY_SHEN_EXACT or js.startswith(_LUCKY_SHEN_PREFIXES)
    ]


def _hour_entry(t) -> dict:
    return {
        "zhi": t.getZhi(),
        "range": "{}-{}".format(t.getMinHm(), t.getMaxHm()),
        "tian_shen": t.getTianShen(),
        "luck": t.getTianShenLuck(),
        "yi": t.getYi(),
        "ji": t.getJi(),
        "chong": t.getChong(),
    }


def _hours(lunar) -> list[dict]:
    """十二时辰吉凶条。lunar-python 把子时拆成早子（00:00-00:59）与晚子（23:00-23:59）
    两条，晚子按五鼠遁实为次日的子时干支。本函数合并为一条：内容取当日早子段
    （值神/吉凶/宜忌），主流老黄历即此取法；时间范围标签仍用跨零点的完整子时区间。"""
    times = lunar.getTimes()
    zi = _hour_entry(times[0])
    zi["range"] = "{}-{}".format(times[-1].getMinHm(), times[0].getMaxHm())
    return [zi] + [_hour_entry(t) for t in times[1:-1]]


def _build_positions(lunar) -> dict:
    """八吉神方位：财神（民历日干表）/喜神/福神（流派2）/五鬼（日干表）按干查；
    阳贵/阴贵/生门/死门按日柱查六十甲子逐日表，丙日阳贵覆写正南（对齐主流 App 实测）。"""
    day_gan = lunar.getDayGan()
    yang_gui, yin_gui, sheng_men, si_men = _DAY_GOD_POS[lunar.getDayInGanZhi()]
    if day_gan == "丙" and _YANG_GUI_BING_OVERRIDE:
        yang_gui = _YANG_GUI_BING_OVERRIDE
    return {
        "cai": _CAI_MINLI[day_gan],
        "xi": lunar.getDayPositionXiDesc(),
        "fu": lunar.getDayPositionFuDesc(sect=2),
        "yang_gui": yang_gui,
        "yin_gui": yin_gui,
        "five_ghost": _WUGUI_GAN[day_gan],
        "sheng_men": sheng_men,
        "si_men": si_men,
    }


def build_huangli_day(date: str) -> dict:
    """完整当日黄历。date 为 YYYY-MM-DD，省略由调用方补今天。"""
    d = parse_date(date)
    solar = Solar.fromYmd(d.year, d.month, d.day)
    lunar = solar.getLunar()
    return {
        "date": d.isoformat(),
        "solar": "{} {}".format(d.isoformat(), _WEEKDAY_CN[d.weekday()]),
        "lunar": {
            "year_gz": lunar.getYearInGanZhi(),
            "month_gz": lunar.getMonthInGanZhi(),
            "day_gz": lunar.getDayInGanZhi(),
            "text": "农历{}年{}月{}".format(
                lunar.getYearInGanZhi(), lunar.getMonthInChinese(), lunar.getDayInChinese()
            ),
        },
        "festivals": list(solar.getFestivals()) + list(lunar.getFestivals()) + list(lunar.getOtherFestivals()),
        "jieqi": lunar.getJieQi(),
        "yi": lunar.getDayYi(sect=1),
        "ji": lunar.getDayJi(sect=1),
        "chong": {"desc": lunar.getDayChongDesc(), "sha": lunar.getDaySha()},
        "pengzu": {"gan": lunar.getPengZuGan(), "zhi": lunar.getPengZuZhi()},
        "taishen": lunar.getDayPositionTai().replace(" ", ""),
        "nayin": lunar.getDayNaYin(),
        "jishen": lunar.getDayJiShen(),
        "xiongsha": lunar.getDayXiongSha(),
        "positions": _build_positions(lunar),
        "tian_shen": {
            "name": lunar.getDayTianShen(),
            "type": lunar.getDayTianShenType(),
            "luck": lunar.getDayTianShenLuck(),
        },
        "zhixing": lunar.getZhiXing(),
        "nine_star": "{}{}{}".format(
            lunar.getDayNineStar().getNumber(),
            lunar.getDayNineStar().getColor(),
            lunar.getDayNineStar().getWuXing(),
        ),
        "xiu": {"name": lunar.getXiu(), "luck": lunar.getXiuLuck()},
        "hours": _hours(lunar),
    }


def _iter_dates(start: _dt.date, end: _dt.date):
    for offset in range((end - start).days + 1):
        yield start + _dt.timedelta(days=offset)


def build_range_briefs(start: str, end: str) -> list[dict]:
    """月视图轻量简报，每日仅保留摘要字段。超 31 天抛 ValueError。"""
    s, e = parse_date(start), parse_date(end)
    if s > e:
        raise ValueError("start 不能晚于 end")
    if (e - s).days + 1 > RANGE_MAX_DAYS:
        raise ValueError("区间上限 {} 天".format(RANGE_MAX_DAYS))
    briefs = []
    for d in _iter_dates(s, e):
        solar = Solar.fromYmd(d.year, d.month, d.day)
        lunar = solar.getLunar()
        briefs.append({
            "date": d.isoformat(),
            "weekday": _WEEKDAY_CN[d.weekday()],
            "lunar_day": "{}月{}".format(lunar.getMonthInChinese(), lunar.getDayInChinese()),
            "festivals": list(solar.getFestivals()) + list(lunar.getFestivals()) + list(lunar.getOtherFestivals()),
            "jieqi": lunar.getJieQi(),
            "yi_top5": lunar.getDayYi(sect=1)[:5],
            "ji_top3": lunar.getDayJi(sect=1)[:3],
            "tianshe": "天赦" in lunar.getDayJiShen(),
        })
    return briefs


def filter_zeji(yi: str, start: str, end: str, avoid_chong: str = "") -> list[dict]:
    """择吉：筛选区间内宜含目标事项的日子，吉神加星优先，可排除冲某生肖之日。

    avoid_chong 传生肖名（如"鼠"）。区间超 ZEJI_MAX_DAYS 天抛 ValueError。
    """
    s, e = parse_date(start), parse_date(end)
    if s > e:
        raise ValueError("start 不能晚于 end")
    if (e - s).days + 1 > ZEJI_MAX_DAYS:
        raise ValueError("区间上限 {} 天".format(ZEJI_MAX_DAYS))
    hits = []
    for d in _iter_dates(s, e):
        solar = Solar.fromYmd(d.year, d.month, d.day)
        lunar = solar.getLunar()
        if yi not in lunar.getDayYi(sect=1):
            continue
        if avoid_chong and lunar.getDayChongShengXiao() == avoid_chong:
            continue
        lucky = _lucky_shens(lunar.getDayJiShen())
        hits.append({
            "date": d.isoformat(),
            "day_gz": lunar.getDayInGanZhi(),
            "chong": lunar.getDayChongDesc(),
            "jishen": lucky,
            "tian_shen": lunar.getDayTianShen(),
            "stars": len(lucky),
            "note": "·".join(lucky) if lucky else "",
        })
    hits.sort(key=lambda h: (-h["stars"], h["date"]))
    return hits
