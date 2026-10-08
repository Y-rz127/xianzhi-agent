"""黄金命盘快照：改动 domain/ 后输出必须逐字段一致。

这是阶段 3 / 4 的前置防线。`shensha_calc._compute_shensha`（513 行）与
`workflow_messages.check_facts`（451 行）历史上都出过"AST 解析通过、import 成功、
运行静默错"的事故——缩进错位让 `continue` 之后的命中判断变成永不执行的死代码，
灾煞/吊客/病符三段曾全中招。按行拆这类函数时，必须有"改动前后输出全等"的锚点，
否则回归在测试里不报错、只在线上表现为"某个神煞再也不出现了"。

重生成快照：
    UPDATE_GOLDEN=1 ../.venv/Scripts/python.exe -m pytest tests/test_bazi_golden.py -q
重生成后**必须人工核对 diff**，确认每处变化都是预期的。

排查某段指纹变化：
    ../.venv/Scripts/python.exe scripts/golden_bazi.py --show zhuanwang_quzhi xipan.liuyue
"""

from __future__ import annotations

import pytest

from tests import bazi_golden as G

CASES = G.load_cases()
CASE_IDS = [c["id"] for c in CASES]


def _regenerate_or_compare(case: dict) -> None:
    actual = G.build_case_snapshot(case)
    path = G.snapshot_path(case["id"])

    if G.update_enabled() or not path.exists():
        G.write_snapshot(actual)
        if not path.exists():  # pragma: no cover - 写入失败才走到
            pytest.fail(f"快照写入失败：{path}")
        return

    expected = G.read_snapshot(case["id"])
    diffs = G.diff_paths(expected, actual)
    if diffs:
        head = "\n".join(f"  - {d}" for d in diffs[:25])
        more = f"\n  …另有 {len(diffs) - 25} 处" if len(diffs) > 25 else ""
        pytest.fail(
            f"命盘快照不一致（case={case['id']}，{case['desc']}），共 {len(diffs)} 处差异：\n{head}{more}\n"
            f"确认变化符合预期后执行 UPDATE_GOLDEN=1 重生成。"
        )


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_golden_chart_matches_snapshot(case: dict) -> None:
    _regenerate_or_compare(case)


# ---------------- 快照集合自身的完整性 ----------------


def test_every_case_has_snapshot_file() -> None:
    """用例清单与快照文件一一对应，不留孤儿。"""
    missing = [c["id"] for c in CASES if not G.snapshot_path(c["id"]).exists()]
    assert not missing, f"以下用例缺少快照文件：{missing}"


def test_no_orphan_snapshot_files() -> None:
    """快照目录里不该有用例清单之外的文件（改名后残留会导致误判为"已覆盖"）。"""
    known = {f"{c['id']}.json" for c in CASES}
    on_disk = {p.name for p in G.FIXTURE_DIR.glob("*.json")} - {"cases.json"}
    assert not (on_disk - known), f"存在无对应用例的快照文件：{sorted(on_disk - known)}"


def test_case_ids_are_unique() -> None:
    assert len(CASE_IDS) == len(set(CASE_IDS)), "用例 id 重复会让快照互相覆盖"


def test_cases_declare_pinned_params_only_through_params_field() -> None:
    """`today` / `liunian_start_year` 只能由快照层钉死，用例不得覆盖。"""
    for case in CASES:
        params = case.get("params") or {}
        clash = [k for k in G.PINNED_PARAMS if k in params]
        assert not clash, f"{case['id']} 试图覆盖钉死参数 {clash}"


def test_write_snapshot_is_idempotent(tmp_path, monkeypatch) -> None:
    """内容未变时不落盘 —— 否则 `UPDATE_GOLDEN` 会把全部文件 mtime 刷新，
    `git status` 显示"全都变了"，人工核对时看不出受影响的到底是哪几例。"""
    monkeypatch.setattr(G, "FIXTURE_DIR", tmp_path)
    snap = G.build_case_snapshot(CASES[0])

    path = G.write_snapshot(snap)
    first_mtime = path.stat().st_mtime_ns

    G.write_snapshot(snap)  # 内容相同
    assert path.stat().st_mtime_ns == first_mtime, "内容未变却重写了文件"

    changed = dict(snap)
    changed["desc"] = snap["desc"] + "（已改）"
    G.write_snapshot(changed)
    assert path.stat().st_mtime_ns != first_mtime, "内容变化却未落盘"


# ---------------- 覆盖度承诺 ----------------


def test_case_set_covers_all_ten_day_masters() -> None:
    """10 日干全覆盖 —— 这是命例库的既定目标，缺哪个应立刻发现。"""
    seen = {G.build_case_snapshot(c)["chart"]["wuxing"]["day_master"] for c in CASES}
    expected = set("甲乙丙丁戊己庚辛壬癸")
    assert expected <= seen, f"缺失日干：{sorted(expected - seen)}"


def test_case_set_covers_all_special_pattern_names() -> None:
    """专旺五格（曲直/炎上/稼穑/从革/润下）全覆盖。"""
    seen = {
        s["chart"]["wuxing"]["strength"]
        for s in (G.build_case_snapshot(c) for c in CASES)
        if s["chart"]["wuxing"]["special_pattern"]
    }
    expected = {"曲直格", "炎上格", "稼穑格", "从革格", "润下格"}
    assert expected <= seen, f"缺失专旺格：{sorted(expected - seen)}"


def test_case_set_covers_all_conging_subtypes() -> None:
    """从格八子格（真从/假从 × 财杀儿势）全覆盖。

    `_CONG_SELF_WX_MAX = 0.50` 曾让从格恒不成立（死代码），28 个用例无一例从格 ——
    这种"分支整体不可达"的缺口只有覆盖承诺断言能发现。
    """
    seen = {
        s["chart"]["wuxing"]["strength"]
        for s in (G.build_case_snapshot(c) for c in CASES)
        if s["chart"]["wuxing"]["special_pattern"] in ("从格", "假从")
    }
    expected = {
        "从财格", "从杀格", "从儿格", "从势格",
        "假从财格", "假从杀格", "假从儿格", "假从势格",
    }
    assert expected <= seen, f"缺失从格子格：{sorted(expected - seen)}"


def test_case_set_covers_both_true_and_fake_conging() -> None:
    """真从与假从必须都有用例 —— 两类 kind 不同，提示词与岁运断法也不同。"""
    kinds = {
        s["chart"]["wuxing"]["special_pattern"]
        for s in (G.build_case_snapshot(c) for c in CASES)
        if s["chart"]["wuxing"]["special_pattern"]
    }
    assert {"从格", "假从"} <= kinds, f"缺少 kind：{sorted({'从格', '假从'} - kinds)}"


def test_case_set_covers_all_strength_levels() -> None:
    seen = {G.build_case_snapshot(c)["chart"]["wuxing"]["strength"] for c in CASES}
    expected = {"极旺", "偏旺", "中和", "偏弱", "极弱"}
    assert expected <= seen, f"缺失强弱档：{sorted(expected - seen)}"


# `shensha_calc` 能产出的**全部**神煞名（59 个）。
# 冻结它的意义：黄金盘必须把每一个都触发到，否则拆族时某一族被漏掉/改坏名字
# 不会有任何测试报错 —— 这正是历史上"某神煞再也不出现"的事故形态。
# 引擎新增神煞时：补一个能触发它的用例，再把名字加到这里。
EXPECTED_SHENSHA_ROSTER = {
    "三奇贵人", "丧门", "九丑日", "亡神", "元辰", "八专日",
    "六秀日", "劫煞", "勾绞煞", "十恶大败", "十灵日", "华盖",
    "吊客", "四废日", "国印贵人", "地网", "地转日", "天乙贵人",
    "天医", "天厨贵人", "天喜", "天德合", "天德贵人", "天罗",
    "天赦日", "天转日", "太极贵人", "孤辰", "孤鸾煞", "学堂",
    "寡宿", "将星", "德秀贵人", "披麻", "拱禄", "文昌贵人",
    "月德合", "月德贵人", "桃花", "正学堂", "正词馆", "流霞",
    "灾煞", "病符", "禄神", "福星贵人", "空亡", "童子煞",
    "红艳煞", "红鸾", "羊刃", "血刃", "词馆", "金神",
    "金舆", "阴差阳错", "飞刃", "驿马", "魁罡",
}


def test_case_set_triggers_every_shensha_name() -> None:
    """黄金盘必须触发全部 59 个神煞名（少一个就说明有用例没覆盖到的分支）。

    改动 `shensha_calc` 后若本测试失败：
    - 少了某名 → 该神煞的判定被改坏或被删，**这通常就是 bug**；
    - 多了某名 → 引擎新增了神煞，补一个触发用例并把名字加进 EXPECTED_SHENSHA_ROSTER。
    """
    covered: set[str] = set()
    for c in CASES:
        covered |= {s["name"] for s in G.build_case_snapshot(c)["shensha_pillars"]}

    missing = EXPECTED_SHENSHA_ROSTER - covered
    assert not missing, (
        f"以下神煞在黄金盘中一个都没被触发，说明对应分支已失效或缺失用例：{sorted(missing)}"
    )
    unexpected = covered - EXPECTED_SHENSHA_ROSTER
    assert not unexpected, (
        f"出现名册之外的神煞名：{sorted(unexpected)}。"
        "若为新增神煞，请补触发用例并更新 EXPECTED_SHENSHA_ROSTER。"
    )


def test_declared_roster_matches_frozen_roster() -> None:
    """源码里能产出的神煞名集合必须与冻结名册一致。

    与 `test_case_set_triggers_every_shensha_name` 是两个方向：
    前者看"源码声明了什么"（拆族时漏搬一族、改名都在这层暴露），
    后者看"实际算出来什么"（判定逻辑被改坏但名字还在，只有这层能发现）。
    """
    declared = G.shensha_names_declared()
    assert declared, "未能从 shensha_calc 解析出任何神煞名（提取器或包结构已变）"
    removed = EXPECTED_SHENSHA_ROSTER - declared
    added = declared - EXPECTED_SHENSHA_ROSTER
    assert not removed, f"以下神煞名已从源码中消失：{sorted(removed)}"
    assert not added, (
        f"源码新增了名册外的神煞：{sorted(added)}。"
        "请补一个能触发它的黄金用例，并把名字加进 EXPECTED_SHENSHA_ROSTER。"
    )


def test_shensha_entries_have_complete_shape() -> None:
    """每条神煞必须是 {name, description, pillar} 三键齐全的非空结构。"""
    for c in CASES:
        for entry in G.build_case_snapshot(c)["shensha_pillars"]:
            assert set(entry) == {"name", "description", "pillar"}, f"{c['id']} 条目结构异常：{entry}"
            assert entry["name"], f"{c['id']} 出现空神煞名"
            assert entry["description"], f"{c['id']} 的神煞 {entry['name']} 没有描述"


# ---------------- 防漂移 ----------------


def test_build_is_deterministic() -> None:
    """同一用例连续构建两次必须完全一致（否则快照每次跑都变，测试形同虚设）。"""
    case = CASES[0]
    assert G.build_case_snapshot(case) == G.build_case_snapshot(case)


def test_reference_date_is_pinned_not_system_clock() -> None:
    """快照必须不依赖系统当天 —— 改基准日应改变输出，改系统时钟不应。"""
    import datetime

    from app.domain.chart_builder import build_bazi_chart

    case = CASES[0]
    params = G.case_params(case)
    baseline = build_bazi_chart(case["birth"], case["gender"], **params).to_dict()

    # 显式传同一天 → 一致
    same = build_bazi_chart(
        case["birth"],
        case["gender"],
        liunian_start_year=params["liunian_start_year"],
        today=datetime.date.fromisoformat(G.REFERENCE_DATE),
    ).to_dict()
    assert G.diff_paths(baseline, same) == []

    # 换一天 → 细盘"当前岁运"必须变（证明 today 真的透传下去了）
    other = build_bazi_chart(
        case["birth"],
        case["gender"],
        liunian_start_year=params["liunian_start_year"],
        today=datetime.date.fromisoformat(G.REFERENCE_DATE) - datetime.timedelta(days=400),
    ).to_dict()
    assert G.diff_paths(baseline, other), "today 未透传到细盘：换基准日输出没变，快照仍会随系统日期漂移"


def test_digest_only_sections_recorded() -> None:
    """被指纹化的三段必须真的写进快照（否则那部分等于没覆盖）。"""
    snap = G.read_snapshot(CASES[0]["id"])
    for key in G.DIGEST_ONLY_XIPAN_KEYS:
        assert key in snap["chart"]["xipan"], f"xipan.{key} 未出现在快照中"
        digest = snap["chart"]["xipan"][key]
        assert digest.get("_digest_only") is True, f"xipan.{key} 未按指纹存储"
        assert digest.get("_count", 0) > 0


def test_pillars_shensha_recorded_separately() -> None:
    """原局神煞必须单独入快照 —— `to_dict()` 里没有这些字段。"""
    snap = G.read_snapshot(CASES[0]["id"])
    assert "shensha_pillars" not in snap["chart"], "原局神煞不应混进 chart（to_dict 本就不含）"
    assert isinstance(snap["shensha_pillars"], list)
    assert snap["shensha_pillars"], "原局神煞为空，阶段 3 拆 _compute_shensha 时没有锚点"


def test_fact_context_recorded() -> None:
    """LLM 事实上下文全文入快照（它直接决定生成与审核看到什么）。"""
    snap = G.read_snapshot(CASES[0]["id"])
    assert isinstance(snap["fact_context"], str)
    assert len(snap["fact_context"]) > 500


# ---------------- diff_paths 的诊断能力 ----------------


def test_diff_paths_reports_nested_field() -> None:
    assert G.diff_paths({"a": {"b": 1}}, {"a": {"b": 2}}) == ["a.b: 值已变"]


def test_diff_paths_reports_added_and_removed_keys() -> None:
    assert G.diff_paths({"a": 1}, {"b": 1}) == ["a: 字段消失", "b: 新增字段"]


def test_diff_paths_reports_type_change() -> None:
    assert G.diff_paths({"a": 1}, {"a": "1"}) == ["a: 类型 int → str"]


def test_diff_paths_same_length_list_is_positional() -> None:
    """长度相同时逐位比对 —— 顺序本身有语义，不能按标识索引掩盖顺序错乱。"""
    exp = [{"name": "甲"}, {"name": "乙"}]
    act = [{"name": "乙"}, {"name": "甲"}]
    assert G.diff_paths(exp, act) == ["[0].name: 值已变", "[1].name: 值已变"]


def test_diff_paths_pinpoints_disappeared_list_entry() -> None:
    """长度变化时必须点名是哪一条没了，而不是只报长度。"""
    exp = [{"name": "灾煞", "pillar": "日柱"}, {"name": "吊客", "pillar": "时柱"}]
    act = [{"name": "吊客", "pillar": "时柱"}]
    assert G.diff_paths(exp, act) == ["[name=灾煞]: 条目消失"]


def test_diff_paths_pinpoints_new_list_entry() -> None:
    exp = [{"name": "吊客"}]
    act = [{"name": "吊客"}, {"name": "病符"}]
    assert G.diff_paths(exp, act) == ["[name=病符]: 新增条目"]


def test_diff_paths_falls_back_to_length_for_unkeyable_lists() -> None:
    """元素无法按标识键索引时，退回报告长度。"""
    assert G.diff_paths([1, 2, 3], [1, 2]) == ["<root>: 列表长度 3 → 2"]
