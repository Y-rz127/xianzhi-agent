"""出生信息解析（从用户输入提取生日 / 性别 / 八字四柱 / 生辰信号）。

纯函数模块，不持有实例状态，供 Xianzhi 智能体的 mount_chart_context 调用。
从 app/agent/xianzhi.py 抽离（解耦：把生辰解析这一单一职责独立成模块），
行为与原内联实现完全一致。
"""
from __future__ import annotations

import re
from typing import Optional

from app.core.logger import log

# 从用户输入中尝试提取出生时间与性别（完整公历，如 "男 1992-05-03 14:30"）
_BIRTH_INFO_RE = re.compile(
    r"(?P<gender>男|女)[^\d]*(?P<year>\d{4})[-年/](?P<month>\d{1,2})[-月/](?P<day>\d{1,2})[日\s]*(?P<hour>\d{1,2})[:：](?P<minute>\d{1,2})",
    re.UNICODE,
)
_BIRTH_INFO_RE2 = re.compile(
    r"(?P<year>\d{4})[-年/](?P<month>\d{1,2})[-月/](?P<day>\d{1,2})[日\s]*(?P<hour>\d{1,2})[:：](?P<minute>\d{1,2})[^\d]*(?P<gender>男|女)",
    re.UNICODE,
)

# 从用户输入中识别八字四柱（如 "甲申庚午壬申甲辰"），用于反推候选出生日期
_PILLARS_RE = re.compile(r"([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]){4}")
_GENDER_RE = re.compile(r"(男|女|乾造|坤造|乾命|坤命)")

# 从用户输入中提取出生地（城市名，交给前端 region-data 匹配经度）
_BIRTH_PLACE_RE = re.compile(
    r"(?:出生于|出生在|出生地|生在|老家(?:是|在|位于)?|籍贯(?:是|在)?)[:：为]?\s*"
    r"([\u4e00-\u9fa5]{2,8}?)(?=[\s,，。.!！?？;；、）)）]|$)",
    re.UNICODE,
)

# 模糊生辰信号词：精确正则抓不到但用户确实在提供生辰信息时，用这些词做兜底检测
_SHICHEN_WORDS = ("子时", "丑时", "寅时", "卯时", "辰时", "巳时",
                  "午时", "未时", "申时", "酉时", "戌时", "亥时")
_LUNAR_WORDS = ("农历", "阴历")
_FESTIVAL_WORDS = ("春节", "元旦", "端午", "中秋", "重阳", "元宵",
                   "七夕", "中元", "腊八", "冬至")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")

# 八字选择解析用中文数字（"第一/选2/1" → 序号）
_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
           "七": 7, "八": 8, "九": 9, "十": 10}


def extract_birth_info(text: str):
    """从用户输入中提取出生时间和性别，返回 (birth_time, gender)。

    支持两种语序：性别在前（"男 1992-..."）或年份在前（"1992-... 男"）。
    未匹配返回 (None, None)。birth_time 标准化为 "YYYY-MM-DD HH:MM"。
    """
    for pattern in (_BIRTH_INFO_RE, _BIRTH_INFO_RE2):
        m = pattern.search(text)
        if m:
            d = m.groupdict()
            birth_time = "{}-{:02d}-{:02d} {:02d}:{:02d}".format(
                int(d["year"]), int(d["month"]), int(d["day"]),
                int(d["hour"]), int(d["minute"]),
            )
            return birth_time, d["gender"]
    return None, None


def extract_birth_place(text: str) -> Optional[str]:
    """从用户输入中提取出生地（城市名原文，未匹配返回 None）。

    仅提取出生地关键词附近的中文地名，交给前端 region-data 匹配经度。
    过滤含数字的明显非地名内容。
    """
    m = _BIRTH_PLACE_RE.search(text or "")
    if not m:
        return None
    place = m.group(1).strip()
    # 过滤明显的非地名内容（纯时间 / 数字 / 无意义词）
    if not place or any(ch.isdigit() for ch in place):
        return None
    return place


def extract_pillars(text: str):
    """从文本中提取八字四柱与性别，返回 (pillars8字, gender) 或 (None, None)。"""
    m = _PILLARS_RE.search(text or "")
    if not m:
        return None, None
    gm = _GENDER_RE.search(text or "")
    if not gm:
        return None, None
    g = gm.group(1)
    gender = "男" if g in ("男", "乾造", "乾命") else ("女" if g in ("女", "坤造", "坤命") else None)
    if not gender:
        return None, None
    return m.group(0), gender


def detect_birth_signal(text: str) -> bool:
    """检测文本是否含疑似生辰信号（年份 + 性别 + 时辰/农历/节日）。

    用于闲聊短路放行：当精确正则（_BIRTH_INFO_RE）无法抓取但用户确实
    在提供生辰信息时（如"2004年端午节 辰时 男"），不走闲聊短路，
    让 ReAct 路径的 LLM 调 bazi_full 排盘（工具内部 _normalize_birth_time
    支持农历/节日/时辰自动转公历）。

    判定条件（全部满足）：
    1. 含年份（19xx/20xx）
    2. 含性别（男/女/乾造/坤造等）
    3. 含时间信号（传统时辰 / 农历 / 阴历 / 节日 / HH:MM）
    """
    if not text:
        return False
    has_gender = bool(_GENDER_RE.search(text))
    has_year = bool(_YEAR_RE.search(text))
    if not (has_gender and has_year):
        return False
    has_time_signal = (
        any(w in text for w in _SHICHEN_WORDS)
        or any(w in text for w in _LUNAR_WORDS)
        or any(w in text for w in _FESTIVAL_WORDS)
        or bool(re.search(r"\d{1,2}[:：]\d{1,2}", text))
    )
    return has_time_signal


def resolve_bazi_selection(text: str, pending: dict) -> Optional[str]:
    """把用户回复解析为已选定的出生日期（birth_time）。

    支持：①回复候选序号（"第一个"/"第2个"/"选2"/"1"）；②回复候选年份（"2004年"）。
    未匹配返回 None，交由 LLM 继续追问。
    """
    import re as _re
    cands = pending.get("candidates") or []
    if not cands:
        return None
    # ① 年份命中
    for c in cands:
        bt = c.get("birth_time", "")
        y = bt[:4]
        if y and (y in text or _re.search(r"(?<!\d)" + y + r"(?!\d)", text)):
            return bt
    # ② 序号：第N个 / 选N / 开头 N（支持中文数字 一二三…）
    m = _re.search(r"第\s*([0-9]+|[" + "".join(_CN_NUM.keys()) + r"])", text)
    if not m:
        m = _re.search(r"选\s*([0-9]+|[" + "".join(_CN_NUM.keys()) + r"])", text)
    if not m:
        m = _re.match(r"\s*([0-9]+)", text)
    if m:
        tok = m.group(1)
        idx = _CN_NUM.get(tok, None)
        if idx is None:
            try:
                idx = int(tok)
            except ValueError:
                idx = None
        if idx is not None:
            idx -= 1
            if 0 <= idx < len(cands):
                return cands[idx].get("birth_time")
    return None
