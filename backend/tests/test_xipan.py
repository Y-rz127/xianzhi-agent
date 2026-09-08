"""细盘（时间层级）单元与集成测试。

基准命例：2004-06-22 08:00 男 → 甲申 / 庚午 / 壬申 / 甲辰（日主壬），与专业排盘软件口径逐项核对：
- 起运：出生后4年11月，2009-05-22 交运，逢己年，顺排
- 大运：童限(2004-2008) → 辛未/壬申/癸酉/甲戌/乙亥…（月柱庚午顺排）
- 流年：2004-2128 共 125 年，童限段带小运
- 流月：每年 12 节气月，五虎遁定干（2024 甲辰年寅月丙寅、立春 2/4）
- 当前快照（2026-09-06 注入）：壬申大运 / 丙午流年 / 丙申流月（立秋后）
"""

import datetime

from lunar_python import Solar

from app.domain.chart_builder import build_bazi_chart, chart_to_api_dict
from app.domain.models import Pillar
from app.domain.xipan import (
    _month_ganzhi,
    _wuxing_state,
    _year_ganzhi,
    build_xipan,
    ten_god,
    zizuo,
)

BIRTH = "2004-06-22 08:00"


def _chart_xipan(gender: str = "男") -> dict:
    return chart_to_api_dict(build_bazi_chart(BIRTH, gender, liunian_start_year=2026, liunian_years=1))[
        "xipan"
    ]


def _direct_xipan(birth: str, gender_int: int, direction: str, today: datetime.date) -> dict:
    date_part, _, time_part = birth.partition(" ")
    y, m, d = (int(v) for v in date_part.split("-"))
    h, mi = (int(v) for v in time_part.split(":")) if time_part else (8, 0)
    ec = Solar.fromYmdHms(y, m, d, h, mi, 0).getLunar().getEightChar()
    yun = ec.getYun(gender_int, 1)

    def mk(name: str, gz: str) -> Pillar:
        return Pillar(
            name=name,
            ganzhi=gz,
            gan=gz[0],
            zhi=gz[1],
            gan_wuxing="",
            zhi_wuxing="",
            nayin="",
            xunkong="",
            hidden_stems=[],
            shishen_gan="",
            shishen_zhi=[],
        )

    pillars = [
        mk("年柱", ec.getYear()),
        mk("月柱", ec.getMonth()),
        mk("日柱", ec.getDay()),
        mk("时柱", ec.getTime()),
    ]
    return build_xipan(yun, pillars, gender_int, ec.getDayGan(), direction, today=today)


# ---------- 十神 ----------


def test_ten_god_covers_all_relations_for_ren_day_master():
    expected = {
        "甲": "食神",
        "乙": "伤官",
        "丙": "偏财",
        "丁": "正财",
        "戊": "七杀",
        "己": "正官",
        "庚": "偏印",
        "辛": "正印",
        "壬": "比肩",
        "癸": "劫财",
    }
    for gan, god in expected.items():
        assert ten_god("壬", gan) == god, gan


def test_ten_god_empty_input_returns_empty():
    assert ten_god("", "甲") == ""
    assert ten_god("壬", "") == ""


# ---------- 十二长生 ----------


def test_zizuo_yang_stem_forward():
    assert zizuo("壬", "申") == "长生"
    assert zizuo("壬", "亥") == "临官"
    assert zizuo("壬", "子") == "帝旺"
    assert zizuo("壬", "卯") == "死"


def test_zizuo_yin_stem_backward():
    assert zizuo("丁", "酉") == "长生"
    assert zizuo("丁", "午") == "临官"


# ---------- 干支工具 ----------


def test_year_ganzhi_lichun_cycle():
    assert _year_ganzhi(1984) == "甲子"
    assert _year_ganzhi(2024) == "甲辰"
    assert _year_ganzhi(2026) == "丙午"


def test_month_ganzhi_wuhu_dun():
    assert _month_ganzhi("甲", 0) == "丙寅"
    assert _month_ganzhi("甲", 11) == "丁丑"
    assert _month_ganzhi("庚", 0) == "戊寅"


def test_wuxing_state_wang_xiang_xiu_qiu_si():
    # 午月：火旺、土相、木休、水囚、金死
    assert _wuxing_state("午") == [
        {"name": "火", "state": "旺"},
        {"name": "土", "state": "相"},
        {"name": "木", "state": "休"},
        {"name": "水", "state": "囚"},
        {"name": "金", "state": "死"},
    ]
    # 子月：水旺、木相、金休、土囚、火死
    states = {w["name"]: w["state"] for w in _wuxing_state("子")}
    assert states == {"水": "旺", "木": "相", "金": "休", "土": "囚", "火": "死"}


# ---------- 起运 ----------


def test_qiyun_forward_male_baseline():
    qiyun = _chart_xipan("男")["qiyun"]
    assert qiyun["after"] == "出生后4年11月"
    assert qiyun["startDate"].startswith("2009-05-22")
    assert qiyun["gan"] == "己"  # 2009 己丑年交运
    assert qiyun["jieqi"] == "立夏"
    assert qiyun["daysAfterJieqi"] == 17
    assert qiyun["direction"] == "顺排"


def test_qiyun_reverse_female_baseline():
    qiyun = _chart_xipan("女")["qiyun"]
    assert qiyun["after"] == "出生后5年6月20天"
    assert qiyun["direction"] == "逆排"


# ---------- 大运 ----------


def test_dayun_includes_tongxian_then_forward_sequence():
    dayun = _chart_xipan("男")["dayun"]
    assert len(dayun) == 13  # 童限 + 12 步大运（地支排满一轮）
    assert "".join(d["ganzhi"][1] for d in dayun[1:]) == "未申酉戌亥子丑寅卯辰巳午"
    assert (dayun[0]["index"], dayun[0]["ganzhi"]) == (0, "童限")
    assert (dayun[0]["startYear"], dayun[0]["endYear"]) == (2004, 2008)
    assert dayun[0]["shishen"] == ""
    seq = [(d["index"], d["ganzhi"], d["shishen"]) for d in dayun[1:5]]
    assert seq == [(1, "辛未", "正印"), (2, "壬申", "比肩"), (3, "癸酉", "劫财"), (4, "甲戌", "食神")]
    # 月柱庚午顺排：辛未→壬申→癸酉
    ages = [(d["startAge"], d["endAge"]) for d in dayun[1:4]]
    assert ages == [(6, 15), (16, 25), (26, 35)]


def test_dayun_reverse_female():
    dayun = _chart_xipan("女")["dayun"]
    # 月柱庚午逆排：己巳→戊辰→丁卯
    assert [d["ganzhi"] for d in dayun[1:4]] == ["己巳", "戊辰", "丁卯"]
    assert dayun[1]["shishen"] == "正官"


# ---------- 流年 ----------


def test_liunian_covers_birth_to_last_dayun_with_xiaoyun():
    xp = _chart_xipan("男")
    liunian = xp["liunian"]
    years = [item["year"] for item in liunian]
    assert years == list(range(2004, 2129))  # 封顶到最后一步大运末年
    first = liunian[0]
    assert (first["year"], first["ganzhi"], first["age"], first["dayunIndex"]) == (2004, "甲申", 1, 0)
    assert first["xiaoyun"] == "乙巳"  # 童限段小运
    # 每年所属大运 index 与大运年份区间一致
    for d in xp["dayun"]:
        for ln in liunian:
            if ln["dayunIndex"] == d["index"]:
                assert d["startYear"] <= ln["year"] <= d["endYear"]


def test_liunian_carries_branch_god_and_changsheng():
    """流年横条需要地支十神与星运：与专业排盘软件截图逐项核对（壬日主）。"""
    by_year = {ln["year"]: ln for ln in _chart_xipan("男")["liunian"]}
    # 2025 乙巳：乙=伤官，巳本气丙=偏财，壬主巳地绝
    ln25 = by_year[2025]
    assert (ln25["ganzhi"], ln25["shishen"], ln25["xiaoyun"]) == ("乙巳", "伤官", "丙寅")
    assert (
        ln25["shishenZhi"][0] == "偏财" and ln25["changsheng"] == "绝"
    )  # 巳藏丙戊庚，丙=偏财（软件标「才」）
    assert by_year[2026]["shishenZhi"] == ["正财", "正官"]  # 午藏丁己
    assert by_year[2028]["shishenZhi"][0] == "偏印" and by_year[2028]["changsheng"] == "长生"  # 申=枭/长生


# ---------- 流月 ----------


def test_liuyue_twelve_jieqi_months_per_year():
    liuyue = [m for m in _chart_xipan("男")["liuyue"] if m["year"] == 2024]
    assert len(liuyue) == 12
    assert [m["zhi"] for m in liuyue] == [
        "寅",
        "卯",
        "辰",
        "巳",
        "午",
        "未",
        "申",
        "酉",
        "戌",
        "亥",
        "子",
        "丑",
    ]
    first = liuyue[0]
    assert (first["jieqi"], first["date"], first["ganzhi"]) == ("立春", "2/4", "丙寅")  # 2024 甲辰年五虎遁
    by_zhi = {m["zhi"]: m for m in liuyue}
    assert by_zhi["子"]["jieqi"] == "大雪" and by_zhi["子"]["ganzhi"] == "丙子"
    assert by_zhi["丑"]["jieqi"] == "小寒" and by_zhi["丑"]["date"] == "1/5"  # 小寒落在次年 1 月


def test_liuyue_years_align_with_dayun_end():
    xp = _chart_xipan("男")
    max_dayun_end = max(d["endYear"] for d in xp["dayun"])
    assert xp["liuyue"][0]["year"] == 2004
    assert xp["liuyue"][-1]["year"] == max_dayun_end
    assert len(xp["liuyue"]) == (max_dayun_end - 2004 + 1) * 12


def test_liuyue_carries_branch_god_and_changsheng():
    """流月的地支十神与星运（现按 monthMeta 去重下发），对齐专业排盘软件 2025 截图。"""
    xp = _chart_xipan("男")
    meta = xp["monthMeta"]
    assert len(meta) == 12, "monthMeta 按月支去重，应恰好 12 条"
    assert meta["寅"]["shishenZhi"][0] == "食神" and meta["寅"]["changsheng"] == "病"  # 寅藏甲，壬主寅地病
    assert meta["酉"]["shishenZhi"] == ["正印"] and meta["酉"]["changsheng"] == "沐浴"
    assert meta["辰"]["shishenZhi"][0] == "七杀" and meta["午"]["shishenZhi"] == ["正财", "正官"]
    by_zhi = {m["zhi"]: m for m in xp["liuyue"] if m["year"] == 2025}
    assert (by_zhi["寅"]["jieqi"], by_zhi["寅"]["ganzhi"], by_zhi["寅"]["shishen"]) == ("立春", "戊寅", "七杀")
    assert (by_zhi["酉"]["jieqi"], by_zhi["酉"]["ganzhi"], by_zhi["酉"]["shishen"]) == ("白露", "乙酉", "伤官")


def test_liuyue_shensha_indexed_by_ganzhi():
    """流月行不带神煞；名列表按干支收进 liuyueShensha，说明查 shenshaDict。"""
    xp = _chart_xipan("男")
    assert all("shensha" not in m for m in xp["liuyue"])
    by_gz = xp["liuyueShensha"]
    assert len(by_gz) <= 60, "月干支 60 个一循环，索引不应超过 60 条"
    lookup = xp["shenshaDict"]
    months = [m for m in xp["liuyue"] if m["year"] == 2026]
    names = {n for m in months for n in by_gz[m["ganzhi"]]}
    assert names, "流月应能查到神煞"
    assert all(lookup.get(n) for n in names), "流月出现的每个神煞都要能在 shenshaDict 里取到说明"


# ---------- 当前快照 ----------


def test_current_snapshot_injected_today():
    xp = _direct_xipan(BIRTH, 1, "顺排", datetime.date(2026, 9, 6))
    cur = xp["current"]
    assert cur["year"] == 2026 and cur["age"] == 23  # 丙午年，虚岁 23
    assert cur["dayunIndex"] == 2
    assert (cur["dayun"], cur["dayunLabel"], cur["dayunShishen"]) == ("壬申", "大运", "比肩")
    assert (cur["liunian"], cur["liunianShishen"]) == ("丙午", "偏财")
    assert (cur["liuyue"], cur["liuyueJieqi"]) == ("丙申", "立秋")  # 9/6 已过立秋未到白露
    snap = xp["snapshot"]
    assert [c["name"] for c in snap["columns"]] == ["流年", "大运", "年柱", "月柱", "日柱", "时柱"]
    assert snap["label"] == "元男"
    assert snap["columns"][0]["ganzhi"] == "丙午"
    assert snap["columns"][1]["ganzhi"] == "壬申"


def test_current_before_lichun_uses_previous_year():
    xp = _direct_xipan(BIRTH, 1, "顺排", datetime.date(2026, 2, 1))
    cur = xp["current"]
    assert cur["year"] == 2025 and cur["liunian"] == "乙巳"
    assert cur["liuyue"] == "己丑" and cur["liuyueJieqi"] == "小寒"  # 丑月


def test_current_child_uses_xiaoyun():
    # 2022-03-15 10:00 男：2026 年仍未交大运（8 岁起运），童限期以当年小运代替大运
    xp = _direct_xipan("2022-03-15 10:00", 1, "顺排", datetime.date(2026, 9, 6))
    cur = xp["current"]
    assert cur["dayunIndex"] == 0
    assert (cur["dayun"], cur["dayunLabel"]) == ("庚戌", "小运")
    assert xp["snapshot"]["columns"][1]["name"] == "小运"
    assert xp["snapshot"]["columns"][1]["ganzhi"] == "庚戌"


# ---------- 月令旺衰 / 人元司令 ----------


def test_wuxing_state_in_payload():
    xp = _chart_xipan("男")  # 午月
    assert xp["wuxingState"] == [
        {"name": "火", "state": "旺"},
        {"name": "土", "state": "相"},
        {"name": "木", "state": "休"},
        {"name": "水", "state": "囚"},
        {"name": "金", "state": "死"},
    ]


def test_siling_fenye_baseline():
    siling = _chart_xipan("男")["siling"]
    # 6-22 出生，芒种(6/5)后 18 天；午月分野 丙10/己9/丁11 → 第 11-19 天己司令
    assert siling == {"stem": "己", "detail": "芒种后18天，己司令"}


# ---------- 集成 ----------


def test_chart_api_payload_contains_xipan():
    payload = chart_to_api_dict(build_bazi_chart(BIRTH, "男", liunian_start_year=2026, liunian_years=1))
    xipan = payload["xipan"]
    assert set(xipan) == {
        "qiyun",
        "current",
        "dayun",
        "liunian",
        "liuyue",
        "liuyueShensha",
        "liunianShensha",
        "shenshaDict",
        "monthMeta",
        "ganzhiMeta",
        "snapshot",
        "relations",
        "wuxingState",
        "siling",
        "note",
    }
    assert payload["pillars"][1]["ganzhi"] == "庚午"


def test_liunian_shensha_covers_every_dayun():
    """流年神煞按干支索引：切到任何一步大运的十年都取得到（旧实现只覆盖当前大运）。"""
    xp = _chart_xipan("男")
    index = xp["liunianShensha"]
    assert len(index) <= 60, "流年神煞按干支去重，最多 60 条"
    for ln in xp["liunian"]:
        assert ln["ganzhi"] in index, f"{ln['year']} 的流年干支 {ln['ganzhi']} 查不到神煞"
    # 非当前大运的十年也要能算出神煞（此前是空的）
    other = [ln for ln in xp["liunian"] if ln["dayunIndex"] != xp["current"]["dayunIndex"]]
    assert any(index[ln["ganzhi"]] for ln in other), "其他大运的流年应当也能算出神煞"


def test_ganzhi_meta_matches_snapshot_columns():
    """ganzhiMeta 必须与后端 snapshot 已算出的大运/流年列一致——前端靠它重拼任意选择的表。"""
    xp = _chart_xipan("男")
    meta = xp["ganzhiMeta"]
    assert len(meta) == 60
    fields = ("shishen", "gan", "zhi", "hiddenStems", "shishenZhi", "changsheng", "zizuo", "xunkong", "nayin")
    for col in xp["snapshot"]["columns"]:
        if col["name"] not in ("大运", "流年"):
            continue
        entry = meta[col["ganzhi"]]
        assert {f: entry[f] for f in fields} == {f: col[f] for f in fields}, col["name"]


def test_payload_carries_fields_frontend_selection_depends_on():
    """契约：前端「选中态 + 去重查表」依赖的字段必须都在。

    这类字段一旦缺失，表现不是报错而是界面静默显示错误内容（例如 chart.dayun 少了 index
    会让折叠态匹配不到任何一项、退回显示全部大运），所以在此钉死。
    """
    payload = chart_to_api_dict(build_bazi_chart(BIRTH, "男", liunian_start_year=2026, liunian_years=1))
    xp = payload["xipan"]

    for d in payload["dayun"]:
        assert isinstance(d.get("index"), int), "chart.dayun 必须带 index（前端 isSameDayun 的首选依据）"
        assert d.get("ganzhi") and d.get("startYear") is not None
    # chart.dayun 不含童限，与 xipan.dayun 的 index>0 段必须逐项对齐
    assert [(d["index"], d["ganzhi"], d["startYear"]) for d in payload["dayun"]] == [
        (d["index"], d["ganzhi"], d["startYear"]) for d in xp["dayun"] if d["index"] > 0
    ]
    for l in xp["liunian"]:
        assert isinstance(l.get("dayunIndex"), int) and l.get("year") and l.get("ganzhi")
    for m in xp["liuyue"]:
        assert m.get("year") and m.get("zhi") and m.get("ganzhi")

    # 逐行出现的键，必须都能在去重附表里查到
    assert {m["ganzhi"] for m in xp["liuyue"]} <= set(xp["liuyueShensha"])
    assert {l["ganzhi"] for l in xp["liunian"]} <= set(xp["liunianShensha"])
    assert {m["zhi"] for m in xp["liuyue"]} <= set(xp["monthMeta"])
    used_gz = {l["ganzhi"] for l in xp["liunian"]} | {d["ganzhi"] for d in xp["dayun"] if d["index"] > 0}
    assert used_gz <= set(xp["ganzhiMeta"])
    # 神煞名都要能在 shenshaDict 里取到说明（流月/流年两处查表共用）
    names = {n for lst in xp["liuyueShensha"].values() for n in lst}
    names |= {n for lst in xp["liunianShensha"].values() for n in lst}
    assert names <= set(xp["shenshaDict"])


def test_relations_match_professional_software():
    """岁运/原局分析六栏，逐项对齐专业排盘软件截图（2026-09-07 丁酉流月，白露节气当日）。"""
    r = _chart_xipan("男")["relations"]
    assert r["suiyun"]["label"] == "壬申 · 丙午 · 丁酉"
    assert "丙庚相克" in r["suiyun"]["gan"]
    assert "壬丙相克" in r["suiyun"]["gan"]
    assert len(r["suiyun"]["gan"]) >= 2
    assert r["yuanju"]["gan"] == ["庚甲相克"]
    assert r["yuanju"]["zhi"] == ["申辰拱合子"]
    assert r["yuanju"]["zhu"] == ["甲申截脚", "庚午截脚", "甲辰盖头"]
