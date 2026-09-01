"""检索相关性打分工具：供向量库 rerank 与命例库检索共同使用。"""

from __future__ import annotations

import re


def _bigrams(s: str) -> set[str]:
    """提取字符级 2-gram（去空白），用于轻量相关性打分。"""
    s = re.sub(r"\s+", "", s or "")
    return {s[i : i + 2] for i in range(len(s) - 1)}


def keyword_overlap(query: str, text: str) -> float:
    """query 对 text 的 2-gram 覆盖率：query 中有多少比例的 2-gram 出现在 text 中。

    相比 Jaccard（len(bq & bt) / len(bq | bt)），覆盖率不受 text 长度惩罚：
    350 字 chunk 有 ~349 个 2-gram，query 只有 4 个，Jaccard 全命中也仅 0.01；
    覆盖率全命中则为 1.0，能真实反映 query 与 chunk 的相关性。
    """
    bq, bt = _bigrams(query), _bigrams(text)
    if not bq or not bt:
        return 0.0
    return len(bq & bt) / len(bq)