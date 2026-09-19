"""命理 K 线黄金快照的构建 / 比对逻辑（供 test 与脚本共用）。

为什么需要它：K 线的分数由 `fortune_score` 里的若干系数（喜忌基准、岁运柱权重、
K 值、关系修正表）共同决定。这些系数**任何一处被顺手改一下，全盘分数都会平移**，
而单测断言（比如"某年 > 60"）抓不住这种整体漂移。必须有"改动前后逐字段全等"的锚点。

三条设计决定：

1. **不另建 cases.json**。用例清单直接复用 `tests.bazi_golden.load_cases()`——
   两套清单必然漂移，而 K 线的正确性本来就依赖同一批命盘的原局口径。
2. **时间与性别等参数同样钉死**。复用 `bazi_golden.case_params`，保证 K 线的
   起运年、流年干支与原局快照取自同一套参数。
3. **月分数与关系串压成单行**。单例约 80 年，若按 list 逐元素缩进写，
   单例膨胀到 30KB+、`git diff` 不可读。压成
   `"45.1,52.3,..."` 与 `"子午冲、寅亥合木"` 后仍**内容敏感**：
   任何一个数变了字符串就变，diff 仍能精确报到是哪一年。

重生成快照：
    UPDATE_GOLDEN=1 ../.venv/Scripts/python.exe -m pytest tests/test_kline_golden.py -q
重生成后**必须人工核对 diff**（尤其 K_SCORE / 关系系数变动会导致全量平移）。

维度指纹同理，但只在 8 个代表命盘上冻结收盘序列（见文件末尾「维度指纹」一节）：
    UPDATE_GOLDEN=1 ../.venv/Scripts/python.exe -m pytest tests/test_kline_dimensions.py -q
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain import fortune_score as FS
from tests import bazi_golden as BG

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "kline_golden"

# K 线覆盖上限：起运年 → 出生年 + MAX_AGE。与原局快照的 liunian 范围无关。
MAX_AGE = 80

# 逐字段比对直接复用 bazi_golden 的实现（含"按标识键定位消失条目"的能力）
diff_paths = BG.diff_paths
get_by_path = BG.get_by_path
update_enabled = BG.update_enabled
load_cases = BG.load_cases
find_case = BG.find_case
build_case_chart = BG.build_case_chart


def compact(candle: dict[str, Any]) -> dict[str, Any]:
    """单根蜡烛 → 快照形态（月分数与关系串压成单行）。"""
    return {
        "year": candle["year"],
        "age": candle["age"],
        "ganzhi": candle["ganzhi"],
        "dayun": candle["dayun"],
        "open": candle["open"],
        "close": candle["close"],
        "high": candle["high"],
        "low": candle["low"],
        "volume": candle["volume"],
        "relationAdj": candle["relationAdj"],
        "volatility": candle["volatility"],
        "isDayunStart": candle["isDayunStart"],
        "isUp": candle["isUp"],
        "monthScores": ",".join(f"{v:g}" for v in candle["monthScores"]),
        "relations": "、".join(candle["relations"]),
    }


def build_kline_snapshot(case: dict[str, Any]) -> dict[str, Any]:
    """构建一个命盘的 K 线快照（走缓存，多次调用只算一次）。"""
    chart = cached_chart(case["id"])
    candles = cached_kline(case["id"])
    return {
        "id": case["id"],
        "desc": case["desc"],
        "birth": case["birth"],
        "gender": case["gender"],
        "maxAge": MAX_AGE,
        "kScore": FS.K_SCORE,
        "favor": FS.chart_favor_summary(chart),
        "kline": [compact(c) for c in candles],
    }


# ---------------- 快照读写 ----------------


def snapshot_path(case_id: str) -> Path:
    return FIXTURE_DIR / f"{case_id}.json"


def write_snapshot(snapshot: dict[str, Any]) -> Path:
    """写入快照；内容无变化则**不落盘**（与 bazi_golden 同策略，保住 diff 可读性）。"""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = snapshot_path(snapshot["id"])
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == payload:
        return path
    path.write_text(payload, encoding="utf-8")
    return path


def read_snapshot(case_id: str) -> dict[str, Any]:
    return json.loads(snapshot_path(case_id).read_text(encoding="utf-8"))


# ---------------- 构建缓存 ----------------
# 单例约 80 年 × 12 个月，一次构建约 0.3s。快照层与不变量层有多条测试都要遍历
# 同一批命盘，若不缓存会重复构建几百次、把测试从秒级拖到分钟级。
# 评分是纯函数，故按 case_id 缓存是安全的。


@lru_cache(maxsize=None)
def cached_chart(case_id: str) -> Any:
    return BG.build_case_chart(find_case(case_id))


@lru_cache(maxsize=None)
def cached_kline(case_id: str) -> list[dict[str, Any]]:
    return FS.build_kline(cached_chart(case_id), max_age=MAX_AGE)


# ---------------- 维度指纹 ----------------
# 维度靠 `_DIM_EMPHASIS` 里的一小组侧重系数驱动。这组数和 K_SCORE 一样属于
# 「顺手改一下全盘平移」的系数，必须有自己的锚点；但它不适合并进逐蜡烛快照
# （36 例 × 5 维度 = 180 条曲线，逐字段写会变成几十万行）。
#
# 折中：只在**有代表性的 8 个命盘**上冻结「收盘分序列」，覆盖正格/专旺/真从/假从/
# 极弱/女命六类。系数一旦漂移，这 8 例里至少一例会变。
# 同时单独存一个文件，**不能放进 `kline_golden/` 目录**
# —— 那里有 `test_no_orphan_snapshot_files` 按用例 id 校验，多出的文件会被判孤儿。

DIM_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kline_dimensions.json"

DIM_FINGERPRINT_CASES = (
    "stem_yi",  # 正格 · 日主偏弱
    "stem_bing",  # 正格 · 日主偏旺
    "zhuanwang_quzhi",  # 专旺 · 曲直格
    "zhuanwang_runxia",  # 专旺 · 润下格
    "cong_true_cai",  # 真从 · 从财格
    "cong_fake_sha",  # 假从 · 假从杀格
    "strength_ji_ruo",  # 极弱档
    "boundary_female",  # 女命（感情维度取用与男命相反）
)


@lru_cache(maxsize=None)
def cached_kline_dim(case_id: str, dimension: str) -> list[dict[str, Any]]:
    return FS.build_kline(cached_chart(case_id), max_age=MAX_AGE, dimension=dimension)


def build_dimension_snapshot() -> dict[str, Any]:
    """构建维度指纹（走缓存，多次调用只算一次）。"""
    cases: dict[str, Any] = {}
    for case_id in DIM_FINGERPRINT_CASES:
        entry: dict[str, Any] = {}
        for dim in FS.DIMENSIONS:
            candles = cached_kline_dim(case_id, dim)
            entry[dim] = {
                "upCount": sum(1 for c in candles if c["isUp"]),
                "closes": ",".join(f"{c['close']:g}" for c in candles),
            }
        cases[case_id] = entry
    return {"maxAge": MAX_AGE, "kScore": FS.K_SCORE, "cases": cases}


def read_dimension_snapshot() -> dict[str, Any]:
    return json.loads(DIM_FIXTURE.read_text(encoding="utf-8"))


def write_dimension_snapshot(snapshot: dict[str, Any]) -> Path:
    """写入维度指纹；内容无变化则不落盘（同 `write_snapshot` 策略）。"""
    DIM_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if DIM_FIXTURE.exists() and DIM_FIXTURE.read_text(encoding="utf-8") == payload:
        return DIM_FIXTURE
    DIM_FIXTURE.write_text(payload, encoding="utf-8")
    return DIM_FIXTURE
