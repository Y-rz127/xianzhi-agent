"""真太阳时校正：经度差 + 均时差。

真太阳时 = 北京时间 + 4 分钟 × (当地经度 − 120°) + 均时差
（公式见知识库 08_八字排盘基础.md；均时差全年约 −14 ~ +16 分钟）。

2026-10-24 修正：原实现写成 ``(120 - 经度) × 4`` 并加到时间上，方向与公式相反，
西部城市反而被推后（东经 108.63° 的 08:05 被校成 08:50，正确是 07:18）。
"""
from __future__ import annotations

import datetime
import math

_MIN_LONGITUDE = 60.0
_MAX_LONGITUDE = 140.0


def equation_of_time_minutes(moment: datetime.datetime) -> int:
    """均时差近似值（分钟），按一年中的日序计算。"""
    b = 2 * math.pi * (moment.timetuple().tm_yday - 81) / 365
    return round(9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b))


def solar_correction_minutes(moment: datetime.datetime, longitude: float | None) -> int:
    """北京时间 → 当地真太阳时的分钟偏移；经度缺失或越界（非中国范围）不校正。"""
    if not longitude or not _MIN_LONGITUDE <= longitude <= _MAX_LONGITUDE:
        return 0
    return round(4 * (longitude - 120)) + equation_of_time_minutes(moment)


def apply_solar_time(
    y: int, m: int, d: int, h: int, mi: int, longitude: float | None
) -> tuple[int, int, int, int, int]:
    """返回校正后的 (年, 月, 日, 时, 分)。"""
    corr = solar_correction_minutes(datetime.datetime(y, m, d, h, mi), longitude)
    if corr == 0:
        return y, m, d, h, mi
    corrected = datetime.datetime(y, m, d, h, mi) + datetime.timedelta(minutes=corr)
    return corrected.year, corrected.month, corrected.day, corrected.hour, corrected.minute
