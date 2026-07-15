import json
from pathlib import Path

import pytest

from app.domain.bazi_engine import build_bazi_chart, chart_to_api_dict
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
