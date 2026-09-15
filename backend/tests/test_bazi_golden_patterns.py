"""从格 / 专旺 判定的函数级契约测试（合成输入）。

口径来源：`app/rag/knowledge_docs/33_从格专旺化气体系.md`
- §一.2 从格成立条件（必须同时满足）：日主无根 / 天干无印比 / 全局气势专一 / **月令为所从之神**
- §一.2 关键判定：'地支藏干中只要有日主微根（如甲木见辰中乙木、亥中甲木），
  即不为真从，为假从。天干虚浮一比一印，亦为假从。'
- §八.1 假从：有微根或虚浮印比；行顺从运可发，行帮身运即破败。**现实：假从居多，真从极少。**
- §八.3 边界：根极弱 → 假从；根有力 → 正格；印比有力 → 正格。

`_CONG_SELF_WX_MAX = 0.50` 已于 2026-09-15 删除 —— 它比较"日主五行**绝对**权重，
而日干自身必然贡献 1.0，该量最小值恒为 1.0（6 万样本实测），守卫恒真、从格永不成立。
本文件用合成输入把三档语义钉死，重组 `_root_profile` 时才有锚点。
"""

from __future__ import annotations

import pytest

from app.domain import analysis_calc as A
from app.domain.tables import CONTROLS, GENERATES

# 以甲木日主为例派生印/官杀/财/食伤，避免硬编码五行关系
DAY_MASTER = "甲"
DAY_WX = A.GAN_WUXING[DAY_MASTER]        # 木
RESOURCE = A._producer_of(DAY_WX)        # 水（印）
OFFICER = A._controller_of(DAY_WX)       # 金（官杀）
WEALTH = CONTROLS[DAY_WX]                # 土（财）
OUTPUT = GENERATES[DAY_WX]               # 火（食伤）

# ---- 根气三档的合成四柱（`pillars` 形态是"干支"两字符串，p[0]=天干, p[1]=地支）----
# 巳/戌/午 的藏干都不含木（比劫）也不含水（印）→ 甲木无根
# 同时要注意各子格的**破格之神**不得有力：从财忌官杀(金)、从杀忌食伤(火)，
# 故取地支时须避开该五行的本气（巳/午 是火本气 → 会破从杀局）。
ROOTLESS_MONTH_WEALTH = ["己巳", "己戌", "甲戌", "己午"]   # 月支 戌=土=财；地支无金本气
ROOTLESS_MONTH_OFFICER = ["己戌", "己酉", "甲戌", "己酉"]  # 月支 酉=金=官杀；地支无火本气
ROOTLESS_MONTH_OUTPUT = ["己巳", "己午", "甲戌", "己午"]   # 月支 午=火=食伤；地支无水本气
WEAK_ROOT = ["己巳", "戊辰", "甲戌", "己午"]               # 辰藏乙木 → 微根
SOLID_ROOT_LU = ["己巳", "己寅", "甲戌", "己午"]           # 寅为甲禄 → 有力
SOLID_ROOT_STEM = ["乙亥", "己戌", "甲戌", "己午"]         # 乙透干且亥藏甲 → 有力
FLOATING_STEM = ["乙酉", "己戌", "甲戌", "己午"]           # 乙透干但地支无木 → 微根（虚浮）
# 破格之神有力的两组（其余条件都满足：无根 + 月令当令）
IMPURE_CAI_BRANCH_METAL = ["己酉", "己戌", "甲戌", "己午"]  # 酉=金本气 → 官杀泄财
IMPURE_SHA_STEM_FIRE = ["丙戌", "己酉", "甲戌", "己酉"]     # 丙=火透干 → 食伤制杀


def _weights(**overrides: float) -> dict[str, float]:
    base = {DAY_WX: 0.1, RESOURCE: 0.1, OUTPUT: 0.3, WEALTH: 0.2, OFFICER: 0.2}
    base.update(overrides)
    return base


def _conging(weighted, pillars=ROOTLESS_MONTH_WEALTH):
    return A._detect_conging(
        weighted, pillars, DAY_WX, DAY_MASTER, RESOURCE, OFFICER, WEALTH, OUTPUT
    )


# ---------------- 根气三档 ----------------


def test_rootless_verdict():
    assert A._root_profile(ROOTLESS_MONTH_WEALTH, DAY_MASTER, DAY_WX, RESOURCE).verdict == "无根"


def test_weak_root_verdict_from_hidden_stem_trace():
    """辰藏乙木 —— 知识库：'只要有日主微根，即不为真从，为假从'。门槛是"有一丝"，非本气级。"""
    profile = A._root_profile(WEAK_ROOT, DAY_MASTER, DAY_WX, RESOURCE)
    assert profile.verdict == "微根"
    assert profile.hidden_day > 0
    assert not profile.lu_ren_ku


def test_solid_verdict_from_lu_branch():
    profile = A._root_profile(SOLID_ROOT_LU, DAY_MASTER, DAY_WX, RESOURCE)
    assert profile.verdict == "有力"
    assert profile.lu_ren_ku is True


def test_solid_verdict_from_stem_with_earthly_support():
    """乙透干且亥藏甲木 → 印比有力。亥不在甲木禄刃库（寅卯未）内，故只可能是 solid_support 路径。"""
    profile = A._root_profile(SOLID_ROOT_STEM, DAY_MASTER, DAY_WX, RESOURCE)
    assert profile.lu_ren_ku is False
    assert profile.solid_support == ("乙",)
    assert profile.verdict == "有力"


def test_floating_stem_is_weak_not_solid():
    """乙透干但地支无木 → 虚浮 → 假从，不是正格。"""
    profile = A._root_profile(FLOATING_STEM, DAY_MASTER, DAY_WX, RESOURCE)
    assert profile.solid_support == ()
    assert profile.floating_support == ("乙",)
    assert profile.verdict == "微根"


@pytest.mark.parametrize("pillars", [SOLID_ROOT_LU, SOLID_ROOT_STEM])
def test_solid_root_never_conging(pillars):
    """根有力 / 印比有力 → 正格，不论从（知识库 §八.3）。"""
    assert _conging(_weights(**{WEALTH: 3.0}), pillars=pillars) is None


# ---------------- 真从（kind = "从格"） ----------------


@pytest.mark.parametrize(
    ("pillars", "dominant", "expected_label"),
    [
        (ROOTLESS_MONTH_WEALTH, WEALTH, "从财格"),
        (ROOTLESS_MONTH_OFFICER, OFFICER, "从杀格"),
        (ROOTLESS_MONTH_OUTPUT, OUTPUT, "从儿格"),
    ],
)
def test_true_conging_requires_rootless_and_month_season(pillars, dominant, expected_label):
    """真从 = 无根 + 月令为所从之神当令。"""
    result = _conging(_weights(**{dominant: 3.0}), pillars=pillars)
    assert result is not None
    kind, label, hint = result
    assert kind == "从格"
    assert label == expected_label
    assert "假从" not in hint, "真从不应带假从告诫"


def test_true_congshi_when_two_elements_comparable():
    result = _conging(_weights(**{WEALTH: 2.0, OFFICER: 1.6}))
    assert result is not None
    assert result[0] == "从格"
    assert result[1] == "从势格"


def test_congshi_threshold_boundary():
    """`_CONG_SECOND_RATIO` 两侧：略低 → 独旺型；达到 → 从势。"""
    below = _conging(_weights(**{WEALTH: 2.0, OFFICER: 2.0 * 0.79}))
    at = _conging(_weights(**{WEALTH: 2.0, OFFICER: 2.0 * A._CONG_SECOND_RATIO}))
    assert below is not None and below[1] == "从财格"
    assert at is not None and at[1] == "从势格"


# ---------------- 假从（kind = "假从"） ----------------


def test_fake_conging_when_weak_root():
    """有微根但气势仍旺 → 假从（知识库：假从居多）。"""
    result = _conging(_weights(**{WEALTH: 3.0}), pillars=WEAK_ROOT)
    assert result is not None
    kind, label, hint = result
    assert kind == "假从"
    assert label == "假从财格"
    assert "行帮身运即破败" in hint


def test_fake_conging_when_month_not_in_follow_season():
    """无根但月令不当令（月支酉=官杀，而所从为财）→ 降为假从。"""
    result = _conging(_weights(**{WEALTH: 3.0}), pillars=ROOTLESS_MONTH_OFFICER)
    assert result is not None
    assert result[0] == "假从"
    assert result[1] == "假从财格"


def test_fake_conging_when_stem_support_floating():
    result = _conging(_weights(**{OFFICER: 3.0}), pillars=FLOATING_STEM)
    assert result is not None
    assert result[0] == "假从"
    assert result[1] == "假从杀格"


def test_fake_conging_carries_caveat():
    """假从提示必须写清"行顺从运可发、行帮身运即破败"，供 LLM 区分真假从。"""
    result = _conging(_weights(**{WEALTH: 3.0}), pillars=WEAK_ROOT)
    assert result is not None
    assert "根基不稳" in result[2]


# ---------------- 破格之神（知识库 §二.1/§三.1/§四.1 第 4 条） ----------------


def test_breaker_element_mapping():
    """各子格的破格之神：从财忌官杀（泄财）、从杀忌食伤（制杀）、从儿忌印（克食伤）。"""
    assert A._breaker_element("财", RESOURCE, OFFICER, OUTPUT) == OFFICER
    assert A._breaker_element("官杀", RESOURCE, OFFICER, OUTPUT) == OUTPUT
    assert A._breaker_element("食伤", RESOURCE, OFFICER, OUTPUT) == RESOURCE
    assert A._breaker_element("从势", RESOURCE, OFFICER, OUTPUT) == ""


def test_breaker_potent_by_branch_main_qi():
    """地支见破格之神本气即算有力。"""
    assert A._breaker_is_potent(IMPURE_CAI_BRANCH_METAL, OFFICER) is True


def test_breaker_potent_by_revealed_stem():
    """破格之神透干即算有力。"""
    assert A._breaker_is_potent(IMPURE_SHA_STEM_FIRE, OUTPUT) is True


def test_breaker_weak_when_only_leftover_qi():
    """仅藏干余气/中气（不透干、非地支本气）不算有力 —— 库中之气不构成破格。

    例：土月的 戌 藏辛金（金为官杀），辛只是余气，不足以泄财。
    """
    assert A._breaker_is_potent(ROOTLESS_MONTH_WEALTH, OFFICER) is False


def test_potent_breaker_demotes_congcai_to_fake():
    """无根且月令当令，但官杀有力 → 从财格不纯 → 假从。"""
    result = _conging(_weights(**{WEALTH: 3.0}), pillars=IMPURE_CAI_BRANCH_METAL)
    assert result is not None
    kind, label, hint = result
    assert kind == "假从"
    assert label == "假从财格"
    assert "官杀有力" in hint
    assert "格局不纯" in hint


def test_potent_breaker_demotes_congsha_to_fake():
    """从杀格见食伤有力 → 制杀破从局 → 假从。"""
    result = _conging(_weights(**{OFFICER: 3.0}), pillars=IMPURE_SHA_STEM_FIRE)
    assert result is not None
    assert result[0] == "假从"
    assert result[1] == "假从杀格"
    assert "食伤有力" in result[2]


def test_breakered_chart_outweighs_other_reasons():
    """破格是降级之由之一，提示里要写明具体原因，供 LLM 分辨。"""
    result = _conging(_weights(**{WEALTH: 3.0}), pillars=IMPURE_CAI_BRANCH_METAL)
    assert result is not None
    assert "假从之由：" in result[2]
    assert "月令非所从之神当令" not in result[2], "月令是当令的，不该被列为降级之由"


def test_conger_breaker_condition_is_vacuous():
    """从儿格的破格之神是印星，而"无印"已是根气前置条件 → 该条恒满足（实测 10/10 例无印）。

    故从儿格不存在"仅因破格而降级"的情形；降级只可能来自微根（印本身就是虚浮印比）。
    """
    assert A._breaker_is_potent(ROOTLESS_MONTH_OUTPUT, RESOURCE) is False


def test_congshi_has_no_breaker():
    """从势格财官食伤皆旺，不设破格之神。"""
    result = _conging(_weights(**{WEALTH: 2.0, OFFICER: 1.6}))
    assert result is not None
    assert result[0] == "从格"


# ---------------- 不从 ----------------


def test_no_follow_when_no_dominant_element():
    """克泄耗无一行 ≥ 0.5 → 没有可从之势。"""
    assert _conging(_weights(**{OUTPUT: 0.3, WEALTH: 0.3, OFFICER: 0.3})) is None


def test_congshi_month_check_accepts_any_of_three_elements():
    """从势无一定之从：月令落在官杀/财/食伤任一行都算当令。"""
    for pillars in (ROOTLESS_MONTH_WEALTH, ROOTLESS_MONTH_OFFICER, ROOTLESS_MONTH_OUTPUT):
        result = _conging(_weights(**{WEALTH: 2.0, OFFICER: 1.6}), pillars=pillars)
        assert result is not None, f"{pillars} 从势被误拒"
        assert result[0] == "从格", f"{pillars} 从势月令判定失败"


# ---------------- 专旺侧（对称检查） ----------------


def test_zhuanwang_returns_kind_label_hint():
    result = A._detect_zhuanwang(
        {DAY_WX: 7.0, RESOURCE: 0.5, OUTPUT: 0.2, WEALTH: 0.2, OFFICER: 0.1},
        DAY_WX, RESOURCE, OFFICER, WEALTH, OUTPUT,
    )
    assert result is not None
    kind, label, hint = result
    assert kind == "专旺"
    assert label == A._ZHUANWANG_NAME[DAY_WX]
    assert hint


def test_zhuanwang_uses_ratio_threshold():
    """专旺用的是**占比**口径，从格侧已统一为根气画像 —— 二者都不再依赖绝对权重。"""
    payload = {DAY_WX: 4.0, RESOURCE: 3.0, OUTPUT: 0.5, WEALTH: 0.3, OFFICER: 0.2}
    assert A._detect_zhuanwang(payload, DAY_WX, RESOURCE, OFFICER, WEALTH, OUTPUT) is None


def test_zhuanwang_rejected_when_pressure_too_high():
    payload = {DAY_WX: 7.0, RESOURCE: 0.5, OUTPUT: 2.0, WEALTH: 2.0, OFFICER: 2.0}
    assert A._detect_zhuanwang(payload, DAY_WX, RESOURCE, OFFICER, WEALTH, OUTPUT) is None


def test_every_wuxing_has_a_zhuanwang_name():
    assert set(A._ZHUANWANG_NAME) == {"金", "木", "水", "火", "土"}


def test_no_absolute_weight_threshold_remains():
    """`_CONG_SELF_WX_MAX` 必须彻底消失 —— 它是结构性不可满足的死阈值。"""
    assert not hasattr(A, "_CONG_SELF_WX_MAX")


# ---------------- 分派逻辑 ----------------


def test_special_pattern_only_evaluated_in_extreme_zone():
    sp = A._detect_special_pattern(
        ROOTLESS_MONTH_WEALTH, _weights(**{WEALTH: 3.0}), DAY_WX, DAY_MASTER, 3.0,
        RESOURCE, OUTPUT, WEALTH, OFFICER,
    )
    assert sp["is_special"] is False


def test_special_pattern_routes_positive_score_to_zhuanwang():
    sp = A._detect_special_pattern(
        ROOTLESS_MONTH_WEALTH,
        {DAY_WX: 7.0, RESOURCE: 0.5, OUTPUT: 0.2, WEALTH: 0.2, OFFICER: 0.1},
        DAY_WX, DAY_MASTER, 8.0, RESOURCE, OUTPUT, WEALTH, OFFICER,
    )
    assert sp["is_special"] is True
    assert sp["kind"] == "专旺"


@pytest.mark.parametrize(
    ("pillars", "expected_kind"),
    [(ROOTLESS_MONTH_WEALTH, "从格"), (WEAK_ROOT, "假从")],
)
def test_special_pattern_routes_negative_score_to_conging(pillars, expected_kind):
    sp = A._detect_special_pattern(
        pillars, _weights(**{WEALTH: 3.0}), DAY_WX, DAY_MASTER, -8.0,
        RESOURCE, OUTPUT, WEALTH, OFFICER,
    )
    assert sp["is_special"] is True
    assert sp["kind"] == expected_kind
