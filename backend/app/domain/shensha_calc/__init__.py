"""神煞计算包：以四柱 + 月支推算全部神煞命中。

对外沿用原单文件模块的接口（`_compute_shensha` / `_zhi_to_month_index`），
故所有调用方无需改动；实现按神煞族拆在以下子模块中：

    _core.py          编排：构造上下文 → 逐族收集 → 去重
    _context.py       四柱派生键（日干/年支/月支/日支/纳音/季节…）与共用小工具
    _day_stem.py      一、以日干/年干查的贵人（天乙/太极/文昌/禄神/羊刃/学堂词馆/…）
    _month_branch.py  二、以月支查（天德/月德/天德合/月德合/德秀/天医）
    _year_branch.py   三、四、以年支（或年支+日支）查（华盖/桃花/驿马/…/灾煞/吊客/病符/…）
    _combinations.py  五、特殊组合（魁罡/十恶大败/三奇贵人/童子煞/…）
    _xunkong.py       六、空亡

**顺序敏感**：`_compute_shensha` 的输出是 list，各族产出按固定顺序拼接，
族内产出顺序亦有语义（先精后粗等）。改动任何族的 yield 顺序都会改变输出，
`tests/test_bazi_golden.py` 的 24 例快照会立刻报出差异字段路径。
"""

from __future__ import annotations

from app.domain.shensha_calc._core import _compute_shensha, _zhi_to_month_index

__all__ = ["_compute_shensha", "_zhi_to_month_index"]
