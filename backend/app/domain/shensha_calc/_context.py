"""四柱派生键与共用小工具：各族计算只读这里的值，不再各自重算。

原 `_compute_shensha` 把 day_gan / year_zhi / month_zhi / day_zhi / 纳音五行 /
季节 / 月份索引 等派生值散在 513 行的开头与各处，拆族后必须集中一处，
否则容易出现"某族用了另一个口径的月支"这类静默不一致。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import Pillar
from app.domain.tables import BRANCH_ORDER, SEASON_OF_BRANCH

# 阳干集合（勾绞煞/元辰依"年干阴阳 + 性别"定向）
YANG_GAN = frozenset({"甲", "丙", "戊", "庚", "壬"})


def zhi_to_month_index(zhi: str) -> int:
    """地支 → 农历月份索引。寅=1, 卯=2, ..., 子=11, 丑=12。"""
    m = {"寅": 1, "卯": 2, "辰": 3, "巳": 4, "午": 5, "未": 6,
         "申": 7, "酉": 8, "戌": 9, "亥": 10, "子": 11, "丑": 12}
    return m.get(zhi, 0)


def adv(zhi: str, step: int) -> str:
    """地支按序平移 step 位（勾绞煞/元辰用）。"""
    i = BRANCH_ORDER.index(zhi)
    return BRANCH_ORDER[(i + step) % 12]


@dataclass(frozen=True)
class ShenshaContext:
    """一次神煞计算的只读上下文。"""

    pillars: list
    gender_int: int | None
    day_gan: str
    year_gan: str
    year_zhi: str
    month_zhi: str
    day_zhi: str
    day_gz: str
    year_nayin_wx: str
    month_idx: int
    season: str

    @classmethod
    def build(cls, pillars: list[Pillar], gender_int: int | None) -> "ShenshaContext":
        month_zhi = pillars[1].zhi
        return cls(
            pillars=pillars,
            gender_int=gender_int,
            day_gan=pillars[2].gan,
            year_gan=pillars[0].gan,
            year_zhi=pillars[0].zhi,
            month_zhi=month_zhi,
            day_zhi=pillars[2].zhi,
            day_gz=pillars[2].ganzhi,
            year_nayin_wx=pillars[0].nayin[-1] if pillars[0].nayin else "",
            month_idx=zhi_to_month_index(month_zhi),
            season=SEASON_OF_BRANCH.get(month_zhi),
        )

    @property
    def other_three(self) -> list:
        """月/日/时三柱（排除年柱自身；学堂词馆以年柱纳音查此三柱）。"""
        return self.pillars[1:]

    @property
    def all_zhi(self) -> list[str]:
        return [p.zhi for p in self.pillars]

    @property
    def is_yang_year(self) -> bool:
        return self.year_gan in YANG_GAN

    @property
    def is_male(self) -> bool:
        return self.gender_int == 1
