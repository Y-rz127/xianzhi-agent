"""轻量、可复现的六爻起卦核心（爻序由下至上）。"""
from __future__ import annotations

import random
from datetime import datetime

TRIGRAMS = {
    "111": ("乾", "天", "☰"), "110": ("兑", "泽", "☱"),
    "101": ("离", "火", "☲"), "100": ("震", "雷", "☳"),
    "011": ("巽", "风", "☴"), "010": ("坎", "水", "☵"),
    "001": ("艮", "山", "☶"), "000": ("坤", "地", "☷"),
}
HEXAGRAMS = {
    "乾": ["乾为天", "泽天夬", "火天大有", "雷天大壮", "风天小畜", "水天需", "山天大畜", "地天泰"],
    "兑": ["天泽履", "兑为泽", "火泽睽", "雷泽归妹", "风泽中孚", "水泽节", "山泽损", "地泽临"],
    "离": ["天火同人", "泽火革", "离为火", "雷火丰", "风火家人", "水火既济", "山火贲", "地火明夷"],
    "震": ["天雷无妄", "泽雷随", "火雷噬嗑", "震为雷", "风雷益", "水雷屯", "山雷颐", "地雷复"],
    "巽": ["天风姤", "泽风大过", "火风鼎", "雷风恒", "巽为风", "水风井", "山风蛊", "地风升"],
    "坎": ["天水讼", "泽水困", "火水未济", "雷水解", "风水涣", "坎为水", "山水蒙", "地水师"],
    "艮": ["天山遁", "泽山咸", "火山旅", "雷山小过", "风山渐", "水山蹇", "艮为山", "地山谦"],
    "坤": ["天地否", "泽地萃", "火地晋", "雷地豫", "风地观", "水地比", "山地剥", "坤为地"],
}
TRIGRAM_ORDER = ["乾", "兑", "离", "震", "巽", "坎", "艮", "坤"]


def _line(value: int, index: int) -> dict:
    yang = value in (7, 9)
    moving = value in (6, 9)
    return {"index": index + 1, "value": value, "yang": yang, "moving": moving,
            "symbol": "━━━ ○ ━━━" if value == 9 else "━━ ━━ × ━━ ━" if value == 6 else "━━━━━━━" if yang else "━━ ━━"}


def _hexagram(lines: list[dict]) -> dict:
    bits = "".join("1" if line["yang"] else "0" for line in lines)
    lower = TRIGRAMS[bits[:3]][0]
    upper = TRIGRAMS[bits[3:]][0]
    # HEXAGRAMS 按 [下卦][上卦] 编排（"乾"行即内卦为乾的八卦）
    name = HEXAGRAMS[lower][TRIGRAM_ORDER.index(upper)]
    return {"name": name, "upper": {"name": upper, "symbol": TRIGRAMS[bits[3:]][2]},
            "lower": {"name": lower, "symbol": TRIGRAMS[bits[:3]][2]}}


def cast(method: str, numbers: list[int] | None = None) -> dict:
    if method == "numbers" and numbers and len(numbers) >= 2:
        first, second = abs(numbers[0]), abs(numbers[1])
        values = [6 + ((first + second + i * 3) % 4) for i in range(6)]
    elif method == "time":
        now = datetime.now()
        seed = now.year + now.month + now.day + now.hour
        values = [6 + ((seed + i * 5) % 4) for i in range(6)]
    else:
        values = [sum(random.choice((2, 3)) for _ in range(3)) for _ in range(6)]
        method = "coins"
    lines = [_line(value, index) for index, value in enumerate(values)]
    changed = [_line(7 if line["value"] == 6 else 8 if line["value"] == 9 else line["value"], i) for i, line in enumerate(lines)]
    moving = [line["index"] for line in lines if line["moving"]]
    return {"method": method, "createdAt": datetime.now().isoformat(timespec="seconds"), "lines": lines,
            "original": _hexagram(lines), "changed": _hexagram(changed) if moving else None, "movingLines": moving,
            "summary": "静卦重在观其本意。" if not moving else f"第{'、'.join(map(str, moving))}爻发动，宜结合本卦与变卦的变化来审视问题。"}
