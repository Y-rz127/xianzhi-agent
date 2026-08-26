"""八字命盘结构化数据模型（dataclass）；BaziChart 为命盘事实来源。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class BirthInfo:
    """排盘基础信息（公历/农历/生肖/性别/流派）。"""
    solar: str
    lunar: str
    gender: str
    shengxiao: str
    sect: int
    yun_sect: int


@dataclass(frozen=True)
class Pillar:
    """单柱（年/月/日/时）的结构化数据：干支、五行、纳音、空亡、藏干、十神、星运、自坐。"""
    name: str
    ganzhi: str
    gan: str
    zhi: str
    gan_wuxing: str
    zhi_wuxing: str
    nayin: str
    xunkong: str
    hidden_stems: list[str]
    shishen_gan: str = ""
    shishen_zhi: list[str] = field(default_factory=list)
    changsheng: str = ""          # 星运：日干在四柱地支的十二长生
    zizuo: str = ""               # 自坐：本柱天干在本柱地支的十二长生


@dataclass(frozen=True)
class DayunItem:
    """大运单项：干支、起止年份/年龄、空亡、详情（主星/藏干/副星/星运/神煞）。"""
    index: int
    ganzhi: str
    start_year: int
    end_year: int
    start_age: int
    end_age: int
    xunkong: str
    shishen_gan: str = ""
    gan: str = ""
    zhi: str = ""
    hidden_stems: list[str] = field(default_factory=list)
    shishen_zhi: list[str] = field(default_factory=list)
    changsheng: str = ""
    shensha: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class LiunianItem:
    """流年单项：年份、干支、虚岁、所在大运区间、详情（主星/藏干/副星/星运/神煞）。"""
    year: int
    ganzhi: str
    age: int
    dayun_ganzhi: str
    dayun_start_year: int | None
    dayun_end_year: int | None
    xunkong: str
    shishen_gan: str = ""
    gan: str = ""
    zhi: str = ""
    hidden_stems: list[str] = field(default_factory=list)
    shishen_zhi: list[str] = field(default_factory=list)
    changsheng: str = ""
    shensha: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class WuxingAnalysis:
    """五行分析结果：含权重统计、日主强弱、用神提示与口径说明。"""
    counts: dict[str, float]
    visible_counts: dict[str, int]
    strongest: str
    weakest: str
    day_master: str
    day_master_wuxing: str
    strength: str
    strength_score: float
    useful_hint: str
    notes: list[str]
    special_pattern: str = ""   # 特殊格局类型："专旺" / "从格" / 空串


@dataclass(frozen=True)
class DomainAnalysis:
    """十神/合冲刑害/调候/格局等命局结构分析。"""
    ten_gods: dict[str, int]
    exposed_stems: list[str]
    rooted_stems: list[str]
    combinations: list[str]
    clashes: list[str]
    harms: list[str]
    punishments: list[str]
    three_assemblies: list[str]
    season: str
    adjustment: str
    pattern_hint: str
    confidence: float


@dataclass(frozen=True)
class BaziChart:
    """八字命盘完整结构化数据（事实来源），供 API/图表/代理上下文共用。"""
    birth: BirthInfo
    pillars: list[Pillar]
    wuxing: WuxingAnalysis
    analysis: DomainAnalysis
    dayun: list[DayunItem]
    liunian: list[LiunianItem]
    ming_gong: str
    ming_gong_nayin: str
    shen_gong: str
    shen_gong_nayin: str
    start_yun: dict[str, Any]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
