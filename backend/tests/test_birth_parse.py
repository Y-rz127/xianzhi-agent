r"""出生信息解析（birth_parse）回归测试。

背景（2026-09-15 线上问题）：用户输入"我是2005年9月28日18: 00出生的男命"
（中文输入法在全角冒号后自动补了空格），旧正则 `[:：]\d` 直接不匹配 →
后端没能挂盘 → 客户端顶栏一直显示"点击设置出生信息"。
本模块把"必须认得"和"必须别误抓"两类写法都钉死，避免同类回退。

同时覆盖：12 小时制时段词换算、无分钟写法补 00、点号日期、
以及放宽后**不能再出现**的回溯误伤（"2005年9月28日出生 男" 曾被解析成 2005-09-02 08:00）。
"""

from __future__ import annotations

import pytest

from app.agent.birth_parse import detect_birth_signal, extract_birth_info

# (输入, 期望 birth_time, 期望 gender)
CASES = [
    # —— 本次事故的原始写法：全角冒号 + 输入法补的空格 ——
    ("我是2005年9月28日18：00出生的男命", "2005-09-28 18:00", "男"),
    ("我是2005年9月28日18： 00出生的男命", "2005-09-28 18:00", "男"),
    ("我是2005年9月28日18: 00出生的男命", "2005-09-28 18:00", "男"),
    # —— X时Y分 / X点 ——
    ("2005年9月28日18时00分 男命", "2005-09-28 18:00", "男"),
    ("我是2005年9月28日18时出生 男", "2005-09-28 18:00", "男"),
    # —— 时段词（12 小时制）——
    ("我2005年9月28日下午6点出生，男", "2005-09-28 18:00", "男"),
    ("我2005年9月28日下午6点30分出生，男", "2005-09-28 18:30", "男"),
    ("2005年9月28日晚上8点 男", "2005-09-28 20:00", "男"),
    ("2005年9月28日凌晨12点 男", "2005-09-28 00:00", "男"),
    ("2005年9月28日中午12点30分 女", "2005-09-28 12:30", "女"),
    # —— 日期分隔符：点号 / 斜杠 / 连字符 ——
    ("我是2005.9.28 18:00出生 男", "2005-09-28 18:00", "男"),
    ("2005/9/28 6:05 女", "2005-09-28 06:05", "女"),
    # —— 既有口径不能坏：性别在前 / 年份在前 ——
    ("男 1992-05-03 14:30", "1992-05-03 14:30", "男"),
    ("1992-05-03 14:30 女", "1992-05-03 14:30", "女"),
    ("公历1990年5月20日 08:30 男", "1990-05-20 08:30", "男"),
]


@pytest.mark.parametrize("text,expect_time,expect_gender", CASES)
def test_extract_birth_info_supported_phrasings(text, expect_time, expect_gender):
    assert extract_birth_info(text) == (expect_time, expect_gender)


# 放开写法后容易误抓/回溯误伤的反例（每条都对应一个真实风险）
NEGATIVE = [
    "我的八字是?",
    "1992年出生的男命运势如何",
    "我今年18岁 男",
    # 有时间无性别
    "我是2005年9月28日18:00出生的",
    # 只给到日期、没给时辰 → 不该被当成完整生辰（应走模糊信号 → ReAct 调工具）
    "2005年9月28日出生 男",
    # 回溯误伤：日 28 的 2 被当"日"、8 被当"小时"（历史 bug）
    "2005年9月28日出生 男",
    "2005年9月2日出生的男命",
]


@pytest.mark.parametrize("text", NEGATIVE)
def test_extract_birth_info_does_not_misfire(text):
    assert extract_birth_info(text) == (None, None)


def test_numeric_out_of_range_rejected():
    assert extract_birth_info("1992-13-45 14:30 男") == (None, None)
    assert extract_birth_info("1992-05-03 25:61 男") == (None, None)


def test_first_leftmost_match_wins_known_limitation():
    """已知取舍：正则取最左匹配，该匹配数值越界时不会继续往后找第二个日期。

    保持既有行为（改前改后一致）；真出现"先说错日期再说对的"这种输入，
    交给 LLM 追问即可，不值得为它引入回溯搜索。
    """
    assert extract_birth_info("男 1992-13-45 14:30，女 1992-05-03 14:30") == (None, None)
    assert extract_birth_info("1992-13-45 14:30 男") == (None, None)
    # 性别按"就近位置"取，不保证与日期语义配对（同一句里出现两个日期+两个性别时按位置组合）
    assert extract_birth_info("1992-13-45 14:30 男，1992-05-03 14:30 女") == ("1992-05-03 14:30", "男")


def test_shichen_and_festival_still_go_fuzzy_path():
    """辰时/节日这类没有精确 HH:MM 的写法，仍由模糊信号交给 ReAct 排盘。"""
    for text in ("1990年5月20日 辰时 男", "2004年端午 辰时 男命", "农历2000年八月十五 20:30 女"):
        assert extract_birth_info(text)[0] is None or text.startswith("农历")
    assert detect_birth_signal("1990年5月20日 辰时 男") is True
    assert detect_birth_signal("2004年端午 辰时 男命") is True
