"""结构化命例库：与知识库规则分离，供 workflow 注入 few-shot 案例参考。

知识库存原始规则与古籍，本模块单独存放案例类记录，避免把案例当作权威规则使用。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logger import log
from app.domain.bazi_engine import BaziChart
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
    features: dict = field(default_factory=dict)


def _to_record(item: dict, *, content_key: str, default_source: str, default_rating: int) -> CaseRecord | None:
    content = (item.get(content_key) or "").strip()
    if not content:
        return None
    domains = item.get("domains")
    return CaseRecord(
        id=str(item.get("id") or ""),
        title=str(item.get("title") or ""),
        question_domain=(domains or ["general"])[0] if domains else "general",
        content=content,
        source=str(item.get("source") or default_source),
        rating=int(item.get("rating") or default_rating),
        verified=bool(item.get("verified", True)),
        features=dict(item.get("features") or {}),
    )


def _read_db_cases() -> list[CaseRecord]:
    """从 PostgreSQL 读取相似命例：cases（命理库八字命例）+ chart_cases（用户反馈结构化案例）。"""
    try:
        from app.db import user_data
        records = [_to_record(item, content_key="content", default_source="cases", default_rating=5)
                   for item in user_data.search_cases_for_rag(limit=200)]
        records += [_to_record(item, content_key="analysis", default_source="chart_cases", default_rating=4)
                    for item in user_data.search_chart_cases(limit=200)]
        return [r for r in records if r is not None]
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
