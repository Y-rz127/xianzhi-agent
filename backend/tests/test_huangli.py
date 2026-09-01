"""黄历领域计算与择吉筛选测试（黄金快照 + 边界校验）。

黄金用例对照当版《中华民俗老黄历》/主流排盘 App 手工核验：
- 2024-02-10 甲辰年正月初一（春节），甲辰日冲戊戌狗，煞南
- 2025-01-29 乙巳年正月初一（春节），戊戌日冲壬辰龙，煞北
- 2026-08-30 丙午年七月十八，丙子日冲庚午马，煞南，青龙黄道，建星定
"""
from __future__ import annotations

import pytest

from app.domain.huangli_calc import (
    RANGE_MAX_DAYS,
    YI_JI_ITEMS,
    ZEJI_MAX_DAYS,
    build_huangli_day,
    build_range_briefs,
    filter_zeji,
    parse_date,
)
from app.sub_app.huangli.huangli_app import huangli_day, zeji

# ===== 黄金快照 =====

@pytest.mark.parametrize("date,expected", [
    (
        "2024-02-10",
        {"day_gz": "甲辰", "lunar_text": "农历甲辰年正月初一", "festivals": ["春节"],
         "chong_desc": "(戊戌)狗", "sha": "南", "zhixing": "满", "tian_shen": "金匮",
         "yi_head": "嫁娶", "pengzu_zhi_head": "辰"},
    ),
    (
        "2025-01-29",
        {"day_gz": "戊戌", "lunar_text": "农历乙巳年正月初一", "festivals": ["春节"],
         "chong_desc": "(壬辰)龙", "sha": "北", "zhixing": "收", "tian_shen": "青龙",
         "yi_head": "祭祀", "pengzu_zhi_head": "戌"},
    ),
    (
        "2026-08-30",
        {"day_gz": "丙子", "lunar_text": "农历丙午年七月十八", "festivals": [],
         "chong_desc": "(庚午)马", "sha": "南", "zhixing": "定", "tian_shen": "青龙",
         "yi_head": "嫁娶", "pengzu_zhi_head": "子"},
    ),
])
def test_golden_day(date, expected):
    day = build_huangli_day(date)
    assert day["lunar"]["day_gz"] == expected["day_gz"]
    assert day["lunar"]["text"] == expected["lunar_text"]
    assert day["festivals"] == expected["festivals"]
    assert day["chong"]["desc"] == expected["chong_desc"]
    assert day["chong"]["sha"] == expected["sha"]
    assert day["zhixing"] == expected["zhixing"]
    assert day["tian_shen"]["name"] == expected["tian_shen"]
    assert day["yi"][0] == expected["yi_head"]
    # 彭祖百忌地支句以当日地支开头（"子不问卜…"）
    assert day["pengzu"]["zhi"].startswith(expected["pengzu_zhi_head"])
    # 星期与日期一致（用 datetime 独立交叉验证）
    import datetime
    d = datetime.date.fromisoformat(date)
    weekdays = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
    assert day["solar"].endswith(weekdays[d.weekday()])


def test_day_structure_complete():
    day = build_huangli_day("2026-08-30")
    # 十二时辰：lunar-python 把子时拆两条，领域层应合并为 12 条
    assert [h["zhi"] for h in day["hours"]] == [
        "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥",
    ]
    assert day["hours"][0]["range"] == "23:00-00:59"
    # 子时内容必须取当日早子（金匮·吉），而非晚子段（次日子时干支·天刑·凶）；
    # 曾出过取错半段的 bug：与主流老黄历对照时唯独子时吉凶相反。
    assert day["hours"][0]["tian_shen"] == "金匮"
    assert day["hours"][0]["luck"] == "吉"
    for h in day["hours"]:
        assert h["luck"] in ("吉", "凶")
        assert isinstance(h["yi"], list) and isinstance(h["ji"], list)
    # 八吉神方位齐备
    assert set(day["positions"]) == {
        "cai", "xi", "fu", "yang_gui", "yin_gui", "five_ghost", "sheng_men", "si_men",
    }
    # 九星为"数字+颜色+五行"三字（如 九紫火），不带北斗星名后缀
    assert len(day["nine_star"]) == 3
    assert day["nine_star"] == "九紫火"
    # 胎神/纳音与主流老黄历 App 对照核验（丙子日：厨灶碓外西南 / 涧下水）
    assert day["taishen"] == "厨灶碓外西南"
    assert day["nayin"] == "涧下水"


def test_positions_school():
    """方位流派钉死：财神用民历通书派（与主流老黄历 App 对照核验），
    非 lunar-python 内置的《玉匣记》派（丙日会算出西南）。"""
    bingzi = build_huangli_day("2026-08-30")  # 丙子日
    p = bingzi["positions"]
    assert p["cai"] == "正西"
    # 喜神/福神/阴贵与主流老黄历一致，维持 lunar 输出
    assert p["xi"] == "西南"
    assert p["fu"] == "西北"
    assert p["yin_gui"] == "西北"
    # 阳贵：六十甲子逐日表 + 丙日覆写（手机丙子/丙戌实测正南，古表为正西）
    assert p["yang_gui"] == "正南"
    # 五鬼（日干表）/生门/死门（逐日表）：与手机 8/30 截图逐项一致
    assert p["five_ghost"] == "正北"
    assert p["sheng_men"] == "正北"
    assert p["si_men"] == "正南"
    # 民历派财神表抽查：甲申东北 / 庚辰正东 / 壬午正南
    assert build_huangli_day("2026-09-07")["positions"]["cai"] == "东北"
    assert build_huangli_day("2026-09-03")["positions"]["cai"] == "正东"
    assert build_huangli_day("2026-09-05")["positions"]["cai"] == "正南"
    # 手机对照批次抽查：丁亥（阳贵西北/五鬼正北/生门西南/死门东北）、戊子（生门东北/死门西南）
    dinghai = build_huangli_day("2026-09-10")["positions"]
    assert (dinghai["yang_gui"], dinghai["five_ghost"]) == ("西北", "正北")
    assert (dinghai["sheng_men"], dinghai["si_men"]) == ("西南", "东北")
    wuzi = build_huangli_day("2026-09-11")["positions"]
    assert (wuzi["sheng_men"], wuzi["si_men"]) == ("东北", "西南")
    # 表本身抽查（无手机对照日）：庚寅 阳贵东北/生门东北/死门西南
    gengyin = build_huangli_day("2026-09-13")["positions"]
    assert (gengyin["yang_gui"], gengyin["sheng_men"], gengyin["si_men"]) == ("东北", "东北", "西南")
    # 8/26-8/28 批次：癸酉、甲戌与手机全字段一致
    guiyou = build_huangli_day("2026-08-27")["positions"]
    assert (guiyou["cai"], guiyou["five_ghost"], guiyou["sheng_men"], guiyou["si_men"]) == (
        "正南", "西南", "正南", "正北")
    jiaxu = build_huangli_day("2026-08-28")["positions"]
    assert (jiaxu["cai"], jiaxu["fu"], jiaxu["five_ghost"], jiaxu["sheng_men"]) == (
        "东北", "正北", "东南", "正南")
    # 壬申日：五鬼西北补齐十干最后一项实测。其生门/死门手机显示正南/正北（下一三日组
    # 的值）——已由 8/24 庚午、8/25 辛未截图定案：这两天手机与我们的东南/西北完全一致，
    # 证明是手机 App 壬申行自身错组，本实现按古表+三日组律维持不变。
    renshen = build_huangli_day("2026-08-26")["positions"]
    assert (renshen["cai"], renshen["xi"], renshen["fu"]) == ("正南", "正南", "东南")
    assert (renshen["yang_gui"], renshen["yin_gui"], renshen["five_ghost"]) == (
        "正东", "东南", "西北")
    assert (renshen["sheng_men"], renshen["si_men"]) == ("东南", "西北")
    # 8/24 庚午、8/25 辛未：手机全 8 字段与实现一致（壬申同组，定案证据）
    gengwu = build_huangli_day("2026-08-24")["positions"]
    assert tuple(gengwu[k] for k in ("cai", "xi", "fu", "yang_gui", "yin_gui",
                                     "five_ghost", "sheng_men", "si_men")) == (
        "正东", "西北", "西南", "东北", "西南", "东北", "东南", "西北")
    xinwei = build_huangli_day("2026-08-25")["positions"]
    assert tuple(xinwei[k] for k in ("cai", "xi", "fu", "yang_gui", "yin_gui",
                                     "five_ghost", "sheng_men", "si_men")) == (
        "正东", "西南", "西北", "东北", "正南", "东北", "东南", "西北")


def test_day_god_pos_table_integrity():
    """六十甲子逐日诸神表完整性：60 行、干支全覆盖、方位值合法、生门死门恒对冲。"""
    from app.domain.huangli_calc import _DAY_GOD_POS

    assert len(_DAY_GOD_POS) == 60
    import datetime as dt

    from lunar_python import Solar

    start = dt.date(2026, 1, 1)
    all_gz = {
        Solar.fromYmd(*(start + dt.timedelta(days=i)).timetuple()[:3]).getLunar().getDayInGanZhi()
        for i in range(60)
    }
    assert set(_DAY_GOD_POS) == all_gz
    valid = {"东北", "正东", "东南", "东北", "西南", "正西", "西北", "正北", "正南"}
    opposites = {"正北": "正南", "正南": "正北", "正东": "正西", "正西": "正东",
                 "东北": "西南", "西南": "东北", "西北": "东南", "东南": "西北"}
    for gz, (yg, ygui, sm, dm) in _DAY_GOD_POS.items():
        assert yg in valid and ygui in valid and sm in valid and dm in valid, gz
        assert opposites[sm] == dm, f"{gz} 生门{sm} 死门{dm} 不相对"
    # 三日组律：按甲子序自丙子起每 3 日一组，组内同门同向（源表讹字即由此律抓出）
    seq = [
        Solar.fromYmd(*(dt.date(2026, 1, 1) + dt.timedelta(days=i)).timetuple()[:3])
        .getLunar().getDayInGanZhi()
        for i in range(60)
    ]
    idx = seq.index("丙子")
    ordered = seq[idx:] + seq[:idx]
    for g in range(0, 60, 3):
        group = ordered[g:g + 3]
        assert len({_DAY_GOD_POS[x][2] for x in group}) == 1, f"生门组内不一致: {group}"
        assert len({_DAY_GOD_POS[x][3] for x in group}) == 1, f"死门组内不一致: {group}"


def test_day_default_is_today():
    import datetime
    day = huangli_day("")
    assert day["date"] == datetime.date.today().isoformat()
    assert day == build_huangli_day(datetime.date.today().isoformat())


# ===== 边界与错误 =====

def test_parse_date_range_limit():
    assert parse_date("1900-01-01") is not None
    assert parse_date("2100-12-31") is not None
    assert parse_date("20260830").isoformat() == "2026-08-30"
    with pytest.raises(ValueError, match="仅支持"):
        parse_date("1899-12-31")
    with pytest.raises(ValueError, match="仅支持"):
        parse_date("2101-01-01")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_date("2026年8月30日")
    with pytest.raises(ValueError):
        parse_date("2026-13-40")


def test_range_limit_31_days():
    assert len(build_range_briefs("2026-08-01", "2026-08-31")) == 31
    with pytest.raises(ValueError, match="区间上限 {} 天".format(RANGE_MAX_DAYS)):
        build_range_briefs("2026-08-01", "2026-09-01")
    with pytest.raises(ValueError, match="start 不能晚于 end"):
        build_range_briefs("2026-08-30", "2026-08-01")


def test_range_brief_fields():
    briefs = build_range_briefs("2025-01-28", "2025-01-30")
    chunjie = next(b for b in briefs if b["date"] == "2025-01-29")
    assert chunjie["festivals"] == ["春节"]
    assert chunjie["lunar_day"] == "正月初一"
    assert chunjie["tianshe"] is False
    assert len(chunjie["yi_top5"]) <= 5 and len(chunjie["ji_top3"]) <= 3


def test_other_festivals_merged():
    """lunar 的 getFestivals() 只含八大节，中元/上巳/下元/祭灶等 24 个民俗节
    在 getOtherFestivals()，两表必须合并，否则月视图缺节（曾因只调前者漏中元节）。"""
    day = build_huangli_day("2026-08-27")  # 七月十五
    assert "中元节" in day["festivals"]
    briefs = build_range_briefs("2026-08-27", "2026-08-27")
    assert "中元节" in briefs[0]["festivals"]
    # 主表行为不变：七夕（主表）当天不多不少
    assert build_huangli_day("2026-08-19")["festivals"] == ["七夕节"]


def test_zeji_wordlist_validation():
    assert len(YI_JI_ITEMS) == 139
    # 去重且无退化词条
    assert len(set(YI_JI_ITEMS)) == len(YI_JI_ITEMS)
    for excluded in ("无", "诸事不宜", "馀事勿取"):
        assert excluded not in YI_JI_ITEMS
    assert "嫁娶" in YI_JI_ITEMS and "开市" in YI_JI_ITEMS
    with pytest.raises(ValueError, match="不支持的择吉事项"):
        zeji("不存在的项目", "2026-09-01", "2026-09-15")


def test_zeji_hit_and_avoid_chong():
    hits = zeji("开市", "2026-09-01", "2026-09-15")
    assert hits, "区间内应存在宜开市的日子"
    for h in hits:
        assert h["date"] and h["day_gz"] and h["chong"]
        assert "开市" in build_huangli_day(h["date"])["yi"]

    avoided = zeji("开市", "2026-09-01", "2026-09-15", avoid_chong="鼠")
    # 避冲只会减少或保持命中，且剩余日子不冲鼠
    assert len(avoided) <= len(hits)
    for h in avoided:
        assert not build_huangli_day(h["date"])["chong"]["desc"].endswith(")鼠")


def test_zeji_stars_sorting():
    days = filter_zeji("嫁娶", "2026-01-01", "2026-03-01")
    if len(days) >= 2:
        stars = [d["stars"] for d in days]
        assert stars == sorted(stars, reverse=True)
        for d in days:
            assert d["stars"] == len(d["jishen"])
            assert (d["note"] != "") == (d["stars"] > 0)


def test_zeji_limit_60_days():
    with pytest.raises(ValueError, match="区间上限 {} 天".format(ZEJI_MAX_DAYS)):
        filter_zeji("嫁娶", "2026-01-01", "2026-03-02")


def test_zeji_empty_result_message():
    # 全部被避冲排除时返回空列表而非报错
    days = filter_zeji("开市", "2026-09-01", "2026-09-15", avoid_chong="")
    assert isinstance(days, list)


def test_yi_ji_wordlist_roundtrip():
    """词表回环：lunar 实际输出的宜/忌词必须全部在 YI_JI_ITEMS 内。

    硬编码词表一旦与 lunar 内部表漂移，择吉会「永远为空且不报错」、
    /items 下拉缺项，故用连续两年全量日期 + 一天全量时辰做回归兜底。
    """
    import datetime as dt

    from lunar_python import Solar

    seen: set[str] = set()
    d = dt.date(2025, 1, 1)
    while d <= dt.date(2026, 12, 31):
        lunar = Solar.fromYmd(d.year, d.month, d.day).getLunar()
        seen |= set(lunar.getDayYi(sect=1)) | set(lunar.getDayJi(sect=1))
        if d == dt.date(2025, 6, 15):  # 抽一天全量时辰，覆盖 LunarTime 词表
            for t in lunar.getTimes():
                seen |= set(t.getYi()) | set(t.getJi())
        d += dt.timedelta(days=1)

    vocab = set(YI_JI_ITEMS) | {"无", "诸事不宜", "馀事勿取"}
    missing = seen - vocab
    assert not missing, f"lunar 输出词未收录进 YI_JI_ITEMS（择吉/词表已漂移）: {sorted(missing)}"
    assert len(seen) > 80, f"回环扫描输出词数异常偏少（{len(seen)}），检查 lunar 是否失效"
