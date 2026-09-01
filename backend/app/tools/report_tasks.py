"""报告任务执行器：各 kind 的实际生成逻辑（同步、CPU/LLM 密集，调用方放线程池）。

从 app/api/xianzhi.py 迁出：接口层只负责提交/查询任务，生成逻辑与执行器同居一处。
"""
from __future__ import annotations

from typing import Any

from app.core.llm_throttle import llm_tag
from app.tools.bazi import bazi_analysis, bazi_chart, bazi_dayun, bazi_liunian
from app.tools.pdf_report import generate_bazi_report
from app.tools.report_generator import DEFAULT_SECTIONS, generate_full_report

# kind -> (human 文件名前缀, content-type)
KINDS = {
    "basic_report": ("xianzhi_bazi_report", "application/pdf"),
    "full_report": ("xianzhi_full_report", "text/markdown; charset=utf-8"),
    "full_report_pdf": ("xianzhi_full_report", "application/pdf"),
}


def _sections(params: dict) -> list[str]:
    raw = (params.get("sections") or "").strip()
    return [s for s in raw.split(",") if s] if raw else list(DEFAULT_SECTIONS)


def build_basic_report_pdf(birth_time: str, gender: str) -> bytes:
    """基础 PDF：排盘工具 + 渲染，无 LLM 调用。"""
    chart_text = bazi_chart.invoke({"birth_time": birth_time, "gender": gender})
    analysis_text = bazi_analysis.invoke({"birth_time": birth_time, "gender": gender, "question": "整体命盘"})
    dayun_text = bazi_dayun.invoke({"birth_time": birth_time, "gender": gender, "count": 8})
    liunian_text = bazi_liunian.invoke({"birth_time": birth_time, "gender": gender, "years": 10})
    return generate_bazi_report(
        birth_time=birth_time,
        gender=gender,
        chart_text=chart_text,
        analysis_text=analysis_text,
        dayun_text=dayun_text,
        liunian_text=liunian_text,
    )


def build_full_report_markdown(chat_model: Any, params: dict) -> bytes:
    """LLM 分节报告（Markdown 文本）。"""
    content = generate_full_report(chat_model, params["birth_time"], params["gender"], _sections(params))
    return content.encode("utf-8")


def build_full_report_pdf(chat_model: Any, params: dict) -> bytes:
    """LLM 分节报告渲染为 PDF（多次 LLM 调用 + 排盘 + PDF 渲染）。"""
    ai_commentary = generate_full_report(chat_model, params["birth_time"], params["gender"], _sections(params))
    chart_text = bazi_chart.invoke({"birth_time": params["birth_time"], "gender": params["gender"]})
    analysis_text = bazi_analysis.invoke(
        {"birth_time": params["birth_time"], "gender": params["gender"], "question": "整体命盘"}
    )
    dayun_text = bazi_dayun.invoke({"birth_time": params["birth_time"], "gender": params["gender"], "count": 8})
    liunian_text = bazi_liunian.invoke({"birth_time": params["birth_time"], "gender": params["gender"], "years": 10})
    return generate_bazi_report(
        birth_time=params["birth_time"],
        gender=params["gender"],
        chart_text=chart_text,
        analysis_text=analysis_text,
        dayun_text=dayun_text,
        liunian_text=liunian_text,
        ai_commentary=ai_commentary,
    )


def run_task(chat_model: Any, kind: str, params: dict) -> bytes:
    """按 kind 分发执行，返回产物字节。"""
    with llm_tag("report"):
        if kind == "basic_report":
            return build_basic_report_pdf(params["birth_time"], params["gender"])
        if kind == "full_report":
            return build_full_report_markdown(chat_model, params)
        if kind == "full_report_pdf":
            return build_full_report_pdf(chat_model, params)
    raise ValueError(f"未知任务类型: {kind}")