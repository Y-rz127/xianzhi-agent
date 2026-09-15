"""命例收藏 / 通用 AI 解读记录 / 问题反馈 / 答案反馈与训练样本导出，按 user_id 隔离。

2026-09-15 由单文件（~600 行）拆为子模块，本 __init__ 仅做显式 re-export，
保证 ``from app.db.user_records import <func>`` 与 ``app.db.user_records.<func>``
两条既有导入路径继续可用（调用方零改动）。
"""

# 包级转发：_ensure_tables / get_pool / _safe_json 的统一出口。
# 子模块经「app.db.user_records.X」在调用时取用，便于测试对包级符号打桩
# （test_exception_tightening 直接 monkeypatch user_records._ensure_tables / get_pool）。
from app.db.pool import get_pool
from app.db.schema import _ensure_tables, _safe_json
from app.db.user_records.ai_interpretation import (
    add_ai_interpretation_record,
    delete_ai_interpretation_record,
    list_ai_interpretation_records,
)
from app.db.user_records.answer_feedback import (
    _answer_feedback_from_row,
    _extract_case_features,
    _first,
    _refill_features_by_rechart,
    add_answer_feedback,
    delete_answer_feedback,
    export_dpo_samples,
    export_sft_samples,
    get_answer_feedback,
    list_answer_feedback,
    mark_answer_reviewed,
    promote_to_case,
    unpromote_answer_to_case,
)
from app.db.user_records.favorites import (
    add_favorite,
    is_favorite,
    list_favorites,
    remove_favorite,
)
from app.db.user_records.feedback import (
    add_feedback,
    delete_feedback,
    list_feedback,
)

__all__ = [
    "_ensure_tables",
    "_safe_json",
    "get_pool",
    "add_favorite",
    "list_favorites",
    "remove_favorite",
    "is_favorite",
    "add_ai_interpretation_record",
    "list_ai_interpretation_records",
    "delete_ai_interpretation_record",
    "add_feedback",
    "list_feedback",
    "delete_feedback",
    "add_answer_feedback",
    "list_answer_feedback",
    "delete_answer_feedback",
    "export_sft_samples",
    "mark_answer_reviewed",
    "get_answer_feedback",
    "_answer_feedback_from_row",
    "_first",
    "_extract_case_features",
    "_refill_features_by_rechart",
    "promote_to_case",
    "unpromote_answer_to_case",
    "export_dpo_samples",
]
