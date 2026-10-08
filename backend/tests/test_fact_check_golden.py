"""审核黄金样本回归测试：`check_facts` 的判定结果必须逐字一致。

覆盖 `check_facts` 的全部 7 个校验维度（柱位/流年/大运干支、十神组合与单个归属、
神煞存在性与柱位归属）以及 5 个辅助机制（否定词、动态岁运语境、理论豁免、
归属断言锚点、合婚双盘），并含 3 条历史事故的回归锚点。

重生成（须先人工核对 diff）：
    UPDATE_FACT_CHECK=1 ../.venv/Scripts/python.exe -m pytest tests/test_fact_check_golden.py -q
查看当前判定：
    ../.venv/Scripts/python.exe scripts/fact_check_golden.py --list
"""

from __future__ import annotations

import pytest

from tests import fact_check_golden as F

CASES = F.load_cases()
CASE_IDS = [c["id"] for c in CASES]


def _regenerate_or_compare(case: dict) -> None:
    actual = F.run_case(case)
    snapshot = F.read_snapshot()

    if F.update_enabled() or case["id"] not in snapshot:
        merged = dict(snapshot)
        merged[case["id"]] = actual
        F.write_snapshot(merged)
        return

    diffs = F.diff_paths(snapshot[case["id"]], actual)
    if diffs:
        head = "\n".join(f"  - {d}" for d in diffs[:15])
        pytest.fail(
            f"审核判定发生变化（case={case['id']}，{case['desc']}）：\n"
            f"  回答：{case['answer']}\n  期望：{snapshot[case['id']]}\n  实际：{actual}\n{head}\n"
            "确认变化符合预期后执行 UPDATE_FACT_CHECK=1 重生成。"
        )


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_fact_check_matches_snapshot(case: dict) -> None:
    _regenerate_or_compare(case)


# ---------------- 样本集自身的完整性 ----------------


def test_no_orphan_snapshot_entries() -> None:
    """快照里不该有已删样本的残留条目（残留会让"已覆盖"的错觉成立）。"""
    known = {c["id"] for c in CASES}
    extra = set(F.read_snapshot()) - known
    assert not extra, f"快照中存在无对应样本的条目：{sorted(extra)}"


def test_case_ids_are_unique() -> None:
    assert len(CASE_IDS) == len(set(CASE_IDS)), "样本 id 重复会让结果互相覆盖"


def test_chart_case_references_exist() -> None:
    """chart_case 必须指向真实存在的黄金命盘用例。"""
    for case in CASES:
        try:
            F.bazi_golden.find_case(case["chart_case"])
        except KeyError as e:
            pytest.fail(f"样本 {case['id']} 引用了不存在的命盘用例：{e}")


# ---------------- 语义承诺（比快照更强的断言） ----------------
#
# 快照只能保证"和上次一样"；下面按 intent 断言"应该是什么"。
# 两者互补：快照管逐字回归，语义管方向正确 —— 否则一条把违规改判为放行的
# 改动只要同步刷了快照就能悄悄通过。

_OK_CASES = [c for c in CASES if c["intent"] == "ok"]
_VIOLATION_CASES = [c for c in CASES if c["intent"] == "violation"]
_REGRESSION_CASES = [c for c in CASES if c["intent"] == "regression"]


@pytest.mark.parametrize("case", _OK_CASES, ids=[c["id"] for c in _OK_CASES])
def test_intent_ok_is_not_flagged(case: dict) -> None:
    """合法表述不得被误杀（误杀比漏检更伤体验）。"""
    result = F.run_case(case)
    assert result["ok"] is True, f"{case['id']} 被误判：{result['issues']}"


@pytest.mark.parametrize(
    "case", _VIOLATION_CASES + _REGRESSION_CASES,
    ids=[c["id"] for c in _VIOLATION_CASES + _REGRESSION_CASES],
)
def test_intent_violation_is_flagged(case: dict) -> None:
    """违规与历史事故样本必须被拦住，且给出可读的 issue。"""
    result = F.run_case(case)
    assert result["ok"] is False, f"{case['id']} 漏检（应报问题却放行）"
    assert result["issues"], f"{case['id']} 报了不通过却没有 issue 文本"


def test_case_set_covers_every_check_dimension() -> None:
    """七个校验维度都必须有'应拦截'样本，缺哪个说明该维度没被回归覆盖。"""
    dims = {
        "柱位干支": ["bad_pillar"],
        "流年干支": ["bad_liunian", "reg_dayun_leak_liunian"],
        "大运干支": ["bad_dayun", "reg_dayun_gz_collides_liunian"],
        "十神归属": ["bad_shishen_single", "bad_shishen_combo"],
        "神煞存在性": ["bad_shensha_exists", "reg_single_char_negation"],
        "神煞柱位归属": ["bad_shensha_pillar"],
        "合婚双盘": ["bad_hehun_dayun"],
    }
    ids = set(CASE_IDS)
    for dim, required in dims.items():
        missing = [i for i in required if i not in ids]
        assert not missing, f"维度「{dim}」缺少样本：{missing}"
        for cid in required:
            case = next(c for c in CASES if c["id"] == cid)
            assert F.run_case(case)["ok"] is False, f"维度「{dim}」的样本 {cid} 未被拦截"


def test_regression_cases_present() -> None:
    """历史事故的回归锚点不得被删除 —— 它们对应的 bug 都曾真实上线。"""
    assert len(_REGRESSION_CASES) >= 3, "历史事故回归样本被删"
    for case in _REGRESSION_CASES:
        assert "历史事故" in case["desc"], f"{case['id']} 应说明它对应哪次事故"
