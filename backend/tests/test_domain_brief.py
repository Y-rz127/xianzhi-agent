"""domain_brief.py 领域投影层单测。

覆盖：事业简报要素、感情性别的配偶星取值、appearance 简报、零注入领域短路、
以及映射表神煞名与 shensha_calc 实际产出集合的交叉校验（防止映射名漂移筛不出）。
"""

import app.domain.domain_brief as db
from app.domain.chart_builder import build_bazi_chart, parse_gender
from app.domain.domain_brief import build_domain_brief
from app.domain.shensha_calc import _compute_shensha
from tests import bazi_golden as G

MALE = "\u7537"
FEMALE = "\u5973"


def _chart(birth_time: str = "1990-05-20 14:30", gender: str = MALE):
    return build_bazi_chart(birth_time, gender)


def _shensha_names_producible() -> set[str]:
    """shensha_calc 实际可产出的神煞名（委托共享提取器，兼容包结构与拆族后的产出形式）。"""
    return G.shensha_names_declared()


def test_career_brief_has_gods_and_palace():
    brief = build_domain_brief(_chart(), "career")
    assert "正官" in brief
    assert "七杀" in brief
    assert "月柱" in brief
    assert "相关神煞" in brief


def test_love_male_uses_wealth_star():
    brief = build_domain_brief(_chart(gender=MALE), "love")
    assert "配偶星（男命取 正财、偏财）" in brief
    assert "正财" in brief


def test_love_female_uses_officer_star():
    brief = build_domain_brief(_chart(gender=FEMALE), "love")
    assert "配偶星（女命取 正官、七杀）" in brief
    assert "正官" in brief


def test_appearance_brief_nonempty():
    brief = build_domain_brief(_chart(), "appearance")
    assert brief.strip() != ""
    assert "形貌" in brief
    # appearance 关注泄秀十神（食神/伤官）与印比
    assert any(g in brief for g in ("食神", "伤官", "劫财", "比肩"))


def test_zero_injection_domains_return_empty():
    chart = _chart()
    for domain in ("naming", "auspicious", "theory", "chitchat"):
        assert build_domain_brief(chart, domain) == ""


def test_shensha_mapping_names_are_producible():
    """映射表所有神煞名必须是 shensha_calc 实际能产出的名字，否则投影会筛空。"""
    producible = _shensha_names_producible()
    assert producible, "未能解析 shensha_calc 可产出神煞集合"
    mapped: set[str] = set()
    for spec in db._DOMAIN_PROJECTION.values():
        mapped.update(spec.get("shensha", ()))
    unknown = mapped - producible
    assert not unknown, f"映射表中未产出神煞名: {sorted(unknown)}"


def test_compute_shensha_anchor_sanity():
    """实际产出锚点 sanity：某真实命盘总能产出至少一个神煞。"""
    chart = _chart()
    names = {s["name"] for s in _compute_shensha(chart.pillars, parse_gender(chart.birth.gender))}
    assert names, "测试命盘未产出任何神煞，锚点失效"
