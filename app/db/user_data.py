"""用户私有数据（兼容门面）。

R9 拆分：按资源拆为
- schema        惰性建表与共享工具（_ensure_tables / _safe_json 等）
- profiles      八字档案 CRUD
- user_records  收藏/塔罗/反馈/答案反馈与训练样本导出
- chart_store   命盘画像/断事知识/结构化命例

本模块重导出全部原公共符号，既有 `from app.db import user_data` 用法无需改动。
"""
from __future__ import annotations

from app.db.chart_store import (  # noqa: F401
    _GAN_WUXING,
    _chart_hash,
    _extract_bazi_features,
    add_chart_case,
    add_chart_fact,
    get_chart_facts,
    get_chart_facts_for_llm,
    get_chart_profile,
    list_chart_profiles_by_user,
    search_cases_for_rag,
    search_chart_cases,
    update_chart_profile_stats,
    upsert_chart_profile,
)
from app.db.profiles import (  # noqa: F401
    _row_to_profile,
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    update_profile,
)
from app.db.schema import (  # noqa: F401
    _READY,
    _do_ensure_tables,
    _ensure_tables,
    _record_error,
    _safe_json,
)
from app.domain.chart_format import extract_bazi_brief  # noqa: F401  (命盘摘要提取，重复定义已收敛至 domain 层)
from app.db.user_records import (  # noqa: F401
    add_answer_feedback,
    add_favorite,
    add_feedback,
    add_tarot_record,
    delete_feedback,
    delete_tarot_record,
    export_dpo_samples,
    export_sft_samples,
    get_answer_feedback,
    is_favorite,
    list_answer_feedback,
    list_favorites,
    list_feedback,
    list_tarot_records,
    mark_answer_reviewed,
    promote_to_case,
    remove_favorite,
)
