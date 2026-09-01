"""紫微斗数子应用核心：组装领域引擎，供 REST 路由与 Agent 工具共用。"""
from __future__ import annotations

from app.domain.ziwei import engine


def cast_chart_dict(
    *,
    solar_date: str | None = None,
    lunar_date: str | None = None,
    leap: bool = False,
    time_index: int,
    gender: str,
    calendar: str = "solar",
) -> dict:
    """排盘并返回 snake_case 命盘 dict（非法参数抛 ValueError）。"""
    chart = engine.cast_chart(
        solar_date=solar_date, lunar_date=lunar_date, leap=leap,
        time_index=time_index, gender=gender, calendar=calendar,
    )
    return chart.to_dict()


def _star_text(star: dict) -> str:
    parts = [star["name"]]
    if star.get("brightness"):
        parts.append(star["brightness"])
    if star.get("mutagen"):
        parts.append(f"化{star['mutagen']}")
    return "".join(parts) if len(parts) > 1 else star["name"]


def _palace_label(name: str) -> str:
    """宫名展示：命宫已含「宫」，其余补「宫」。"""
    return name if name.endswith("宫") else name + "宫"


def build_chart_summary(chart: dict, focus: str = "") -> str:
    """把命盘 dict 压成结构化文本，作为 LLM 解读的事实源（不虚构、可追溯）。"""
    lines = [
        "【基本信息】性别{}，阳历{}，{}（{}），{}，{}，命宫在{}宫，身宫在{}宫。".format(
            chart["gender"], chart["solar_date"], chart["lunar_date"],
            chart["time_name"], chart["time_range"], chart["five_elements_class"],
            chart["earthly_branch_of_soul"], chart["earthly_branch_of_body"],
        ),
        "【四柱】年{} 月{} 日{} 时{}。".format(
            chart["four_pillars"]["yearly"], chart["four_pillars"]["monthly"],
            chart["four_pillars"]["daily"], chart["four_pillars"]["hourly"],
        ),
        "【命主】{}，【身主】{}。".format(chart["soul_star"], chart["body_star"]),
        "【十二宫】（寅宫起，逐宫列主星/亮度/四化，括号内为辅煞与重要杂曜、大限年龄段）",
    ]
    for p in chart["palaces"]:
        majors = "、".join(_star_text(s) for s in p["major_stars"]) or "空宫（借对宫主星）"
        support = [s["name"] for s in p["minor_stars"]]
        support += [s["name"] for s in p["adjective_stars"] if s["type"] in ("soft", "tough", "lucun", "tianma")]
        support_txt = "、".join(support) if support else "—"
        body = "身宫" if p["is_body"] else ""
        dec = "{}~{}岁".format(*p["decadal"]["range"]) if p["decadal"] else "—"
        lines.append(
            "  {}（{}{}）：{}；辅煞杂曜：{}；大限{}。".format(
                _palace_label(p["name"]), p["heavenly_stem"], p["earthly_branch"], majors, support_txt, dec
            ) + (f"〔{body}〕" if body else "")
        )
    if focus:
        lines.append(f"【问测重点】{focus}")
    return "\n".join(lines)
