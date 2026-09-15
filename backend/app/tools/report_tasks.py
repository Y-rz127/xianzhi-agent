"""报告任务执行器：各 kind 的实际生成逻辑（同步、CPU/LLM 密集，调用方放线程池）。

从 app/api/xianzhi.py 迁出：接口层只负责提交/查询任务，生成逻辑与执行器同居一处。
"""
from __future__ import annotations

from typing import Any

from app.core.llm_throttle import llm_tag
from app.domain.chart_builder import (
    build_bazi_chart,
    chart_to_api_dict,
)
from app.tools.bazi import bazi_analysis, bazi_chart, bazi_dayun, bazi_liunian
from app.tools.pdf_report import generate_bazi_report
from app.tools.report_generator import DEFAULT_SECTIONS, generate_full_report


def _xipan_tables(birth_time: str, gender: str) -> dict[str, Any]:
    """从细盘取数拼 PDF 富表格：12 步大运 / 未来 12 年流年 / 当年 12 流月 / 关系六栏 / 按柱神煞。

    与专业细盘同源同口径（同一 build_bazi_chart），修掉旧 PDF 大运只有 9 步（count=8）的问题。
    """
    import datetime as _dt

    payload = chart_to_api_dict(build_bazi_chart(birth_time, gender, dayun_count=12))
    xp = payload["xipan"]
    today = _dt.date.today()

    dy_shensha = {
        d["index"]: [s["name"] for s in (d.get("shensha") or [])]
        for d in payload["dayun"]
    }
    dayun_rows = [{
        "ganzhi": d["ganzhi"],
        "shishen": d.get("shishen") or "—",
        "years": f"{d['startYear']}-{d['endYear']}",
        "ages": f"{d['startAge']}-{d['endAge']}岁",
        "hidden": "、".join(d.get("hiddenStems") or []) or "—",
        "fuxing": "、".join(d.get("shishenZhi") or []) or "—",
        "changsheng": d.get("changsheng") or "—",
        "shensha": "、".join(dy_shensha.get(d["index"], [])) or "—",
    } for d in xp["dayun"]]

    ln_shensha = xp.get("liunianShensha") or {}
    liunian_rows = [{
        "year": ln["year"],
        "ganzhi": ln["ganzhi"],
        "shishen": ln.get("shishen") or "—",
        "age": ln["age"],
        "changsheng": ln.get("changsheng") or "—",
        "shensha": "、".join(ln_shensha.get(ln["ganzhi"], [])) or "—",
    } for ln in xp["liunian"] if today.year <= ln["year"] <= today.year + 11]

    meta = xp.get("monthMeta") or {}
    lm_shensha = xp.get("liuyueShensha") or {}
    liuyue_rows = [{
        "jieqi": m["jieqi"],
        "date": m["date"],
        "ganzhi": m["ganzhi"],
        "shishen": m.get("shishen") or "—",
        "changsheng": (meta.get(m["zhi"]) or {}).get("changsheng") or "—",
        "shensha": "、".join(lm_shensha.get(m["ganzhi"], [])) or "—",
    } for m in xp["liuyue"] if m["year"] == today.year]

    by_pillar: dict[str, list[str]] = {}
    for s in payload.get("shensha") or []:
        by_pillar.setdefault(s.get("pillar") or "日柱", []).append(s["name"])
    shensha_by_pillar = [(p["name"], by_pillar.get(p["name"], [])) for p in payload["pillars"]]

    return {
        "dayun_rows": dayun_rows,
        "liunian_rows": liunian_rows,
        "liuyue_rows": liuyue_rows,
        "relations": xp.get("relations") or {},
        "shensha_by_pillar": shensha_by_pillar,
    }

# kind -> (human 文件名前缀, content-type)
KINDS = {
    "basic_report": ("xianzhi_bazi_report", "application/pdf"),
    "full_report": ("xianzhi_full_report", "text/markdown; charset=utf-8"),
    "full_report_pdf": ("xianzhi_full_report", "application/pdf"),
}


def _sections(params: dict) -> list[str]:
    raw = (params.get("sections") or "").strip()
    return [s for s in raw.split(",") if s] if raw else list(DEFAULT_SECTIONS)


def _collect_chart_texts(birth_time: str, gender: str) -> dict[str, str]:
    """一次取齐四处排盘文本（大运 12 步 / 流年 10 年，与专业细盘同口径）。"""
    return {
        "chart_text": bazi_chart.invoke({"birth_time": birth_time, "gender": gender}),
        "analysis_text": bazi_analysis.invoke(
            {"birth_time": birth_time, "gender": gender, "question": "整体命盘"}
        ),
        "dayun_text": bazi_dayun.invoke({"birth_time": birth_time, "gender": gender, "count": 12}),
        "liunian_text": bazi_liunian.invoke({"birth_time": birth_time, "gender": gender, "years": 10}),
    }


def build_basic_report_pdf(birth_time: str, gender: str) -> bytes:
    """基础 PDF：排盘工具 + 渲染，无 LLM 调用。"""
    return generate_bazi_report(
        birth_time=birth_time,
        gender=gender,
        **_collect_chart_texts(birth_time, gender),
        **_xipan_tables(birth_time, gender),
    )


def build_full_report_markdown(chat_model: Any, params: dict) -> bytes:
    """LLM 分节报告（Markdown 文本）。"""
    content = generate_full_report(chat_model, params["birth_time"], params["gender"], _sections(params))
    return content.encode("utf-8")


def build_full_report_pdf(chat_model: Any, params: dict) -> bytes:
    """LLM 分节报告渲染为 PDF（多次 LLM 调用 + 排盘 + PDF 渲染）。"""
    birth_time, gender = params["birth_time"], params["gender"]
    ai_commentary = generate_full_report(chat_model, birth_time, gender, _sections(params))
    return generate_bazi_report(
        birth_time=birth_time,
        gender=gender,
        ai_commentary=ai_commentary,
        **_collect_chart_texts(birth_time, gender),
        **_xipan_tables(birth_time, gender),
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
