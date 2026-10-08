"""神煞计算编排：构造上下文 → 逐族收集 → 去重成列表。

原为 513 行的单一函数 `_compute_shensha`。拆族后本模块只负责：
1. 空输入短路；
2. 构造只读上下文 `ShenshaContext`；
3. **按固定顺序**拼接各族的 `(name, desc, pillar)` 产出，经统一 `add()` 去重。

**顺序即契约**：`add()` 的调用顺序决定返回列表顺序，且各族内产出顺序也有语义
（如学堂词馆"先精后粗"、三奇贵人"顺次连续不隔柱"）。任何顺序改动都会被
`tests/test_bazi_golden.py` 的 24 例快照报出具体字段路径。

族划分见 `app/domain/shensha_calc/__init__.py`。
"""

from __future__ import annotations

from app.domain.models import Pillar
from app.domain.shensha_calc import _combinations, _day_stem, _month_branch, _year_branch
from app.domain.shensha_calc._context import ShenshaContext, zhi_to_month_index as _zhi_to_month_index

__all__ = ["_compute_shensha", "_zhi_to_month_index"]


def _compute_shensha(pillars: list[Pillar], gender_int: int | None = None) -> list[dict[str, str]]:
    """根据四柱干支计算传统神煞。

    以日干、年支、日支、月支为查表主键，遍历四柱地支判断是否带神煞。
    返回 [{"name": "天乙贵人", "description": "日干甲见丑，逢凶化吉"}, ...]
    """
    if not pillars:
        return []

    ctx = ShenshaContext.build(pillars, gender_int)

    result: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(name: str, desc: str, pillar_name: str = ""):
        key = f"{name}-{pillar_name}"
        if key in seen:
            return
        seen.add(key)
        result.append({"name": name, "description": desc, "pillar": pillar_name})

    # 一、以日干/年干查的贵人系（见 _day_stem）
    for hit in _day_stem.collect(ctx):
        add(*hit)

    # 二、以月支查（见 _month_branch）
    for hit in _month_branch.collect(ctx):
        add(*hit)

    # 三、以年支/日支查（见 _year_branch）
    for hit in _year_branch.collect_year_day_branch(ctx):
        add(*hit)

    # 四、以年支查的专属神煞（见 _year_branch）
    for hit in _year_branch.collect_year_branch(ctx):
        add(*hit)

    # 五、特殊组合类神煞（见 _combinations）
    for hit in _combinations.collect_combinations(ctx):
        add(*hit)

    # 六、空亡（见 _combinations）
    for hit in _combinations.collect_xunkong(ctx):
        add(*hit)

    return result
