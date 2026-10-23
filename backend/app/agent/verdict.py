"""命盘 LLM 裁决：阶段三已转正——LLM 终审为格局/强弱/用神的最终依据。

演进纪律
--------
阶段一~二（影子模式）：本模块只被 scripts/run_verdict_shadow.py 调用，
结果只落库 chart_verdicts 不生效。经 v4~v7 四轮影子对比（铁律遵守、
论据质量、结构化合规均达标，模型阵容 qwen3.8-27b 主 + deepseek-v4-pro 备），
用户拍板转正：线上通过 `chart_with_verdict` 接入——

- 缓存命中（chart_hash+engine_version+prompt_version 的 ok 行）直接取，毫秒级；
- 未命中调 LLM 裁决并落库（同盘只判一次，之后所有人复用，省时间省 token）；
- LLM 失败/超时/invalid 一律回退计算版（引擎初判兜底，绝不阻塞主流程）。

终审模型沿用主问答模型（get_chat_model，同一模型池与降级链），
不单独走子应用配置。

输出契约：LLM 必须回严格 JSON，字段枚举钉死；
解析或校验失败 status=invalid 落库（raw_text 留排查），绝不静默吞掉。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
import time
from dataclasses import replace
from typing import Any

from app.core.logger import log
from app.core.privacy import safe_birth_time
from app.domain.analysis_calc import ENGINE_VERSION
from app.domain.chart_builder import BaziChart
from app.domain.fortune_score import detect_ailment, favor_vector

PROMPT_VERSION = "v9"

# 终审 LLM 总超时（秒）：模型层各有 timeout/重试/熔断，这里兜底防接口被拖死
_VERDICT_TIMEOUT = 180.0

_VALID_STRENGTH = ("极旺", "偏旺", "中和", "偏弱", "极弱")
_VALID_WUXING = ("金", "木", "水", "火", "土")
_VALID_KIND = ("无", "专旺", "从格", "假从")
_VALID_RELATION = ("confirm", "override")
_VALID_LABELS = (
    "无",
    "曲直格",
    "炎上格",
    "稼穑格",
    "从革格",
    "润下格",
    "从财格",
    "从杀格",
    "从儿格",
    "从势格",
    "假从财格",
    "假从杀格",
    "假从儿格",
    "假从势格",
)

VERDICT_SYSTEM_PROMPT = """你是严谨的子平命理审盘人。引擎已按确定性规则算出初判（位置权重、藏干比、合冲刑害力学修正都已在其中），你的任务是复核这份初判并给出最终裁决。

先说结论倾向：**引擎初判经过全量标定盘校准，默认应当 confirm**。引擎的力学计算（五行权重、根气画像、合冲修正）比人工直觉可靠；你复核的价值在于捕捉引擎力学无法表达的**结构性**命理机制，而不是重新比一遍五行大小。

confirm 与 override 的门槛（刻意不对称）：
- **confirm**：初判的强弱/格局与盘面结构不矛盾，即可确认。盘面接近档位边界（初判分数在门槛附近）时，**必须 confirm**——边界盘的裁量不构成推翻依据。
- **override**：必须同时满足三条，缺一不可——
  a) 存在引擎力学**无法表达**的结构性论据（如禄根被冲而力散于全局、微根被合化截断而无生克通路、虚浮天干不受生等）；
  b) 该论据**直接改变**旺衰档位或格局结论（仅"轻重之别"不够）；
  c) 论据出自给定材料或主流命理共识（子平/滴天髓等权威古籍口径），不是你的个人发挥。
- 以下情形**一律 confirm**：你的论据其实已被引擎涵盖（合冲修正 notes 里已列出的机制）；你只是对权重占比有不同感觉；你说不出引擎具体哪一步算错。

其余纪律：
1. 只依据【给定事实】与【引擎初判】判断，不得虚构盘面信息。
2. **从格三档口径**（铁律）：《子平真诠》："从者，日主无根，满局官杀，无印绶以化之，无比劫以分之，而后可从。"据此分三档——
   - 完全无根（禄刃库根皆无）：才可能判**真从**；
   - 仅余气/中气微根：不得判真从，最多讨论**假从**（实战以正格为稳妥）；
   - 禄刃强根（哪怕被冲，冲是根损不是根灭）或印比透干有地支支撑：**正格，不论从**。
   - **例外（根变性入局）**：微根所在的地支若已合而化成**所从之神**（三合局/三会方/六合化为所从五行），根气变性归局、名存实亡，微根不碍从——可直接判**真从**。合为他行或仅合绊不化的，不适用此例外。
   - 合化成立的条件是合化的五行在原局处于旺/相状态，不然合而不化(引擎已经有了这个逻辑)。盘面已给出引擎的根气画像三档判定，可对照引用，但你有权按盘面结构复核它。
3. **印旺不等于身旺**（土重金埋）：日元须有一定力量方能受重印所生；日主无强根而印星独大成势时（如水多木漂），是印重身弱之病，不判身旺，亦不轻判从格——按印重病药论（忌印、喜财制印/比劫泄印）取用。
4. 日主极弱无根或微根被冲克受损、合化变性且克泄耗一行独旺时考虑从格；一行独旺无克泄或克泄耗极低可忽略不计时考虑专旺。
5. 通用规则：正格按扶抑（弱喜印比、旺喜克泄耗），从格喜所从之神、忌印比，专旺顺其旺势。
6. **五神取用（子平口径）**，按五行的**功能**分五类，不要混用：
   - **用神**（useful_god，必填）：对命局起关键救应作用的那一行，全局的枢纽；
   - **忌神**（avoid_god，必填）：克用神或助长病神者（如用神水而土克水）；
   - **喜神**（xishen，可选）：生扶用神、助其成用者（如用神水，则金生水为喜）；
   - **仇神**（choushen，可选）：克喜神、生忌神者，属"帮凶"性质（如喜金而火克金、火又生土）；
   - **平神**（pingshen，可选）：既非喜亦非忌的闲神，只在盘面确实中立时才填。
   后三类**不是每张盘都能判出来**：分析不出就留空数组，绝不为了凑数硬填；
   注意：五神取用需结合具体盘面结构和五行生克制化关系综合判断；某一五行即使对日主有帮助，但是过旺也可能导致五行失衡，转药为病。
7. reason 须引用至少一条具体盘面事实（如"三酉冲一卯，禄根被伤"），不得空话；override 时须点名引擎错在哪一步。

输出**严格 JSON**（无 markdown 代码块、无多余文字）：
{"relation_to_engine": "confirm|override 之一",
 "strength": "极旺|偏旺|中和|偏弱|极弱 之一",
 "special_pattern": "无|专旺|从格|假从 之一",
 "special_label": "无|曲直格|炎上格|稼穑格|从革格|润下格|从财格|从杀格|从儿格|从势格|假从财格|假从杀格|假从儿格|假从势格 之一",
 "useful_god": "金|木|水|火|土 之一（用神，必填）",
 "avoid_god": "金|木|水|火|土 之一（忌神，必填）",
 "xishen": ["金|木|水|火|土", "…"],   // 喜神，可空数组（判断不出就给 []）
 "choushen": ["金|木|水|火|土", "…"],  // 仇神，可空数组
 "pingshen": ["金|木|水|火|土", "…"],  // 平神，可空数组
 "reason": "≤300字裁决依据，须引用具体盘面事实；override 时须点名引擎错在哪一步"}"""


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
    v5 起把引擎的关键中间结论一并透出（根气画像、强弱分构成、藏干明细、
    K 线喜忌方向）——LLM 要"点名引擎错在哪一步"，就得看到分数怎么来的。
    """
    w = chart.wuxing
    # 地支藏干串提前拼：f-string 内嵌 f-string 不能复用外层引号（Python 3.11 语法）
    zhigan = " ".join(f"{p.zhi}[{'、'.join(p.hidden_stems)}]" for p in chart.pillars)
    lines = [
        f"四柱：{' '.join(p.ganzhi for p in chart.pillars)}（{chart.birth.solar} {chart.birth.gender}）",
        f"日主：{w.day_master}（{w.day_master_wuxing}）；根气画像（引擎判定）：{w.root_verdict}",
        f"月令：{chart.analysis.season}；调候：{chart.analysis.adjustment}",
        f"地支藏干：{zhigan}",
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

    lines.append("\n【引擎初判（供审阅，可推翻但须说理，K 线喜忌方向可一并复核）】")
    detail = w.strength_detail or {}
    sup, pre = detail.get("support", {}), detail.get("pressure", {})
    lines.append(
        f"强弱：{w.strength}（score={w.strength_score}）\n"
        f"分构成（合冲修正后权重，未乘系数）：support=比劫{sup.get('比劫', 0)}"
        f" + 印{sup.get('印星', 0)}×{sup.get('印系数', 0.85)}"
        f" − 虚浮折扣{sup.get('虚浮折扣', 0)} − 根损折扣{sup.get('根损折扣', 0)}；"
        f"pressure=食伤{pre.get('食伤', 0)}×0.55 + 财{pre.get('财', 0)}×0.7"
        f" + 官杀{pre.get('官杀', 0)}×0.8\n"
        f"格局：{w.special_pattern or '无'}{('·' + w.strength) if w.special_pattern else ''}"
    )
    fav = favor_vector(chart)
    if fav:
        fav_str = "、".join(f"{k}{v:+.2f}" for k, v in sorted(fav.items(), key=lambda x: -x[1]))
        ailment = detect_ailment(chart)
        lines.append(f"K线用神判定：病神={ailment or '无'}；喜忌倾向（正喜负忌）：{fav_str}")
    lines.append(f"用神方向：{w.useful_hint}")
    return "\n".join(lines)


def _parse_god_list(data: dict[str, Any], key: str) -> list[str]:
    """解析可选五神数组（喜神/仇神/平神）：缺省或空 → []，非法五行 → 整份裁决 invalid。

    契约是"分析不出就留空"，所以缺字段、null、空串、空数组一律视为"没判出来"，
    只有**写了但写错**（非五行、非数组）才算 invalid —— 不能因为模型少给一类就整份作废。
    """
    raw = data.get(key)
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):  # 容忍 "金、水" 这种串行写法
        raw = [p for p in re.split(r"[、,，/\s]+", raw) if p]
    if not isinstance(raw, list):
        raise ValueError(f"{key} 需为数组（或省略）")
    out: list[str] = []
    for item in raw:
        s = str(item).strip()
        if not s:
            continue
        if s not in _VALID_WUXING:
            raise ValueError(f"{key} 含非法五行: {s!r}")
        if s not in out:
            out.append(s)
    return out


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
    # 五神去重：用神/忌神已占用的五行不再留在喜/仇/平里（口径"一行只归一类"）；
    # 只在**留下的**那几个之间继续占位——被"每类最多两个"截掉的不算已归类，
    # 否则模型多写一个喜神，会把本可以显示的同类仇神/平神一起悄悄吃掉。
    taken = {data["useful_god"], data["avoid_god"]}
    gods: dict[str, list[str]] = {}
    for key in ("xishen", "choushen", "pingshen"):
        kept = [w for w in _parse_god_list(data, key) if w not in taken]
        # 每类最多两个：五神本就少见堆砌，写多了是模型在凑，保留前两个即可
        kept = kept[:2]
        taken.update(kept)
        gods[key] = kept
    return {
        "relation_to_engine": data["relation_to_engine"],
        "strength": data["strength"],
        "special_pattern": data["special_pattern"],
        "special_label": data["special_label"],
        "useful_god": data["useful_god"],
        "avoid_god": data["avoid_god"],
        **gods,
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
                row["chart_hash"],
                row["birth_time"],
                row["gender"],
                row["engine_version"],
                row["prompt_version"],
                row["status"],
                json.dumps(row["verdict"], ensure_ascii=False) if row["verdict"] else None,
                json.dumps(row["computed"], ensure_ascii=False),
                row["diff"],
                row["model"],
                row["latency_ms"],
                row["raw_text"],
            ),
        )


# ---------------- 阶段三：终审应用（缓存 → LLM → 回退计算版） ----------------


def _err_text(e: BaseException) -> str:
    """异常文案兜底：`str(TimeoutError())` 是空串，直接打日志会只剩一个冒号。

    Asyncio 的超时/取消类异常都不带消息，统一补类型名，日志才查得下去。
    """
    return str(e).strip() or type(e).__name__


def _verdict_enabled() -> bool:
    """终审总开关：VERDICT_ENABLED=0 关闭；pytest 内自动禁用（快照不可依赖 LLM）。"""
    if os.environ.get("VERDICT_ENABLED") == "0":
        return False
    return "pytest" not in sys.modules


def _get_cached_verdict(chash: str) -> dict[str, Any] | None:
    """取同版本（engine+prompt）的 ok 裁决；无则 None。命中即毫秒级复用。"""
    from app.db.pool import get_pool

    with get_pool().connection() as conn:
        row = conn.execute(
            """
            SELECT verdict FROM chart_verdicts
            WHERE chart_hash = %s AND engine_version = %s AND prompt_version = %s
              AND status = 'ok'
            """,
            (chash, ENGINE_VERSION, PROMPT_VERSION),
        ).fetchone()
    if row is None:
        return None
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def _get_stale_verdict(chash: str) -> dict[str, Any] | None:
    """取**任意版本**最近一次 ok 裁决（版本升级后的降级展示用）。

    为什么需要它：`_get_cached_verdict` 按 (engine, prompt) 精确匹配，版本一 bump
    全线 miss。此时若仍走"同步判一次"，用户进对话/进详情页就要白等 LLM 跑完
    （最多 _VERDICT_TIMEOUT=180s）——命盘按钮甚至要等排盘返回才出现。
    正确做法是**旧版结论先顶上**（标注旧版），后台同时重判当前版本。
    """
    from app.db.pool import get_pool

    with get_pool().connection() as conn:
        row = conn.execute(
            """
            SELECT verdict FROM chart_verdicts
            WHERE chart_hash = %s AND status = 'ok'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (chash,),
        ).fetchone()
    if row is None:
        return None
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def _apply_stale(chart: BaziChart, chash: str = "") -> BaziChart | None:
    """有旧版裁决就应用并返回新 chart；没有/读失败/结构不兼容返回 None。

    旧行可能来自更早的版本、字段口径不同——应用失败绝不能让 /chart 500，
    一律降级为计算版（后台照常重判当前版本）。
    """
    chash = chash or _hash_of(chart)
    if not chash:
        return None
    try:
        stale = _get_stale_verdict(chash)
    except Exception as e:
        log.warning("[verdict] 旧版裁决读取失败，按无缓存处理: {}", _err_text(e))
        return None
    if stale is None:
        return None
    try:
        return apply_verdict(
            chart, stale, stale.get("relation_to_engine", "confirm"), stale=True
        )
    except Exception as e:
        log.warning("[verdict] 旧版裁决结构不兼容，回退计算版: {}", _err_text(e))
        return None


def verdict_applied(chart: BaziChart) -> bool:
    """该 chart 是否已应用 LLM 终审（apply_verdict 会追加一条 "LLM终审[...]" 注记）。

    接口层缓存的 payload 里嵌着终审结论，靠这个判断决定缓存命名空间；前端也用它
    决定要不要提示"终审版生成中，下拉刷新"。旧版终审也算已应用（结论同样来自 LLM），
    是否过期另看 `verdict_is_stale`。
    """
    return any(
        str(n).startswith(("LLM终审[", "LLM终审·旧版[")) for n in chart.wuxing.notes
    )


def verdict_is_stale(chart: BaziChart) -> bool:
    """该 chart 应用的是**旧版本**终审（版本已 bump、当前版本仍在后台重判）。

    用途：接口层缓存命名空间 —— 旧版载荷不能进 "v"，否则新裁决落库后
    cache key 不变、详情页会永远吐旧结论。
    """
    return any(str(n).startswith("LLM终审·旧版[") for n in chart.wuxing.notes)


def apply_verdict(
    chart: BaziChart, verdict: dict[str, Any], relation: str = "override", stale: bool = False
) -> BaziChart:
    """把终审裁决写回 chart.wuxing（不可变替换，原 chart 不动）。

    表示法沿用引擎约定：成格时 strength 装格名（如"从杀格"）、special_pattern
    装类别；正格时 strength 装五档。力学数值（counts/score/strength_detail）
    保留计算版不动 —— 终审覆盖的是**结论标签**，不是力学基础。

    stale=True 表示这是旧版本裁决的临时顶替（注记会写明"旧版"），后台会重判。
    """
    w = chart.wuxing
    pattern = "" if verdict["special_pattern"] == "无" else verdict["special_pattern"]
    strength = verdict["special_label"] if pattern else verdict["strength"]
    hint = f"日主{verdict['strength']}，最喜{verdict['useful_god']}，最忌{verdict['avoid_god']}（LLM 终审）。"
    prefix = "LLM终审·旧版" if stale else "LLM终审"
    notes = [*w.notes, f"{prefix}[{PROMPT_VERSION}]：{relation}——{verdict['reason'][:80]}"]
    return replace(
        chart,
        wuxing=replace(w, strength=strength, special_pattern=pattern, useful_hint=hint, notes=notes),
    )


def five_gods_from_verdict(verdict: dict[str, Any]) -> dict[str, str]:
    """裁决 JSON → 五神可读串（用神/喜神/忌神/仇神/平神）。

    **只返回判得出来的类别**：某类没给（或给的数组为空）就整键缺席，前端据此不显示，
    而不是显示一个空标签或"未定"。键与前端约定一致：yongshen/xishen/jishen/choushen/pingshen。
    """

    def _join(*groups: Any) -> str:
        out: list[str] = []
        for group in groups:
            items = group if isinstance(group, (list, tuple)) else [group]
            for item in items:
                s = str(item or "").strip()
                if s and s not in out:
                    out.append(s)
        return "、".join(out)

    gods = {
        "yongshen": _join(verdict.get("useful_god")),  # 用神
        "xishen": _join(verdict.get("xishen") or []),  # 喜神
        "jishen": _join(verdict.get("avoid_god")),  # 忌神
        "choushen": _join(verdict.get("choushen") or []),  # 仇神
        "pingshen": _join(verdict.get("pingshen") or []),  # 平神
    }
    return {k: v for k, v in gods.items() if v}


def verdict_five_gods(chart: BaziChart) -> dict[str, str]:
    """已应用终审 → 五神（缺项缺席）；未终审或读不到裁决 → 空 dict。

    为什么回读 DB 而不是把五神塞进 chart.wuxing：`WuxingAnalysis` 是纯力学事实载体，
    往里加展示字段会污染命盘快照（36 例黄金快照逐字比对）。终审结论本来就以
    chart_verdicts 为准，展示层按需回读更干净；失败一律降级为 `{}`（前端回退「最喜/最忌」）。
    """
    if not verdict_applied(chart):
        return {}
    chash = _hash_of(chart)
    if not chash:
        return {}
    try:
        cached = _get_cached_verdict(chash)
        if not cached and verdict_is_stale(chart):
            # 旧版终审正在顶替展示：五神也从旧版裁决取，否则页面会"有结论没喜忌"
            cached = _get_stale_verdict(chash)
    except Exception as e:
        log.warning("[verdict] 五神回读失败（前端回退计算版喜忌）: {}", _err_text(e))
        return {}
    if not cached:
        return {}
    return five_gods_from_verdict(cached)


async def chart_with_verdict(
    chart: BaziChart, model: Any = None, *, allow_stale: bool = True
) -> BaziChart:
    """终审应用主入口（async 路径：/chart、/kline、聊天挂载）。

    **前台一律不阻塞**：同版本缓存命中直接应用；只有旧版裁决 → 先应用旧版并派后台
    重判；连旧版都没有（首次排盘）→ 先给计算版并派后台补判。用户随时能进详情页，
    下拉刷新即得终审结论。

    allow_stale=False 只给后台重判线程用：那里才真正同步调 LLM 并落库；
    若后台也走"先顶上"分支，就永远不会产生新版本裁决（死循环式空转）。
    """
    if not _verdict_enabled():
        return chart
    try:
        from app.db.chart_store import chart_hash_of

        chash = chart_hash_of(chart.birth.solar, chart.birth.gender)
    except Exception as e:  # DB 不可用：直接回退，不拖主流程
        log.warning("[verdict] chart_hash 计算失败，回退计算版: {}", e)
        return chart

    verdict = None
    try:
        verdict = await asyncio.to_thread(_get_cached_verdict, chash)
    except Exception as e:
        log.warning("[verdict] 缓存读取失败，走 LLM 裁决: {}", _err_text(e))

    if verdict is None and allow_stale:
        stale_chart = await asyncio.to_thread(_apply_stale, chart, chash)
        if stale_chart is not None:
            log.info(
                "[verdict] {} 当前版本无裁决，先应用旧版终审并后台重判",
                safe_birth_time(chart.birth.solar),
            )
            _submit_background_verdict(chart, model, chash)
            return stale_chart
        # 首次排盘：也不等 LLM。详情页先显示计算版（前端有"终审版生成中"提示），
        # 后台判完落库，下次请求/下拉刷新即是终审版。
        log.info(
            "[verdict] {} 首次排盘无任何裁决，先给计算版并后台补判",
            safe_birth_time(chart.birth.solar),
        )
        _submit_background_verdict(chart, model, chash)
        return chart

    # 只有后台重判线程（allow_stale=False）会走到这里：真正同步调 LLM 并落库。
    # 前台请求在上面两个分支已经返回，永远不会为了终审让用户等 180 秒。
    if verdict is None:
        try:
            if model is None:
                # 终审沿用主问答模型（同一模型池与降级链），不单独走子应用配置。
                # 2026-10-11：曾考虑终审改走 flash 快模型，用户验证过输出口径不可用，否决。
                from app.agent.context import get_chat_model

                model = get_chat_model()
            row = await asyncio.wait_for(run_shadow_verdict(chart, model), timeout=_VERDICT_TIMEOUT)
            if row["status"] == "ok":
                verdict = row["verdict"]
            else:
                log.warning(
                    "[verdict] {} 裁决 invalid，回退计算版",
                    safe_birth_time(chart.birth.solar),
                )
        except asyncio.TimeoutError:
            # 单独接住：TimeoutError 的 str() 是空串，混在通用分支里会打成
            # "LLM 裁决失败（）"这种查不出所以然的日志（2026-10-11）
            log.warning(
                "[verdict] {} 裁决超时（{}s 预算），回退计算版",
                safe_birth_time(chart.birth.solar),
                int(_VERDICT_TIMEOUT),
            )
        except Exception as e:
            log.warning(
                "[verdict] {} LLM 裁决失败（{}），回退计算版",
                safe_birth_time(chart.birth.solar),
                _err_text(e),
            )

    if verdict is None:
        return chart
    return apply_verdict(chart, verdict, verdict.get("relation_to_engine", "confirm"))


# 后台补判去重：同一张盘同时只允许一个补判在跑。密集挂盘（一次对话里反复排同一张盘）
# 会连着派发同一个 chart_hash，不去重就是判三遍——既烧 token，又跟正在跑的对话抢模型配额。
_bg_inflight: set[str] = set()
_bg_inflight_lock = threading.Lock()


def _hash_of(chart: BaziChart) -> str:
    """命盘指纹；失败返回空串（调用方按"拿不到指纹就回退计算版"处理）。"""
    try:
        from app.db.chart_store import chart_hash_of

        return chart_hash_of(chart.birth.solar, chart.birth.gender)
    except Exception as e:
        log.warning("[verdict] chart_hash 计算失败: {}", _err_text(e))
        return ""


def verdict_in_flight(chash: str) -> bool:
    """这张盘是否已有后台补判在跑（接口层据此避免重复判、重复等）。"""
    if not chash:
        return False
    with _bg_inflight_lock:
        return chash in _bg_inflight


def verdict_cache_namespace(chash: str) -> str:
    """进程内 payload 缓存的命名空间：v=同版本裁决 / s=只有旧版 / p=无裁决。

    接口层缓存的 payload 里嵌着终审结论，key 不带这个状态就会出现"先按计算版缓存过、
    此后补判落库了也永远吐旧 payload"——命盘详情页会一直停在计算版。
    **旧版终审必须单独占 "s"**：若把它当 "v"，新裁决落库后 key 不变，页面会永远
    吐旧结论（版本升级后"下拉刷新也刷不出新的"）。DB 读不到时按计算版处理
    （宁可白算一次，也不要把没终审的载荷当终审版供出去）。
    """
    if not chash:
        return "p"
    try:
        if _get_cached_verdict(chash) is not None:
            return "v"
        return "s" if _get_stale_verdict(chash) is not None else "p"
    except Exception as e:
        log.warning("[verdict] 缓存命名空间判定失败，按计算版处理: {}", _err_text(e))
        return "p"


async def chart_with_verdict_for_api(chart: BaziChart, model: Any = None) -> BaziChart:
    """/chart、/kline 等 HTTP 接口用：已有后台补判在跑就跳过终审。

    重复判没有意义：后台那次跑完会落库，下次请求命中缓存自然就是终审版；这里再判
    一次只会让用户多等（最多 _VERDICT_TIMEOUT 秒）并重复烧 token。
    但"跳过"不等于给计算版——有旧版裁决就先顶上，旧结论也比没有强。
    """
    if _verdict_enabled():
        chash = _hash_of(chart)
        if verdict_in_flight(chash):
            log.info("[verdict] {} 已有后台补判在跑，本次请求直接用旧版/计算版", chart.birth.solar)
            stale_chart = await asyncio.to_thread(_apply_stale, chart, chash)
            return stale_chart if stale_chart is not None else chart
    return await chart_with_verdict(chart, model)


def chart_with_verdict_sync(chart: BaziChart, model: Any = None) -> BaziChart:
    """终审应用的同步包装（工具线程 / 挂盘路径）。

    三条路径一致地**不阻塞**：同版本缓存命中直接应用；只有旧版裁决时先应用旧版
    （标注"旧版"）并派后台重判；连旧版都没有则返回计算版并派后台。绝不为了终审
    阻塞主链路。

    为什么不留"阻塞等终审"的选项：2026-10-11 实测，挂盘为了等终审白卡满
    _VERDICT_TIMEOUT（150 秒）× 2 次，把整轮从半分钟拖成 4 分钟；而且超时后拿到的
    仍是计算版——干等纯亏。终审是**影子增强**：结论写回只影响断语口径，晚一轮命中
    没有任何损失。终审改走快模型曾被否（flash 输出口径不可用），所以只能"后台跑"。

    block 参数已废弃删除：调用方（bazi_full hook / 挂盘）从未显式传过。
    """
    if not _verdict_enabled():
        return chart

    chash = _hash_of(chart)
    if not chash:
        return chart

    try:
        cached = _get_cached_verdict(chash)
    except Exception as e:
        # 本轮拿不到缓存（DB 抖）不影响正确性：回退计算版 + 照常派后台补判
        log.warning("[verdict] 缓存读取失败，回退计算版: {}", _err_text(e))
        cached = None
    else:
        if cached is not None:
            return apply_verdict(chart, cached, (cached or {}).get("relation_to_engine", "confirm"))

    # 版本升级：旧版裁决先顶上（标注旧版），后台同步重判当前版本
    stale_chart = _apply_stale(chart, chash)
    _submit_background_verdict(chart, model, chash)
    return stale_chart if stale_chart is not None else chart


def _submit_background_verdict(chart: BaziChart, model: Any, chash: str) -> None:
    """派一个后台补判线程；同一 chart_hash 已在跑则跳过（去重）。"""
    with _bg_inflight_lock:
        if chash in _bg_inflight:
            return
        _bg_inflight.add(chash)
    threading.Thread(
        target=_background_verdict, args=(chart, model, chash), name="verdict-bg", daemon=True
    ).start()


def _background_verdict(chart: BaziChart, model: Any, chash: str = "") -> None:
    """后台补判：独立线程里跑完整 async 流程；失败只留日志。

    这里**不再套自己的 wait_for**：chart_with_verdict 内部已经有 150 秒预算兜底，
    外面再叠一层同长的等待只会先到期、取消内层，把真实原因（超时/排队/上游报错）
    一起吞掉——2026-10-11 那 4 条只有冒号的日志就是这么来的。

    `allow_stale=False` 是关键：后台线程若也走"旧版先顶上"分支，就会立刻返回旧版、
    永远不产生新版本裁决——版本升级后旧结论将一直顶替下去。
    """
    try:
        asyncio.run(chart_with_verdict(chart, model, allow_stale=False))
    except Exception as e:
        log.warning(
            "[verdict] 后台补判失败（{} {}）: {}",
            chart.birth.solar,
            chart.birth.gender,
            _err_text(e),
        )
    finally:
        if chash:
            with _bg_inflight_lock:
                _bg_inflight.discard(chash)
