"""出生信息解析（从用户输入提取生日 / 性别 / 八字四柱 / 生辰信号）。

纯函数模块，不持有实例状态，供 Xianzhi 智能体的 mount_chart_context 调用。
从 app/agent/xianzhi.py 抽离（解耦：把生辰解析这一单一职责独立成模块），
行为与原内联实现完全一致。
"""
from __future__ import annotations

import re
from typing import Optional

# 中国城市经度映射（自动生成，见 app/domain/city_longitude.py）
from app.domain.city_longitude import CITY_LONGITUDE

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
    月/日/时/分做范围校验（正则 1-2 位数字会放过 13 月/32 日/25 时等非法值）。
    """
    for pattern in (_BIRTH_INFO_RE, _BIRTH_INFO_RE2):
        m = pattern.search(text)
        if m:
            d = m.groupdict()
            month, day = int(d["month"]), int(d["day"])
            hour, minute = int(d["hour"]), int(d["minute"])
            if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
                continue  # 数值越界（如 1992-13-45），视为非出生信息，尝试下一模式
            birth_time = "{}-{:02d}-{:02d} {:02d}:{:02d}".format(
                int(d["year"]), month, day, hour, minute,
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


def birth_place_to_longitude(place: Optional[str]) -> float:
    """把出生地文本解析为东经度数（用于真太阳时校正），无法识别返回 0（不校正）。

    匹配优先级：
    1. 省级行政区划词后的城市段（"四川省成都市" → "成都"）；
    2. 从左到右的后缀子串，最长优先（"四川成都" → "成都"、"呼和浩特" → "呼和浩特"）。
    城市经度数据见 app/domain/city_longitude.py（与前端 shared/utils/region-data.ts 同源）。
    """
    if not place:
        return 0.0
    p = re.sub(r"\s+", "", str(place).strip())
    if not p:
        return 0.0
    candidates = []
    # 优先：行政区划词后的最后一段（城市段）
    parts = re.split(r"省|自治区|特别行政区|自治州", p)
    if len(parts) > 1 and parts[-1]:
        candidates.append(parts[-1])
    # 兜底：后缀子串最长优先
    candidates.extend(p[i:] for i in range(len(p)))
    for seg in candidates:
        key = seg.replace("市", "")
        if key in CITY_LONGITUDE:
            return CITY_LONGITUDE[key]
    return 0.0


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
    cands = pending.get("candidates") or []
    if not cands:
        return None
    # ① 年份命中（带数字边界："2004年" 命中，但 "2004" 不会误命中 "12004年"）
    for c in cands:
        bt = c.get("birth_time", "")
        y = bt[:4]
        if y and re.search(r"(?<!\d)" + y + r"(?!\d)", text):
            return bt
    # ② 序号：第N个 / 选N / 开头 N（支持中文数字 一二三…）
    m = re.search(r"第\s*([0-9]+|[" + "".join(_CN_NUM.keys()) + r"])", text)
    if not m:
        m = re.search(r"选\s*([0-9]+|[" + "".join(_CN_NUM.keys()) + r"])", text)
    if not m:
        m = re.match(r"\s*([0-9]+)", text)
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
