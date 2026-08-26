"""数据访问异步门面（R1 数据访问异步化）。

背景：app/api 的 async handler 曾直接调用同步 psycopg 的 db/memory 函数，
每条 DB 请求都阻塞唯一事件循环，并发吞吐随 DB 延迟线性下降。

本模块将 users / user_data / postgres_memory 的同步函数统一包装为
`await asyncio.to_thread(...)` 的异步版本，API 层一律经此门面调用；
SQL 与表结构保持不变，同步实现继续供线程内场景（agent 工具、后台任务）复用。

用法：
    from app.db import repository as repo
    user = await repo.get_by_token(token)
"""
from __future__ import annotations

import asyncio
from functools import wraps

from app.db import user_data
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

# ===== 用户私有数据（app.db.user_data） =====
add_answer_feedback = _async(user_data.add_answer_feedback)
add_chart_case = _async(user_data.add_chart_case)
add_chart_fact = _async(user_data.add_chart_fact)
add_favorite = _async(user_data.add_favorite)
add_feedback = _async(user_data.add_feedback)
add_tarot_record = _async(user_data.add_tarot_record)
create_profile = _async(user_data.create_profile)
delete_feedback = _async(user_data.delete_feedback)
delete_profile = _async(user_data.delete_profile)
delete_tarot_record = _async(user_data.delete_tarot_record)
ensure_tables = _async(user_data._ensure_tables)
export_dpo_samples = _async(user_data.export_dpo_samples)
export_sft_samples = _async(user_data.export_sft_samples)
get_answer_feedback = _async(user_data.get_answer_feedback)
get_chart_facts = _async(user_data.get_chart_facts)
get_chart_facts_for_llm = _async(user_data.get_chart_facts_for_llm)
get_chart_profile = _async(user_data.get_chart_profile)
get_profile = _async(user_data.get_profile)
is_favorite = _async(user_data.is_favorite)
list_answer_feedback = _async(user_data.list_answer_feedback)
list_chart_profiles_by_user = _async(user_data.list_chart_profiles_by_user)
list_favorites = _async(user_data.list_favorites)
list_feedback = _async(user_data.list_feedback)
list_profiles = _async(user_data.list_profiles)
list_tarot_records = _async(user_data.list_tarot_records)
mark_answer_reviewed = _async(user_data.mark_answer_reviewed)
promote_to_case = _async(user_data.promote_to_case)
unpromote_answer_to_case = _async(user_data.unpromote_answer_to_case)
remove_favorite = _async(user_data.remove_favorite)
search_cases_for_rag = _async(user_data.search_cases_for_rag)
search_chart_cases = _async(user_data.search_chart_cases)
update_chart_profile_stats = _async(user_data.update_chart_profile_stats)
update_profile = _async(user_data.update_profile)
upsert_chart_profile = _async(user_data.upsert_chart_profile)

# ===== 会话记忆（app.memory.postgres_memory 模块级函数） =====
get_session_info = _async(postgres_memory.get_session_info)
get_session_owner = _async(postgres_memory.get_session_owner)
get_messages = _async(postgres_memory.get_messages)
delete_session = _async(postgres_memory.delete_session)
get_birth_info_from_session = _async(postgres_memory.get_birth_info_from_session)
