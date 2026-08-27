"""六爻（纳甲/周易）起卦与 AI 解读模块。

支持铜钱、数字、时间三种起卦方式；输出本卦、变卦、动爻、卦象文字，
并交给 LLM 做流式白话解读。
"""
from __future__ import annotations

import random
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logger import log

LineValue = int
LineKind = Literal["老阴", "少阳", "少阴", "老阳"]
Method = Literal["coin", "number", "time"]

TRIGRAM_NAMES = ["乾", "兑", "离", "震", "巽", "坎", "艮", "坤"]
TRIGRAM_ATTRS = [
    ("天", "金"),
    ("泽", "金"),
    ("火", "火"),
    ("雷", "木"),
    ("风", "木"),
    ("水", "水"),
    ("山", "土"),
    ("地", "土"),
]

# 64 卦名称（下卦 × 上卦），下卦为内、上卦为外。
# 索引：下卦 0-7（乾兑离震巽坎艮坤），上卦 0-7。
HEXAGRAM_TABLE: list[list[str]] = [
    ["乾为天", "泽天夬", "火天大有", "雷天大壮", "风天小畜", "水天需", "山天大畜", "地天泰"],
    ["天泽履", "兑为泽", "火泽睽", "雷泽归妹", "风泽中孚", "水泽节", "山泽损", "地泽临"],
    ["天火同人", "泽火革", "离为火", "雷火丰", "风火家人", "水火既济", "山火贲", "地火明夷"],
    ["天雷无妄", "泽雷随", "火雷噬嗑", "震为雷", "风雷益", "水雷屯", "山雷颐", "地雷复"],
    ["天风姤", "泽风大过", "火风鼎", "雷风恒", "巽为风", "水风井", "山风蛊", "地风升"],
    ["天水讼", "泽水困", "火水未济", "雷水解", "风水涣", "坎为水", "山水蒙", "地水师"],
    ["天山遁", "泽山咸", "火山旅", "雷山小过", "风山渐", "水山蹇", "艮为山", "地山谦"],
    ["天地否", "泽地萃", "火地晋", "雷地豫", "风地观", "水地比", "山地剥", "坤为地"],
]

YAO_NAMES = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]


def _line_kind(value: LineValue) -> LineKind:
    return {6: "老阴", 7: "少阳", 8: "少阴", 9: "老阳"}[value]


def _stable_yao(value: LineValue) -> int:
    """把动爻化为变卦的阴阳：6 老阴变阳，9 老阳变阴；7、8 不变。"""
    if value == 6:
        return 1  # 阳
    if value == 9:
        return 0  # 阴
    return 1 if value == 7 else 0


def _is_changing(value: LineValue) -> bool:
    return value in (6, 9)


def _value_from_yin_yang_changing(yin: int, changing: bool) -> LineValue:
    """用于数字/时间起卦：已知阴阳与是否动爻，反推 line value。"""
    if yin:
        return 6 if changing else 8
    return 9 if changing else 7


def _trigram_from_lines(lines: list[LineValue]) -> int:
    """三爻组成一卦，从下往上：0-7 索引对应先天八卦。
    阳=1，阴=0，下爻为最低位。
    """
    bits = [1 if _stable_yao(line) else 0 for line in lines]
    return bits[0] + (bits[1] << 1) + (bits[2] << 2)


def _gua_name(lines: list[LineValue]) -> str:
    lower = _trigram_from_lines(lines[:3])
    upper = _trigram_from_lines(lines[3:])
    return HEXAGRAM_TABLE[lower][upper]


def _yao_to_string(line: LineValue) -> str:
    if line in (7, 9):  # 阳爻
        return "━" if not _is_changing(line) else "━O━"  # 老阳加圈表示动
    return "━━" if not _is_changing(line) else "━X━"  # 老阴加叉表示动


def _render_gua(lines: list[LineValue]) -> str:
    """从上爻到下爻竖排绘制。"""
    return "\n".join(reversed([_yao_to_string(line) for line in lines]))


def coin_gua() -> list[LineValue]:
    """三枚铜钱起卦，每次得一爻，共六爻（初爻到上爻）。"""
    lines: list[LineValue] = []
    for _ in range(6):
        toss = sum(random.choices([2, 3], k=3))
        lines.append(toss)
    return lines


def _mod8(n: int) -> int:
    """周易起卦习惯：整除取 8（坤）。"""
    return 8 if n % 8 == 0 else n % 8


def _mod6(n: int) -> int:
    """动爻：整除取 6（上爻）。"""
    return 6 if n % 6 == 0 else n % 6


def number_gua(numbers: list[int]) -> list[LineValue]:
    """数字起卦：优先取前三位，分别用于上卦、下卦、动爻。
    不足三位时对全部数字求和再分三份。
    """
    nums = [abs(int(x)) for x in numbers if isinstance(x, (int, float))]
    if len(nums) < 3:
        total = sum(nums) or 1
        nums = [(total + i) for i in range(3)]

    upper_idx = _mod8(nums[0]) - 1  # 1-8 -> 0-7
    lower_idx = _mod8(nums[1]) - 1
    change_pos = _mod6(nums[2]) - 1  # 1-6 -> 0-5，0 为初爻

    # 把上卦下卦展开成六爻，初始无动爻；再把动爻位置设为老阳/老阴
    def trigram_lines(idx: int) -> list[LineValue]:
        # idx 的二进制三位：最低位为下爻
        lines = [7 if (idx >> i) & 1 else 8 for i in range(3)]
        return lines

    lines = trigram_lines(lower_idx) + trigram_lines(upper_idx)
    # 动爻：阴阳翻转并标记为动
    original = lines[change_pos]
    yin = 0 if _stable_yao(original) else 1
    lines[change_pos] = _value_from_yin_yang_changing(yin, True)
    return lines


def time_gua(dt: datetime | None = None) -> list[LineValue]:
    """时间起卦：以当前时间数字取卦。
    年+月+日上卦，年+月+日+时下卦，年+月+日+时+分+秒动爻。
    """
    now = dt or datetime.now()
    upper = _mod8(now.year + now.month + now.day)
    lower = _mod8(now.year + now.month + now.day + now.hour)
    change = _mod6(now.year + now.month + now.day + now.hour + now.minute + now.second)
    return number_gua([upper, lower, change])


class LiuyaoApp:
    """六爻应用：起卦 + LLM 解读。"""

    _system_prompt = (
        "你是一位精通《周易》与六爻占卜的解卦师。请根据用户的问题、本卦、变卦与动爻，"
        "用现代、温暖且易懂的白话文给出解读。解读结构建议：\n"
        "1. 总体卦象与吉凶基调；\n"
        "2. 结合所问事情，分析本卦与变卦的启示；\n"
        "3. 动爻（变爻）对事情发展的关键提示；\n"
        "4. 给出具体、可执行的建议。\n"
        "保持尊重传统文化，但不宣扬迷信，提醒用户理性看待。"
    )

    def __init__(self, chat_model: BaseChatModel):
        self.chat_model = chat_model

    def cast(self, method: Method, numbers: list[int] | None = None) -> list[LineValue]:
        """根据起卦方式得到六爻。"""
        if method == "coin":
            return coin_gua()
        if method == "number":
            return number_gua(numbers or [random.randint(1, 100) for _ in range(3)])
        return time_gua()

    def build_result(self, question: str, lines: list[LineValue]) -> dict:
        """把六爻数字整理成本卦、变卦、动爻、卦象文字等结构化信息。"""
        primary_lines = lines
        changed_lines = [_stable_yao(v) for v in lines]
        changing_positions = [i for i, v in enumerate(primary_lines) if _is_changing(v)]

        primary_name = _gua_name(primary_lines)
        changed_name = _gua_name([_value_from_yin_yang_changing(v, False) for v in changed_lines])
        lower_idx = _trigram_from_lines(primary_lines[:3])
        upper_idx = _trigram_from_lines(primary_lines[3:])

        return {
            "question": question,
            "lines": primary_lines,
            "line_kinds": [_line_kind(v) for v in primary_lines],
            "primary_gua": primary_name,
            "changed_gua": changed_name,
            "lower_trigram": TRIGRAM_NAMES[lower_idx],
            "upper_trigram": TRIGRAM_NAMES[upper_idx],
            "changing_positions": [i + 1 for i in changing_positions],
            "changing_yao_names": [YAO_NAMES[i] for i in changing_positions],
            "primary_text": _render_gua(primary_lines),
            "changed_text": _render_gua([_value_from_yin_yang_changing(v, False) for v in changed_lines]),
        }

    async def interpret_stream(
        self, question: str, result: dict
    ) -> AsyncIterator[str]:
        """LLM 流式解读。"""
        q = (question or "").strip() or "所问之事"
        changing = "、".join(result["changing_yao_names"]) or "无"
        user_prompt = f"""用户问题：{q}

本卦：{result['primary_gua']}（上卦：{result['upper_trigram']}，下卦：{result['lower_trigram']}）
动爻：{changing}
变卦：{result['changed_gua']}

卦象：
{result['primary_text']}

请给出六爻解读。"""

        msgs = [SystemMessage(content=self._system_prompt), HumanMessage(content=user_prompt)]
        try:
            has_any_chunk = False
            async for chunk in self.chat_model.astream(msgs):
                text = chunk.content
                if text:
                    has_any_chunk = True
                    yield text
            if not has_any_chunk:
                yield self._fallback_reading(result)
        except Exception:
            log.exception("六爻 LLM 解读失败")
            yield "\n[AI 解读暂不可用，以下为卦象基础信息]\n\n"
            yield self._fallback_reading(result)

    def _fallback_reading(self, result: dict) -> str:
        changing = "、".join(result["changing_yao_names"]) or "无"
        return (
            f"本卦：{result['primary_gua']}，上卦{result['upper_trigram']}、下卦{result['lower_trigram']}，"
            f"动爻：{changing}。变卦：{result['changed_gua']}。\n\n"
            "卦象信息如上，建议结合《周易》卦辞与爻辞进一步参详。"
        )
