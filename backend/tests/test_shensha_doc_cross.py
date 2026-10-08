"""神煞口径 × 代码的交叉守卫：文档每个条目的「八字实例分析」必须与代码一致。

**能力边界（务必先读，别误以为它能抓所有偏差）**
本守卫只校验两件事：
  1. **存在性**——文档实例声明命中的神煞，代码要算得出来（守"表算错/判定条件失效"，
     典型事故形态：某神煞再也不出现，但没有任何测试报错）；
  2. **不多算**——文档结论为「此八字无X」的，代码不能算出来。

它**抓不到**柱位偏差与漏报/多报条数：2026-10-08 修的四类偏差（天罗地网柱位错位、
日柱多地转日、月柱漏德秀、年柱多天德）四种都仍然"命中"，本守卫一个都抓不到。
柱位与条数由 `test_shensha_rules.py`（问真对照盘专项）+ `test_bazi_golden.py`（24 例快照）负责。

之所以仍保留本守卫：文档口径比代码可靠（2026-10-08 实证四处全是代码跑偏），
用文档的 58 个实例做"存在性 + 不多算"交叉核对，是补在黄金快照之外的**另一维度**——
快照只覆盖 24 个盘，文档实例覆盖 58 个。

文档措辞不统一（「故X在Y柱」/「结论：有X在Y柱」/「结论：此八字无X」），
命中与否按结论段是否含**精确否定表述**判断。
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

from app.domain.chart_builder import build_bazi_chart, parse_gender
from app.domain.shensha_calc import _compute_shensha

KNOWLEDGE_DIR = Path(__file__).parents[1] / "app" / "rag" / "knowledge_docs"
DOC = KNOWLEDGE_DIR / "07_神煞初探.md"

# 2026-10-08 时的实例条数；文档新增条目后本守卫必须重新核对并更新此下界，
# 否则解析器漏读新条目会变成静默失效。
MIN_INSTANCES = 58

_HEAD_RE = re.compile(r"^### \d+\.\s*(.+?)\s*$")
_TIME_RE = re.compile(r"(\d{4})/(\d{2})/(\d{2})\s+(\d{1,2}):(\d{2})")
_PILLARS_RE = re.compile(r"[（(]([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]\s*){4}[)）]")

# 文档条目名 → 代码神煞名（"天罗地网"在代码里是两个独立煞，按用户要求不合并）
NAME_ALIAS = {"天罗地网": ("天罗", "地网")}


def _doc_expects_hit(name: str, line: str) -> bool:
    """实例结论是否声明「命中」。

    默认命中，仅在结论段出现**精确否定**时判不命中。否定判断必须带神煞名，
    否则会被「年干庚→贵人丑、未」这类含"未"的正常表述误伤。
    """
    tail = line.split("结论", 1)[-1] if "结论" in line else line
    for neg in (f"无{name}", f"没有{name}", "未找到", "不符合", "无此"):
        if neg in tail:
            return False
    return True


def _parse_doc():
    """→ [(条目名, 生辰, 文档四柱串|None, 是否期望命中)]"""
    out = []
    cur = None
    for line in DOC.read_text(encoding="utf-8").splitlines():
        m = _HEAD_RE.match(line)
        if m:
            cur = m.group(1).strip()
            continue
        if "八字实例分析" not in line or cur is None:
            continue
        tm = _TIME_RE.search(line)
        if not tm:
            continue
        y, mo, d, hh, mm = (int(x) for x in tm.groups())
        pm = _PILLARS_RE.search(line)
        pillars = pm.group(0).strip("（）() ") if pm else None
        out.append((cur, datetime.datetime(y, mo, d, hh, mm), pillars, _doc_expects_hit(cur, line)))
    return out


def test_doc_examples_match_code():
    """文档 58 条实例：文档称命中的代码必须算出；文档称"无此煞"的代码不能算出。"""
    items = _parse_doc()
    assert len(items) >= MIN_INSTANCES, (
        f"只解析到 {len(items)} 条实例（期望 ≥{MIN_INSTANCES}）："
        "文档格式可能改了，或新增条目未纳入核对 —— 请更新本守卫的解析逻辑与下界。"
    )

    four_pillar_mismatch, missed, extra = [], [], []
    for name, dt, doc_pillars, expects_hit in items:
        chart = build_bazi_chart(dt.strftime("%Y-%m-%d %H:%M"), "男")
        real = [p.ganzhi for p in chart.pillars]
        if doc_pillars and "".join(doc_pillars.split()) != "".join(real):
            four_pillar_mismatch.append(f"{name}@{dt:%Y-%m-%d}: doc={doc_pillars} code={''.join(real)}")
            continue
        want = NAME_ALIAS.get(name, (name,))
        got = [
            s["pillar"]
            for s in _compute_shensha(chart.pillars, parse_gender("男"))
            if s["name"] in want
        ]
        if not expects_hit:
            if got:
                extra.append(f"{name}@{dt:%Y-%m-%d %H:%M}: 文档称「无此煞」，代码却算出 {got}")
        elif not got:
            missed.append(f"{name}@{dt:%Y-%m-%d %H:%M} ({' '.join(real)})")

    assert not four_pillar_mismatch, "实例四柱与文档对不上（文档或解析器有问题）：\n" + "\n".join(
        four_pillar_mismatch
    )
    assert not missed, "文档称命中、代码没算出来（表算错或判定条件失效）：\n" + "\n".join(missed)
    assert not extra, "文档称不命中、代码却算出来（多算）：\n" + "\n".join(extra)
