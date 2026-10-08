"""紫微斗数排盘数据模型（dataclass + snake_case 序列化，供 REST/工具/前端共用）。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Star:
    """单颗星曜。type 见 tables（major/soft/tough/lucun/tianma/flower/helper/adjective）。"""

    name: str
    type: str
    brightness: str = ""
    mutagen: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "brightness": self.brightness,
            "mutagen": self.mutagen,
        }


@dataclass
class Decadal:
    """大限：年龄段 [start, end]（虚岁）与该宫干支。"""

    range: list[int]
    heavenly_stem: str
    earthly_branch: str

    def to_dict(self) -> dict:
        return {
            "range": self.range,
            "heavenly_stem": self.heavenly_stem,
            "earthly_branch": self.earthly_branch,
        }


@dataclass
class Palace:
    """一宫。index 以寅宫为 0、顺时针至丑宫为 11。"""

    index: int
    name: str
    heavenly_stem: str
    earthly_branch: str
    is_body: bool = False
    major_stars: list[Star] = field(default_factory=list)
    minor_stars: list[Star] = field(default_factory=list)
    adjective_stars: list[Star] = field(default_factory=list)
    changsheng12: str = ""
    boshi12: str = ""
    jiangqian12: str = ""
    suiqian12: str = ""
    decadal: Decadal | None = None
    ages: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "heavenly_stem": self.heavenly_stem,
            "earthly_branch": self.earthly_branch,
            "is_body": self.is_body,
            "major_stars": [s.to_dict() for s in self.major_stars],
            "minor_stars": [s.to_dict() for s in self.minor_stars],
            "adjective_stars": [s.to_dict() for s in self.adjective_stars],
            "changsheng12": self.changsheng12,
            "boshi12": self.boshi12,
            "jiangqian12": self.jiangqian12,
            "suiqian12": self.suiqian12,
            "decadal": self.decadal.to_dict() if self.decadal else None,
            "ages": self.ages,
        }


@dataclass
class Chart:
    """整张命盘。"""

    gender: str
    solar_date: str
    lunar_date: str
    time_index: int
    time_name: str
    time_range: str
    sign: str = ""
    zodiac: str = ""
    earthly_branch_of_soul: str = ""
    earthly_branch_of_body: str = ""
    soul_star: str = ""
    body_star: str = ""
    five_elements_class: str = ""
    # 四柱（干支），供中央信息区展示
    yearly_ganzhi: str = ""
    monthly_ganzhi: str = ""
    daily_ganzhi: str = ""
    hourly_ganzhi: str = ""
    palaces: list[Palace] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "gender": self.gender,
            "solar_date": self.solar_date,
            "lunar_date": self.lunar_date,
            "time_index": self.time_index,
            "time_name": self.time_name,
            "time_range": self.time_range,
            "sign": self.sign,
            "zodiac": self.zodiac,
            "earthly_branch_of_soul": self.earthly_branch_of_soul,
            "earthly_branch_of_body": self.earthly_branch_of_body,
            "soul_star": self.soul_star,
            "body_star": self.body_star,
            "five_elements_class": self.five_elements_class,
            "four_pillars": {
                "yearly": self.yearly_ganzhi,
                "monthly": self.monthly_ganzhi,
                "daily": self.daily_ganzhi,
                "hourly": self.hourly_ganzhi,
            },
            "palaces": [p.to_dict() for p in self.palaces],
        }
