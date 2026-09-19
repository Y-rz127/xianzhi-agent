"""合盘共振线专项单测 + 黄金快照。

分三层：
1. **纯函数层** —— 地支关系归类、档位判定、同步度、基线公式（不依赖命盘）。
2. **不变量层** —— 确定性、交换对称、年份取交集、极值与序列自洽、维度可区分、
   以及最要紧的一条：**共振计算不得反过来改动单盘 K 线的任何数值**。
3. **快照层** —— 8 对代表命盘的整条共振线逐字段冻结（权重漂移的锚点）。

重生成快照：
    UPDATE_GOLDEN=1 ../.venv/Scripts/python.exe -m pytest tests/test_kline_resonance.py -q
"""

from __future__ import annotations

import pytest

from app.api import xianzhi_kline
from app.domain import fortune_score as FS, kline_resonance as KR
from tests import kline_resonance_golden as KG

PAIR_IDS = [(a, b, desc) for a, b, desc in KG.PAIRS]
PAIR_PARAMS = [pytest.param(a, b, desc, id=KG.pair_key(a, b)) for a, b, desc in PAIR_IDS]


# ---------------- 1. 纯函数层 ----------------


class TestVerdict:
    def test_bands_descend_strictly(self):
        """档位下界必须严格递减，否则 verdict_of 会跳过某一档。"""
        floors = [f for f, _ in KR.VERDICT_BANDS]
        assert floors == sorted(floors, reverse=True)
        assert len(set(floors)) == len(floors)
        assert floors[-1] == 0.0

    @pytest.mark.parametrize(
        "score,expected",
        [
            (100.0, "强共振"),
            (72.0, "强共振"),
            (71.9, "偏顺"),
            (58.0, "偏顺"),
            (57.9, "平稳"),
            (42.0, "平稳"),
            (41.9, "偏逆"),
            (30.0, "偏逆"),
            (29.9, "背离"),
            (0.0, "背离"),
        ],
    )
    def test_boundaries(self, score, expected):
        assert KR.verdict_of(score) == expected


class TestSyncOf:
    def test_same_sign_is_plus_one(self):
        assert KR._sync_of(3.0, 0.5) == 1
        assert KR._sync_of(-3.0, -0.5) == 1

    def test_opposite_sign_is_minus_one(self):
        assert KR._sync_of(3.0, -0.5) == -1
        assert KR._sync_of(-3.0, 0.5) == -1

    def test_zero_side_is_neutral(self):
        """任一侧为 0 时"同不同步"无从谈起，记 0 而不是扣分。"""
        assert KR._sync_of(0.0, 5.0) == 0
        assert KR._sync_of(5.0, 0.0) == 0
        assert KR._sync_of(0.0, 0.0) == 0


class TestPalaceRelation:
    @pytest.mark.parametrize(
        "a,b,expected",
        [
            ("子", "午", "冲"),
            ("卯", "酉", "冲"),
            ("辰", "戌", "冲"),
            ("子", "丑", "合"),
            ("寅", "巳", "刑"),
            ("子", "未", "害"),
            ("辰", "丑", "破"),
            ("子", "子", "同支"),
            ("", "子", ""),
            ("子", "", ""),
        ],
    )
    def test_kinds(self, a, b, expected):
        assert KR.palace_relation(a, b) == expected

    @pytest.mark.parametrize("a,b", [("巳", "申"), ("寅", "亥")])
    def test_he_wins_over_po_and_xing(self, a, b):
        """合破/合刑同见时取合。

        巳申既六合又六破还半刑、寅亥既六合又六破 —— 这是**必须钉死的取舍**：
        若把破或刑排在合前，这两个真六合会被报成最弱的关系类，基线分被反向拉低。
        """
        assert KR.palace_relation(a, b) == "合"

    def test_symmetric(self):
        """地支关系对称：a 与 b 的归类不因书写顺序改变。"""
        for x in "子丑寅卯辰巳午未申酉戌亥":
            for y in "子丑寅卯辰巳午未申酉戌亥":
                assert KR.palace_relation(x, y) == KR.palace_relation(y, x)


# ---------------- 2. 不变量层 ----------------


class TestPairBase:
    def test_score_matches_formula(self):
        """基线分 = clamp(50 + 各项点之和 × BASE_UNIT)，公式必须可复算。"""
        for a, b, _ in KG.PAIRS:
            base = KG.cached_resonance(a, b, FS.DIM_COMPREHENSIVE)["base"]
            expect = round(min(FS.SCORE_MAX, max(FS.SCORE_MIN, KR.BASE_SCORE + sum(base["points"].values()) * KR.BASE_UNIT)), 1)
            assert base["score"] == expect, f"{a}×{b}"

    def test_self_pair_is_same_kind_and_same_branch(self):
        """同一人自配对：日主必同类、日支必同支（确定性，不依赖具体命盘）。"""
        for case_id in ("stem_ren", "zhuanwang_runxia", "cong_true_cai"):
            base = KG.cached_resonance(case_id, case_id, FS.DIM_COMPREHENSIVE)["base"]
            assert base["relationKind"] == "同类"
            assert base["dayZhi"]["relation"] == "同支"

    def test_day_master_points_order(self):
        """日主关系取值的次序：相生 > 同类 > 相克（相生是互补，相克是耗损）。

        只测取值表本身，不用命盘 —— 全库实测里某个同类对与某个相克对同分是可能的，
        拿"同类必高于相克"当命盘断言会误报。
        """
        assert (
            KR._DAY_MASTER_POINTS["相生"]
            > KR._DAY_MASTER_POINTS["同类"]
            > KR._DAY_MASTER_POINTS["相克"]
        )

    def test_symmetric_in_scoring_content(self):
        """基线分、关系类别、各项点数交换甲乙后必须完全一致。

        只比**计分内容**，不比 detail 字段：`dayZhi.a/b`、`complement.aNeeds/bNeeds`
        本身就是按甲/乙两侧标注的，天然互为镜像，不参与计分。
        """
        for a, b, _ in KG.PAIRS:
            fwd = KG.cached_resonance(a, b, FS.DIM_COMPREHENSIVE)["base"]
            rev = KG.cached_resonance(b, a, FS.DIM_COMPREHENSIVE)["base"]
            assert fwd["score"] == rev["score"], f"{a}×{b} 基线分不对称"
            assert fwd["relationKind"] == rev["relationKind"], f"{a}×{b} 关系类别不对称"
            assert fwd["points"] == rev["points"], f"{a}×{b} 各项点数不对称"
            # detail 是镜像而非相等：甲的日支应等于乙视角里的"对方日支"
            assert fwd["dayZhi"]["a"] == rev["dayZhi"]["b"]
            assert fwd["complement"]["aNeeds"] == rev["complement"]["bNeeds"]


class TestBuildResonance:
    def test_deterministic(self):
        fwd = KG.cached_resonance("stem_ren", "stem_jia", FS.DIM_COMPREHENSIVE)
        again = KG.cached_resonance("stem_ren", "stem_jia", FS.DIM_COMPREHENSIVE)
        assert fwd == again

    def test_swap_symmetric_yearly(self):
        """整条逐年序列交换甲乙后必须逐字相同（共振是关系的属性，不是某一方的）。"""
        fwd = KG.cached_resonance("stem_ren", "boundary_female", FS.DIM_COMPREHENSIVE)["years"]
        rev = KG.cached_resonance("boundary_female", "stem_ren", FS.DIM_COMPREHENSIVE)["years"]
        assert [r["resonance"] for r in fwd] == [r["resonance"] for r in rev]

    def test_year_range_is_intersection(self):
        """年份范围 = 两盘 K 线年份的交集（起运年不同，童限期无共同刻度）。"""
        for a, b, _ in KG.PAIRS:
            res = KG.cached_resonance(a, b, FS.DIM_COMPREHENSIVE)
            ka = {c["year"] for c in FS.build_kline(KG.build_case_chart(KG.find_case(a)), max_age=KG.MAX_AGE)}
            kb = {c["year"] for c in FS.build_kline(KG.build_case_chart(KG.find_case(b)), max_age=KG.MAX_AGE)}
            expect = sorted(ka & kb)
            assert [r["year"] for r in res["years"]] == expect, f"{a}×{b}"
            assert res["meta"]["startYear"] == (expect[0] if expect else None)
            assert res["meta"]["yearCount"] == len(expect)

    def test_terms_sum_to_resonance(self):
        """每一项逐年修正之和 + 基线 = 共振分（不许有暗项）。"""
        for a, b, _ in KG.PAIRS:
            res = KG.cached_resonance(a, b, FS.DIM_COMPREHENSIVE)
            base = res["base"]["score"]
            for row in res["years"]:
                expect = round(min(FS.SCORE_MAX, max(FS.SCORE_MIN, base + sum(row["terms"].values()))), 1)
                assert row["resonance"] == expect, f"{a}×{b} {row['year']}"

    def test_terms_keys_are_fixed(self):
        res = KG.cached_resonance("stem_ren", "stem_ren", FS.DIM_COMPREHENSIVE)
        for row in res["years"]:
            assert set(row["terms"]) == {"trend", "align", "sync", "palace"}

    def test_peak_trough_consistent(self):
        for a, b, _ in KG.PAIRS:
            res = KG.cached_resonance(a, b, FS.DIM_COMPREHENSIVE)
            rows = res["years"]
            if not rows:
                assert res["meta"]["peakYear"] is None
                continue
            peak = max(r["resonance"] for r in rows)
            trough = min(r["resonance"] for r in rows)
            assert res["meta"]["peakYear"] in [r["year"] for r in rows if r["resonance"] == peak]
            assert res["meta"]["troughYear"] in [r["year"] for r in rows if r["resonance"] == trough]
            assert res["meta"]["meanScore"] == round(sum(r["resonance"] for r in rows) / len(rows), 1)

    def test_scores_within_bounds(self):
        for a, b, _ in KG.PAIRS:
            for row in KG.cached_resonance(a, b, FS.DIM_COMPREHENSIVE)["years"]:
                assert FS.SCORE_MIN <= row["resonance"] <= FS.SCORE_MAX

    def test_dimension_changes_curve(self):
        """维度经 effective_favor 影响喜忌，曲线必须随之变化。"""
        curves = {}
        for dim in FS.DIMENSIONS:
            res = KG.cached_resonance("stem_ren", "boundary_female", dim)
            curves[dim] = [r["resonance"] for r in res["years"]]
        assert len({tuple(v) for v in curves.values()}) == len(FS.DIMENSIONS)

    def test_weights_declared_as_uncalibrated(self):
        """权重是待校准先验，口径说明必须说清楚，不许假装已验证。"""
        meta = KG.cached_resonance("stem_ren", "stem_jia", FS.DIM_COMPREHENSIVE)["meta"]
        assert meta["weights"]["trend"] == KR.TREND_UNIT
        assert meta["weights"]["sync"] == KR.SYNC_UNIT
        assert "待校准" in meta["note"]
        assert "相对次序" in meta["note"]


class TestScoringIsolation:
    def test_resonance_does_not_touch_single_chart_kline(self):
        """共振是**只读**叠加层：算完之后单盘 K 线必须逐字段不变。"""
        chart = KG.build_case_chart(KG.find_case("stem_ren"))
        before = FS.build_kline(chart, max_age=KG.MAX_AGE)
        before_favor = FS.chart_favor_summary(chart)
        KG.cached_resonance("stem_ren", "stem_jia", FS.DIM_COMPREHENSIVE)
        KG.cached_resonance("stem_ren", "stem_bing", "wealth")
        assert FS.build_kline(chart, max_age=KG.MAX_AGE) == before
        assert FS.chart_favor_summary(chart) == before_favor


class TestPairCoverage:
    def test_pairs_cover_all_three_day_master_kinds(self):
        """配对清单必须覆盖日主相生/同类/相克三类分支，否则快照守不住基线分叉。"""
        kinds = set()
        for a, b, _ in KG.PAIRS:
            kinds.add(KR.pair_relation_kind(KG.build_case_chart(KG.find_case(a)), KG.build_case_chart(KG.find_case(b))))
        assert {"相生", "同类", "相克"} <= kinds, f"配对未覆盖全三类：{kinds}"


# ---------------- 3. 快照层 ----------------


@pytest.mark.parametrize("id_a,id_b,desc", PAIR_PARAMS)
def test_resonance_matches_snapshot(id_a, id_b, desc):
    actual = KG.build_snapshot(id_a, id_b)
    if KG.update_enabled():
        KG.write_snapshot(actual)
        return
    try:
        expected = KG.read_snapshot(id_a, id_b)
    except FileNotFoundError:
        pytest.fail(
            f"缺少快照 {KG.pair_key(id_a, id_b)}.json；"
            "首次生成请执行 UPDATE_GOLDEN=1 ../.venv/Scripts/python.exe -m pytest tests/test_kline_resonance.py -q"
        )
    diff = KG.diff_paths(expected, actual)
    assert not diff, (
        f"共振快照不一致（{id_a} × {id_b}，{desc}），共 {len(diff)} 处差异：\n  "
        + "\n  ".join(diff[:20])
        + "\n若为刻意的口径调整（共振权重 / 喜忌系数 / 关系修正表），"
        "确认变化符合预期后执行 UPDATE_GOLDEN=1 重生成。"
    )


def test_no_orphan_resonance_snapshots():
    """快照目录不许留已不在配对清单里的文件（会掩盖"删了配对没删快照"）。"""
    if not KG.FIXTURE_DIR.exists():
        return
    expected = {f"{KG.pair_key(a, b)}.json" for a, b, _ in KG.PAIRS}
    actual = {p.name for p in KG.FIXTURE_DIR.glob("*.json")}
    assert actual == expected, f"多出：{sorted(actual - expected)}；缺失：{sorted(expected - actual)}"


# ---------------- 4. 接口契约 ----------------


def _body(**overrides):
    kwargs = {
        "birth_time_a": "1990-05-20 14:30",
        "gender_a": "男",
        "birth_time_b": "1992-08-08 09:00",
        "gender_b": "女",
        "sect": 2,
        "yun_sect": 1,
        "longitude_a": None,
        "longitude_b": None,
        "max_age": 40,
        "dimension": FS.DIM_COMPREHENSIVE,
    }
    kwargs.update(overrides)
    return xianzhi_kline.KlineResonanceRequest(**kwargs)


def _run(**overrides):
    import asyncio

    return asyncio.run(xianzhi_kline.get_kline_resonance(_body(**overrides)))


class TestResonanceEndpoint:
    @pytest.fixture(autouse=True)
    def _fresh_cache(self):
        from app.tools.cache import bazi_cache

        bazi_cache.clear()
        yield
        bazi_cache.clear()

    def test_router_declares_resonance_path(self):
        paths = {
            (r.path, m) for r in xianzhi_kline.router.routes for m in getattr(r, "methods", set())
        }
        assert ("/kline/resonance", "POST") in paths, f"共振端点未声明，实际：{sorted(paths)}"

    def test_endpoint_is_mounted_on_app(self):
        try:
            from main import app
        except Exception as e:  # pragma: no cover - 缺少启动依赖时跳过
            pytest.skip(f"应用无法导入，跳过挂载校验：{e}")
        paths = set(app.openapi().get("paths", {}))
        assert "/api/ai/xianzhi/kline/resonance" in paths, (
            f"共振端点未挂载。含 xianzhi 的路径：{sorted(p for p in paths if 'xianzhi' in p)[:10]}"
        )

    def test_happy_path_shape(self):
        out = _run()
        assert set(out) >= {"base", "years", "meta", "favorA", "favorB"}
        assert out["years"], "共振年份不应为空"
        assert out["meta"]["dimensionLabel"]
        assert out["meta"]["availableDimensions"]
        assert out["favorA"]["dayMaster"] and out["favorB"]["dayMaster"]
        # 逐年行必须自带可解释的明细，供前端 tooltip / 批注引用
        for row in out["years"]:
            assert set(row["terms"]) == {"trend", "align", "sync", "palace"}
            assert row["verdict"]
            assert row["align"]["label"]

    def test_matches_engine_directly(self):
        """接口只是外壳：结果必须与直接调引擎逐字段相同。

        两端的命盘都经 `_build_chart` 构建 —— 若接口偷偷用了别的流派/大运步数，
        这里就会对不上（这正是"批注解的盘和画出来的线不是同一张"那类事故的守门测试）。
        """
        kwargs = {
            "birth_time_a": "1985-01-03 00:00",
            "gender_a": "男",
            "birth_time_b": "1985-01-05 00:00",
            "gender_b": "男",
        }
        out = _run(**kwargs)
        chart_a = xianzhi_kline._build_chart(kwargs["birth_time_a"], kwargs["gender_a"], 2, 1, None)
        chart_b = xianzhi_kline._build_chart(kwargs["birth_time_b"], kwargs["gender_b"], 2, 1, None)
        expect = KR.build_resonance(chart_a, chart_b, max_age=40, dimension=FS.DIM_COMPREHENSIVE)
        assert out["base"] == expect["base"]
        assert [r["resonance"] for r in out["years"]] == [r["resonance"] for r in expect["years"]]
        assert out["meta"]["startYear"] == expect["meta"]["startYear"]
        assert out["meta"]["yearCount"] == expect["meta"]["yearCount"]

    def test_max_dayun_aligns_pair_span(self):
        """两盘按步数覆盖时，交集右端 = 两盘第 10 步大运结束年里更早的那个。

        页面上共振线与主图并排，右端对不齐会被一眼看出长短不一。
        """
        out = _run(max_dayun=10)
        ends = []
        for bt, g in (("1990-05-20 14:30", "男"), ("1992-08-08 09:00", "女")):
            chart = xianzhi_kline._build_chart(bt, g, 2, 1, None)
            ends.append(xianzhi_kline._dayun_end_year(chart, 10))
        assert out["years"][-1]["year"] == min(ends)
        assert out["years"][-1]["year"] > _run()["years"][-1]["year"]

    def test_rejects_bad_max_dayun(self):
        from fastapi import HTTPException

        for bad in (-1, xianzhi_kline.MAX_DAYUN_LIMIT + 1):
            with pytest.raises(HTTPException) as e:
                _run(max_dayun=bad)
            assert e.value.status_code == 400
            assert "max_dayun" in str(e.value.detail)

    @pytest.mark.parametrize("max_age", [0, -1, xianzhi_kline.MAX_AGE_LIMIT + 1])
    def test_rejects_bad_max_age(self, max_age):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _run(max_age=max_age)
        assert e.value.status_code == 400

    def test_rejects_bad_dimension(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _run(dimension="not-a-dimension")
        assert e.value.status_code == 400

    def test_rejects_bad_birth_time(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            _run(birth_time_b="不是时间")
        assert e.value.status_code == 400

    def test_second_call_is_cached(self):
        first = _run()
        assert first["cached"] is False
        second = _run()
        assert second["cached"] is True
        assert [r["resonance"] for r in second["years"]] == [r["resonance"] for r in first["years"]]

    def test_cache_key_separates_the_second_person(self):
        """缓存主键是甲，但乙的身份必须编进 key —— 否则换个人会拿到上一个人的线。"""
        a = _run()
        b = _run(birth_time_b="1985-01-06 00:00", gender_b="男")
        assert b["cached"] is False, "换了乙方却命中缓存，key 没把乙编进去"
        assert a["base"] != b["base"] or [r["resonance"] for r in a["years"]] != [
            r["resonance"] for r in b["years"]
        ]

    def test_cache_key_separates_dimension(self):
        _run()
        other = _run(dimension="love")
        assert other["cached"] is False

