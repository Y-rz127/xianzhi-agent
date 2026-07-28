"""案例向量库：结构化命例的存储与混合检索。

独立于知识库向量库，为 Workflow 提供「相似命例 Few-shot 注入」能力。
"""
from __future__ import annotations

import json
import hashlib
import time
import re
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.config import settings
from app.logger import log

CASES_DIR = Path("data/cases")
CASE_COLLECTION = "xianzhi_cases"
_FINGERPRINT_FILE = "cases_fingerprint.json"


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"\s+", "", s or "")
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _keyword_overlap(query: str, text: str) -> float:
    bq, bt = _bigrams(query), _bigrams(text)
    if not bq or not bt:
        return 0.0
    return len(bq & bt) / len(bq | bt)


def _load_cases() -> list[dict]:
    """从 data/cases/ 目录加载所有 JSON 案例。"""
    cases: list[dict] = []
    if not CASES_DIR.exists():
        log.warning("案例目录不存在: {}", CASES_DIR)
        return cases
    for f in sorted(CASES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            cases.append(data)
        except Exception as e:
            log.warning("加载案例文件失败 {}: {}", f.name, e)
    log.info("加载案例 {} 条", len(cases))
    return cases


def _case_to_document(case: dict) -> Document:
    """将案例 JSON 转为向量库 Document。

    page_content: 分析过程 + 结论，用于语义检索。
    metadata: 命局特征字段，用于元数据过滤。
    """
    features = case.get("features", {})
    text = f"【案例】{case.get('title', '')}\n"
    text += f"命局特征：{json.dumps(features, ensure_ascii=False)}\n"
    text += f"分析：{case.get('analysis', '')}\n"
    text += f"结论：{case.get('conclusion', '')}"

    meta = {
        "case_id": case.get("id", ""),
        "source": case.get("source", ""),
        "type": case.get("type", ""),
        "title": case.get("title", ""),
        "day_master": features.get("day_master", ""),
        "day_master_wuxing": features.get("day_master_wuxing", ""),
        "strength": features.get("strength", ""),
        "pattern": features.get("pattern", ""),
        "useful_god": features.get("useful_god", ""),
        "key_traits": json.dumps(features.get("key_traits", []), ensure_ascii=False),
        "domains": json.dumps(case.get("domains", []), ensure_ascii=False),
        "rating": case.get("rating", 0),
        "verified": case.get("verified", False),
        "keywords": json.dumps(case.get("keywords", []), ensure_ascii=False),
    }
    return Document(page_content=text, metadata=meta)


def _cases_hash() -> str:
    """对全部案例 JSON 文件内容计算哈希。"""
    h = hashlib.sha256()
    if CASES_DIR.exists():
        for f in sorted(CASES_DIR.glob("*.json")):
            h.update(f.name.encode("utf-8"))
            h.update(f.read_bytes())
    return h.hexdigest()


def _fingerprint_path() -> Path:
    return settings.vector_db_dir / _FINGERPRINT_FILE


def _load_fingerprint() -> dict | None:
    p = _fingerprint_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_fingerprint(docs_hash: str, embedding_id: str) -> None:
    p = _fingerprint_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "cases_hash": docs_hash,
        "embedding_id": embedding_id,
        "updated_at": time.time(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


class CaseStore:
    """案例向量库：加载、检索、管理命例案例。"""

    def __init__(self):
        self._store = None
        self._ready = False
        self._embeddings: Optional[Embeddings] = None

    @property
    def ready(self) -> bool:
        return self._ready

    def initialize(self, embeddings: Embeddings) -> None:
        """初始化案例向量库（与知识库共用 embedding 模型）。"""
        self._embeddings = embeddings
        try:
            from langchain_chroma import Chroma
            docs = _load_cases()
            if not docs:
                log.warning("案例库为空，跳过案例向量库初始化")
                return
            case_docs = [_case_to_document(c) for c in docs]
            current_hash = _cases_hash()
            fp = _load_fingerprint()
            embedding_id = getattr(embeddings, "model", "unknown")
            if fp and fp.get("cases_hash") == current_hash and fp.get("embedding_id") == embedding_id:
                self._store = Chroma(
                    collection_name=CASE_COLLECTION,
                    embedding_function=embeddings,
                    persist_directory=str(settings.vector_db_dir),
                )
                log.info("案例向量库复用已有索引（{} 条案例）", len(case_docs))
            else:
                self._store = Chroma.from_documents(
                    documents=case_docs,
                    embedding=embeddings,
                    collection_name=CASE_COLLECTION,
                    persist_directory=str(settings.vector_db_dir),
                )
                _save_fingerprint(current_hash, embedding_id)
                log.info("案例向量库重建完成（{} 条案例）", len(case_docs))
            self._ready = True
        except Exception as e:
            log.warning("案例向量库初始化失败: {}", e)
            self._ready = False

    def retrieve_similar(
        self,
        query: str,
        day_master: str = "",
        strength: str = "",
        domain: str = "",
        top_k: int = 3,
    ) -> list[dict]:
        """混合检索相似案例。

        策略：
        1. 语义检索召回 top_k * 3 个候选
        2. 关键词重叠重排，返回 top_k

        Args:
            query: 用户问题（语义检索）
            day_master: 日主（如"甲木"），用于关键词重排加权
            strength: 强弱（如"身旺"），用于关键词重排加权
            domain: 领域（如"love"），用于关键词重排加权
            top_k: 返回数量

        Returns:
            案例列表，每个案例包含 title, analysis, conclusion, features, rating 等字段
        """
        if not self._ready or not self._store:
            return []

        try:
            candidates = self._store.similarity_search(query, k=top_k * 3)
        except Exception as e:
            log.warning("案例检索失败: {}", e)
            return []

        if not candidates:
            return []

        scored = []
        for doc in candidates:
            meta = doc.metadata
            score = 0.0
            if day_master and day_master in meta.get("day_master", ""):
                score += 0.3
            if strength and strength in meta.get("strength", ""):
                score += 0.2
            if domain:
                domains = meta.get("domains", "[]")
                if domain in domains:
                    score += 0.2
            score += _keyword_overlap(query, doc.page_content) * 0.3
            scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[dict] = []
        seen_ids: set[str] = set()
        for score, doc in scored:
            case_id = doc.metadata.get("case_id", "")
            if case_id in seen_ids:
                continue
            seen_ids.add(case_id)
            results.append({
                "title": doc.metadata.get("title", ""),
                "source": doc.metadata.get("source", ""),
                "day_master": doc.metadata.get("day_master", ""),
                "strength": doc.metadata.get("strength", ""),
                "pattern": doc.metadata.get("pattern", ""),
                "key_traits": doc.metadata.get("key_traits", "[]"),
                "analysis": doc.page_content,
                "rating": doc.metadata.get("rating", 0),
                "score": round(score, 3),
            })
            if len(results) >= top_k:
                break

        log.info("案例检索: query='{}' → 召回 {} 条候选，重排后返回 {} 条",
                 query[:50], len(candidates), len(results))
        return results


case_store = CaseStore()