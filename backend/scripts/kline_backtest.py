"""命理 K 线回测 CLI：拿真实事件标注算命中率，并扫一遍可选口径。

用途：`kline_resonance.py` 与 `fortune_score.py` 里的权重都是**先验**，
`scripts/kline_diagnose.py` 只能证明曲线形状好看，证明不了"分高真的更好过"。
本脚本是唯一能回答后者的入口。

四种用法
--------
1. 看单盘现状：
    ../.venv/Scripts/python.exe scripts/kline_backtest.py
2. 把库里的标注导出成 JSON（便于版本管理与人工复核，再改口径重跑）：
    ../.venv/Scripts/python.exe scripts/kline_backtest.py --dump events.json
3. 拿 JSON 离线跑（不连库；annotation 攒够前先用它验证管线）：
    ../.venv/Scripts/python.exe scripts/kline_backtest.py --events events.json
4. 关系（合盘）回测 —— **共振权重唯一的校准数据源**：
    ../.venv/Scripts/python.exe scripts/kline_backtest.py --pair
    ../.venv/Scripts/python.exe scripts/kline_backtest.py --pair --dump pair_events.json

单盘事件只能校准"这个人这年过得好不好"；"这两人这年顺不顺"才校准得了共振分。
`--pair` 会额外打印**逐项诊断**（`delta = 实际吉年均值 − 实际凶年均值`）：
`delta <= 0` 的那一项（或其符号）与现实相反，是调权重该先看的地方。
注意合盘**没有 `--predictor`**（只有一个预测源：共振分），`dimension` 也不接受 `auto`
（关系事件没有事业/健康之分）。

`--sweep` 会把（单盘：predictor × dimension / 合盘：dimension）的组合各跑一遍并列表对比：
口径的选择**必须由数据决定**，而不是由"哪个数好看"决定。

退出码：0 正常；2 = 事件库为空，或 `--require-significant` 下未达显著（可挂 CI）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain import (
    fortune_score as FS,  # noqa: E402
    kline_backtest as KB,  # noqa: E402
)

# 扫参组合（dimension × predictor）
SWEEP_DIMENSIONS = (KB.DIMENSION_AUTO, *FS.DIMENSIONS)


def _load_events(path: str) -> list[dict]:
    data = json.loads(open(path, encoding="utf-8").read())
    items = data.get("items", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SystemExit(f"{path} 里没找到事件列表（应为 [...] 或 {{'items': [...]}}）")
    return items


def _load_from_db() -> list[dict]:
    from app.db.chart_store import list_kline_events

    return list_kline_events(limit=10000)


def _load_pair_events_from_db() -> list[dict]:
    from app.db.chart_store import list_kline_pair_events

    return list_kline_pair_events(limit=10000)


def _pct(v: float | None) -> str:
    return "  —  " if v is None else f"{v * 100:5.1f}%"


def _pp(v: float | None) -> str:
    return "  —  " if v is None else f"{v * 100:+5.1f}pp"


def _summary_line(label: str, s: dict) -> str:
    ci = s.get("ci95")
    ci_txt = f"[{ci[0] * 100:.1f},{ci[1] * 100:.1f}]" if ci else "—"
    return (
        f"  {label:<26} n={s['samples']:<5} 命中 {_pct(s['hitRate'])} "
        f"基线 {_pct(s['randomBaseline'])} lift {_pp(s['lift'])} 95%CI {ci_txt}"
    )


def _print_groups(title: str, groups: list[dict], key: str) -> list[str]:
    lines = [f"\n  {title}"]
    for g in groups[:12]:
        lines.append(_summary_line(str(g[key])[:26], g))
    return lines


def report(result: dict) -> list[str]:
    s = result["summary"]
    lines = [
        f"事件 {result['events']['used']} 条已用 / "
        f"{result['events']['unmatched']} 条在 K 线区间外 / "
        f"{result['events']['invalid']} 条非法 / "
        f"{result['events']['duplicate']} 条重复；涉及 {result['charts']} 张盘，"
        f"年份 {result['yearFrom']}–{result['yearTo']}",
        f"口径：dimension={result['dimension']} predictor={result['predictor']}",
        "",
        _summary_line("合计", s),
        f"  严格口径（仅实际有吉凶的 {s['decided']} 条）"
        f"  命中 {_pct(s['hitRateStrict'])} 基线 {_pct(s['randomBaselineStrict'])} "
        f"lift {_pp(s['liftStrict'])}",
        f"  多数类基线（恒猜最多的一类）{_pct(s['majorityBaseline'])}",
    ]
    if not s["ok"]:
        lines.append(f"  结论：不可用 —— 样本 {s['samples']} 条 < 下限 {result['minSamples']} 条。")
    elif s["significant"]:
        lines.append("  结论：命中率显著高于随机基线（95% 区间下界高于基线），有区分度。")
    else:
        lines.append("  结论：暂判不出区分度 —— 命中率未显著高于随机基线，别急着调权重。")

    lines += _print_groups("按领域", result["byDomain"], "domain")
    lines += _print_groups("按维度", result["byDimension"], "dimension")
    lines += _print_groups("按命盘", result["byChart"], "chart")

    if result["misses"]:
        lines.append("\n  错判样例（惊讶度由高到低，供人工复盘）")
        for m in result["misses"]:
            lines.append(
                f"    {m['year']} {m['ganzhi']}  预测 {m['pred']}({m['score']:.1f})  "
                f"实际 {m['truth']}  {m['domain']}  {m['note'][:30]}"
            )
    for w in result["warnings"]:
        lines.append(f"\n  ⚠ {w}")
    return lines


def sweep(pairs: list[tuple]) -> list[dict]:
    """predictor × dimension 全组合各跑一遍。样本不变、只换口径。"""
    out = []
    for predictor in KB.PREDICTORS:
        for dimension in SWEEP_DIMENSIONS:
            r = KB.run_backtest(pairs, dimension=dimension, predictor=predictor)
            out.append(r)
    return out


def pair_sweep(pairs: list[tuple]) -> list[dict]:
    """合盘只扫 dimension —— 预测源只有一个（共振分），没有 predictor 可换。"""
    return [
        KB.run_pair_backtest(pairs, dimension=dimension)
        for dimension in FS.DIMENSIONS
    ]


# ---------------- 关系（合盘）回测的报告 ----------------
#
# 与单盘报告的三处差别（都不是排版偏好）
# 1. 分母是「对」不是「张盘」：一件事关两个人，一个人可能有好几段关系。
# 2. **必须打印逐项诊断**：合盘产出不只是"准不准"，而是"哪一项 term 的方向与现实相反"，
#    那才是校准权重的输入。20 个数字读不了手机，只有控制台摆得下。
# 3. 要打印**回测窗口**：事件落在窗口外时只说"N 条没用上"，用户会以为是自己没录进去。

def _term_rows(diags: list[dict]) -> list[str]:
    """逐项诊断表。`delta <= 0` 明确标成「相反」并置顶 —— 那是调参的第一顺位。"""
    lines = [
        "\n  逐项诊断（delta = 实际吉年均值 − 实际凶年均值；<=0 说明该项方向与现实相反）",
        f"    {'term':<8}{'吉年均值':>10}{'凶年均值':>10}{'delta':>9}  样本(吉/凶)  方向",
    ]
    for d in sorted(diags, key=lambda x: (x["delta"] is None, x["delta"] if x["delta"] is not None else 0)):
        mu = "  —  " if d["meanUp"] is None else f"{d['meanUp']:9.3f}"
        md = "  —  " if d["meanDown"] is None else f"{d['meanDown']:9.3f}"
        delta = "  —  " if d["delta"] is None else f"{d['delta']:+8.3f}"
        if d["signOk"] is None:
            verdict = "样本不足"
        elif d["signOk"]:
            verdict = "正确"
        else:
            verdict = "相反 ← 权重该先调这里"
        lines.append(
            f"    {d['term']:<8}{mu:>10}{md:>10}{delta:>9}  "
            f"{d['samplesUp']:>4}/{d['samplesDown']:<4}  {verdict}"
        )
    return lines


def pair_report(result: dict) -> list[str]:
    s = result["summary"]
    span = (
        f"{result['spanFrom']}–{result['spanTo']}"
        if result["spanFrom"] is not None
        else "（无可建盘的配对）"
    )
    lines = [
        f"关系事件 {result['events']['used']} 条已用 / "
        f"{result['events']['unmatched']} 条在共振区间外 / "
        f"{result['events']['invalid']} 条非法 / "
        f"{result['events']['duplicate']} 条重复；涉及 {result['pairs']} 对，"
        f"命中年份 {result['yearFrom']}–{result['yearTo']}",
        f"回测窗口 {span}（阈值固定按 1-{result['ageSpan']} 虚岁取全期分位，不随事件伸缩）",
        f"口径：dimension={result['dimension']} predictor={result['predictor']}（合盘只有共振一个预测源）",
        "",
        _summary_line("合计", s),
        f"  严格口径（仅实际有顺逆的 {s['decided']} 条）"
        f"  命中 {_pct(s['hitRateStrict'])} 基线 {_pct(s['randomBaselineStrict'])} "
        f"lift {_pp(s['liftStrict'])}",
        f"  多数类基线（恒猜最多的一类）{_pct(s['majorityBaseline'])}",
    ]
    if not s["ok"]:
        lines.append(f"  结论：不可用 —— 样本 {s['samples']} 条 < 下限 {result['minSamples']} 条。")
    elif s["significant"]:
        lines.append("  结论：共振分显著高于随机基线 —— 这才谈得上反推权重。")
    else:
        lines.append("  结论：暂判不出区分度 —— 别急着调权重，先看下面的逐项诊断。")

    lines += _term_rows(result["termDiagnostics"])
    lines += _print_groups("按关系类型", result["byRelation"], "relation")
    lines += _print_groups("按配对", result["byPair"], "pair")

    if result["misses"]:
        lines.append("\n  错判样例（惊讶度由高到低，供人工复盘）")
        for m in result["misses"]:
            lines.append(
                f"    {m['year']} {m['ganzhi']}  预测 {m['pred']}({m['score']:.1f})  "
                f"实际 {m['truth']}  {m['relation']}  {m['note'][:30]}"
            )
    for w in result["warnings"]:
        lines.append(f"\n  ⚠ {w}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="命理 K 线回测")
    ap.add_argument("--events", help="事件 JSON 路径（缺省则从数据库读）")
    ap.add_argument("--dump", help="把读出的事件导出到 JSON 后退出")
    ap.add_argument(
        "--pair",
        action="store_true",
        help="关系（合盘）回测：读 kline_pair_events，校准的是共振权重",
    )
    ap.add_argument("--dimension", default=None, choices=(KB.DIMENSION_AUTO, *FS.DIMENSIONS))
    ap.add_argument("--predictor", default=KB.PREDICTOR_CLOSE, choices=KB.PREDICTORS)
    ap.add_argument("--min-samples", type=int, default=KB.DEFAULT_MIN_SAMPLES)
    ap.add_argument("--sweep", action="store_true", help="扫一遍可选口径")
    ap.add_argument("--json", action="store_true", help="输出原始 JSON")
    ap.add_argument(
        "--require-significant",
        action="store_true",
        help="未达统计显著时以退出码 2 结束（可挂 CI）",
    )
    args = ap.parse_args(argv)

    # 合盘没有 auto 映射，也没有 predictor 可换 —— 提前拦下来，别让用户以为参数生效了
    if args.pair:
        if args.dimension == KB.DIMENSION_AUTO:
            ap.error("--pair 不接受 --dimension auto：关系事件没有事业/健康之分")
        if args.predictor != KB.PREDICTOR_CLOSE:
            ap.error("--pair 不接受 --predictor：合盘只有一个预测源（共振分）")

    events = _load_events(args.events) if args.events else (
        _load_pair_events_from_db() if args.pair else _load_from_db()
    )
    if args.dump:
        payload = json.dumps({"items": events}, ensure_ascii=False, indent=2)
        with open(args.dump, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
        print(f"已导出 {len(events)} 条事件 → {args.dump}")
        return 0
    if not events:
        kind = "关系" if args.pair else ""
        path = "pair-events" if args.pair else "events"
        print(f"{kind}事件库为空：先用 POST /api/ai/xianzhi/kline/{path} 录入真实事件标注。")
        return 2

    if args.pair:
        return _run_pair(args, events)
    return _run_single(args, events)


def _run_single(args: argparse.Namespace, events: list[dict]) -> int:
    from app.api.xianzhi_kline import _backtest_pairs

    # 命令行不设盘数上限（接口层的 MAX_BACKTEST_CHARTS 是给 HTTP 请求兜底的），
    # 故 max_charts 传 None。
    pairs, _ = _backtest_pairs(events)

    result = KB.run_backtest(
        pairs,
        dimension=args.dimension or KB.DIMENSION_AUTO,
        predictor=args.predictor,
        min_samples=args.min_samples,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n".join(report(result)))

    if args.sweep:
        rows = sweep(pairs)
        print("\n口径对比（命中率 / 严格口径 / lift / 是否显著）")
        print(f"  {'predictor':<10}{'dimension':<16}{'n':>5}{'命中':>9}{'严格':>9}{'lift':>10}  显著")
        for r in rows:
            s = r["summary"]
            print(
                f"  {r['predictor']:<10}{r['dimension']:<16}{s['samples']:>5}"
                f"{_pct(s['hitRate']):>9}{_pct(s['hitRateStrict']):>9}{_pp(s['lift']):>10}"
                f"  {'是' if s['significant'] else '否'}"
            )
        print("  提示：扫参看的是「哪个口径更有区分度」，不是「哪个数最高」——"
              "样本少时最高分通常只是运气，务必看 lift 与显著性两列。")

    if args.require_significant and not result["summary"]["significant"]:
        return 2
    return 0


def _run_pair(args: argparse.Namespace, events: list[dict]) -> int:
    from app.api.xianzhi_kline import _backtest_pair_groups

    pairs, _ = _backtest_pair_groups(events)
    dimension = args.dimension or FS.DIM_COMPREHENSIVE
    result = KB.run_pair_backtest(
        pairs, dimension=dimension, min_samples=args.min_samples
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n".join(pair_report(result)))

    if args.sweep:
        rows = pair_sweep(pairs)
        print("\n维度对比（命中率 / 严格口径 / lift / 是否显著 / 方向相反的项）")
        print(f"  {'dimension':<16}{'n':>5}{'命中':>9}{'严格':>9}{'lift':>10}  显著  方向反了")
        for r in rows:
            s = r["summary"]
            bad = [d["term"] for d in r["termDiagnostics"] if d["signOk"] is False]
            print(
                f"  {r['dimension']:<16}{s['samples']:>5}"
                f"{_pct(s['hitRate']):>9}{_pct(s['hitRateStrict']):>9}{_pp(s['lift']):>10}"
                f"  {'是' if s['significant'] else '否':<4}  {'/'.join(bad) or '—'}"
            )
        print("  提示：共振权重是**四个 term 的相对大小**在决定排序，"
              "所以先看「方向反了」那一列，再看命中率。")

    if args.require_significant and not result["summary"]["significant"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
