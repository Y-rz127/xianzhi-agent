"""真太阳时校正回归：经度方向、均时差、跨日回退。

2026-10-24 修复前实现符号写反（西部城市被推后），本文件钉死方向。
"""
from __future__ import annotations

import datetime

from app.domain.solar_time import (
    apply_solar_time,
    equation_of_time_minutes,
    solar_correction_minutes,
)


def test_west_longitude_moves_time_earlier_and_crosses_day():
    """东经 87.6°（乌鲁木齐一带）比 120°E 慢约 130 分钟，00:30 应回退到前一日。"""
    assert apply_solar_time(1985, 1, 5, 0, 30, 87.6) == (1985, 1, 4, 22, 15)


def test_beijing_longitude_is_only_equation_of_time():
    """116.4°E 的经度差约 -14 分钟，再叠加均时差。"""
    corrected = apply_solar_time(2004, 6, 22, 8, 5, 116.4)
    assert corrected == (2004, 6, 22, 7, 49)


def test_xian_birth_time_corrected_earlier():
    """东经 108.63°：08:05 应为 07:18，而不是修复前的 08:50。"""
    assert apply_solar_time(2004, 6, 22, 8, 5, 108.63) == (2004, 6, 22, 7, 18)


def test_east_longitude_moves_time_later():
    """东经 126.5°（东北）比 120°E 快约 26 分钟。"""
    assert apply_solar_time(2004, 6, 22, 8, 5, 126.5) == (2004, 6, 22, 8, 29)


def test_missing_or_out_of_range_longitude_keeps_clock_time():
    assert apply_solar_time(2004, 6, 22, 8, 5, None) == (2004, 6, 22, 8, 5)
    assert apply_solar_time(2004, 6, 22, 8, 5, 0) == (2004, 6, 22, 8, 5)
    assert apply_solar_time(2004, 6, 22, 8, 5, 200) == (2004, 6, 22, 8, 5)


def test_equation_of_time_seasonal_range():
    """均时差全年约 -14 ~ +16 分钟（11 月初最快、2 月中旬最慢）。"""
    assert -8 <= equation_of_time_minutes(datetime.datetime(2026, 1, 5)) <= -3
    assert 14 <= equation_of_time_minutes(datetime.datetime(2026, 11, 3)) <= 17
    assert -15 <= equation_of_time_minutes(datetime.datetime(2026, 2, 11)) <= -12


def test_solar_correction_combines_longitude_and_equation_of_time():
    moment = datetime.datetime(2004, 6, 22, 8, 5)
    assert solar_correction_minutes(moment, 108.63) == -47
    assert solar_correction_minutes(moment, 120.0) == equation_of_time_minutes(moment)
