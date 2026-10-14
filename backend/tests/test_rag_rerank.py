"""RAG 重排单测：前导区元信息 chunk 降权。

背景（2026-10-14 检索质量修订）：文档 H1 与首个 ## 之间的「约束/别名/导语」会被切成
无「二级标题」元数据的独立 chunk，其文本含大量领域词，会在 rerank 中抢走真知识 chunk
的 top1 位（52 条探针实测命中 47/52 → 降权后 52/52）。
"""

import pytest
from langchain_core.documents import Document

from app.rag.knowledge import DOC_TYPE_WEIGHT
from app.rag.relevance import keyword_overlap
from app.rag.vector_store import _PREAMBLE_PENALTY, _rerank_weight


def test_preamble_chunk_is_demoted():
    """无「二级标题」的前导区 chunk：权重 = 同文本正文权重 × 系数。"""
    q = "婚姻宫看月支还是日支"
    body = "配偶宫以日支为主，兼看月支与配偶星组合。"
    normal = Document(
        page_content=body,
        metadata={"doc_type": "rule", "一级标题": "婚恋关系规则卡", "二级标题": "一、感情判断核心"},
    )
    preamble = Document(
        page_content=body,
        metadata={"doc_type": "rule", "一级标题": "婚恋关系规则卡"},
    )
    assert _rerank_weight(q, preamble) == pytest.approx(
        _rerank_weight(q, normal) * _PREAMBLE_PENALTY
    )


def test_sectioned_chunk_keeps_original_formula():
    """有二级标题的正文 chunk：权重仍为 keyword_overlap × doc_type 权重（未被降权）。"""
    q = "冲配偶宫会怎样"
    d = Document(
        page_content="日支逢冲，配偶宫动，主婚姻变化。",
        metadata={"doc_type": "rule", "二级标题": "二、六冲"},
    )
    expected = keyword_overlap(q, d.page_content) * DOC_TYPE_WEIGHT.get("rule", 1.0)
    assert _rerank_weight(q, d) == pytest.approx(expected)


def test_penalty_value_frozen():
    """系数冻结：调整须以 52 条探针口径重跑实测（见 memory 检索质量修订记录）。"""
    assert _PREAMBLE_PENALTY == 0.4
