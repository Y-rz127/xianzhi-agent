"""基于 PostgreSQL 的对话记忆（与 FileBasedChatMemory 同接口）。

利用 langchain_postgres.PostgresChatMessageHistory 持久化对话，
表名默认 message_store，session_id 作为会话隔离键。

连接管理：模块级 psycopg_pool 连接池（线程安全）。
psycopg.Connection 本身非线程安全，全局单连接在并发请求下会互相干扰；
连接池按需检出/归还，配合会话 Agent 池支持多会话并行。

注意：PostgresChatMessageHistory 的签名是
  __init__(table_name, session_id, /, *, sync_connection=, async_connection=)
即 table_name/session_id 是位置参数，连接必须传 psycopg.Connection 对象。
"""
from __future__ import annotations

import threading
import uuid as uuid_module
from typing import List

from langchain_core.messages import BaseMessage

from app.config import settings
from app.logger import log


# ---------------------------------------------------------------
# 模块级连接池（懒创建，线程安全）
# ---------------------------------------------------------------

_pg_pool = None
_pool_lock = threading.Lock()
_schema_ready = False


def _get_pool():
    """获取模块级 psycopg 连接池（懒创建）。ConnectionPool 本身线程安全。"""
    global _pg_pool
    with _pool_lock:
        if _pg_pool is None:
            from psycopg_pool import ConnectionPool
            _pg_pool = ConnectionPool(
                settings.postgres_connection_string,
                min_size=1,
                max_size=5,
                kwargs={"autocommit": True},
                open=True,
            )
            log.info("PG 连接池已创建 (min=1, max=5)")
        return _pg_pool


def _ensure_schema():
    """建表与索引（进程内只执行一次）。"""
    global _schema_ready
    if _schema_ready:
        return
    pool = _get_pool()  # 先取池（内部自锁），避免嵌套持锁
    with _pool_lock:
        if _schema_ready:
            return
        with pool.connection() as conn:
            try:
                from langchain_postgres import PostgresChatMessageHistory
                PostgresChatMessageHistory.create_tables(conn, settings.memory_table_name)
                # 会话元数据表：持久化 UUID -> conversation_id 的映射
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS session_metadata (
                        session_id UUID PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        module TEXT,
                        user_id TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # 兼容旧部署：补充 user_id 列
                conn.execute("ALTER TABLE session_metadata ADD COLUMN IF NOT EXISTS user_id TEXT")
                # 会话列表/消息查询的高频过滤列，避免每次全表扫描
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_message_store_session_created
                    ON {} (session_id, created_at DESC)
                """.format(settings.memory_table_name))
                log.info("PG 记忆表已就绪: {}", settings.memory_table_name)
            except Exception as e:
                log.warning("PG 记忆表创建失败（可能已存在）: {}", e)
        _schema_ready = True


def close_global_conn():
    """关闭模块级连接池（应用退出时调用）。"""
    global _pg_pool, _schema_ready
    with _pool_lock:
        if _pg_pool is not None:
            try:
                _pg_pool.close()
            except Exception:
                pass
            finally:
                _pg_pool = None
                _schema_ready = False


class PostgresChatMemory:
    """PostgreSQL 版对话记忆，与 FileBasedChatMemory 接口一致。

    连接从模块级连接池按需检出，实例本身不持有连接，
    因此同一实例可被多线程（多会话 Agent）安全共享。
    """

    # 固定命名空间，确保同一 conversation_id 始终映射到同一 UUID
    _NAMESPACE = uuid_module.UUID("00000000-0000-0000-0000-000000000001")

    def __init__(self, connection_string: str = None, table_name: str = "message_store"):
        # connection_string 保留用于接口兼容；实际连接统一走模块级连接池
        self.connection_string = connection_string or settings.postgres_connection_string
        self.table_name = table_name
        _ensure_schema()

    @staticmethod
    def _to_uuid(conversation_id: str) -> str:
        """将任意 conversation_id 转为确定性 UUID（PostgresChatMessageHistory 要求）"""
        return str(uuid_module.uuid5(PostgresChatMemory._NAMESPACE, conversation_id))

    @staticmethod
    def _to_session_id(prefix: str, conversation_id: str) -> str:
        return f"{prefix}-{conversation_id}"

    def _history(self, conversation_id: str, conn):
        from langchain_postgres import PostgresChatMessageHistory
        session_uuid = self._to_uuid(conversation_id)
        return PostgresChatMessageHistory(
            self.table_name,
            session_uuid,
            sync_connection=conn,
        )

    def get(self, conversation_id: str) -> List[BaseMessage]:
        try:
            with _get_pool().connection() as conn:
                return self._history(conversation_id, conn).messages
        except Exception as e:
            log.warning("读取PG记忆失败 {} : {}", conversation_id, e)
            return []

    def add(self, conversation_id: str, messages: List[BaseMessage]):
        try:
            session_uuid = self._to_uuid(conversation_id)
            global _session_uuid_map
            _session_uuid_map[session_uuid] = conversation_id
            # 持久化 UUID -> conversation_id 映射
            module = _extract_module(conversation_id)
            with _get_pool().connection() as conn:
                user_id = _extract_user_id(conversation_id)
                conn.execute("""
                    INSERT INTO session_metadata (session_id, conversation_id, module, user_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE
                    SET conversation_id = EXCLUDED.conversation_id,
                        module = EXCLUDED.module,
                        user_id = EXCLUDED.user_id,
                        updated_at = CURRENT_TIMESTAMP
                """, (session_uuid, conversation_id, module, user_id))
                history = self._history(conversation_id, conn)
                for m in messages:
                    history.add_message(m)
        except Exception as e:
            log.warning("写入PG记忆失败 {} : {}", conversation_id, e)

    def clear(self, conversation_id: str):
        try:
            with _get_pool().connection() as conn:
                self._history(conversation_id, conn).clear()
        except Exception as e:
            log.warning("清空PG记忆失败 {} : {}", conversation_id, e)

    def close(self):
        """连接由模块级连接池统一管理，实例无需单独关闭（保留接口兼容）。"""


# 反向查找表：UUID -> 原始 conversation_id（由 PostgresChatMemory 实例维护）
_session_uuid_map: dict[str, str] = {}


def _extract_module(conversation_id: str) -> str:
    """从 conversation_id 提取模块前缀。

    格式约定：
      - "web-xianzhi-1783429404556"       → "web-xianzhi"（旧格式）
      - "mp-xianzhi__<userId>__<rand>"    → "mp-xianzhi"（用户态，双下划线分隔）
      - "default" / 无连字符               → ""

    双下划线 `__` 用于分隔 user_id，避免与模块名里的连字符冲突，
    这样 PC web、小程序、先知、用户态会话互不干扰。
    """
    if not conversation_id:
        return ""
    base = conversation_id.split("__")[0]
    if "-" not in base:
        return base
    parts = base.split("-")
    first = parts[0]
    if len(parts) >= 2 and not parts[1].isdigit():
        return f"{first}-{parts[1]}"
    return first


def _extract_user_id(conversation_id: str) -> str:
    """从 conversation_id 提取 user_id（格式 `module__<userId>__<rand>`）。

    旧格式或游客会话返回空串。
    """
    parts = conversation_id.split("__")
    if len(parts) >= 2 and parts[1]:
        return parts[1]
    return ""


def get_session_info(prefix: str = "", user_id: str = None) -> list:
    """获取所有会话信息（用于前端会话列表），按 prefix 过滤。

    单条 SQL 完成聚合 + 最后一条消息提取：
    - 聚合子查询算首末时间与消息数；
    - DISTINCT ON 子查询取每个会话最新一条消息（配合 session_id+created_at 索引），
      替代原来的逐组相关子查询，消除 N+1 放大。
    """
    try:
        _ensure_schema()
        with _get_pool().connection() as conn:
            sql = """
                SELECT agg.session_id,
                       sm.conversation_id,
                       sm.module,
                       sm.user_id,
                       last.message AS last_msg,
                       agg.first_time,
                       agg.last_time,
                       agg.msg_count
                FROM (
                    SELECT session_id,
                           MIN(created_at) AS first_time,
                           MAX(created_at) AS last_time,
                           COUNT(*) AS msg_count
                    FROM message_store
                    GROUP BY session_id
                ) agg
                JOIN (
                    SELECT DISTINCT ON (session_id) session_id, message
                    FROM message_store
                    ORDER BY session_id, created_at DESC
                ) last ON last.session_id = agg.session_id
                LEFT JOIN session_metadata sm ON sm.session_id = agg.session_id
            """
            params = []
            if user_id:
                sql += " WHERE sm.user_id = %s"
                params.append(user_id)
            sql += " ORDER BY agg.last_time DESC"
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
        sessions = []
        for row in rows:
            session_uuid = str(row[0])
            conversation_id = row[1]
            module = row[2]
            # 如果 session_metadata 中没有记录（旧数据或尚未同步），使用内存映射
            if not conversation_id:
                conversation_id = _session_uuid_map.get(session_uuid, session_uuid)
                module = _extract_module(str(conversation_id))
            # 按 prefix 过滤
            if prefix and str(module) != prefix:
                continue
            last_msg_raw = row[4]
            last_msg_text = ""
            if last_msg_raw:
                try:
                    import json
                    if isinstance(last_msg_raw, str):
                        msg_obj = json.loads(last_msg_raw)
                    else:
                        msg_obj = last_msg_raw
                    if isinstance(msg_obj, dict):
                        last_msg_text = (
                            msg_obj.get("content")
                            or msg_obj.get("data", {}).get("content")
                            or ""
                        )
                except Exception:
                    last_msg_text = str(last_msg_raw)[:50]
            sessions.append({
                "id": conversation_id,
                "title": last_msg_text[:30] if last_msg_text else "新会话",
                "lastMessage": last_msg_text[:50] if last_msg_text else "",
                "firstTime": str(row[5]) if row[5] else "",
                "lastTime": str(row[6]) if row[6] else "",
                "messageCount": row[7],
            })
        return sessions
    except Exception as e:
        log.exception("获取会话列表失败")
        return []

def _resolve_session_uuid(session_id: str) -> str:
    """解析 conversation_id 为真实的 session_uuid。
    优先查询 session_metadata，找不到再用 _to_uuid 计算。"""
    try:
        with _get_pool().connection() as conn:
            row = conn.execute(
                "SELECT session_id FROM session_metadata WHERE conversation_id = %s",
                (session_id,)
            ).fetchone()
        if row:
            return str(row[0])
    except Exception:
        pass
    return PostgresChatMemory._to_uuid(session_id)


def delete_session(session_id: str):
    """删除指定会话的所有消息。"""
    try:
        session_uuid = _resolve_session_uuid(session_id)
        with _get_pool().connection() as conn:
            conn.execute("DELETE FROM message_store WHERE session_id = %s", (session_uuid,))
            conn.execute("DELETE FROM session_metadata WHERE session_id = %s", (session_uuid,))
    except Exception as e:
        log.exception("删除会话失败: {}", session_id)


def clear_session(session_id: str):
    """清空指定会话的消息记录，但保留会话本身（session_metadata 保留）。

    用于“清空当前会话”操作：会话仍出现在历史列表中，但消息数为 0。
    """
    try:
        session_uuid = _resolve_session_uuid(session_id)
        with _get_pool().connection() as conn:
            conn.execute("DELETE FROM message_store WHERE session_id = %s", (session_uuid,))
            # 更新 updated_at，让该会话在列表中保持位置但消息数归零
            conn.execute(
                "UPDATE session_metadata SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s",
                (session_uuid,),
            )
    except Exception as e:
        log.exception("清空会话消息失败: {}", session_id)


def get_messages(session_id: str) -> list:
    """获取指定会话的所有消息。

    返回前端期望的 role 格式：user / assistant。
    过滤掉 tool/system 类型消息（工具调用结果、推理片段）以及
    tool_call_agent.think 注入的 next_step_prompt 占位 HumanMessage，
    防止历史会话恢复时显示无效内容。
    """
    try:
        session_uuid = _resolve_session_uuid(session_id)
        with _get_pool().connection() as conn:
            cur = conn.execute("""
                SELECT message, created_at FROM message_store
                WHERE session_id = %s ORDER BY created_at
            """, (session_uuid,))
            rows = cur.fetchall()
        messages = []
        for row in rows:
            msg = row[0]
            content = msg.get("data", {}).get("content", "") or ""
            raw_role = msg.get("type", "").replace("_message", "")
            # 过滤：工具调用结果、推理片段、系统消息
            if raw_role in ("tool", "system"):
                continue
            # 过滤 next_step_prompt 占位消息（tool_call_agent 注入的 HumanMessage）
            if raw_role == "human" and "根据用户需求选择最合适的工具" in content:
                continue
            # 过滤无内容的空消息
            if not content.strip():
                continue
            # 映射 role 为前端期望的格式
            role = "user" if raw_role == "human" else "assistant"
            messages.append({
                "role": role,
                "content": content,
                "time": str(row[1]) if row[1] else "",
            })
        return messages
    except Exception as e:
        log.exception("获取会话消息失败: {}", session_id)
        return []


# 排盘工具名集合（与 app.agent.xianzhi._BAZI_TOOLS 保持一致）
_BAZI_TOOL_NAMES = {
    "bazi_chart", "bazi_analysis", "bazi_dayun", "bazi_liunian",
    "bazi_liuyue", "bazi_liuri", "bazi_hehun", "bazi_full",
}


def get_birth_info_from_session(session_id: str) -> dict | None:
    """从会话消息历史中的排盘工具调用参数提取出生信息。

    用户可能用农历/节日/时辰等自然语言输入（如"2004年端午节 辰时 男"），
    前端正则无法提取。此函数从 AIMessage 的 tool_calls 中提取 LLM 已解析的
    标准 birth_time/gender，供前端从历史会话恢复时使用。
    """
    try:
        session_uuid = _resolve_session_uuid(session_id)
        with _get_pool().connection() as conn:
            cur = conn.execute("""
                SELECT message FROM message_store
                WHERE session_id = %s ORDER BY created_at
            """, (session_uuid,))
            rows = cur.fetchall()
        for row in reversed(rows):  # 逆序：取最近一次排盘
            msg = row[0]
            if msg.get("type") != "ai":
                continue
            tool_calls = msg.get("data", {}).get("tool_calls", []) or []
            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("args", {}) or {}
                if name in _BAZI_TOOL_NAMES:
                    bt = args.get("birth_time")
                    gd = args.get("gender")
                    if bt and gd:
                        return {"time": bt, "gender": gd}
        return None
    except Exception as e:
        log.warning("提取会话出生信息失败 {} : {}", session_id, e)
        return None
