"""岁运关系计算层（纯函数，无 IO 无 LLM）。

把「大运/流年 × 原局」「流年 × 大运」的干支关系预先算好，供工作流消息装配
与 Reviewer 审核共用同一份事实，避免 LLM 自行编排干支关系。

复用 app.domain.xipan 的判定函数与 _build_relations，保证与细盘「岁运」栏口径
一致；本模块只做要素筛选、归位与关系判定，不产生任何断语。
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Sequence

from app.domain.chart_builder import parse_gender
from app.domain.models import BaziChart, DayunItem
from app.domain.tables import GZ_WUXING, HIDDEN_STEMS, LIU_CHONG
from app.domain.xipan import (
    _build_liuyue_list,
    _build_relations,
    _ke,
    _zhi_pair_rel,
    ten_god,
)

# 柱位 → 标准宫位（与事实块口径一致；领域专属别名在 domain_brief 层面渲染）
_PALACE_LABEL = {
    "年柱": "祖上父母宫",
    "月柱": "父母兄弟宫",
    "日柱": "配偶宫",
    "时柱": "子女宫",
}

_CN_NUM = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

_GANZHI_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")


@dataclass(frozen=True)
class SuiRelations:
    """一组岁运（可只含大运，或大运 + 流年）与原局及彼此的关系。"""

    label: str = ""  # 展示标识，如 "2027丁未" / "第3步辛未(2028-2037)"
    ganzhi: str = ""  # 主岁柱干支（优先流年，否则大运）
    wuxing: str = ""  # 干支五行，如 "火土"（丁未）；确定性事实，不做喜忌判定
    shishen_gan: str = ""  # 干对日主十神
    shishen_zhi: list[str] = field(default_factory=list)
    gan_rel: list[str] = field(default_factory=list)  # 天干：合 / 相克
    zhi_rel: list[str] = field(default_factory=list)  # 地支：六合/六冲/六害/六破/三刑/三合
    zhu_rel: list[str] = field(default_factory=list)  # 伏吟 / 反吟（岁运 × 原局）
    touched_pillars: list[str] = field(default_factory=list)  # 被引动的原局柱 + 宫位
    sui_yun_bing_lin: bool = False  # 岁运并临（流年 == 大运）
    tian_ke_di_chong: bool = False  # 天克地冲（流年 vs 大运）
    is_tongxian: bool = False  # 童限期，以当年小运代大运


def _touched_pillars(chart: BaziChart, sui_ganzhis: list[str]) -> list[str]:
    """被岁运地支合/冲/害/破到的原局柱，翻译为「柱(宫位)」。"""
    sui_zhis = [g[1] for g in sui_ganzhis]
    touched: list[str] = []
    for p in chart.pillars:
        if any(_zhi_pair_rel(z, p.zhi) for z in sui_zhis):
            touched.append(f"{p.name}({_PALACE_LABEL.get(p.name, '')})")
    return touched


def _tian_ke_di_chong(dayun_gz: str, liunian_gz: str) -> bool:
    if len(dayun_gz) != 2 or len(liunian_gz) != 2 or dayun_gz == liunian_gz:
        return False
    dg, dz, lg, lz = dayun_gz[0], dayun_gz[1], liunian_gz[0], liunian_gz[1]
    return (_ke(dg, lg) or _ke(lg, dg)) and frozenset((dz, lz)) in LIU_CHONG


def relations_for(
    chart: BaziChart,
    *,
    dayun_ganzhi: str = "",
    liunian_ganzhi: str = "",
    label: str = "",
    is_tongxian: bool = False,
) -> SuiRelations:
    """给定大运/流年干支，计算其与原局及彼此的关系（label 缺省取干支组合）。"""
    sui = [g for g in (dayun_ganzhi, liunian_ganzhi) if len(g) == 2]
    if not sui:
        return SuiRelations()
    main_gz = liunian_ganzhi if len(liunian_ganzhi) == 2 else dayun_ganzhi
    day_master = chart.wuxing.day_master
    suiyun = _build_relations(chart.pillars, sui)["suiyun"]
    return SuiRelations(
        label=label or " · ".join(sui),
        ganzhi=main_gz,
        wuxing=GZ_WUXING.get(main_gz[0], "") + GZ_WUXING.get(main_gz[1], ""),
        shishen_gan=ten_god(day_master, main_gz[0]),
        shishen_zhi=[ten_god(day_master, s) for s, _ in HIDDEN_STEMS.get(main_gz[1], ())],
        gan_rel=list(suiyun["gan"]),
        zhi_rel=list(suiyun["zhi"]),
        zhu_rel=list(suiyun["zhu"]),
        touched_pillars=_touched_pillars(chart, sui),
        sui_yun_bing_lin=bool(dayun_ganzhi) and dayun_ganzhi == liunian_ganzhi,
        tian_ke_di_chong=_tian_ke_di_chong(dayun_ganzhi, liunian_ganzhi),
        is_tongxian=is_tongxian,
    )


def dayun_relations(chart: BaziChart, limit: int | None = None) -> list[SuiRelations]:
    """每步大运 × 原局（limit 限制步数，None=全部）。"""
    dayun = chart.dayun if limit is None else chart.dayun[:limit]
    items: list[SuiRelations] = []
    for d in dayun:
        if len(d.ganzhi) != 2:
            continue
        items.append(
            relations_for(
                chart,
                dayun_ganzhi=d.ganzhi,
                label=f"第{d.index}步{d.ganzhi}({d.start_year}-{d.end_year})",
            )
        )
    return items


def liunian_relations(chart: BaziChart, years: Sequence[int]) -> list[SuiRelations]:
    """目标流年 ×（所在大运 + 原局）。"""
    by_year = {item.year: item for item in chart.liunian}
    items: list[SuiRelations] = []
    for year in years:
        item = by_year.get(year)
        if item is None or len(item.ganzhi) != 2:
            continue
        dy = item.dayun_ganzhi if len(item.dayun_ganzhi or "") == 2 else ""
        items.append(
            relations_for(
                chart,
                dayun_ganzhi=dy,
                liunian_ganzhi=item.ganzhi,
                label=f"{item.year}{item.ganzhi}",
            )
        )
    return items


def _cn_to_int(s: str) -> int:
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + _CN_NUM.get(s[1:], 0)
    if "十" in s:
        a, b = s.split("十", 1)
        return _CN_NUM.get(a, 0) * 10 + _CN_NUM.get(b, 0)
    return _CN_NUM.get(s, 0)


def _resolve_spec(spec: str) -> tuple[str, object]:
    """解析大运指认 spec → (kind, value)。

    kind ∈ current/next/age/seq/ganzhi/invalid；
    value：age=(lo,hi)、seq=int、ganzhi=str，其余为 None。
    """
    if spec in ("当前", "現在"):
        return ("current", None)
    if spec in ("下一步", "下步", "下个大运", "下一运"):
        return ("next", None)
    m = re.search(r"(\d{1,2})\s*[-~到至]\s*(\d{1,2})", spec)
    if m:
        return ("age", (int(m.group(1)), int(m.group(2))))
    m = _GANZHI_RE.search(spec)
    if m:
        return ("ganzhi", m.group(0))
    m = re.search(r"第?\s*([一二三四五六七八九十]+|\d{1,2})\s*[步運运]", spec)
    if m:
        return ("seq", _cn_to_int(m.group(1)))
    m = re.fullmatch(r"([一二三四五六七八九十]+|\d{1,2})", spec)
    if m:
        return ("seq", _cn_to_int(m.group(1)))
    return ("invalid", None)


def resolve_target_dayuns(chart: BaziChart, spec: str) -> list[DayunItem]:
    """把用户/LLM 对大运的指认解析成命中的大运（0-2 个，区间跨步可取两个）。

    不处理童限期（童限期没有真正的 DayunItem，见 current_sui）。
    """
    spec = (spec or "").strip()
    if not spec or not chart.dayun:
        return []
    kind, value = _resolve_spec(spec)
    today_year = datetime.date.today().year
    if kind == "current":
        return [d for d in chart.dayun if d.start_year <= today_year <= d.end_year]
    if kind == "next":
        cur = [d for d in chart.dayun if d.start_year <= today_year <= d.end_year]
        if cur:
            i = chart.dayun.index(cur[0])
            return chart.dayun[i + 1 : i + 2]
        return chart.dayun[:1]  # 童限：下一步 = 第一步大运
    if kind == "age":
        lo, hi = value
        return [d for d in chart.dayun if d.start_age <= hi and d.end_age >= lo]
    if kind == "seq":
        return [d for d in chart.dayun if d.index == value]
    if kind == "ganzhi":
        return [d for d in chart.dayun if d.ganzhi == value]
    return []


def current_sui(chart: BaziChart) -> tuple[str, bool]:
    """当前阶段岁柱与是否童限：交大运→(大运干支, False)；童限→(当年小运干支, True)。

    优先复用 xipan.current 已算好的当前岁柱，避免重复排盘。
    """
    cur = (chart.xipan or {}).get("current", {})
    if cur:
        gz = cur.get("dayun", "")
        if len(gz) == 2:
            return gz, cur.get("dayunLabel") == "小运"
    today_year = datetime.date.today().year
    for d in chart.dayun:
        if d.start_year <= today_year <= d.end_year:
            return d.ganzhi, False
    return "", False


def effective_target_years(
    chart: BaziChart,
    target_years: Sequence[int],
    target_dayun: str,
) -> list[int]:
    """有效目标年份 = 显式年份 ∪ 大运指认覆盖的年份区间（按年龄区间裁剪）。"""
    years = set(target_years or ())
    kind, value = _resolve_spec(target_dayun) if target_dayun else ("invalid", None)
    age_lo, age_hi = None, None
    if kind == "age":
        age_lo, age_hi = value
    for d in resolve_target_dayuns(chart, target_dayun):
        if age_lo is not None:
            y_lo = d.start_year + max(0, age_lo - d.start_age)
            y_hi = d.end_year - max(0, d.end_age - age_hi)
            years.update(range(y_lo, y_hi + 1))
        else:
            years.update(range(d.start_year, d.end_year + 1))
    return sorted(years)


def liuyue_line(chart: BaziChart, year: int) -> str:
    """某年的 12 节气月，按月分行（便于 LLM 抓取单月）。

    开头注明"节气月（立春起算），非阳历月"，避免 LLM 把"2/3 起的寅月"误解为阳历 2 月。
    """
    items, _ = _build_liuyue_list(
        year, year, chart.wuxing.day_master, chart.pillars, parse_gender(chart.birth.gender)
    )
    if not items:
        return ""
    head = f"流月 {year}（节气月，寅月起于立春，非阳历月）:"
    lines = [head] + [f"  {it['zhi']}月{it['ganzhi']}({it['shishen']}, {it['date']}起)" for it in items]
    return "\n".join(lines)


def format_sui_relations(items: Sequence[SuiRelations]) -> str:
    """岁运关系紧凑注入文本，每个岁柱一行。"""
    lines: list[str] = []
    for it in items:
        if it.is_tongxian:
            head = f"童限期（未交大运，以 {it.ganzhi} 小运论）"
        else:
            head = it.label or it.ganzhi
        tags = [t for t in (it.shishen_gan, it.wuxing) if t]
        rels: list[str] = []
        rels.extend(it.gan_rel)
        rels.extend(it.zhi_rel)
        rels.extend(it.zhu_rel)
        if it.tian_ke_di_chong and "天克地冲" not in rels:
            rels.append("天克地冲")
        if it.sui_yun_bing_lin and "岁运并临" not in rels:
            rels.append("岁运并临")
        if it.touched_pillars:
            rels.append("引动" + "、".join(it.touched_pillars))
        line = head
        if tags:
            line += f"（{'、'.join(tags)}）"
        if rels:
            line += "：" + "、".join(rels)
        lines.append(line + "。")
    return "\n".join(lines)
