"""八字合婚应用：规则排盘基础数据 + LLM 综合解读（无状态，模块函数）。

从 app.api.tools 抽出：合婚规则计算复用 bazi_hehun 工具，LLM 解读独立成服务，
路由层只做参数校验与并发调度。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.prompts import HEHUN_SYSTEM_PROMPT
from app.core.logger import log
from app.tools.text_clean import clean_think_tags


def rule_basis(
    birth_time_a: str,
    gender_a: str,
    birth_time_b: str,
    gender_b: str,
    sect: int = 2,
    longitude_a: float | None = None,
    longitude_b: float | None = None,
) -> str:
    """调规则合婚工具（bazi_hehun）生成双盘基础数据；参数非法时以"合婚失败"开头。"""
    from app.tools.bazi import bazi_hehun

    return bazi_hehun.invoke(
        {
            "birth_time_a": birth_time_a,
            "gender_a": gender_a,
            "birth_time_b": birth_time_b,
            "gender_b": gender_b,
            "sect": sect,
            "longitude_a": longitude_a,
            "longitude_b": longitude_b,
        }
    )


def analyze(
    birth_time_a: str,
    gender_a: str,
    birth_time_b: str,
    gender_b: str,
    sect: int = 2,
    longitude_a: float | None = None,
    longitude_b: float | None = None,
    chat_model=None,
) -> str:
    """合婚分析：先拿规则基础数据，再由 LLM 做综合解读。

    chat_model 为 None（如未初始化）或解读失败时回退规则结果。
    """
    base_result = rule_basis(
        birth_time_a, gender_a, birth_time_b, gender_b,
        sect=sect, longitude_a=longitude_a, longitude_b=longitude_b,
    )
    if not base_result or base_result.startswith("合婚失败") or chat_model is None:
        return base_result

    messages = [
        SystemMessage(content=HEHUN_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "以下是系统根据双方出生时间自动排盘生成的合婚基础数据，"
                "请基于这些事实进行综合解读，给出缘分分析和合婚建议：\n\n"
                f"{base_result}"
            )
        ),
    ]
    try:
        resp = chat_model.invoke(messages)
        content = clean_think_tags((getattr(resp, "content", "") or "").strip())
        return content or base_result
    except Exception as e:
        log.warning("合婚 LLM 解读失败，返回规则结果: {}", e)
        return base_result