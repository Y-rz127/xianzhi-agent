"""user_records 特征提取纯逻辑单测。

覆盖 R9/审查重构拆出的 _first 与 _extract_case_features：
两端 chart_snapshot 结构不一致（camelCase/snake_case 混用），多层回退必须保序。
"""
from app.db.user_records import _extract_case_features, _first


def test_first_returns_first_truthy():
    assert _first("", None, "x", "y") == "x"
    assert _first("", None, default="d") == "d"
    assert _first([1], []) == [1]
    assert _first() is None


def test_extract_features_prefers_features_block():
    chart = {
        "features": {"day_master": "乙", "strength": "偏弱"},
        "chartData": {"dayMaster": "甲", "pattern": "伤官配印"},
    }
    feats = _extract_case_features(chart)
    assert feats["day_master"] == "乙"  # features 优先于 chartData
    assert feats["strength"] == "偏弱"
    assert feats["pattern"] == "伤官配印"  # features 缺失时回退 chartData
    assert feats["combinations"] == []


def test_extract_features_camel_and_wuxing_fallback():
    chart = {
        "chartData": {
            "dayMaster": "庚",
            "usefulGod": "水",
            "wuxing": {"day_master_wuxing": "金", "strength": "偏强"},
        },
    }
    feats = _extract_case_features(chart)
    assert feats["day_master"] == "庚"
    assert feats["useful_god"] == "水"
    assert feats["day_master_wuxing"] == "金"  # wuxing 子结构兜底
    assert feats["strength"] == "偏强"


def test_extract_features_snake_and_top_level():
    chart = {"day_master": "丙", "clashes": ["子午冲"]}
    feats = _extract_case_features(chart)
    assert feats["day_master"] == "丙"
    assert feats["clashes"] == ["子午冲"]
    assert feats["sects"] == []


def test_extract_features_empty_chart():
    feats = _extract_case_features({})
    assert feats["day_master"] == ""
    assert feats["key_traits"] == []
    assert feats["useful_god"] == ""
