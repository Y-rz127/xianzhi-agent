"""每日黄历与择吉工具（基于 lunar-python 纯算法，确定性计算）。"""
from __future__ import annotations

from langchain_core.tools import tool

from app.domain.huangli_calc import YI_JI_ITEMS
from app.sub_app.huangli import huangli_app


@tool
def huangli_today(date: str = "") -> str:
    """查询每日黄历：宜忌、冲煞、财神方位、吉凶神、值神、时辰吉凶要点。

    用户问"今天/明天适合做什么、有什么禁忌、财神在哪个方位"等黄历问题时调用。
    日期支持 1900-2100 年任意一天；"明天/下周三"等相对日期请先换算成公历再传入。

    Args:
        date: 公历日期 YYYY-MM-DD，如 2026-08-30；留空表示今天

    Returns:
        当日黄历文本摘要（宜忌/冲煞/彭祖/吉凶神/方位/值神/时辰要点）
    """
    try:
        day = huangli_app.huangli_day(date)
    except ValueError as e:
        return "黄历查询失败: {}".format(e)
    except Exception as e:
        return "黄历查询失败: {}".format(e)

    lunar = day["lunar"]
    lines = [
        "{}（{}，{}）".format(day["solar"], lunar["text"], lunar["day_gz"]),
        "宜：{}".format("、".join(day["yi"])),
        "忌：{}".format("、".join(day["ji"])),
        "冲煞：{} 煞{}".format(day["chong"]["desc"], day["chong"]["sha"]),
        "胎神占方：{}；日柱纳音：{}".format(day["taishen"], day["nayin"]),
        "彭祖百忌：{}；{}".format(day["pengzu"]["gan"], day["pengzu"]["zhi"]),
        "吉神宜趋：{}".format("、".join(day["jishen"])),
        "凶煞宜忌：{}".format("、".join(day["xiongsha"])),
        "财神方位：{}；喜神：{}；福神：{}；阳贵：{}；阴贵：{}".format(
            day["positions"]["cai"], day["positions"]["xi"], day["positions"]["fu"],
            day["positions"]["yang_gui"], day["positions"]["yin_gui"],
        ),
        "五鬼（凶方）：{}；生门（吉方）：{}；死门（凶方）：{}".format(
            day["positions"]["five_ghost"], day["positions"]["sheng_men"], day["positions"]["si_men"]
        ),
        "值神：{}（{}·{}）；建星：{}；九星：{}；二十八宿：{}（{}）".format(
            day["tian_shen"]["name"], day["tian_shen"]["type"], day["tian_shen"]["luck"],
            day["zhixing"], day["nine_star"], day["xiu"]["name"], day["xiu"]["luck"],
        ),
    ]
    if day["festivals"]:
        lines.append("节日：{}".format("、".join(day["festivals"])))
    if day["jieqi"]:
        lines.append("节气：{}".format(day["jieqi"]))
    lucky_hours = [h for h in day["hours"] if h["luck"] == "吉"]
    lines.append("吉时：{}".format(
        "、".join("{}时（{}）".format(h["zhi"], h["range"]) for h in lucky_hours) or "无"
    ))
    lines.append("（以上为传统民俗文化参考）")
    return "\n".join(lines)


@tool
def huangli_zeji(yi: str, start: str, end: str, avoid_chong: str = "") -> str:
    """择吉：在日期区间内筛选"宜"包含目标事项的吉日，吉神加持者排前。

    用户要"挑个开业/搬家/嫁娶的吉日"时调用。事项必须使用标准黄历词表，
    可选排除与某生肖相冲的日子（如当事人属鼠则 avoid_chong 传"鼠"）。

    Args:
        yi: 择吉事项，须为标准词表用词，如 嫁娶/开市/移徙/入宅/出行/祭祀/破土/安葬
        start: 起始日期 YYYY-MM-DD
        end: 结束日期 YYYY-MM-DD，区间不超过 60 天
        avoid_chong: 可选，排除相冲的生肖，如"鼠"

    Returns:
        候选吉日列表（含日干支、冲煞、吉神、值神），按吉神多寡排序
    """
    try:
        days = huangli_app.zeji(yi, start, end, avoid_chong)
    except ValueError as e:
        return "择吉失败: {}（可选事项示例：{}）".format(e, "、".join(YI_JI_ITEMS[:12]))
    except Exception as e:
        return "择吉失败: {}".format(e)

    if not days:
        return "{}-{} 期间没有宜「{}」的日子{}".format(
            start, end, yi,
            "（已排除冲{}之日）".format(avoid_chong) if avoid_chong else "",
        )
    lines = ["{}-{} 宜「{}」的吉日{}：".format(
        start, end, yi, "（避冲{}）".format(avoid_chong) if avoid_chong else ""
    )]
    for d in days:
        note = "，吉神：{}".format(d["note"]) if d["note"] else ""
        lines.append("  {} {} 冲{} 值神{}{}".format(
            d["date"], d["day_gz"], d["chong"], d["tian_shen"], note
        ))
    lines.append("（以上为传统民俗文化参考）")
    return "\n".join(lines)


huangli_tools = [huangli_today, huangli_zeji]
