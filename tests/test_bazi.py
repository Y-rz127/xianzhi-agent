import json
from pathlib import Path

import pytest

from app.domain.bazi_engine import build_bazi_chart, chart_to_api_dict
from app.tools.bazi import bazi_analysis, bazi_chart, bazi_dayun, bazi_liunian


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
