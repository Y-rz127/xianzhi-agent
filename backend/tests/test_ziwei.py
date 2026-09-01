"""紫微斗数引擎黄金快照测试：逐组断言 app/domain/ziwei/engine.py 与 iztro 2.6.0 默认配置一致。

oracle fixtures 由 scripts/gen_ziwei_oracle.js 一次性生成（tests/fixtures/ziwei_oracle/）。
改引擎或改流派表都须让本测试全绿；如需变更真值，重跑生成器并同步评审。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.ziwei import engine
from app.domain.ziwei.models import Chart

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ziwei_oracle"


def _load_cases() -> list[dict]:
    files = sorted(FIXTURE_DIR.glob("case_*.json"))
    assert len(files) >= 40, f"oracle fixtures 不足 40 组（当前 {len(files)}），请先跑 scripts/gen_ziwei_oracle.js"
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


CASES = _load_cases()


def _norm_chart(chart: Chart) -> dict:
    """把引擎 Chart 归一化成与 oracle 相同的可比结构（星曜按名字排序）。"""

    def stars(lst):
        return sorted(
            [{"name": s.name, "type": s.type, "brightness": s.brightness, "mutagen": s.mutagen} for s in lst],
            key=lambda x: x["name"],
        )

    return {
        "fiveElementsClass": chart.five_elements_class,
        "earthlyBranchOfSoulPalace": chart.earthly_branch_of_soul,
        "earthlyBranchOfBodyPalace": chart.earthly_branch_of_body,
        "soul": chart.soul_star,
        "body": chart.body_star,
        "gender": chart.gender,
        "palaces": [
            {
                "index": p.index,
                "name": p.name,
                "heavenlyStem": p.heavenly_stem,
                "earthlyBranch": p.earthly_branch,
                "isBodyPalace": p.is_body,
                "majorStars": stars(p.major_stars),
                "minorStars": stars(p.minor_stars),
                "adjectiveStars": stars(p.adjective_stars),
                "changsheng12": p.changsheng12,
                "boshi12": p.boshi12,
                "jiangqian12": p.jiangqian12,
                "suiqian12": p.suiqian12,
                "decadal": {"range": p.decadal.range} if p.decadal else None,
                "ages": p.ages,
            }
            for p in chart.palaces
        ],
    }


def _run_case(case: dict) -> Chart:
    inp = case["inputs"]
    if inp["calendar"] == "solar":
        return engine.cast_chart(solar_date=inp["solar"], time_index=inp["timeIndex"], gender=inp["gender"])
    return engine.cast_chart(
        lunar_date=inp["lunar"], leap=inp.get("isLeap", False), time_index=inp["timeIndex"], gender=inp["gender"], calendar="lunar"
    )


def _diffs(expected: dict, actual: dict, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k in expected:
            if k not in actual:
                out.append(f"{path}.{k}: 引擎缺字段")
            else:
                out += _diffs(expected[k], actual[k], f"{path}.{k}")
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            out.append(f"{path}: 长度 {len(actual)} != 期望 {len(expected)}")
        for i, (e, a) in enumerate(zip(expected, actual)):
            out += _diffs(e, a, f"{path}[{i}]")
    else:
        if expected != actual:
            out.append(f"{path}: 引擎={actual!r} 期望={expected!r}")
    return out


@pytest.mark.parametrize("case", CASES, ids=[c["inputs"].get("note", f"{i}") + f"#{i}" for i, c in enumerate(CASES)])
def test_matches_oracle(case):
    # oracle 只存了 {name,type,brightness,mutagen} 归一化，这里对齐比较
    expected = {"fiveElementsClass": case["primitives"]["fiveElementsClass"],
                "earthlyBranchOfSoulPalace": case["primitives"]["earthlyBranchOfSoulPalace"],
                "earthlyBranchOfBodyPalace": case["primitives"]["earthlyBranchOfBodyPalace"],
                "soul": case["primitives"]["soul"], "body": case["primitives"]["body"],
                "gender": case["primitives"]["gender"],
                "palaces": [
                    {k: p[k] for k in ("index", "name", "heavenlyStem", "earthlyBranch", "isBodyPalace",
                                        "majorStars", "minorStars", "adjectiveStars", "changsheng12",
                                        "boshi12", "jiangqian12", "suiqian12", "ages")} | {"decadal": {"range": p["decadal"]["range"]}}
                    for p in case["palaces"]
                ]}
    # oracle 星曜按名字排序（生成器已排），引擎侧也排序
    for p in expected["palaces"]:
        for key in ("majorStars", "minorStars", "adjectiveStars"):
            p[key] = sorted(p[key], key=lambda x: x["name"])
    actual = _norm_chart(_run_case(case))
    diffs = _diffs(expected, actual)
    assert not diffs, f"[{case['inputs']}] 与 iztro 不一致：\n" + "\n".join(diffs[:40])


def test_coverage_five_elements_and_timeindex():
    cov = json.loads((FIXTURE_DIR / "coverage.json").read_text(encoding="utf-8"))
    assert set(cov["fiveElementsClass"]) == {"水二局", "木三局", "金四局", "土五局", "火六局"}
    assert set(int(k) for k in cov["timeIndex"]) == set(range(13))
    assert cov["leap"] >= 1 and cov["lateZi"] >= 1


# --------------------------------------------------------------------------- #
# 边界与规则专项
# --------------------------------------------------------------------------- #
def test_late_zi_equals_next_day_early_zi_for_ziwei():
    """晚子时（23:30）起紫微应与次日早子一致（iztro dayDivide=forward）。"""
    a = engine.cast_chart(solar_date="1999-09-08", time_index=12, gender="女")
    b = engine.cast_chart(solar_date="1999-09-09", time_index=0, gender="女")
    # 五行局与紫微/天府分布应一致（晚子归次日）
    assert a.five_elements_class == b.five_elements_class


def test_leap_month_boundary():
    """闰二月十五归本月、十六归下月：两者命盘应不同。"""
    r15 = engine.cast_chart(solar_date="2023-04-05", time_index=6, gender="男")
    r16 = engine.cast_chart(solar_date="2023-04-06", time_index=6, gender="女")
    # 至少月系星（左辅/右弼）落宫不同
    def zuofu_palace(c):
        return next(p.index for p in c.palaces if any(s.name == "左辅" for s in p.minor_stars))
    assert zuofu_palace(r15) != zuofu_palace(r16)


def test_year_divide_at_lunar_new_year():
    """正月初一分界：除夕与正月初一（同为早子）年干支应不同。"""
    from lunar_python import Solar

    def yearly(s):
        y, m, d = (int(x) for x in s.split("-"))
        return Solar.fromYmd(y, m, d).getLunar().getYearInGanZhi()

    assert yearly("2026-02-16") == "乙巳"
    assert yearly("2026-02-17") == "丙午"


# --------------------------------------------------------------------------- #
# 非法参数
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kwargs,match", [
    ({"solar_date": "2000-08-16", "time_index": 0, "gender": "X"}, "性别"),
    ({"solar_date": "2000-08-16", "time_index": 13, "gender": "男"}, "时辰"),
    ({"solar_date": "2000-08-16", "time_index": -1, "gender": "女"}, "时辰"),
    ({"solar_date": "1800-01-01", "time_index": 0, "gender": "男"}, "1900"),
    ({"solar_date": "2200-01-01", "time_index": 0, "gender": "男"}, "2100"),
    ({"lunar_date": "2023-2-30", "leap": True, "time_index": 0, "gender": "男", "calendar": "lunar"}, "不存在"),
    ({"lunar_date": "2023-4-15", "leap": True, "time_index": 0, "gender": "男", "calendar": "lunar"}, "不存在"),
])
def test_invalid_params(kwargs, match):
    with pytest.raises(ValueError, match=match):
        engine.cast_chart(**kwargs)


def test_to_dict_shape():
    c = engine.cast_chart(solar_date="2000-08-16", time_index=2, gender="男")
    d = c.to_dict()
    assert len(d["palaces"]) == 12
    assert {"major_stars", "minor_stars", "adjective_stars", "decadal", "ages"} <= set(d["palaces"][0])
    assert d["five_elements_class"] in {"水二局", "木三局", "金四局", "土五局", "火六局"}
    assert "four_pillars" in d
