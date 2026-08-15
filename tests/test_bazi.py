import json
from pathlib import Path

import pytest

from app.domain.bazi_engine import (
    Pillar,
    _branch_combinations,
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
    # 大运行格式含十神标注：{干支}({十神}) | 年份区间 | 岁数
    assert "壬午(正印) | 1995-2004 | 6-15岁" in dayun_text
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
    assert set(zheng_pillars) == {"日柱", "月柱", "时柱"}, (
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
    assert set(xueren) == {"年柱", "月柱", "时柱"}, (
        f"亥月见亥，月柱地支=亥 必须命中血刃，实际: {xueren}"
    )


def test_tianchu_guiren_dict_fixed_bing_ding_not_chen_you():
    """回归：天厨贵人字典里「丙」「丁」两个值修正。

    原理：天厨 = 食神建禄 —— X 的食神 Y，Y 禄地支即 X 之天厨。
    丙的食神=戊，戊禄在巳 → 丙人天厨=巳
    丁的食神=己，己禄在午 → 丁人天厨=午

    Bug 现场：用户反馈「丙日柱不应该出现天厨贵人」。
    命盘：壬子·壬子·丙申·壬辰。丙日干按口径查巳，盘中无巳，应不命中。
    引擎原字典「丙: 申」是误把古诀"甲巳乙午丙戊申"断句为"丙戊共申"，
    实际上"丙"独占巳，对齐 bazitai/bazipai/bazitang/iwzbz 等主流口径。

    同时验证：丁天厨应为午（原字典错写"酉"），丁人见午才命中。
    """
    # --- 用户报告的盘：丙日干，盘中无巳 → 应 0 个 ---
    pillars_user = [
        _make_pillar("年柱", "壬子", "壬", "子", ["癸"]),
        _make_pillar("月柱", "壬子", "壬", "子", ["癸"]),
        _make_pillar("日柱", "丙申", "丙", "申", ["庚", "壬", "戊"]),
        _make_pillar("时柱", "壬辰", "壬", "辰", ["戊", "乙", "癸"]),
    ]
    ss_user = _compute_shensha(pillars_user)
    tc_user = [s for s in ss_user if s["name"] == "天厨贵人"]
    # 修复前：会在日柱命中（丙: 申 = 日支申）
    # 修复后：0 个（丙: 巳 = 四支子子申辰无巳）
    assert tc_user == [], (
        f"丙日干·盘中无巳→天厨贵人应 0 个；实际命中: "
        f"{[(s['pillar'], s['description'][:50]) for s in tc_user]}"
    )

    # --- 丙见巳：应命中日柱 ---
    pillars_bing_si = [
        _make_pillar("年柱", "甲辰", "甲", "辰", ["戊", "乙", "癸"]),
        _make_pillar("月柱", "丙寅", "丙", "寅", ["甲", "丙", "戊"]),
        _make_pillar("日柱", "丙巳", "丙", "巳", ["庚", "丙", "戊"]),
        _make_pillar("时柱", "壬子", "壬", "子", ["癸"]),
    ]
    ss_bing = _compute_shensha(pillars_bing_si)
    tc_bing = sorted([s["pillar"] for s in ss_bing if s["name"] == "天厨贵人"])
    # 日柱地支=巳 → 丙人见巳命中（年干甲也配巳，去重后只标日柱 1 次）
    assert tc_bing == ["日柱"], (
        f"丙巳日柱·丙人见巳→应在日柱命中；实际: {tc_bing}"
    )

    # --- 丁见午：原字典"丁: 酉"会让丁日柱见午不命中，必须改为午 ---
    pillars_ding_wu = [
        _make_pillar("年柱", "丁丑", "丁", "丑", ["己", "癸", "辛"]),
        _make_pillar("月柱", "甲辰", "甲", "辰", ["戊", "乙", "癸"]),
        _make_pillar("日柱", "丁未", "丁", "未", ["己", "丁", "乙"]),
        _make_pillar("时柱", "丙午", "丙", "午", ["丁", "己"]),
    ]
    ss_ding = _compute_shensha(pillars_ding_wu)
    tc_ding = sorted([s["pillar"] for s in ss_ding if s["name"] == "天厨贵人"])
    # 年干丁 + 日干丁 都配午，时支=午→时柱命中；丙时干配巳，不命中任何柱（时支=午 ≠ 巳）
    # 因 key 去重，命中只标时柱 1 次
    assert tc_ding == ["时柱"], (
        f"丁人见午 + 丙时干（支午非巳）→ 应仅时柱命中；实际: {tc_ding}"
    )


def test_sanqi_guiren_renzhong_hits_on_mdh_match():
    """三奇贵人：人中三奇 壬-癸-辛，月/日/时三柱天干依次匹配时命中。

    实例引自 07_神煞初探.md §10：2025/06/13 18:00（乙巳·壬午·癸丑·辛酉），
    月柱壬、日柱癸、时柱辛 → 人中三奇，日柱命中。
    """
    pillars = [
        _make_pillar("年柱", "乙巳", "乙", "巳", ["丙", "庚", "戊"]),
        _make_pillar("月柱", "壬午", "壬", "午", ["丁", "己"]),
        _make_pillar("日柱", "癸丑", "癸", "丑", ["己", "癸", "辛"]),
        _make_pillar("时柱", "辛酉", "辛", "酉", ["辛"]),
    ]
    ss = _compute_shensha(pillars)
    sanqi = [s for s in ss if s["name"] == "三奇贵人"]
    assert len(sanqi) == 1 and sanqi[0]["pillar"] == "日柱", (
        f"月/日/时天干依次 壬-癸-辛 → 应日柱命中 1 次；实际: "
        f"{[(s['pillar'], s['description'][:80]) for s in sanqi]}"
    )
    assert "人中三奇" in sanqi[0]["description"], (
        f"人中三奇（壬癸辛）的描述文案应注明「人中三奇」；实际: {sanqi[0]['description']}"
    )


def test_sanqi_guiren_tianshang_dingxi_hits():
    """天上三奇 甲-戊-庚：月甲/日戊/时庚 时命中。"""
    pillars = [
        _make_pillar("年柱", "丙寅", "丙", "寅", ["甲", "丙", "戊"]),
        _make_pillar("月柱", "甲辰", "甲", "辰", ["戊", "乙", "癸"]),
        _make_pillar("日柱", "戊申", "戊", "申", ["庚", "壬", "戊"]),
        _make_pillar("时柱", "庚子", "庚", "子", ["癸"]),
    ]
    ss = _compute_shensha(pillars)
    sanqi = [s for s in ss if s["name"] == "三奇贵人"]
    assert len(sanqi) == 1 and sanqi[0]["pillar"] == "日柱", (
        f"月/日/时天干依次 甲-戊-庚 → 应日柱命中；实际: "
        f"{[(s['pillar'], s['description'][:80]) for s in sanqi]}"
    )
    assert "天上三奇" in sanqi[0]["description"]


def test_sanqi_guiren_dixia_bingding_hits():
    """地下三奇 乙-丙-丁：月乙/日丙/时丁 时命中。"""
    pillars = [
        _make_pillar("年柱", "甲寅", "甲", "寅", ["甲", "丙", "戊"]),
        _make_pillar("月柱", "乙卯", "乙", "卯", ["乙"]),
        _make_pillar("日柱", "丙辰", "丙", "辰", ["戊", "乙", "癸"]),
        _make_pillar("时柱", "丁巳", "丁", "巳", ["庚", "丙", "戊"]),
    ]
    ss = _compute_shensha(pillars)
    sanqi = [s for s in ss if s["name"] == "三奇贵人"]
    assert len(sanqi) == 1 and sanqi[0]["pillar"] == "日柱", (
        f"月/日/时天干依次 乙-丙-丁 → 应日柱命中；实际: {[(s['pillar'], s['description'][:80]) for s in sanqi]}"
    )
    assert "地下三奇" in sanqi[0]["description"]


def test_sanqi_guiren_requires_adjacent_pillars():
    """回归：三奇必须落在「相连」三柱内——年甲·月壬·日戊·时庚 不命中。

    用户口径：只认 年-月-日 或 月-日-时 两个连续窗口。此盘甲戊庚虽在四柱中齐备，
    但分布为年·日·时（月柱夹壬，隔断），不相连 → 不算三奇。
    """
    pillars = [
        _make_pillar("年柱", "甲午", "甲", "午", ["丁", "己"]),
        _make_pillar("月柱", "壬申", "壬", "申", ["庚", "壬", "戊"]),
        _make_pillar("日柱", "戊子", "戊", "子", ["癸"]),
        _make_pillar("时柱", "庚辰", "庚", "辰", ["戊", "乙", "癸"]),
    ]
    ss = _compute_shensha(pillars)
    sanqi = [s for s in ss if s["name"] == "三奇贵人"]
    assert sanqi == [], (
        f"甲戊庚分布在 年·日·时（月柱夹壬隔断）→ 不相连，应不命中；实际: "
        f"{[(s['pillar'], s['description'][:80]) for s in sanqi]}"
    )


def test_sanqi_guiren_permutation_does_not_hit():
    """回归：逆序/乱序不算三奇。《渊海子平》要求天干顺次连续、不可颠倒。

    年戊·月庚·日甲（年-月-日 窗口为 戊-庚-甲，非 甲-戊-庚 顺次）→ 不命中。
    """
    pillars = [
        _make_pillar("年柱", "戊子", "戊", "子", ["癸"]),
        _make_pillar("月柱", "庚寅", "庚", "寅", ["甲", "丙", "戊"]),
        _make_pillar("日柱", "甲辰", "甲", "辰", ["戊", "乙", "癸"]),
        _make_pillar("时柱", "丙午", "丙", "午", ["丁", "己"]),
    ]
    ss = _compute_shensha(pillars)
    sanqi = [s for s in ss if s["name"] == "三奇贵人"]
    assert sanqi == [], (
        f"戊-庚-甲 逆序排列 → 按《渊海子平》不顺次连续，应不命中；实际: "
        f"{[(s['pillar'], s['description'][:80]) for s in sanqi]}"
    )


def test_sanqi_guiren_tianshang_nian_yue_ri_in_order_hits():
    """天上三奇 甲→戊→庚，顺次落 年甲·月戊·日庚（年-月-日窗口精确匹配）→ 命中。"""
    pillars = [
        _make_pillar("年柱", "甲子", "甲", "子", ["癸"]),
        _make_pillar("月柱", "戊辰", "戊", "辰", ["戊", "乙", "癸"]),
        _make_pillar("日柱", "庚申", "庚", "申", ["庚", "壬", "戊"]),
        _make_pillar("时柱", "丙子", "丙", "子", ["癸"]),
    ]
    ss = _compute_shensha(pillars)
    sanqi = [s for s in ss if s["name"] == "三奇贵人"]
    assert len(sanqi) == 1 and sanqi[0]["pillar"] == "日柱", (
        f"年甲·月戊·日庚 顺次天上三奇 → 应日柱命中；实际: "
        f"{[(s['pillar'], s['description'][:80]) for s in sanqi]}"
    )
    assert "天上三奇" in sanqi[0]["description"]


def test_sanqi_guiren_requires_day_gan_to_belong_to_triple():
    """回归：日柱天干不在 triple 内时不应命中（两个窗口都含日柱，故日干不合即全灭）。

    年甲·月戊·日癸·时庚：年月日={甲,戊,癸}、月日时={戊,癸,庚}，均不成三奇 → 不命中。
    """
    pillars = [
        _make_pillar("年柱", "甲申", "甲", "申", ["庚", "壬", "戊"]),
        _make_pillar("月柱", "戊子", "戊", "子", ["癸"]),
        _make_pillar("日柱", "癸酉", "癸", "酉", ["辛"]),
        _make_pillar("时柱", "庚寅", "庚", "寅", ["甲", "丙", "戊"]),
    ]
    # 日柱天干=癸 ∉ triple；月日时顺序 [戊, 癸, 庚] 也不是 (甲,戊,庚) → 应不命中
    ss = _compute_shensha(pillars)
    sanqi = [s for s in ss if s["name"] == "三奇贵人"]
    assert sanqi == [], (
        f"日柱天干=癸 不在任何 triple 内 → 三奇贵人不命中；实际: {[(s['pillar'], s['description'][:80]) for s in sanqi]}"
    )


def test_branch_combinations_three_he_full_board():
    """三合局识别：四组三合局都能被识别。"""
    cases = [
        # 用户盘：壬子·壬子·丙申·壬辰 → 申子辰合水局
        (["子", "子", "申", "辰"], ["申子辰合水局"]),
        # 亥卯未合木局
        (["亥", "卯", "未", "子"], ["亥卯未合木局"]),
        # 寅午戌合火局
        (["寅", "午", "戌", "申"], ["寅午戌合火局"]),
        # 巳酉丑合金局
        (["巳", "酉", "丑", "辰"], ["巳酉丑合金局"]),
    ]
    for zhis, expected in cases:
        got = _branch_combinations(zhis)
        for label in expected:
            assert label in got, f"zhis={zhis} 应含 {label}，实际: {got}"


def test_branch_combinations_three_hui_full_board():
    """三会方识别：四组三会都能被识别。"""
    cases = [
        (["寅", "卯", "辰", "子"], ["寅卯辰会东方木"]),
        (["巳", "午", "未", "子"], ["巳午未会南方火"]),
        (["申", "酉", "戌", "子"], ["申酉戌会西方金"]),
        (["亥", "子", "丑", "午"], ["亥子丑会北方水"]),
    ]
    for zhis, expected in cases:
        got = _branch_combinations(zhis)
        for label in expected:
            assert label in got, f"zhis={zhis} 应含 {label}，实际: {got}"


def test_branch_combinations_liu_po():
    """六破识别：六对相破都能被命中。"""
    pairs = [
        (["子", "酉", "寅", "卯"], "子酉破"),
        (["卯", "午", "寅", "子"], "卯午破"),
        (["辰", "丑", "寅", "子"], "辰丑破"),
        (["巳", "申", "寅", "子"], "巳申破"),
        (["寅", "亥", "卯", "子"], "寅亥破"),
        (["未", "戌", "寅", "子"], "未戌破"),
    ]
    for zhis, label in pairs:
        got = _branch_combinations(zhis)
        assert label in got, f"zhis={zhis} 应含 {label}，实际: {got}"


def test_branch_combinations_empty_when_no_assembly():
    """无关地支不应误报三合/三会/破。"""
    # 子寅辰午：无三合局、无三会方、无相破（注意 子酉才是破，此组不含酉）
    got = _branch_combinations(["子", "寅", "辰", "午"])
    assert got == [], f"无三合/三会/破时应为空，实际: {got}"


def test_branch_combinations_he_and_po_coexist_on_sishen():
    """巳申既六合又相破：三合/三会/破识别层只负责破，
    六合由 _branch_relations 负责；这里验证破层能识别巳申破。"""
    got = _branch_combinations(["巳", "申", "子", "辰"])
    assert "巳申破" in got, f"巳申应识别为相破，实际: {got}"
    # 同时验证三合水局也在（申子辰）
    assert "申子辰合水局" in got, f"申子辰应合水局，实际: {got}"


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


# —— 神煞计算回归（2026-08-11 灾煞/吊客/病符 skip-rule 死代码修复）—————
# 上一次清理查法后缀时，把 `if i == 0: continue` 后面的命中分支误放到
# `if body` 内部，造成死代码、三个神煞永远命中不了。
# 锁定方法：构造用户实盘的特定四柱，断言灾煞必须出现在月柱。
def _full_pillar(name: str, ganzhi: str, gan: str, zhi: str, hidden: list[str]) -> Pillar:
    """完整的 Pillar 工厂（覆盖 frozen dataclass 的全部 13 字段）。"""
    return Pillar(
        name=name, ganzhi=ganzhi, gan=gan, zhi=zhi,
        gan_wuxing="", zhi_wuxing="", nayin="", xunkong="",
        hidden_stems=hidden,
        shishen_gan="", shishen_zhi=[],
        changsheng="", zizuo="",
    )


def test_shensha_zaisha_fires_on_pillar_with_target_branch():
    """回归：年甲子、月丙午、日壬申、时甲辰，应在月柱命中'灾煞'（年支子→灾煞=午）。

    之前 `if i == 0: continue` 后面的命中分支被退化为死代码，
    导致任何四柱都看不到灾煞；本测试钉死该四柱必须出现"月柱-灾煞"。
    """
    pillars = [
        _full_pillar("年柱", "甲子", "甲", "子", ["癸"]),
        _full_pillar("月柱", "丙午", "丙", "午", ["丁", "己"]),
        _full_pillar("日柱", "壬申", "壬", "申", ["庚"]),
        _full_pillar("时柱", "甲辰", "甲", "辰", ["乙", "癸"]),
    ]
    ss = _compute_shensha(pillars)
    zaisha = [s for s in ss if s["name"] == "灾煞"]
    assert zaisha, "灾煞 应该在结果中（之前因 dead code 漏掉）"
    assert any(s["pillar"] == "月柱" for s in zaisha), \
        f"灾煞 应该挂在月柱（zhi=午），实际为: {[s['pillar'] for s in zaisha]}"


def test_shensha_diaoke_bingfu_dead_code_fixed():
    """回归：三个 `if i == 0: continue + 命中分支` 三段必须都还要扫非首柱。

    这里造一个（年巳、月卯、日午、时酉）—— 应对应：
    - 吊客（DIAO_KE['巳']='卯'）命中月柱
    - 病符（BING_FU['巳']='辰'）未命中（四柱无辰，属合理 no-found）
    若三段中任何一段仍是死代码，整段 for-loop 不做事，这两条都不会出现。
    """
    pillars = [
        _full_pillar("年柱", "辛巳", "辛", "巳", ["丙", "庚", "戊"]),
        _full_pillar("月柱", "甲卯", "甲", "卯", ["乙"]),
        _full_pillar("日柱", "壬午", "壬", "午", ["丁", "己"]),
        _full_pillar("时柱", "丁酉", "丁", "酉", ["辛"]),
    ]
    ss = _compute_shensha(pillars)
    # 吊客应出现在月柱（zhi=卯）
    diaoke = [s for s in ss if s["name"] == "吊客"]
    assert diaoke, "吊客 应该扫到月柱（zhi=卯）；回归后不应再是死代码"
    assert any(s["pillar"] == "月柱" for s in diaoke), \
        f"吊客 应在月柱，实际: {[s['pillar'] for s in diaoke]}"
    # 病符：年巳 → 病符=辰，四柱无辰，预期不出现（合理）
    bingfu = [s for s in ss if s["name"] == "病符"]
    assert bingfu == [], f"病符 预期 not-found，实际: {bingfu}"


# —— 神煞查法分支（2026-08-12 天德合地支情形补全）—————
# TIAN_DE_HE["卯"]="巳" / ["午"]="寅" / ["酉"]="亥" / ["子"]="申" ——
# 这四个月支的天德本身是地支（参 TIAN_DE_IS_BRANCH={2,5,8,11}），
# 其天德合走"地支六合"，对应值也是地支，必须查 p.zhi 而非 p.gan。
# 此前只看 p.gan 导致卯/午/酉/子月永远命中不了天德合。
def test_tiande_he_zhi_target_fires_when_month_zhi_is_branch_mao_wu_you_zi():
    """卯/午/酉/子 月支查天德合，字典值是地支（巳/寅/亥/申），应按地支匹配。"""
    # 卯月查巳：时柱地支=巳 → 命中
    pillars = [
        _full_pillar("年柱", "丙辰", "丙", "辰", ["癸", "戊", "乙"]),
        _full_pillar("月柱", "丁卯", "丁", "卯", ["乙"]),
        _full_pillar("日柱", "戊子", "戊", "子", ["癸"]),
        _full_pillar("时柱", "己巳", "己", "巳", ["丙", "庚", "戊"]),
    ]
    ss = _compute_shensha(pillars)
    tdh = [s for s in ss if s["name"] == "天德合"]
    assert any(s["pillar"] == "时柱" for s in tdh), \
        f"卯月→天德合=巳，应在时柱命中；实际: {[s['pillar'] for s in tdh]}"

    # 子月查申：时柱地支=申 → 命中
    pillars = [
        _full_pillar("年柱", "戊辰", "戊", "辰", ["癸", "戊", "乙"]),
        _full_pillar("月柱", "庚子", "庚", "子", ["癸"]),
        _full_pillar("日柱", "壬寅", "壬", "寅", ["甲", "丙", "戊"]),
        _full_pillar("时柱", "甲申", "甲", "申", ["庚", "壬", "戊"]),
    ]
    ss = _compute_shensha(pillars)
    tdh = [s for s in ss if s["name"] == "天德合"]
    assert any(s["pillar"] == "时柱" for s in tdh), \
        f"子月→天德合=申，应在时柱命中；实际: {[s['pillar'] for s in tdh]}"

    # 酉月查亥：时柱地支=亥 → 命中
    pillars = [
        _full_pillar("年柱", "甲辰", "甲", "辰", ["癸", "戊", "乙"]),
        _full_pillar("月柱", "癸酉", "癸", "酉", ["辛"]),
        _full_pillar("日柱", "丙子", "丙", "子", ["癸"]),
        _full_pillar("时柱", "丁亥", "丁", "亥", ["壬", "甲"]),
    ]
    ss = _compute_shensha(pillars)
    tdh = [s for s in ss if s["name"] == "天德合"]
    assert any(s["pillar"] == "时柱" for s in tdh), \
        f"酉月→天德合=亥，应在时柱命中；实际: {[s['pillar'] for s in tdh]}"


def test_tiande_he_gan_target_fires_when_month_zhi_is_other_branches():
    """寅/辰/巳/未/申/戌/亥/丑 月支查天德合，字典值是天干，应按天干匹配（回归）。"""
    # 寅月查壬：月柱天干=壬 → 命中
    pillars = [
        _full_pillar("年柱", "甲子", "甲", "子", ["癸"]),
        _full_pillar("月柱", "壬寅", "壬", "寅", ["甲", "丙", "戊"]),
        _full_pillar("日柱", "庚午", "庚", "午", ["丁", "己"]),
        _full_pillar("时柱", "丁酉", "丁", "酉", ["辛"]),
    ]
    ss = _compute_shensha(pillars)
    tdh = [s for s in ss if s["name"] == "天德合"]
    assert any(s["pillar"] == "月柱" for s in tdh), \
        f"寅月→天德合=壬，应在月柱命中；实际: {[s['pillar'] for s in tdh]}"

