import json
from pathlib import Path

import pytest

from app.domain.bazi_engine import (
    Pillar,
    _classify_strength,
    _compute_shensha,
    _detect_special_pattern,
    build_bazi_chart,
    chart_to_api_dict,
)
from app.tools.bazi import (
    bazi_analysis,
    bazi_chart,
    bazi_dayun,
    bazi_full,
    bazi_hehun,
    bazi_liunian,
    bazi_liuyue,
    lunar_to_solar,
)


MALE = "\u7537"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "bazi_cases.json"


def _load_cases():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_structured_chart_matches_golden_cases(case):
    chart = build_bazi_chart(
        case["birth_time"],
        case["gender"],
        dayun_count=12,
        liunian_start_year=case["liunian_start_year"],
        liunian_years=case["liunian_years"],
    )
    expected = case["expected"]

    assert [p.ganzhi for p in chart.pillars] == expected["pillars"]
    assert {k: chart.start_yun[k] for k in expected["start_yun"]} == expected["start_yun"]
    assert [
        [d.ganzhi, d.start_year, d.end_year, d.start_age, d.end_age]
        for d in chart.dayun[:len(expected["dayun"])]
    ] == expected["dayun"]
    assert [[item.year, item.ganzhi, item.age, item.dayun_ganzhi] for item in chart.liunian] == expected["liunian"]
    for snippet in expected["warning_contains"]:
        assert any(snippet in warning for warning in chart.warnings)


def test_liunian_uses_lichun_and_maps_active_dayun():
    chart = build_bazi_chart(
        "1990-05-20 14:30",
        MALE,
        dayun_count=8,
        liunian_start_year=2025,
        liunian_years=3,
    )

    assert [(item.year, item.ganzhi, item.age, item.dayun_ganzhi) for item in chart.liunian] == [
        (2025, "乙巳", 36, "乙酉"),
        (2026, "丙午", 37, "乙酉"),
        (2027, "丁未", 38, "乙酉"),
    ]


def test_api_payload_is_structured_without_text_parsing():
    chart = build_bazi_chart("1990-05-20 14:30", MALE, liunian_start_year=2026, liunian_years=1)
    payload = chart_to_api_dict(chart)

    assert payload["pillars"][0]["name"] == "年柱"
    assert payload["pillars"][0]["ganzhi"] == "庚午"
    assert payload["analysis"]["day_master"] == "乙"
    assert payload["analysis"]["tenGods"]
    assert "patternHint" in payload["analysis"]
    assert "adjustment" in payload["analysis"]
    assert payload["analysis"]["confidence"] > 0
    assert payload["liunian"][0]["ganzhi"] == "丙午"
    assert payload["liunian"][0]["dayun"] == "乙酉"


def test_legacy_tools_still_return_readable_text():
    chart_text = bazi_chart.invoke({"birth_time": "1990-05-20 14:30", "gender": MALE})
    analysis_text = bazi_analysis.invoke({"birth_time": "1990-05-20 14:30", "gender": MALE, "question": "事业"})
    dayun_text = bazi_dayun.invoke({"birth_time": "1990-05-20 14:30", "gender": MALE, "count": 4})
    liunian_text = bazi_liunian.invoke({"birth_time": "1990-05-20 14:30", "gender": MALE, "years": 1})

    assert "年柱: 庚午" in chart_text
    assert "【五行权重】" in analysis_text
    assert "【结构判断】" in analysis_text
    assert "壬午 | 1995-2004 | 6-15岁" in dayun_text
    assert "所在大运" in liunian_text


# ---- 农历/时辰/节日输入支持 ----
# 1990-05-20 14:30（公历）≡ 农历1990年四月廿六 14:30，用于交叉验证
SOLAR_BIRTH = "1990-05-20 14:30"
LUNAR_BIRTH = "农历1990年四月廿六 14:30"


def test_lunar_to_solar_festival():
    """节日（端午节）转公历。2004年端午节 = 2004-06-22。"""
    r = lunar_to_solar.invoke({"query": "2004年端午节 辰时"})
    assert "2004" in r and "06" in r


def test_lunar_to_solar_cn_day():
    """农历中文日（廿六）转公历。"""
    r = lunar_to_solar.invoke({"query": "农历1990年四月廿六 8:00"})
    assert "1990" in r


def test_bazi_chart_lunar_matches_solar():
    """农历输入与等价公历输入应产出完全相同的排盘结果。"""
    chart_solar = bazi_chart.invoke({"birth_time": SOLAR_BIRTH, "gender": MALE})
    chart_lunar = bazi_chart.invoke({"birth_time": LUNAR_BIRTH, "gender": MALE})
    assert chart_lunar == chart_solar
    assert "庚午" in chart_lunar


def test_bazi_chart_solar_with_zhi_hour():
    """公历+传统时辰输入（无 HH:MM）。"""
    text = bazi_chart.invoke({"birth_time": "1990-05-20 辰时", "gender": MALE})
    assert "庚午" in text


def test_all_bazi_tools_accept_lunar():
    """所有 bazi_* 工具入口均应接受农历输入（回归 _normalize_birth_time 覆盖）。"""
    analysis = bazi_analysis.invoke({"birth_time": LUNAR_BIRTH, "gender": MALE})
    assert "【五行权重】" in analysis

    dayun = bazi_dayun.invoke({"birth_time": LUNAR_BIRTH, "gender": MALE})
    assert "失败" not in dayun

    liunian = bazi_liunian.invoke({"birth_time": LUNAR_BIRTH, "gender": MALE, "years": 1})
    assert "失败" not in liunian

    # liuyue/hehun 曾因 _parse_birth 未定义而 NameError，重点回归
    liuyue = bazi_liuyue.invoke({"birth_time": LUNAR_BIRTH, "gender": MALE})
    assert "流月" in liuyue and "失败" not in liuyue


def _make_pillar(name: str, ganzhi: str, gan: str, zhi: str, hidden: list[str]) -> Pillar:
    return Pillar(
        name=name,
        ganzhi=ganzhi,
        gan=gan,
        zhi=zhi,
        gan_wuxing="",
        zhi_wuxing="",
        nayin="",
        xunkong="",
        hidden_stems=hidden,
    )


def test_yuede_guiren_only_checks_stems_not_hidden():
    """回归：月德贵人只查四柱天干，不查藏干。

    Bug 现场：癸亥×4 八字，月支亥 → 月德应为甲；但每个亥的藏干都含甲，
    原代码 `p.gan == c or any(hs == c for hs in p.hidden_stems)` 会让四柱
    全部误报"月德贵人"。

    口径：对齐 07_神煞初探.md §3 ——「亥卯未月生者见甲，查找方式：以月支查四柱干支」。
    天德贵人仍保留藏干检测（自带"藏干，力弱待引"标记），不在本测试范围。
    """
    pillars = [
        _make_pillar("年柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"]),
        _make_pillar("月柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"]),
        _make_pillar("日柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"]),
        _make_pillar("时柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"]),
    ]
    ss = _compute_shensha(pillars)
    yuede = [s for s in ss if s["name"] == "月德贵人"]

    # 修复前：4 个（每柱都被误报）
    # 修复后：0 个（四柱天干无甲）
    assert yuede == [], (
        f"月德贵人不应在藏干甲上误报，实际命中: {[s['pillar'] for s in yuede]}"
    )
    for s in ss:
        assert "见甲" not in s["description"] or "藏" in s["description"] or s["name"] != "月德贵人"


def test_yuede_guiren_detects_when_stem_present():
    """正向回归：天干真的出现甲时，月德贵人仍需被正确识别（亥月+甲天干）。"""
    pillars = [
        _make_pillar("年柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"]),
        _make_pillar("月柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"]),
        _make_pillar("日柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"]),
        _make_pillar("时柱", "甲寅", "甲", "寅", ["甲", "丙", "戊"]),
    ]
    ss = _compute_shensha(pillars)
    yuede = [s for s in ss if s["name"] == "月德贵人"]

    # 时柱天干为甲，应被识别；其余三柱天干癸不应触发。
    assert len(yuede) == 1, f"应只在时柱命中一次，实际: {yuede}"
    assert yuede[0]["pillar"] == "时柱"
    assert "甲" in yuede[0]["description"]
    assert "藏" not in yuede[0]["description"], "天干直接透出，不应使用藏干话术"


def _make_pillar_with_nayin(name: str, ganzhi: str, gan: str, zhi: str,
                            hidden: list[str], nayin: str) -> Pillar:
    """支持设置 nayin 的 Pillar 工厂（用于学堂/词馆之类的纳音相关神煞）。"""
    return Pillar(
        name=name, ganzhi=ganzhi, gan=gan, zhi=zhi,
        gan_wuxing="", zhi_wuxing="", nayin=nayin, xunkong="",
        hidden_stems=hidden,
    )


def test_zheng_ciguan_supersedes_ciguan_when_both_match():
    """回归：同柱命中正词馆时，不再重复报词馆（精优于粗，留精去粗）。

    Bug 现场：癸亥×4 八字，年柱纳音=水。
    - 水命词馆地支=亥 → 4 个柱子都会匹配（仅地支维度）
    - 水命正词馆=癸亥 → 4 个柱子都会匹配（干支完全匹配）
    - 修复前：月/日/时三柱都同时出现"词馆"+"正词馆"两张标签，重复。

    口径：对齐 07_神煞初探.md §15-16，正词馆是词馆的精确位。
    """
    pillars = [
        # 年柱不论藏干，纳音"大海水"取末字符"水"作年纳音五行
        _make_pillar_with_nayin("年柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"], "大海水"),
        _make_pillar_with_nayin("月柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"], "大海水"),
        _make_pillar_with_nayin("日柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"], "大海水"),
        _make_pillar_with_nayin("时柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"], "大海水"),
    ]
    ss = _compute_shensha(pillars)
    ciguan = [s for s in ss if s["name"] == "词馆"]
    zheng_ciguan = [s for s in ss if s["name"] == "正词馆"]

    # 修复前：词馆=月/日/时柱、正词馆=月/日/时柱（重复 6 张）
    # 修复后：词馆=[]、正词馆=月/日/时柱（互斥，仅 3 张）
    assert ciguan == [], (
        f"同柱命中正词馆时应不再报词馆，实际词馆命中: {ciguan}"
    )
    zheng_pillars = [s["pillar"] for s in zheng_ciguan]
    assert sorted(zheng_pillars) == ["日柱", "月柱", "时柱"], (
        f"正词馆期望落在月/日/时三柱，实际: {zheng_pillars}"
    )


def test_ciguan_fires_when_only_branch_matches():
    """正向回归：当某柱仅地支命中词馆（而非干支完全匹配正词馆）时，词馆仍应正常触发。"""
    pillars = [
        _make_pillar_with_nayin("年柱", "癸亥", "癸", "亥", ["壬", "甲", "戊"], "大海水"),
        _make_pillar_with_nayin("月柱", "戊申", "戊", "申", ["戊", "庚", "壬"], "大海水"),
        _make_pillar_with_nayin("日柱", "己亥", "己", "亥", ["己", "甲", "壬"], "大海水"),
        _make_pillar_with_nayin("时柱", "甲寅", "甲", "寅", ["甲", "丙", "戊"], "大海水"),
    ]
    # 年纳音=水：
    #   词馆地支=亥、申     → 月柱(申)词馆、日柱(亥)词馆、时柱? 不对，时柱寅不在集合里
    #   正词馆=癸亥
    #   实际：月柱 → 词馆(申)；日柱 → 词馆(亥)；时柱 → 学堂(寅, 水命学堂=申 不命中 → 不出)
    ss = _compute_shensha(pillars)
    ciguan = sorted([s["pillar"] for s in ss if s["name"] == "词馆"])
    zheng = sorted([s["pillar"] for s in ss if s["name"] == "正词馆"])
    # 词馆应同时覆盖到月柱(申)和日柱(亥)
    assert ciguan == ["日柱", "月柱"], f"词馆应仅月柱+日柱，实际: {ciguan}"
    assert zheng == [], f"无癸亥柱，正词馆应为空，实际: {zheng}"


def test_xueren_includes_month_pillar_when_self_mapping():
    """回归：血刃的 XUE_REN 表中"亥月→亥"是自映射，月柱必须纳入扫描。

    Bug 现场：癸亥×4（1983 癸亥年、十月=亥月、亥时）排盘 → 月柱地支=亥，
    但原代码 `if i == 1: continue` 跳过了月柱，导致月柱缺血刃。

    口径：对齐 07_神煞初探.md §38 —— 查找方式 = 「以月支查四柱干支」（含月柱自身）。
    """
    pillars = [
        _make_pillar("年柱", "癸亥", "癸", "亥", ["壬", "甲"]),
        _make_pillar("月柱", "癸亥", "癸", "亥", ["壬", "甲"]),
        _make_pillar("日柱", "乙卯", "乙", "卯", ["乙"]),
        _make_pillar("时柱", "癸亥", "癸", "亥", ["壬", "甲"]),
    ]
    # 月支取自月柱地支 = 亥；这里直接传元组，可绕过 engines 内部依赖
    ss = _compute_shensha(pillars, gender_int=1)
    xueren = sorted([s["pillar"] for s in ss if s["name"] == "血刃"])

    # 亥月在 XUE_REN 里是自映射（亥→亥），月柱本身就是命中点
    # 修复前：['年柱', '时柱']（漏掉月柱）
    # 修复后：['年柱', '月柱', '时柱']（月柱一并计入）
    assert xueren == ["年柱", "月柱", "时柱"], (
        f"亥月见亥，月柱地支=亥 必须命中血刃，实际: {xueren}"
    )


def test_xueren_other_months_unaffected():
    """正向回归：非自映射的 11 个月份里"月柱地支 ≠ 目标"，移除 skip 不应产生任何变化。"""
    # 取寅月构造一次：寅月 → 血刃=丑；
    # 月柱=寅（≠丑），所以新增的"扫月柱"不会误命中
    pillars = [
        _make_pillar("年柱", "壬午", "壬", "午", ["丁", "己"]),
        _make_pillar("月柱", "壬寅", "壬", "寅", ["甲", "丙", "戊"]),
        _make_pillar("日柱", "癸卯", "癸", "卯", ["乙"]),
        _make_pillar("时柱", "癸丑", "癸", "丑", ["己", "癸", "辛"]),
    ]
    ss = _compute_shensha(pillars, gender_int=1)
    xueren = sorted([s["pillar"] for s in ss if s["name"] == "血刃"])

    # 寅月 → 血刃=丑；命盘中只有时柱地支丑 → 时柱命中
    assert xueren == ["时柱"], f"寅月血刃仅时柱丑命中，实际: {xueren}"


def test_bazi_tools_accept_lunar_hehun_and_full():
    """liuyue/hehun/bazi_full 工具入口回归（其余工具入口已在 test_all_bazi_tools_accept_lunar 中）。"""
    hehun = bazi_hehun.invoke({
        "birth_time_a": LUNAR_BIRTH,
        "gender_a": MALE,
        "birth_time_b": "农历1992年六月初八 10:00",
        "gender_b": "女",
    })
    assert "合婚" in hehun and "失败" not in hehun

    full = bazi_full.invoke({"birth_time": LUNAR_BIRTH, "gender": MALE})
    assert "庚午" in full and "失败" not in full


def test_lunar_input_missing_year_errors_gracefully():
    """农历输入缺年份时应优雅报错，而非抛异常。"""
    bad = bazi_chart.invoke({"birth_time": "农历五月初五", "gender": MALE})
    assert "失败" in bad or "错误" in bad


# —— 日主强弱五档扩展（方案A）回归 ——————————————————————————————
# 癸亥×4 的加权分：水=12.02、木=1.38，score = 12.02 - 1.38*0.55 ≈ 11.26。
# 原三档逻辑只会标成「偏强」，丢失专旺信息且用神方向错误（泄耗而非顺势）。
# 五档逻辑应标成「极旺（候选专旺格）」，用神走顺势。
_WX = "水"
_RES, _SAME, _OUT, _WEALTH, _OFF = "金", "水", "木", "火", "土"


def test_classify_strength_five_levels_buckets():
    """_classify_strength 五档分档阈值正确。"""
    cases = [
        (11.26, "极旺"), (8.0, "极旺"), (7.0, "极旺"),
        (3.0, "偏旺"), (2.2, "偏旺"),
        (0.0, "中和"),
        (-1.2, "偏弱"), (-3.0, "偏弱"),
        (-7.0, "极弱"), (-8.0, "极弱"),
    ]
    for score, expect in cases:
        strength, _ = _classify_strength(score, _WX, _RES, _SAME, _OUT, _WEALTH, _OFF)
        assert strength == expect, (score, strength, expect)


def test_classify_strength_guihai_x4_is_extreme_prosperity():
    """癸亥×4（score≈11.26）必须归为极旺，而非笼统的偏强。"""
    strength, hint = _classify_strength(11.26, _WX, _RES, _SAME, _OUT, _WEALTH, _OFF)
    assert strength == "极旺"
    assert "候选专旺" in hint
    # 极旺用神走顺势，不应给出偏旺的「泄耗制衡」。
    assert "顺其旺势" in hint
    assert "泄耗制衡" not in hint


def test_classify_strength_extreme_hint_direction_differs():
    """极旺/极弱的用神方向（顺势）与偏旺/偏弱（制衡/扶助）相反。"""
    _, ext_hint = _classify_strength(9.0, _WX, _RES, _SAME, _OUT, _WEALTH, _OFF)
    _, norm_hint = _classify_strength(3.0, _WX, _RES, _SAME, _OUT, _WEALTH, _OFF)
    assert "顺其旺势" in ext_hint
    assert "泄耗制衡" in norm_hint
    assert "顺其旺势" not in norm_hint

    _, weak_hint = _classify_strength(-9.0, _WX, _RES, _SAME, _OUT, _WEALTH, _OFF)
    assert "候选从格" in weak_hint
    assert "顺势相从" in weak_hint


# —— 特殊格局（方案B）回归 ——————————————————————————————
# 五行关系（日主=水）：resource=金(印) / same=水(比劫) / output=木(食伤) /
# wealth=火(财) / officer=土(官杀)。pillars 用 (gan, zhi) 元组即可驱动检测。
_SP = [("癸", "亥"), ("癸", "亥"), ("癸", "亥"), ("癸", "亥")]


def test_detect_special_pattern_guihai_x4_zhuanwang_runcan():
    """癸亥×4（score≈11.26）应判为专旺格·润下格，而非仅标极旺。"""
    sp = _detect_special_pattern(
        _SP, {"金": 0.0, "木": 1.38, "水": 12.02, "火": 0.0, "土": 0.0},
        "水", "癸", 11.26, "金", "木", "火", "土",
    )
    assert sp["is_special"] is True
    assert sp["kind"] == "专旺"
    assert sp["label"] == "润下格"
    assert "顺其旺势" in sp["useful_hint"]


def test_detect_special_pattern_cong_subtypes():
    """极弱候选应正确区分从杀/从财/从儿/从势（均真从：无根无印）。"""
    cong = [("丙", "午"), ("丙", "午"), ("丙", "午"), ("丙", "午")]
    cases = [
        ({"金": 0.0, "木": 0.5, "水": 0.2, "火": 0.5, "土": 10.0}, -8.43, "从杀格"),
        ({"金": 0.0, "木": 0.5, "水": 0.2, "火": 10.0, "土": 0.5}, -7.48, "从财格"),
        ({"金": 0.0, "木": 12.0, "水": 0.2, "火": 0.5, "土": 0.5}, -7.15, "从儿格"),
        ({"金": 0.0, "木": 0.5, "水": 0.2, "火": 6.0, "土": 8.0}, -10.68, "从势格"),
    ]
    for weighted, score, expect in cases:
        sp = _detect_special_pattern(cong, weighted, "水", "壬", score, "金", "木", "火", "土")
        assert sp["is_special"] is True, (weighted, sp)
        assert sp["kind"] == "从格", (weighted, sp)
        assert sp["label"] == expect, (weighted, sp["label"], expect)


def test_detect_special_pattern_fake_cong_has_root():
    """日主坐禄（亥）有根 → 假从/不从，不判从格（沿用 A 基础档）。"""
    fake_root = [("壬", "亥"), ("壬", "亥"), ("壬", "亥"), ("壬", "亥")]
    sp = _detect_special_pattern(
        fake_root, {"金": 0.0, "木": 0.5, "水": 0.2, "火": 0.5, "土": 10.0},
        "水", "壬", -8.43, "金", "木", "火", "土",
    )
    assert sp["is_special"] is False
    assert sp["kind"] == ""
    assert sp["label"] == ""

