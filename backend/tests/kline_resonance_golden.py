"""合盘共振线的黄金快照构建 / 比对逻辑（供 test 与脚本共用）。

为什么需要它
------------
共振分 = 基线 + `trend`/`align`/`sync`/`palace` 四项逐年修正，其中
`BASE_UNIT`/`TREND_UNIT`/`ALIGN_UNIT`/`SYNC_UNIT`/`PALACE_UNIT`/`MOVE_SPAN`/`ALIGN_SPAN`
**任何一处被顺手改一下，整条共振线都会平移**，而单测里的「某年 > 50」抓不住。
同时共振线还依赖 `fortune_score` 的喜忌口径 —— 单盘 K 线快照能守住单盘，
守不住"两盘合起来"的这一层，故必须有自己的锚点。

成对用例怎么选
--------------
共振的正确性依赖**配对的两端**，所以不能像单盘那样遍历 36 个用例（那会变成 36×36）。
折中：手工挑 8 对，覆盖共振里所有会分叉的分支 ——

- 日主同类/相生/相克三种基线关系各一对
- 同日主但性别不同（感情维度的取用男女相反）
- 专旺 × 从格（两端的特殊格局）
- 真从 × 假从（大运是否破格）
- 立春前 × 立春后（起运方向相反的盘，年份交集会缩短）
- 极弱 × 专旺（强弱两端）

重生成快照：
    UPDATE_GOLDEN=1 ../.venv/Scripts/python.exe -m pytest tests/test_kline_resonance.py -q
重生成后**必须人工核对 diff**（尤其权重变动会导致全量平移）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain import fortune_score as FS, kline_resonance as KR
from tests import bazi_golden as BG

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "kline_resonance"
MAX_AGE = 80

update_enabled = BG.update_enabled
load_cases = BG.load_cases
find_case = BG.find_case
build_case_chart = BG.build_case_chart
diff_paths = BG.diff_paths

# (甲, 乙, 说明) —— 说明只用于快照可读性，不参与计算。
PAIRS: tuple[tuple[str, str, str], ...] = (
    ("stem_ren", "stem_ren", "日主同类 · 同干自配对（基线最高的一类）"),
    ("stem_ren", "stem_jia", "日主相生 · 壬水 × 甲木"),
    ("stem_ren", "stem_bing", "日主相克 · 壬水 × 丙火"),
    ("stem_jia", "boundary_female", "同日主不同性别 · 感情维度取用相反"),
    ("zhuanwang_runxia", "cong_true_cai", "专旺 × 真从（两端特殊格局）"),
    ("cong_true_sha", "cong_fake_sha", "真从 × 假从（大运是否破格）"),
    ("boundary_lichun_before", "boundary_lichun_after", "起运方向相反 · 年份交集缩短"),
    ("strength_ji_ruo", "zhuanwang_quzhi", "极弱 × 专旺（强弱两端）"),
)


def pair_key(id_a: str, id_b: str) -> str:
    return f"{id_a}__{id_b}"


def snapshot_path(id_a: str, id_b: str) -> Path:
    return FIXTURE_DIR / f"{pair_key(id_a, id_b)}.json"


@lru_cache(maxsize=None)
def cached_resonance(id_a: str, id_b: str, dimension: str) -> dict[str, Any]:
    """一对命盘的共振结果（走缓存：快照层与专项层会重复取同一对）。"""
    return KR.build_resonance(
        build_case_chart(find_case(id_a)),
        build_case_chart(find_case(id_b)),
        max_age=MAX_AGE,
        dimension=dimension,
    )


def _series(rows: list[dict[str, Any]], key: str, *, nested: str = "") -> str:
    """把逐年数值压成单行，保持**内容敏感**：任何一个数变了字符串就变。"""
    out = []
    for r in rows:
        v = r[nested][key] if nested else r[key]
        out.append(f"{v:g}" if isinstance(v, (int, float)) else str(v))
    return ",".join(out)


def build_snapshot(id_a: str, id_b: str) -> dict[str, Any]:
    """一对命盘的共振快照。逐年五项各压成一串，便于定位漂移出在哪一项。"""
    case_a, case_b = find_case(id_a), find_case(id_b)
    res = cached_resonance(id_a, id_b, FS.DIM_COMPREHENSIVE)
    rows = res["years"]
    return {
        "pair": pair_key(id_a, id_b),
        "cases": [
            {"id": id_a, "desc": case_a.get("desc", ""), "birth": case_a["birth"], "gender": case_a["gender"]},
            {"id": id_b, "desc": case_b.get("desc", ""), "birth": case_b["birth"], "gender": case_b["gender"]},
        ],
        "maxAge": MAX_AGE,
        "dimension": FS.DIM_COMPREHENSIVE,
        "base": res["base"],
        "years": {
            "start": rows[0]["year"] if rows else None,
            "end": rows[-1]["year"] if rows else None,
            "count": len(rows),
            "ganzhi": _series(rows, "ganzhi"),
            "resonance": _series(rows, "resonance"),
            "trend": _series(rows, "trend", nested="terms"),
            "align": _series(rows, "align", nested="terms"),
            "sync": _series(rows, "sync", nested="terms"),
            "palace": _series(rows, "palace", nested="terms"),
        },
    }


def write_snapshot(snapshot: dict[str, Any]) -> Path:
    """写入快照；内容无变化则**不落盘**，保住 diff 可读性。"""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    id_a, id_b = snapshot["pair"].split("__", 1)
    path = snapshot_path(id_a, id_b)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == payload:
        return path
    path.write_text(payload, encoding="utf-8")
    return path


def read_snapshot(id_a: str, id_b: str) -> dict[str, Any]:
    return json.loads(snapshot_path(id_a, id_b).read_text(encoding="utf-8"))
