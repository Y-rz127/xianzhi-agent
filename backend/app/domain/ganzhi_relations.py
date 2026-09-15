"""干支关系单一事实源：原局分析与岁运细盘共用同一套算法。

口径依据：`knowledge_docs/12_合冲刑害规则卡.md` 与 `古籍05_三命通会精选条文.md`
- §一 合局力量排序：**三会 ＞ 三合 ＞ 六合 ＞ 半合 ＞ 拱合** —— 半合/拱合是正式关系类
- §三.4 三刑采用**「两支半刑」**口径（两支见如寅巳亦主刑伤；部分流派坚持三支齐全）
- §三.3 辰/午/酉/亥 自刑
- 古籍05 十二节：六破（子酉破、午卯破、申巳破、亥寅破、辰丑破、戌未破）

**为什么需要这个模块**：`analysis_calc` 与 `xipan` 曾各写一套 —— 前者只认完整三合、
后者支持半合/拱合；自刑还用了两个名字（`辰辰自刑` vs `辰辰相刑`）。实测 36 个黄金命盘里
**34 个两套结论不一致**。现统一为「一个算法、两个视图」：本模块出结构化结果，
各视图只做展示映射（`analysis_calc` 分入 6 个字段，`xipan` 汇总为一栏文字）。

**不做去重**：与 `analysis_calc` 原行为一致（四柱若含同支，同一关系会出现多次）。
视图侧按需自行 `_dedup`（`xipan` 已在做）。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.tables import (
    GAN_CHONG,
    GAN_HE,
    LIU_CHONG,
    LIU_HAI,
    LIU_HE,
    LIU_PO,
    SAN_HE_TRIPLE,
    SAN_HUI,
    SAN_XING_PAIR,
    SAN_XING_TRIPLE,
    SELF_XING,
)

__all__ = [
    "BranchRelations",
    "branch_relations",
    "gan_pair_relation",
    "stem_relations",
    "zhi_pair_relations",
]


@dataclass(frozen=True)
class BranchRelations:
    """地支关系结构化结果（按知识库分类，自成一类不放混）。"""

    hui: tuple[str, ...]          # 三会（方合）
    san_he: tuple[str, ...]       # 三合（三支齐全）
    ban_he: tuple[str, ...]       # 半合（含中神的两支）
    gong_he: tuple[str, ...]      # 拱合（首尾两支，中神虚一）
    liu_he: tuple[str, ...]       # 六合
    chong: tuple[str, ...]        # 六冲
    hai: tuple[str, ...]          # 六害
    po: tuple[str, ...]           # 六破
    san_xing: tuple[str, ...]     # 三刑（三支齐全）
    ban_xing: tuple[str, ...]     # 半刑（两支，知识库 §三.4 口径）
    zi_xing: tuple[str, ...]      # 自刑

    def all_items(self) -> list[str]:
        """按「合 → 冲 → 害 → 破 → 刑」的知识库顺序汇总（岁运细盘的单栏展示用）。"""
        return [
            *self.hui, *self.san_he, *self.ban_he, *self.gong_he, *self.liu_he,
            *self.chong, *self.hai, *self.po,
            *self.san_xing, *self.ban_xing, *self.zi_xing,
        ]


def branch_relations(zhis: list[str]) -> BranchRelations:
    """归纳一组地支间的全部关系。

    成对关系（六合/六冲/六害/六破）按 `i<j` 遍历原列表（含重复支，与原实现一致）；
    局类（三会/三合/半合/拱合）与刑类按集合判定。
    """
    zhi_set = set(zhis)
    hui: list[str] = []
    san_he: list[str] = []
    ban_he: list[str] = []
    gong_he: list[str] = []
    liu_he: list[str] = []
    chong: list[str] = []
    hai: list[str] = []
    po: list[str] = []

    for i in range(len(zhis)):
        for j in range(i + 1, len(zhis)):
            pair = frozenset((zhis[i], zhis[j]))
            if pair in LIU_HE:
                liu_he.append(LIU_HE[pair])
            if pair in LIU_CHONG:
                chong.append(LIU_CHONG[pair])
            if pair in LIU_HAI:
                hai.append(LIU_HAI[pair])
            if pair in LIU_PO:
                po.append(LIU_PO[pair])

    for group, label in SAN_HUI.items():
        if group.issubset(zhi_set):
            hui.append(label)

    # 三合体系：三支齐全 → 三合局；含中神的两支 → 半合；首尾两支（中神虚一）→ 拱合。
    # 三元组已按「生-旺-墓」排列，(a,b,c) 的中神是 b。
    for a, b, c, wx in SAN_HE_TRIPLE:
        has_a, has_b, has_c = a in zhi_set, b in zhi_set, c in zhi_set
        if has_a and has_b and has_c:
            san_he.append(f"{a}{b}{c}合{wx}局")
        elif has_a and has_b:
            ban_he.append(f"{a}{b}半合{wx}")
        elif has_b and has_c:
            ban_he.append(f"{b}{c}半合{wx}")
        elif has_a and has_c:
            gong_he.append(f"{a}{c}拱合{b}")

    san_xing: list[str] = []
    ban_xing: list[str] = []
    for a, b, c, name, disp in SAN_XING_TRIPLE:
        has_a, has_b, has_c = a in zhi_set, b in zhi_set, c in zhi_set
        present = [z for z, ok in ((a, has_a), (b, has_b), (c, has_c)) if ok]
        if len(present) == 3:
            san_xing.append(f"{disp}{name}三刑")
        elif len(present) == 2:
            # 半刑：按三元组的组合顺序输出（寅巳 / 巳申 / 申寅）
            for x, y, has_x, has_y in ((a, b, has_a, has_b), (b, c, has_b, has_c), (c, a, has_c, has_a)):
                if has_x and has_y:
                    ban_xing.append(f"{x}{y}半刑（{name}）")
    for group, label in SAN_XING_PAIR.items():
        if group.issubset(zhi_set):
            san_xing.append(label)

    zi_xing: list[str] = []
    for zhi in sorted(zhi_set):
        if zhi in SELF_XING and zhis.count(zhi) >= 2:
            zi_xing.append(SELF_XING[zhi])

    return BranchRelations(
        hui=tuple(hui),
        san_he=tuple(san_he),
        ban_he=tuple(ban_he),
        gong_he=tuple(gong_he),
        liu_he=tuple(liu_he),
        chong=tuple(chong),
        hai=tuple(hai),
        po=tuple(po),
        san_xing=tuple(san_xing),
        ban_xing=tuple(ban_xing),
        zi_xing=tuple(zi_xing),
    )


def stem_relations(gans: list[str]) -> tuple[list[str], list[str]]:
    """天干五合与相冲。返回 (合, 冲)；命名依知识库 `01_天干地支基础.md`（甲庚冲 / 甲己合土）。"""
    he: list[str] = []
    chong: list[str] = []
    for i in range(len(gans)):
        for j in range(i + 1, len(gans)):
            pair = frozenset((gans[i], gans[j]))
            if pair in GAN_HE:
                he.append(GAN_HE[pair])
            if pair in GAN_CHONG:
                chong.append(GAN_CHONG[pair])
    return he, chong


def gan_pair_relation(a: str, b: str) -> str:
    """两天干关系：五合优先，其次四冲（甲庚/乙辛/丙壬/丁癸）。同日干或空值返回空串。

    天干只列「合」「冲」两类：四冲本身也是相克关系（如壬克丙），一律按「冲」报，
    不得降格写成「相克」；其余非冲的天干相克（如丁克庚）属常规五行生克，不作关系列出。
    """
    if not a or not b or a == b:
        return ""
    pair = frozenset((a, b))
    if pair in GAN_HE:
        return GAN_HE[pair]
    if pair in GAN_CHONG:
        return GAN_CHONG[pair]
    return ""


def zhi_pair_relations(x: str, y: str) -> list[str]:
    """两地支的六合/六冲/六害/六破（同支不论）。"""
    if not x or not y or x == y:
        return []
    pair = frozenset((x, y))
    return [table[pair] for table in (LIU_HE, LIU_CHONG, LIU_HAI, LIU_PO) if pair in table]
