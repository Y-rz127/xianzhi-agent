"""数据访问异步门面（R1 数据访问异步化）。

背景：app/api 的 async handler 曾直接调用同步 psycopg 的 db/memory 函数，
每条 DB 请求都阻塞唯一事件循环，并发吞吐随 DB 延迟线性下降。

本模块将 users / user_records / chart_store / profiles / schema / postgres_memory 的
同步函数统一包装为 `await asyncio.to_thread(...)` 的异步版本，API 层一律经此门面调用；
SQL 与表结构保持不变，同步实现继续供线程内场景（agent 工具、后台任务）复用。

用法：
    from app.db import repository as repo
    user = await repo.get_by_token(token)
"""
from __future__ import annotations

import asyncio
from functools import wraps

from app.db import chart_store, profiles, schema, user_records
from app.db import users as user_store
from app.memory import postgres_memory


def _async(fn):
    """把同步 DB 函数包装为协程：在默认线程池中执行，不阻塞事件循环。"""

    @wraps(fn)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    return wrapper


# ===== 用户账号（app.db.users） =====
authenticate = _async(user_store.authenticate)
count_users = _async(user_store.count_users)
create_or_get_by_wxopenid = _async(user_store.create_or_get_by_wxopenid)
create_user = _async(user_store.create_user)
get_by_id = _async(user_store.get_by_id)
get_by_token = _async(user_store.get_by_token)
list_users = _async(user_store.list_users)
update_user = _async(user_store.update_user)

# ===== 用户私有数据（app.db.profiles） =====
create_profile = _async(profiles.create_profile)
delete_profile = _async(profiles.delete_profile)
get_profile = _async(profiles.get_profile)
list_profiles = _async(profiles.list_profiles)
update_profile = _async(profiles.update_profile)

# ===== 命盘画像 / 断事知识 / 命例（app.db.chart_store） =====
add_chart_case = _async(chart_store.add_chart_case)
add_chart_fact = _async(chart_store.add_chart_fact)
get_chart_facts = _async(chart_store.get_chart_facts)
get_chart_facts_for_llm = _async(chart_store.get_chart_facts_for_llm)
get_chart_profile = _async(chart_store.get_chart_profile)
list_chart_profiles_by_user = _async(chart_store.list_chart_profiles_by_user)
search_cases_for_rag = _async(chart_store.search_cases_for_rag)
search_chart_cases = _async(chart_store.search_chart_cases)
update_chart_profile_stats = _async(chart_store.update_chart_profile_stats)
upsert_chart_profile = _async(chart_store.upsert_chart_profile)

# ===== 收藏 / 塔罗 / 反馈 / 样本导出（app.db.user_records） =====
add_answer_feedback = _async(user_records.add_answer_feedback)
add_favorite = _async(user_records.add_favorite)
add_feedback = _async(user_records.add_feedback)
add_tarot_record = _async(user_records.add_tarot_record)
delete_feedback = _async(user_records.delete_feedback)
delete_tarot_record = _async(user_records.delete_tarot_record)
export_dpo_samples = _async(user_records.export_dpo_samples)
export_sft_samples = _async(user_records.export_sft_samples)
get_answer_feedback = _async(user_records.get_answer_feedback)
is_favorite = _async(user_records.is_favorite)
list_answer_feedback = _async(user_records.list_answer_feedback)
list_favorites = _async(user_records.list_favorites)
list_feedback = _async(user_records.list_feedback)
list_tarot_records = _async(user_records.list_tarot_records)
mark_answer_reviewed = _async(user_records.mark_answer_reviewed)
promote_to_case = _async(user_records.promote_to_case)
unpromote_answer_to_case = _async(user_records.unpromote_answer_to_case)
remove_favorite = _async(user_records.remove_favorite)

# ===== 建表（app.db.schema） =====
ensure_tables = _async(schema._ensure_tables)

# ===== 会话记忆（app.memory.postgres_memory 模块级函数） =====
get_session_info = _async(postgres_memory.get_session_info)
get_session_owner = _async(postgres_memory.get_session_owner)
get_messages = _async(postgres_memory.get_messages)
delete_session = _async(postgres_memory.delete_session)
get_birth_info_from_session = _async(postgres_memory.get_birth_info_from_session)