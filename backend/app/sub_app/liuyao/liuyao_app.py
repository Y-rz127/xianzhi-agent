"""轻量、可复现的六爻起卦核心（爻序由下至上）。"""

from __future__ import annotations

from typing import Any, Generator

import random
from datetime import datetime

from app.agent.prompts import LIUYAO_SYSTEM_PROMPT
from app.api.context import get_app_context
from app.core.llm_throttle import llm_tag
from app.core.logger import log

TRIGRAMS = {
    "111": ("乾", "天", "☰"),
    "110": ("兑", "泽", "☱"),
    "101": ("离", "火", "☲"),
    "100": ("震", "雷", "☳"),
    "011": ("巽", "风", "☴"),
    "010": ("坎", "水", "☵"),
    "001": ("艮", "山", "☶"),
    "000": ("坤", "地", "☷"),
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
    return {
        "index": index + 1,
        "value": value,
        "yang": yang,
        "moving": moving,
        "symbol": "━━━ ○ ━━━"
        if value == 9
        else "━━ ━━ × ━━ ━"
        if value == 6
        else "━━━━━━━"
        if yang
        else "━━ ━━",
    }


def _hexagram(lines: list[dict]) -> dict:
    bits = "".join("1" if line["yang"] else "0" for line in lines)
    lower = TRIGRAMS[bits[:3]][0]
    upper = TRIGRAMS[bits[3:]][0]
    # HEXAGRAMS 按 [下卦][上卦] 编排（"乾"行即内卦为乾的八卦）
    name = HEXAGRAMS[lower][TRIGRAM_ORDER.index(upper)]
    return {
        "name": name,
        "upper": {"name": upper, "symbol": TRIGRAMS[bits[3:]][2]},
        "lower": {"name": lower, "symbol": TRIGRAMS[bits[:3]][2]},
    }


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
    changed = [
        _line(7 if line["value"] == 6 else 8 if line["value"] == 9 else line["value"], i)
        for i, line in enumerate(lines)
    ]
    moving = [line["index"] for line in lines if line["moving"]]
    return {
        "method": method,
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "lines": lines,
        "original": _hexagram(lines),
        "changed": _hexagram(changed) if moving else None,
        "movingLines": moving,
        "summary": "静卦重在观其本意。"
        if not moving
        else f"第{'、'.join(map(str, moving))}爻发动，宜结合本卦与变卦的变化来审视问题。",
    }


def _hexagram_text(hexagram: dict | None) -> str:
    name = (hexagram or {}).get("name", "")
    if not name:
        return "无"
    upper = (hexagram.get("upper") or {}).get("name", "")
    lower = (hexagram.get("lower") or {}).get("name", "")
    return f"{name}（上卦{upper}，下卦{lower}）" if upper and lower else name


def _normalize_chunk_text(raw_content: Any) -> str:
    """归一化 LLM 流式返回的 chunk 文本（兼容多种格式）。"""
    if raw_content is None:
        return ""
    if isinstance(raw_content, str):
        text = raw_content.strip()
        return text if text else ""
    if isinstance(raw_content, list):
        texts = []
        for item in raw_content:
            if isinstance(item, dict) and item.get("text"):
                texts.append(item["text"])
            elif isinstance(item, str):
                texts.append(item)
        text = " ".join(texts).strip()
        return text if text else ""
    if isinstance(raw_content, dict):
        for key in ("text", "content", "delta", "result"):
            val = raw_content.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        for val in raw_content.values():
            if isinstance(val, str) and len(val) > 20 and not val.startswith("<"):
                return val.strip()
        return ""
    text = str(raw_content)
    if len(text) > 200 or "<__" in text or "object at 0x" in text:
        return ""
    return text.strip()


async def interpret_stream(question: str, result: dict) -> Generator[str, None, None]:
    """流式解读六爻结果。"""
    lines = {line.get("index"): line for line in result.get("lines") or []}
    moving = result.get("movingLines") or []
    if not moving:
        moving_text = "无（静卦）"
    else:
        moving_text = "；".join(
            f"第{i}爻（老阳，阳动变阴）"
            if (lines.get(i) or {}).get("value") == 9
            else f"第{i}爻（老阴，阴动变阳）"
            if (lines.get(i) or {}).get("value") == 6
            else f"第{i}爻"
            for i in moving
        )
    prompt = (
        f"请为以下六爻占卜做深度解读：\n\n"
        f"占问者的问题：{question}\n\n"
        f"本卦：{_hexagram_text(result.get('original'))}\n"
        f"变卦：{_hexagram_text(result.get('changed'))}\n"
        f"动爻：{moving_text}\n\n"
        f"请按照系统提示中的结构解读：卦象主题 → 动爻解读 → 本变卦演变 → 具体建议。\n"
        f"解读要落到占问者的具体问题上。"
    )
    from langchain_core.messages import HumanMessage, SystemMessage

    msgs = [SystemMessage(content=LIUYAO_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    try:
        has_any_chunk = False
        with llm_tag("liuyao"):
            async for chunk in get_app_context().chat_model.astream(msgs):
                text = _normalize_chunk_text(getattr(chunk, "content", None))
                if text:
                    has_any_chunk = True
                    yield text
        if not has_any_chunk:
            log.warning("六爻 LLM 返回空片段")
            yield "\n\n[AI 解读暂不可用]\n\n"
    except Exception as e:
        log.exception("六爻 LLM 解读失败")
        yield f"\n\n[AI 解读暂不可用：{type(e).__name__}]\n\n"
