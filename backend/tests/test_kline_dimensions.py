"""维度指纹与不变量：K 线切维度必须「只换取象、不换刻度」。

分两层：

- **指纹层**（`test_dimension_fingerprint_matches_snapshot`）：8 个代表命盘 × 全部维度
  的收盘分序列逐值冻结。`_DIM_EMPHASIS` 里任何一个侧重系数被顺手改动，此层立刻失败
  ——单测断言（如"事业维度某年 > 60"）对整体平移无感。
- **不变量层**：抓"维度能算出来、但已经不自洽"。其中最重要的是
  `test_comprehensive_is_the_default`（综合维度必须与不传维度逐字节相同，这是零回归的
  前提）与 `test_no_dimension_saturates`（任一维度贴到 0/100 硬边界，说明该维度的
  侧重系数破坏了 K_SCORE=40 的标定）。

重生成指纹：
    UPDATE_GOLDEN=1 ../.venv/Scripts/python.exe -m pytest tests/test_kline_dimensions.py -q
重生成后必须人工核对 diff。
"""

from __future__ import annotations

import pytest

from app.domain import fortune_score as FS
from tests import kline_golden as K

DIM_CASES = K.DIM_FINGERPRINT_CASES
NON_COMPREHENSIVE = tuple(d for d in FS.DIMENSIONS if d != FS.DIM_COMPREHENSIVE)

# 维度侧重系数的均值归一容差：归一表按 4 位小数取整，故留一点余量
MEAN_TOL = 1e-3


# ---------------- 指纹层 ----------------


def _regenerate_or_compare() -> None:
    actual = K.build_dimension_snapshot()
    if K.update_enabled() or not K.DIM_FIXTURE.exists():
        K.write_dimension_snapshot(actual)
        if not K.DIM_FIXTURE.exists():  # pragma: no cover - 写入失败才走到
            pytest.fail(f"维度指纹写入失败：{K.DIM_FIXTURE}")
        return

    diffs = K.diff_paths(K.read_dimension_snapshot(), actual)
    if diffs:
        head = "\n".join(f"  - {d}" for d in diffs[:25])
        more = f"\n  …另有 {len(diffs) - 25} 处" if len(diffs) > 25 else ""
        pytest.fail(
            f"维度指纹不一致，共 {len(diffs)} 处差异：\n{head}{more}\n"
            "若为刻意的侧重系数调整，确认各维度仍不饱和/不塌缩后执行 "
            "UPDATE_GOLDEN=1 重生成。"
        )


@pytest.mark.parametrize("case_id", DIM_CASES)
def test_dimension_fingerprint_matches_snapshot(case_id: str) -> None:
    del case_id  # 指纹是全量一次性比对，参数化只为让失败信息带上用例名
    _regenerate_or_compare()


# ---------------- 不变量层 ----------------


def test_comprehensive_is_the_default() -> None:
    """综合维度必须与「不传 dimension」逐字节相同 —— 这是零回归的前提。"""
    for case_id in DIM_CASES:
        chart = K.cached_chart(case_id)
        explicit = FS.build_kline(chart, max_age=K.MAX_AGE, dimension=FS.DIM_COMPREHENSIVE)
        assert explicit == FS.build_kline(chart, max_age=K.MAX_AGE), (
            f"{case_id} 显式 comprehensive 与默认结果不一致"
        )


def test_unknown_dimension_falls_back_to_comprehensive() -> None:
    """未知维度退化为综合维度，而不是抛错或给空曲线。"""
    case_id = DIM_CASES[0]
    chart = K.cached_chart(case_id)
    assert FS.dimension_emphasis(chart, "不存在的维度") == {}
    assert FS.build_kline(chart, max_age=K.MAX_AGE, dimension="不存在的维度") == (
        FS.build_kline(chart, max_age=K.MAX_AGE)
    )


def test_every_dimension_differs_from_comprehensive() -> None:
    """每个非综合维度都必须真正改变曲线 —— 否则等于维度开关是摆设。"""
    for case_id in DIM_CASES:
        base = [c["close"] for c in K.cached_kline(case_id)]
        for dim in NON_COMPREHENSIVE:
            closes = [c["close"] for c in K.cached_kline_dim(case_id, dim)]
            ratio = sum(1 for a, b in zip(base, closes) if a != b) / len(base)
            assert ratio > 0.8, (
                f"{case_id} 的「{FS.DIMENSION_LABELS[dim]}」维度只有 {ratio:.0%} 年份与综合维度不同"
            )


def test_dimensions_do_not_all_collapse_into_one() -> None:
    """各维度之间也必须互不相同，而不是换了个名字的同一条曲线。"""
    for case_id in DIM_CASES:
        series = {
            dim: [c["close"] for c in K.cached_kline_dim(case_id, dim)]
            for dim in FS.DIMENSIONS
        }
        for i, a in enumerate(FS.DIMENSIONS):
            for b in FS.DIMENSIONS[i + 1 :]:
                same = sum(1 for x, y in zip(series[a], series[b]) if x == y) / len(series[a])
                assert same < 0.5, (
                    f"{case_id} 的「{FS.DIMENSION_LABELS[a]}」与「{FS.DIMENSION_LABELS[b]}」"
                    f"有 {same:.0%} 年份重合，维度区分度不足"
                )


def test_dimension_does_not_change_relations() -> None:
    """维度只改分数，不改关系判定 —— 关系仍归 `yun_relations` 单一事实源。"""
    for case_id in DIM_CASES:
        base = [c["relations"] for c in K.cached_kline(case_id)]
        for dim in NON_COMPREHENSIVE:
            assert [c["relations"] for c in K.cached_kline_dim(case_id, dim)] == base, (
                f"{case_id} 的「{FS.DIMENSION_LABELS[dim]}」维度动了 relations"
            )


def test_dimension_scores_within_bounds() -> None:
    for case_id in DIM_CASES:
        for dim in FS.DIMENSIONS:
            for c in K.cached_kline_dim(case_id, dim):
                for key in ("open", "close", "high", "low"):
                    assert 0.0 <= c[key] <= 100.0, (
                        f"{case_id} {FS.DIMENSION_LABELS[dim]} {c['year']} {key}={c[key]} 越界"
                    )


def test_no_dimension_saturates() -> None:
    """任一维度贴到 0/100 硬边界，就说明该维度的侧重系数把 K_SCORE=40 的标定打破了。

    这条是「维度侧重系数不能乱调」的守门人：调大某个十神的权重会把曲线推向边界，
    必须先重跑 `scripts/kline_diagnose.py` 再改。
    """
    saturated: list[str] = []
    for case_id in DIM_CASES:
        for dim in FS.DIMENSIONS:
            for c in K.cached_kline_dim(case_id, dim):
                if c["close"] <= 0 or c["close"] >= 100:
                    saturated.append(f"{case_id}/{FS.DIMENSION_LABELS[dim]}/{c['year']}")
    assert not saturated, f"以下维度分数触及硬边界：{saturated[:10]}"


def test_every_dimension_has_both_up_and_down_candles() -> None:
    """维度切换不能让方向重新退化成常数（见 `test_kline_golden` 里的历史事故）。"""
    degenerate: list[str] = []
    for case_id in DIM_CASES:
        for dim in FS.DIMENSIONS:
            candles = K.cached_kline_dim(case_id, dim)
            ups = sum(1 for c in candles if c["isUp"])
            if ups in (0, len(candles)):
                degenerate.append(f"{case_id}/{FS.DIMENSION_LABELS[dim]}({ups}/{len(candles)})")
    assert not degenerate, f"以下维度方向恒定、实体无信息量：{degenerate}"


# ---------------- 侧重系数本身 ----------------


def test_dimension_emphasis_is_mean_normalized() -> None:
    """侧重系数必须均值归一到 1.0，否则切维度等于换量纲、K_SCORE 标定失效。"""
    for case_id in DIM_CASES:
        chart = K.cached_chart(case_id)
        for dim in NON_COMPREHENSIVE:
            empha = FS.dimension_emphasis(chart, dim)
            assert len(empha) == 5, f"{case_id}/{dim} 侧重表不是 5 个五行：{empha}"
            mean = sum(empha.values()) / len(empha)
            assert abs(mean - 1.0) < MEAN_TOL, f"{case_id}/{dim} 侧重均值 {mean} 未归一"


def test_dimension_emphasis_covers_all_five_wuxing() -> None:
    """侧重表必须覆盖全部五行，且与十神→五行映射一一对应，不得两路撞到同一五行。"""
    for case_id in DIM_CASES:
        chart = K.cached_chart(case_id)
        mapping = FS._shishen_of_wuxing(chart.wuxing.day_master_wuxing)
        assert len(set(mapping.values())) == 5, f"{case_id} 十神→五行映射有重复"
        for dim in FS.DIMENSIONS:
            empha = FS.dimension_emphasis(chart, dim)
            if dim == FS.DIM_COMPREHENSIVE:
                assert empha == {}
                continue
            assert set(empha) == set(mapping.values()), f"{case_id}/{dim} 侧重表五行不全"


def test_love_dimension_depends_on_gender() -> None:
    """感情维度男以财为妻、女以官杀为夫，取用必须相反；其余维度不随性别变。"""
    from app.domain.chart_builder import build_bazi_chart

    male = build_bazi_chart("1985-01-05 00:00", "男")
    female = build_bazi_chart("1985-01-05 00:00", "女")
    assert male.wuxing.day_master_wuxing == female.wuxing.day_master_wuxing

    love_m = FS.dimension_emphasis(male, "love")
    love_f = FS.dimension_emphasis(female, "love")
    assert love_m != love_f, "感情维度对男女给出同一组侧重"

    wealth_wx = FS._shishen_of_wuxing(male.wuxing.day_master_wuxing)["财"]
    officer_wx = FS._shishen_of_wuxing(male.wuxing.day_master_wuxing)["官杀"]
    assert love_m[wealth_wx] > love_f[wealth_wx], "男命感情维度未侧重财星"
    assert love_f[officer_wx] > love_m[officer_wx], "女命感情维度未侧重官杀"

    for dim in ("career", "wealth", "health"):
        assert FS.dimension_emphasis(male, dim) == FS.dimension_emphasis(female, dim), (
            f"「{FS.DIMENSION_LABELS[dim]}」维度不该随性别变化"
        )


def test_study_dimension_structure() -> None:
    """学业维度的侧重结构：印最重（学业文书之本）、食伤次之（聪慧发挥）、财最轻（坏印夺志）。

    钉住 _DIM_EMPHASIS["study"] 的取象次序 —— 只断言偏序关系、不断言具体数值，
    具体数值由指纹层冻结。若有人把学业侧重改成财最重，这条立刻失败。
    """
    from app.domain.chart_builder import build_bazi_chart

    chart = build_bazi_chart("1985-01-05 00:00", "男")
    empha = FS.dimension_emphasis(chart, "study")
    mapping = FS._shishen_of_wuxing(chart.wuxing.day_master_wuxing)
    assert empha[mapping["印枭"]] > empha[mapping["食伤"]], "学业维度印枭应重于食伤"
    assert empha[mapping["食伤"]] > empha[mapping["官杀"]], "学业维度食伤应重于官杀"
    wealth_wx = mapping["财"]
    others = [v for k, v in empha.items() if k != wealth_wx]
    assert all(empha[wealth_wx] < v for v in others), "学业维度财星（坏印夺志）应为最轻"
    # 学业与事业都重印，但事业的官杀（权柄）必须重于学业的官杀 —— 否则两维度区分度不足
    career = FS.dimension_emphasis(chart, "career")
    assert career[mapping["官杀"]] > empha[mapping["官杀"]], "事业维度官杀应重于学业维度官杀"


def test_dimension_is_deterministic() -> None:
    """维度评分同样只由命盘决定：重复调用全等。"""
    case_id = DIM_CASES[0]
    chart = K.cached_chart(case_id)
    first = {dim: K.cached_kline_dim(case_id, dim) for dim in FS.DIMENSIONS}
    again = {dim: FS.build_kline(chart, max_age=K.MAX_AGE, dimension=dim) for dim in FS.DIMENSIONS}
    assert again == first
