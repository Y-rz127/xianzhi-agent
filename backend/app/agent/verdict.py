"""命盘 LLM 裁决（影子模式）：计算版之外的第二意见，只落库不生效。

影子模式的纪律
--------------
本模块**不得**被任何线上判定路径 import（K 线/命盘/聊天仍走计算版）。
唯一入口是 scripts/run_verdict_shadow.py 与后续的差异分析——
等影子数据证明 LLM 裁决比计算版更准，才轮到「切最终依据」的讨论。

输出契约：LLM 必须回严格 JSON，字段枚举钉死；
解析或校验失败 status=invalid 落库（raw_text 留排查），绝不静默吞掉。
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from app.core.logger import log
from app.domain.analysis_calc import ENGINE_VERSION
from app.domain.chart_builder import BaziChart

PROMPT_VERSION = "v3"

_VALID_STRENGTH = ("极旺", "偏旺", "中和", "偏弱", "极弱")
_VALID_WUXING = ("金", "木", "水", "火", "土")
_VALID_KIND = ("无", "专旺", "从格", "假从")
_VALID_RELATION = ("confirm", "override")
_VALID_LABELS = (
    "无", "曲直格", "炎上格", "稼穑格", "从革格", "润下格",
    "从财格", "从杀格", "从儿格", "从势格",
    "假从财格", "假从杀格", "假从儿格", "假从势格",
)

VERDICT_SYSTEM_PROMPT = """你是严谨的子平命理审盘人。引擎已按确定性规则算出初判（位置权重、藏干比、合冲刑害力学修正都已在其中），你的任务是复核这份初判并给出最终裁决。

先说结论倾向：**引擎初判经过全量标定盘校准，默认应当 confirm**。引擎的力学计算（五行权重、根气画像、合冲修正）比人工直觉可靠；你复核的价值在于捕捉引擎力学无法表达的**结构性**命理机制，而不是重新比一遍五行大小。

confirm 与 override 的门槛（刻意不对称）：
- **confirm**：初判的强弱/格局与盘面结构不矛盾，即可确认。盘面接近档位边界（初判分数在门槛附近）时，**必须 confirm**——边界盘的裁量不构成推翻依据。
- **override**：必须同时满足三条，缺一不可——
  a) 存在引擎力学**无法表达**的结构性论据（如禄根被冲而力散于全局、微根被合化截断而无生克通路、虚浮天干不受生）；
  b) 该论据**直接改变**旺衰档位或格局结论（仅"轻重之别"不够）；
  c) 论据出自给定材料或主流命理共识（子平/滴天髓口径），不是你的个人发挥。
- 以下情形**一律 confirm**：你的论据其实已被引擎涵盖（合冲修正 notes 里已列出的机制）；你只是对权重占比有不同感觉；你说不出引擎具体哪一步算错。

其余纪律：
1. 只依据【给定事实】与【引擎初判】判断，不得虚构盘面信息。
2. 日主极弱无根且克泄耗一行独旺时考虑从格；一行独旺无克泄时考虑专旺。
3. 用神唯一：正格按扶抑（弱喜印比、旺喜克泄耗），从格喜所从之神、忌印比，专旺顺其旺势。
4. reason 须引用至少一条具体盘面事实（如"三酉冲一卯，禄根被伤"），不得空话；override 时须点名引擎错在哪一步。

输出**严格 JSON**（无 markdown 代码块、无多余文字）：
{"relation_to_engine": "confirm|override 之一",
 "strength": "极旺|偏旺|中和|偏弱|极弱 之一",
 "special_pattern": "无|专旺|从格|假从 之一",
 "special_label": "无|曲直格|炎上格|稼穑格|从革格|润下格|从财格|从杀格|从儿格|从势格|假从财格|假从杀格|假从儿格|假从势格 之一",
 "useful_god": "金|木|水|火|土 之一",
 "avoid_god": "金|木|水|火|土 之一",
 "reason": "≤150字裁决依据，须引用具体盘面事实；override 时须点名引擎错在哪一步"}"""


def computed_snapshot(chart: BaziChart) -> dict[str, Any]:
    """计算版结论快照（对比基准）：与 LLM verdict 同构，便于逐字段 diff。

    strength_band：成格时 strength 字段装的是格名（从杀格），档位须从
    special_pattern 反推（从格/假从→极弱、专旺→极旺）—— LLM 的 strength
    恒为五档，diff 时按档位对齐，否则表示法冲突会淹没实质分歧。
    """
    w = chart.wuxing
    hint = w.useful_hint
    if w.special_pattern == "专旺":
        band = "极旺"
    elif w.special_pattern in ("从格", "假从"):
        band = "极弱"
    else:
        band = w.strength
    return {
        "strength": band,
        "strength_raw": w.strength,
        "special_pattern": w.special_pattern or "无",
        "special_label": w.strength if w.special_pattern else "无",
        "useful_hint": hint,
    }


def build_verdict_context(chart: BaziChart) -> str:
    """排盘事实 + 引擎初判 → 裁决提示词的 Human 部分。

    引擎初判直接给 LLM 看（确认/推翻模式）：计算版承担确定性力学，
    LLM 在其上做格局成败、从象真伪等动态裁量——不是从零重算。
    """
    w = chart.wuxing
    lines = [
        f"四柱：{' '.join(p.ganzhi for p in chart.pillars)}（{chart.birth.solar} {chart.birth.gender}）",
        f"日主：{w.day_master}（{w.day_master_wuxing}）",
        f"月令：{chart.analysis.season}；调候：{chart.analysis.adjustment}",
        f"五行权重（对日干影响，已含位置权重与合冲刑害修正）：{w.counts}",
        f"显性五行计数：{w.visible_counts}",
        f"十神分布：{chart.analysis.ten_gods}",
        f"透干：{chart.analysis.exposed_stems or '无'}；通根：{chart.analysis.rooted_stems or '无'}",
        f"天干关系：合={[c for c in chart.analysis.combinations if '干合' in c] or '无'}；"
        f"冲={[c for c in chart.analysis.clashes if '干冲' in c] or '无'}",
        f"地支关系：合局/会方={chart.analysis.three_assemblies or '无'}；"
        f"六合/半合={chart.analysis.combinations or '无'}；冲={chart.analysis.clashes or '无'}；"
        f"刑={chart.analysis.punishments or '无'}；害={chart.analysis.harms or '无'}",
    ]
    rel_notes = [n for n in w.notes[3:]] if len(w.notes) > 3 else []
    if rel_notes:
        lines.append(f"合冲刑害力学修正（已应用于上述权重）：{'；'.join(rel_notes)}")
    lines.append(
        f"\n【引擎初判（供审阅，可推翻但须说理）】\n"
        f"强弱：{w.strength}（score={w.strength_score}）\n"
        f"格局：{w.special_pattern or '无'}{('·' + w.strength) if w.special_pattern else ''}\n"
        f"用神方向：{w.useful_hint}"
    )
    return "\n".join(lines)


def parse_verdict(text: str) -> dict[str, Any]:
    """从 LLM 回复中提取并校验裁决 JSON；不合规抛 ValueError（status=invalid）。"""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("回复中无 JSON 对象")
    data = json.loads(m.group(0))
    if data.get("relation_to_engine") not in _VALID_RELATION:
        raise ValueError(f"relation_to_engine 非法: {data.get('relation_to_engine')!r}")
    if data.get("strength") not in _VALID_STRENGTH:
        raise ValueError(f"strength 非法: {data.get('strength')!r}")
    if data.get("special_pattern") not in _VALID_KIND:
        raise ValueError(f"special_pattern 非法: {data.get('special_pattern')!r}")
    if data.get("special_label") not in _VALID_LABELS:
        raise ValueError(f"special_label 非法: {data.get('special_label')!r}")
    for key in ("useful_god", "avoid_god"):
        if data.get(key) not in _VALID_WUXING:
            raise ValueError(f"{key} 非法: {data.get(key)!r}")
    reason = (data.get("reason") or "").strip()
    if len(reason) < 10:
        raise ValueError("reason 过短或缺失")
    # kind 与 label 的一致性：pattern=无 时 label 必须为无；反之 label 须带对应字样
    if data["special_pattern"] == "无" and data["special_label"] != "无":
        raise ValueError("pattern=无 但 label 非无")
    if data["special_pattern"] != "无" and data["special_label"] == "无":
        raise ValueError("pattern 非无 但 label=无")
    return {
        "relation_to_engine": data["relation_to_engine"],
        "strength": data["strength"],
        "special_pattern": data["special_pattern"],
        "special_label": data["special_label"],
        "useful_god": data["useful_god"],
        "avoid_god": data["avoid_god"],
        "reason": reason,
    }


def diff_verdicts(llm: dict[str, Any], computed: dict[str, Any]) -> str:
    """LLM 终审 vs 引擎初判的差异摘要（空=LLM 确认引擎且结论一致）。

    strength 按档位对齐：引擎成格时 strength 装格名，LLM 恒为五档
    （computed_snapshot 已把档位反推进 strength 字段）。
    """
    diffs = []
    if llm["relation_to_engine"] == "override":
        diffs.append(f"[override] {llm['reason'][:60]}")
    if llm["strength"] != computed["strength"]:
        diffs.append(f"强弱: 引擎{computed['strength']}→终审{llm['strength']}")
    if llm["special_label"] != computed["special_label"]:
        diffs.append(f"格局: 引擎{computed['special_label']}→终审{llm['special_label']}")
    return "；".join(diffs)


async def run_shadow_verdict(chart: BaziChart, model) -> dict[str, Any]:
    """对单张命盘跑一次 LLM 裁决并落库（影子：结果不参与任何线上判定）。

    model：LangChain ChatModel（异步 ainvoke）；由调用方构造（脚本直连
    DashScope，线上未来接 get_sub_app_model）。返回落库行摘要。
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.core.llm_throttle import llm_tag
    from app.db.chart_store import chart_hash_of
    from app.db.schema import _ensure_tables

    _ensure_tables()
    chash = chart_hash_of(chart.birth.solar, chart.birth.gender)
    computed = computed_snapshot(chart)
    context = build_verdict_context(chart)

    started = time.monotonic()
    try:
        with llm_tag("verdict"):
            response = await model.ainvoke(
                [SystemMessage(content=VERDICT_SYSTEM_PROMPT), HumanMessage(content=context)]
            )
        latency_ms = int((time.monotonic() - started) * 1000)
        raw = str(response.content)
        verdict = parse_verdict(raw)
        status, verdict_payload = "ok", verdict
    except Exception as e:
        latency_ms = int((time.monotonic() - started) * 1000)
        raw = f"{type(e).__name__}: {e}"
        verdict_payload = None
        status = "invalid"
        log.warning("[verdict] 裁决解析失败: {}", e)

    diff = diff_verdicts(verdict_payload, computed) if verdict_payload else "invalid"
    row = {
        "chart_hash": chash,
        "birth_time": chart.birth.solar,
        "gender": chart.birth.gender,
        "engine_version": ENGINE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "status": status,
        "verdict": verdict_payload,
        "computed": computed,
        "diff": diff,
        "model": getattr(model, "model_name", "") or "",
        "latency_ms": latency_ms,
        "raw_text": raw[:4000],
    }
    await asyncio.to_thread(_upsert_verdict, row)
    return row


def _upsert_verdict(row: dict[str, Any]) -> None:
    from app.db.pool import get_pool

    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO chart_verdicts
                (chart_hash, birth_time, gender, engine_version, prompt_version,
                 status, verdict, computed, diff, model, latency_ms, raw_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chart_hash, engine_version, prompt_version)
            DO UPDATE SET status = EXCLUDED.status, verdict = EXCLUDED.verdict,
                          computed = EXCLUDED.computed, diff = EXCLUDED.diff,
                          model = EXCLUDED.model, latency_ms = EXCLUDED.latency_ms,
                          raw_text = EXCLUDED.raw_text, created_at = NOW()
            """,
            (
                row["chart_hash"], row["birth_time"], row["gender"],
                row["engine_version"], row["prompt_version"], row["status"],
                json.dumps(row["verdict"], ensure_ascii=False) if row["verdict"] else None,
                json.dumps(row["computed"], ensure_ascii=False),
                row["diff"], row["model"], row["latency_ms"], row["raw_text"],
            ),
        )
