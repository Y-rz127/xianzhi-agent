"""命理 K 线黄金快照与结构不变量。

两层防线，各自解决不同问题：

- **快照层**（`test_kline_matches_snapshot`）：抓"系数被顺手改一下导致全盘平移"。
  单测断言（如"某年 > 60"）对整体平移无感，只有逐字段锚点能发现。
- **不变量层**：抓"分数还能算出来、但结构已经不自洽"。
  其中 `test_candle_ohlc_derives_from_month_scores` 是本设计的核心契约——
  收盘必须**等于**该年末月分数、开盘必须**等于**上年收盘。一旦有人为了"让图好看"
  直接把 score 写进 open/close，或者把 open 改回某个固定月分，这条会立刻失败。

重生成快照：
    UPDATE_GOLDEN=1 ../.venv/Scripts/python.exe -m pytest tests/test_kline_golden.py -q
重生成后必须人工核对 diff。
"""

from __future__ import annotations

import pytest

from tests import kline_golden as K

CASES = K.load_cases()
CASE_IDS = [c["id"] for c in CASES]

MONTHS_PER_YEAR = 12


# ---------------- 快照层 ----------------


def _regenerate_or_compare(case: dict) -> None:
    actual = K.build_kline_snapshot(case)
    path = K.snapshot_path(case["id"])

    if K.update_enabled() or not path.exists():
        K.write_snapshot(actual)
        if not path.exists():  # pragma: no cover - 写入失败才走到
            pytest.fail(f"快照写入失败：{path}")
        return

    expected = K.read_snapshot(case["id"])
    diffs = K.diff_paths(expected, actual)
    if diffs:
        head = "\n".join(f"  - {d}" for d in diffs[:25])
        more = f"\n  …另有 {len(diffs) - 25} 处" if len(diffs) > 25 else ""
        pytest.fail(
            f"K 线快照不一致（case={case['id']}，{case['desc']}），共 {len(diffs)} 处差异：\n"
            f"{head}{more}\n"
            "若为刻意的口径调整（K_SCORE / 喜忌系数 / 关系修正表），"
            "确认变化符合预期后执行 UPDATE_GOLDEN=1 重生成。"
        )


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_kline_matches_snapshot(case: dict) -> None:
    _regenerate_or_compare(case)


def test_every_case_has_snapshot_file() -> None:
    missing = [c["id"] for c in CASES if not K.snapshot_path(c["id"]).exists()]
    assert not missing, f"以下用例缺少 K 线快照：{missing}"


def test_no_orphan_snapshot_files() -> None:
    known = {f"{c['id']}.json" for c in CASES}
    on_disk = {p.name for p in K.FIXTURE_DIR.glob("*.json")}
    assert not (on_disk - known), f"存在无对应用例的 K 线快照：{sorted(on_disk - known)}"


def test_snapshot_records_calibration_k() -> None:
    """K 值必须写进快照 —— 它一变全盘平移，快照里不记就无从判断量级。"""
    for case in CASES:
        snap = K.read_snapshot(case["id"])
        assert snap["kScore"] == K.FS.K_SCORE, f"{case['id']} 的 kScore 与实际不一致"


# ---------------- 不变量层 ----------------


def test_candle_ohlc_derives_from_month_scores() -> None:
    """核心契约：收=末月分数、开=上年收盘、高低是「月序列极值 ∪ 开收」± 波动。

    这条防的是"为了让图好看，把某个好看的分数直接塞进 open/close"。
    """
    for case in CASES:
        prev_close = None
        for candle in K.cached_kline(case["id"]):
            months = candle["monthScores"]
            year = candle["year"]
            assert len(months) == MONTHS_PER_YEAR, f"{case['id']} {year} 月数不是 12"
            assert candle["close"] == months[-1], f"{case['id']} {year} 收 ≠ 末月分数"
            assert candle["open"] == (months[0] if prev_close is None else prev_close), (
                f"{case['id']} {year} 开 ≠ 上年收盘（首年才取寅月分数）"
            )
            vol = candle["volatility"]
            pool = [*months, candle["open"], candle["close"]]
            assert candle["high"] == round(min(100.0, max(pool) + vol), 1), (
                f"{case['id']} {year} 高 ≠ 极值+波动"
            )
            assert candle["low"] == round(max(0.0, min(pool) - vol), 1), (
                f"{case['id']} {year} 低 ≠ 极值−波动"
            )
            prev_close = candle["close"]


def test_candles_are_contiguous() -> None:
    """相邻蜡烛首尾相接：本根 open 必须等于上一根 close。

    这条是「实体 = 同比运势升降」语义的锚。若有人把 open 改回某个固定月分，
    实体方向会被"该盘喜木还是喜土"锁死，此断言会立即失败。
    """
    for case in CASES:
        candles = K.cached_kline(case["id"])
        for prev, cur in zip(candles, candles[1:]):
            assert cur["open"] == prev["close"], (
                f"{case['id']} {prev['year']}→{cur['year']} 断裂："
                f"前收 {prev['close']} ≠ 本开 {cur['open']}"
            )


def test_every_case_has_both_up_and_down_candles() -> None:
    """每张盘都必须同时出现阳线与阴线 —— 防"方向常数化"退化回归。

    历史事故：open=寅月(木) / close=丑月(土) 时，两处只差一个流月权重，
    寅丑的固定五行差压过随年份变化的月干差，实测 36/36 盘全阳或全阴，
    实体方向零信息量。改成 open=上年收盘后恢复为 36/36 盘有阳有阴。
    """
    degenerate = []
    for case in CASES:
        candles = K.cached_kline(case["id"])
        ups = sum(1 for c in candles if c["isUp"])
        if ups == 0 or ups == len(candles):
            degenerate.append(f"{case['id']}({ups}/{len(candles)} 阳)")
    assert not degenerate, f"以下命盘 K 线方向恒定、实体无信息量：{degenerate}"


def test_candle_range_is_ordered() -> None:
    """low ≤ min(开,收) ≤ max(开,收) ≤ high —— K 线的立身之本。"""
    for case in CASES:
        for c in K.cached_kline(case["id"]):
            lo, hi = c["low"], c["high"]
            assert lo <= hi, f"{case['id']} {c['year']} 低 > 高（{lo} > {hi}）"
            assert lo <= min(c["open"], c["close"]), f"{case['id']} {c['year']} 低价高于实体"
            assert hi >= max(c["open"], c["close"]), f"{case['id']} {c['year']} 高价低于实体"


def test_all_scores_within_bounds() -> None:
    for case in CASES:
        for c in K.cached_kline(case["id"]):
            for key in ("open", "close", "high", "low"):
                assert 0.0 <= c[key] <= 100.0, f"{case['id']} {c['year']} {key}={c[key]} 越界"


def test_every_case_has_score_variation() -> None:
    """每个命盘的收盘分必须有起伏 —— 全平线说明喜忌方向算成了恒定值。"""
    for case in CASES:
        closes = {c["close"] for c in K.cached_kline(case["id"])}
        assert len(closes) > 5, f"{case['id']} 收盘分只有 {len(closes)} 个取值，K 线退化成平线"


def test_kline_starts_at_first_dayun_year() -> None:
    """K 线起点必须是起运年 —— 童限期无大运可论，不从出生年硬画。"""
    for case in CASES:
        chart = K.cached_chart(case["id"])
        candles = K.cached_kline(case["id"])
        assert candles, f"{case['id']} K 线为空"
        assert candles[0]["year"] == chart.dayun[0].start_year
        assert candles[0]["isDayunStart"] is True


def test_relations_cover_whole_span() -> None:
    """关系串必须跨全区间可用。

    若改回 `liunian_relations`（只覆盖 chart.liunian 的 5 年），覆盖率会掉到
    约 5/76 = 7%，这里立刻失败。不断言 100%：确实存在"流年与本命毫无刑冲合害"
    的年份（实测 zhuanwang_runxia 有 1/76 年如此），那是正确结果而非缺陷。
    """
    for case in CASES:
        candles = K.cached_kline(case["id"])
        with_rel = sum(1 for c in candles if c["relations"])
        ratio = with_rel / len(candles)
        assert ratio > 0.9, (
            f"{case['id']} 仅 {with_rel}/{len(candles)} 年有关系串，"
            "可能又走回了只覆盖 5 年的 liunian_relations"
        )


# ---------------- 喜忌方向守卫 ----------------


def test_favor_direction_follows_strength() -> None:
    """正格方向守卫：偏弱档喜比劫、偏旺档忌比劫。方向反了 K 线会整体镜像。

    **印重之盘排除在「偏旺忌比劫」之外**：那是「印多之病」，比劫是泄印的药
    （04 文档 §三.2），喜比劫正是对的。该路径由 `test_favor_yongshen.py` 单独守卫，
    此处不重复断言，免得把病药论的正确结论判成故障。
    """
    checked = 0
    for case in CASES:
        chart = K.cached_chart(case["id"])
        w = chart.wuxing
        if w.special_pattern:  # 专旺/从格另判
            continue
        if K.FS.detect_ailment(chart):  # 印重之病另判
            continue
        favor = K.FS.favor_vector(chart)
        self_sign = favor.get(w.day_master_wuxing, 0.0)
        if w.strength in ("偏弱", "极弱"):
            assert self_sign > 0, f"{case['id']} {w.strength} 却忌比劫"
            checked += 1
        elif w.strength in ("偏旺", "极旺"):
            assert self_sign < 0, f"{case['id']} {w.strength} 却喜比劫"
            checked += 1
    assert checked >= 6, f"方向守卫只覆盖了 {checked} 例，正格样本不足"


def test_zhuanwang_favors_self_and_opposes_officer() -> None:
    """专旺格宜顺不宜逆：喜比劫助旺、最忌官杀逆克。两处任一写反，该档 K 线整体镜像。"""
    checked = 0
    for case in CASES:
        chart = K.cached_chart(case["id"])
        w = chart.wuxing
        if w.special_pattern != "专旺":
            continue
        officer = K.FS._controller_of(w.day_master_wuxing)
        favor = K.FS.favor_vector(chart)
        assert favor.get(w.day_master_wuxing, 0.0) > 0, f"{case['id']} 专旺却不喜比劫助旺"
        assert favor.get(officer, 0.0) < 0, f"{case['id']} 专旺却喜官杀（{officer}）"
        checked += 1
    assert checked >= 5, f"专旺方向守卫只覆盖 {checked} 例"


def test_conging_opposes_resource() -> None:
    """从格以印为破格之神：印生身即扶身破从，四个子格无一例外。

    刻意**不**断言从儿格忌比劫 —— 从儿格食伤由比劫所生，比劫是「儿之源」，
    引擎自身的断语也只写「切忌木制儿、水犯怒」（忌印、忌官杀），未忌比劫。
    断言比劫全忌会与引擎既有口径冲突。
    """
    checked = 0
    for case in CASES:
        chart = K.cached_chart(case["id"])
        w = chart.wuxing
        if w.special_pattern not in ("从格", "假从"):
            continue
        resource = K.FS._producer_of(w.day_master_wuxing)
        favor = K.FS.favor_vector(chart)
        assert favor.get(resource, 0.0) < 0, f"{case['id']} {w.strength} 却喜印星（{resource}）"
        checked += 1
    assert checked >= 8, f"从格方向守卫只覆盖 {checked} 例"


def test_conging_favors_the_followed_element() -> None:
    """所从之神必须是喜神：从财喜财、从杀喜官杀、从儿喜食伤、从势财官并喜。

    方向表若把子格映射写错（如从财喜了官杀），K 线在这一档会整体反向。
    """
    wealth_officer_output = {
        "财": "wealth",
        "杀": "officer",
        "儿": "output",
    }
    checked = 0
    for case in CASES:
        chart = K.cached_chart(case["id"])
        w = chart.wuxing
        if w.special_pattern not in ("从格", "假从"):
            continue
        kind = w.strength.replace("假从", "").replace("从", "").replace("格", "")
        day_wx = w.day_master_wuxing
        favor = K.FS.favor_vector(chart)
        wx = {
            "wealth": K.FS.CONTROLS[day_wx],
            "officer": K.FS._controller_of(day_wx),
            "output": K.FS.GENERATES[day_wx],
        }
        if kind == "势":  # 财官两行相当
            assert favor[wx["wealth"]] > 0 and favor[wx["officer"]] > 0, (
                f"{case['id']} 从势格未并喜财官"
            )
        else:
            key = wealth_officer_output[kind]
            assert favor[wx[key]] > 0, f"{case['id']} {w.strength} 未喜所从之神（{key}）"
        checked += 1
    assert checked >= 8, f"所从之神守卫只覆盖 {checked} 例"


# ---------------- 确定性 ----------------


def test_build_is_deterministic() -> None:
    """同一用例连续构建两次必须全等，否则快照每次跑都变、测试形同虚设。"""
    case = CASES[0]
    assert K.build_kline_snapshot(case) == K.build_kline_snapshot(case)


def test_scores_do_not_depend_on_system_clock() -> None:
    """评分只由命盘决定，不含"今天"。造两个 today 不同的命盘，K 线必须一致。"""
    import datetime

    case = CASES[0]
    chart_a = K.build_case_chart(case)
    chart_b = K.BG.build_bazi_chart(
        case["birth"],
        case["gender"],
        liunian_start_year=K.BG.LIUNIAN_START_YEAR,
        today=datetime.date.fromisoformat(K.BG.REFERENCE_DATE) - datetime.timedelta(days=400),
    )
    assert K.FS.build_kline(chart_a, max_age=K.MAX_AGE) == K.FS.build_kline(
        chart_b, max_age=K.MAX_AGE
    )


# ---------------- write_snapshot 的幂等 ----------------


def test_write_snapshot_is_idempotent(tmp_path, monkeypatch) -> None:
    """内容未变时不落盘，否则 UPDATE_GOLDEN 会把全部 mtime 刷新、diff 看不出范围。"""
    monkeypatch.setattr(K, "FIXTURE_DIR", tmp_path)
    snap = K.build_kline_snapshot(CASES[0])

    path = K.write_snapshot(snap)
    first_mtime = path.stat().st_mtime_ns

    K.write_snapshot(snap)
    assert path.stat().st_mtime_ns == first_mtime, "内容未变却重写了文件"

    changed = dict(snap)
    changed["desc"] = snap["desc"] + "（已改）"
    K.write_snapshot(changed)
    assert path.stat().st_mtime_ns != first_mtime, "内容变化却未落盘"
