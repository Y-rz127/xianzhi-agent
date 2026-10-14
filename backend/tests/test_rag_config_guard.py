"""RAG 检索链路守卫：embedding 模型 / 阈值 / fetch_k 三者的配置与文档一致性。

背景（2026-10-14）：
- 实测把embedding 从 text-embedding-v2 换成 qwen3.7-text-embedding（recall@3 33/40→39/40，
  MRR 0.792→0.929），rerank 阈值经三轮定标：0.25 → 0.15 → 0.10（整轮口径实测表见上）。
- 阈值原先是 `_search_reranked` 里的局部硬编码 `_MIN_OVERLAP = 0.25`，改它必须改代码、
  很容易被无声改回去；本轮已提为 `settings.rag_min_overlap`。
这些断言守的是「别退回已实测更差的配置」，不是算法正确性。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import BACKEND_ROOT, settings

VECTOR_STORE_PY = Path(__file__).resolve().parents[1] / "app" / "rag" / "vector_store.py"
SETTINGS_PY = Path(__file__).resolve().parents[1] / "app" / "core" / "config" / "settings.py"
EMBEDDINGS_PY = Path(__file__).resolve().parents[1] / "app" / "rag" / "embeddings.py"

# 实测定标值（2026-10-14，整轮口径52 提问 × 3 query = 156 条 query）
#   0.05 → 45/0/12 ｜ 0.10 → 45/0/12 ｜ 0.15 → 41/6/7 ｜ 0.20 → 38/9/5 ｜ 0.25 → 33/15/4
# 取0.10：0.05 完全等效无额外收益；0.25（历史值）会砍掉 12 轮。
# 要改阈值必须先重跑 rerank_realistic.py 拿新表，再改这三个常量。
EXPECTED_MIN_OVERLAP = 0.10
# 明显更差的档位（踩过才知道的）：0.15 起整轮全空 ≥6，0.20 起 ≥8，0.25 起 ≥15
BAD_THRESHOLDS = (0.15, 0.20, 0.25, 0.3, 0.35)


def test_embedding_model_is_qwen37_not_legacy_v2():
    """默认 embedding 必须是 qwen3.7-text-embedding。

    v2 是2026-09-04 排查 flash 挂死时的临时退路，flash 挂死问题已由 BatchEmbeddings
    （batch_size + 总字符双上限）解决；v2 召回最差且单价最高（0.0007）。
    """
    assert settings.embedding_model == "qwen3.7-text-embedding"
    src = SETTINGS_PY.read_text(encoding="utf-8")
    assert 'default="qwen3.7-text-embedding"' in src, "settings 代码默认值须与 .env 一致"


def test_rag_min_overlap_is_configurable_not_hardcoded():
    """阈值必须是 settings 驱动的，不能是方法内局部硬编码。

    ⚠️ 这里必须**断言源码字面量**而非只断言 settings 值：`.env` 里有 RAG_MIN_OVERLAP，
    pydantic 读到的是 .env 的值——只改 settings.py 的 default 时 settings.rag_min_overlap
    仍是 .env 里的值，断言照样通过，守卫就成了假阳性（2026-10-14 变异验证实测漏放过）。
    所以下面两层都要查：settings 的 default 字面量、以及 vector_store 里不许有裸字面量。
    """
    # 第一层：settings.py 的代码默认值字面量本身必须是定标值
    ssrc = SETTINGS_PY.read_text(encoding="utf-8")
    m = re.search(
        r'rag_min_overlap:\s*float\s*=\s*Field\(\s*default=([0-9.]+)\s*,\s*alias="RAG_MIN_OVERLAP"',
        ssrc,
    )
    assert m is not None, "settings.py 里找不到 rag_min_overlap 的 Field 定义"
    actual = float(m.group(1))
    assert actual == EXPECTED_MIN_OVERLAP, (
        f"settings.py 里 rag_min_overlap 的代码默认值是 {actual}，应为 {EXPECTED_MIN_OVERLAP}"
        f"（2026-10-14 整轮口径实测定标）"
    )
    # 已实测更差的档位直接点名，避免下一个人凭感觉往上调
    for bad in BAD_THRESHOLDS:
        assert actual != bad, (
            f"rag_min_overlap={bad} 是实测更差的档位"
            f"（0.15 起整轮全空 ≥6，0.25 起 ≥15）。要改先重跑 rerank_realistic.py 拿新表。"
        )

    # 第二层：vector_store 的局部变量必须绑定 settings，且不得出现裸字面量阈值
    src = VECTOR_STORE_PY.read_text(encoding="utf-8")
    assert re.search(r"_MIN_OVERLAP\s*=\s*settings\.rag_min_overlap", src), (
        "vector_store._MIN_OVERLAP 必须绑定 settings.rag_min_overlap"
    )
    for literal in ("0.15", "0.2", "0.25", "0.3", "0.35"):
        bad = re.search(rf"_MIN_OVERLAP\s*=\s*{literal}\b", src)
        assert bad is None, f"发现硬编码阈值 _MIN_OVERLAP = {literal}，须走 settings"


def test_env_matches_source_defaults_for_rag_config():
    """.env 与 settings 代码默认值必须一致，否则有一侧在骗人。

    ⚠️ **不能只问运行时 settings**：它是模块级单例，首次 import 后 `.env` 再改也不会
    重读（2026-10-14 变异验证实测漏放：`.env` 里 RAG_MIN_OVERLAP 改成 0.25/0.35，守卫仍 passed）。
    所以这里直接解析 `.env` 文件字面量 + `settings.py` 的 default 字面量，
    两个纯文本来源互相比对，不依赖任何已缓存状态。
    """
    env_path = BACKEND_ROOT / ".env"
    if not env_path.exists():
        return  # 无 .env 的环境（CI）跳过：此处守的是部署一致性，不是算法
    env_text = env_path.read_text(encoding="utf-8")
    ssrc = SETTINGS_PY.read_text(encoding="utf-8")

    def env_val(key: str) -> str | None:
        m = re.search(rf"^{key}\s*=\s*(\S+)\s*$", env_text, re.MULTILINE)
        return m.group(1) if m else None

    def src_default(field: str, alias: str):
        m = re.search(rf'{field}:\s*\w+\s*=\s*Field\(\s*default="?([\w.\-]+)"?\s*,\s*alias="{alias}"', ssrc)
        return m.group(1) if m else None

    # EMBEDDING_MODEL：三方一致（.env 字面量 / 源码 default / 运行时）
    ev = env_val("EMBEDDING_MODEL")
    sv = src_default("embedding_model", "EMBEDDING_MODEL")
    if ev:
        assert ev == "qwen3.7-text-embedding", f".env 的 EMBEDDING_MODEL={ev}，应为 qwen3.7-text-embedding"
        assert ev == sv, f".env({ev}) 与 settings.py 默认值({sv}) 漂移了"
        assert ev == settings.embedding_model, f"运行时读到 {settings.embedding_model}，与 .env 不符"

    # RAG_MIN_OVERLAP：同样三方一致，且都必须是定标值
    ev = env_val("RAG_MIN_OVERLAP")
    m = re.search(
        r'rag_min_overlap:\s*float\s*=\s*Field\(\s*default=([0-9.]+)\s*,\s*alias="RAG_MIN_OVERLAP"',
        ssrc,
    )
    sv = m.group(1) if m else None
    if ev:
        assert float(ev) == EXPECTED_MIN_OVERLAP, (
            f".env 的 RAG_MIN_OVERLAP={ev}，应为 {EXPECTED_MIN_OVERLAP}"
        )
        assert sv is not None and abs(float(sv) - EXPECTED_MIN_OVERLAP) < 1e-9, (
            f"settings.py 默认值({sv}) 与 .env({ev}) 漂移了"
        )
        assert abs(float(ev) - settings.rag_min_overlap) < 1e-9, (
            f"运行时读到 {settings.rag_min_overlap}，与 .env({ev}) 不符"
        )


def test_threshold_floor_documented_with_measured_evidence():
    """阈值要写清实测依据，避免下一个人凭感觉再调。

    2026-10-14 整轮口径实测（797 chunk / 52 提问 × 3 query，每格 = 整轮OK/全空/错文档）：
      0.05 → 45/0/12 ｜ 0.10 → 45/0/12 ｜ 0.15 → 41/6/7 ｜ 0.20 → 38/9/5 ｜ 0.25 → 33/15/4
    评估口径必须用整轮（走 retrieve_for_context 多 query），单query top-1 口径会得出相反结论。
    """
    src = SETTINGS_PY.read_text(encoding="utf-8")
    assert "rag_min_overlap" in src, "settings 里应有 rag_min_overlap 定义"
    # 依据表至少要有两档实测数字，避免只剩结论没了依据
    hits = re.findall(r"0\.\d+\s*→\s*\d+/\d+/\d+", src)
    assert len(hits) >= 2, f"settings 注释里应保留实测对照表（读到 {len(hits)} 档）"


def test_embeddings_docstring_no_longer_recommends_legacy_v2():
    """embeddings.py 的 docstring 不能再建议「默认用 text-embedding-v2」。

    这句是 2026-09-04 flash 挂死排查期间的临时结论，模型换成 qwen3.7 后已作废；
    留着会误导下一个人把配置改回去。
    """
    doc = EMBEDDINGS_PY.read_text(encoding="utf-8")
    assert "因此默认 embedding 模型请用 text-embedding-v2" not in doc
    # 重建失败提示也不该再引导换回 v2
    vsrc = VECTOR_STORE_PY.read_text(encoding="utf-8")
    assert "建议改用 text-embedding-v2" not in vsrc


def test_embedding_batch_size_within_hard_api_limit():
    """批次条数不得超过 DashScope 硬上限。

    实测上限按模型不同（v2=25 / v4=10 / qwen3.7=20），默认 10 对三者均安全；
    若将来放宽配置，这个守卫会先于线上 400 报错。
    """
    limits = {"text-embedding-v2": 25, "text-embedding-v4": 10, "qwen3.7-text-embedding": 20}
    limit = limits.get(settings.embedding_model)
    assert limit is not None, f"未登记的 embedding 模型 {settings.embedding_model}，请补硬上限"
    assert 1 <= settings.embedding_batch_size <= limit, (
        f"EMBEDDING_BATCH_SIZE={settings.embedding_batch_size} 超出 "
        f"{settings.embedding_model} 硬上限 {limit}"
    )
