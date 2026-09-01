"""紫微斗数排盘工具（确定性计算，供仙芝对话直接排盘并衔接解读）。"""
from __future__ import annotations

from langchain_core.tools import tool

from app.domain.ziwei import engine
from app.domain.ziwei.tables import CHINESE_TIME

# 时辰名（含早/晚子）→ 序号
_TIME_NAME_TO_INDEX = {name: i for i, name in enumerate(CHINESE_TIME)}


def _parse_time_index(time_desc: str) -> int:
    """把"卯时 / 05:00-07:00 / 5 / 早子时 / 晚子时"解析为时辰序号 0~12。"""
    s = (time_desc or "").strip()
    if not s:
        raise ValueError("请提供出生时辰，如「卯时」或「05:00-07:00」")
    if s in _TIME_NAME_TO_INDEX:
        return _TIME_NAME_TO_INDEX[s]
    # "HH:MM" 或 "HH:MM-HH:MM" → 取起始小时
    head = s.split("-")[0].split("~")[0].strip()
    if ":" in head:
        hour = int(head.split(":")[0])
    elif head.isdigit():
        hour = int(head)
    else:
        # 去掉尾字"时"再试
        core = s.replace("时", "")
        if core in _TIME_NAME_TO_INDEX:
            return _TIME_NAME_TO_INDEX[core]
        raise ValueError(f"无法识别的时辰「{time_desc}」")
    if hour == 0:
        return 0
    if hour == 23:
        return 12
    return (hour + 1) // 2


@tool
def ziwei_chart(date: str, time_desc: str, gender: str) -> str:
    """紫微斗数排盘：按生辰排出命盘，返回命宫主星、五行局、四化、身宫等要点摘要。

    用户问"帮我看看紫微命盘/命宫主星是什么/紫微斗数"等时调用。
    date 为公历 YYYY-MM-DD；"农历/属相等"请先换算成公历。相对时间先换算成具体日期。

    Args:
        date: 公历出生日期 YYYY-MM-DD，如 2000-08-16
        time_desc: 出生时辰，如「卯时」「05:00-07:00」「5」「早子时」「晚子时」
        gender: 「男」或「女」

    Returns:
        命盘文本摘要（命宫/身宫/五行局/命主身主/命宫三方四正主星四化/逐宫主星）
    """
    try:
        time_index = _parse_time_index(time_desc)
        chart = engine.cast_chart(solar_date=date, time_index=time_index, gender=gender).to_dict()
    except ValueError as e:
        return "紫微排盘失败: {}".format(e)
    except Exception as e:  # noqa: BLE001
        return "紫微排盘失败: {}".format(e)

    def star_text(s: dict) -> str:
        t = s["name"]
        if s.get("brightness"):
            t += s["brightness"]
        if s.get("mutagen"):
            t += f"化{s['mutagen']}"
        return t

    soul = next((p for p in chart["palaces"] if p["name"] == "命宫"), None)
    lines = [
        "紫微斗数命盘（{} {}，{}）".format(chart["solar_date"], chart["time_name"], chart["gender"]),
        "农历{}；四柱 年{} 月{} 日{} 时{}".format(
            chart["lunar_date"], chart["four_pillars"]["yearly"], chart["four_pillars"]["monthly"],
            chart["four_pillars"]["daily"], chart["four_pillars"]["hourly"],
        ),
        "{}，命宫在{}宫，身宫在{}宫；命主{}，身主{}".format(
            chart["five_elements_class"], chart["earthly_branch_of_soul"], chart["earthly_branch_of_body"],
            chart["soul_star"], chart["body_star"],
        ),
    ]
    if soul:
        majors = "、".join(star_text(s) for s in soul["major_stars"]) or "空宫（借对宫）"
        lines.append("命宫主星：{}".format(majors))
    # 生年四化
    mutagens = []
    for p in chart["palaces"]:
        for s in p["major_stars"] + p["minor_stars"]:
            if s.get("mutagen"):
                mutagens.append("{}化{}（在{}宫）".format(s["name"], s["mutagen"], p["name"]))
    if mutagens:
        lines.append("生年四化：" + "；".join(mutagens))
    lines.append("逐宫主星：" + "；".join(
        "{}{}".format(p["name"] if p["name"].endswith("宫") else p["name"] + "宫",
                      "、".join(star_text(s) for s in p["major_stars"]) or "空")
        for p in chart["palaces"]
    ))
    lines.append("（以上为传统民俗文化参考）")
    return "\n".join(lines)


ziwei_tools = [ziwei_chart]
