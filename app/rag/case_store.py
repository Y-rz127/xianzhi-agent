"""Structured case retrieval for experience-style prompting.

The knowledge base keeps raw rules and classics.  This module keeps case-like
records separate so the workflow can inject a few relevant examples as
few-shot references without treating them as authoritative rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.bazi_engine import BaziChart
from app.logger import log
from app.rag.vector_store import _keyword_overlap


@dataclass(frozen=True)
class CaseRecord:
    id: str
    title: str
    question_domain: str
    content: str
    source: str = ""
    rating: int = 4
    verified: bool = True
    features: dict[str] = field(default_factory=dict)


def _read_db_cases() -> list[CaseRecord]:
    """从 PostgreSQL 读取相似命例：cases（命理库八字命例）+ chart_cases（用户反馈结构化案例）。"""
    try:
        from app.db import user_data
        records: list[CaseRecord] = []

        # 1) cases 表：命理库收录的八字命例（Web 端新建 + 历史命盘）
        for item in user_data.search_cases_for_rag(limit=200):
            content = (item.get("content") or "").strip()
            if not content:
                continue
            records.append(CaseRecord(
                id=str(item.get("id") or ""),
                title=str(item.get("title") or ""),
                question_domain=str(item.get("domains") or ["general"])[0] if item.get("domains") else "general",
                content=content,
                source=str(item.get("source") or "cases"),
                rating=int(item.get("rating") or 5),
                verified=bool(item.get("verified", True)),
                features=dict(item.get("features") or {}),
            ))

        # 2) chart_cases 表：用户反馈转换的结构化案例
        for item in user_data.search_chart_cases(limit=200):
            content = (item.get("analysis") or "").strip()
            if not content:
                continue
            records.append(CaseRecord(
                id=str(item.get("id") or ""),
                title=str(item.get("title") or ""),
                question_domain=str(item.get("domains") or ["general"])[0] if item.get("domains") else "general",
                content=content,
                source=str(item.get("source") or "chart_cases"),
                rating=int(item.get("rating") or 4),
                verified=bool(item.get("verified", True)),
                features=dict(item.get("features") or {}),
            ))

        return records
    except Exception as e:
        log.warning("从 DB 加载案例失败: {}", e)
        return []


class CaseLibrary:
    def __init__(self):
        self._records: list[CaseRecord] | None = None

    def load(self, force: bool = False) -> list[CaseRecord]:
        if self._records is not None and not force:
            return self._records
        records = _read_db_cases()
        self._records = records
        log.info("结构化命例库加载完成，共 {} 条", len(records))
        return records

    def search(self, chart: BaziChart, question: str, domain: str, top_k: int = 1) -> list[CaseRecord]:
        records = [r for r in self.load() if r.verified and r.rating >= 4]
        if not records or domain == "chitchat":
            return []
        day_wuxing = chart.wuxing.day_master_wuxing or ""
        strength = chart.wuxing.strength or ""
        scored: list[tuple[float, CaseRecord]] = []
        for record in records:
            score = _keyword_overlap(question, record.title + "\n" + record.content) * 3
            if record.question_domain == domain:
                score += 1.5
            elif record.question_domain == "general":
                score += 0.3
            features = record.features or {}
            if day_wuxing and features.get("day_master_wuxing") == day_wuxing:
                score += 1.0
            if strength and features.get("strength") == strength:
                score += 0.8
            if features.get("day_master") and features.get("day_master") == (chart.wuxing.day_master or "")[:1]:
                score += 0.8
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda item: (-item[0], -item[1].rating, item[1].id))
        return [record for _, record in scored[:top_k]]

    def format_for_prompt(self, records: list[CaseRecord]) -> str:
        if not records:
            return ""
        parts: list[str] = []
        for idx, record in enumerate(records, 1):
            features = {k: v for k, v in record.features.items() if v}
            parts.append(
                f"### 案例{idx}：{record.title}（评分{record.rating}/5）\n"
                f"来源：{record.source or '结构化命例库'}\n"
                f"领域：{record.question_domain}; 特征：{features or '未标注'}\n"
                f"分析摘录：{record.content[:700]}"
            )
        return "\n\n".join(parts)


case_library = CaseLibrary()