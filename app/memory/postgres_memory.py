"""基于 PostgreSQL 的对话记忆（与 FileBasedChatMemory 同接口）。

利用 langchain_postgres.PostgresChatMessageHistory 持久化对话（表名默认 message_store），
session_id 作为会话隔离键。连接统一走模块级 psycopg_pool 连接池（线程安全）：
psycopg.Connection 非线程安全，全局单连接在并发下会互相干扰，连接池按需检出/归还。
注意 PostgresChatMessageHistory 的 table_name/session_id 是位置参数，
连接需传 psycopg.Connection 对象（sync_connection）。
"""
from __future__ import annotations

import json
import threading
import uuid as uuid_module
from typing import List

from langchain_core.messages import BaseMessage, messages_from_dict

from app.core.config import settings
from app.core.logger import log
from app.core.observability import record_error as _record_error
from app.db.pool import close_pool as _close_pg_pool, get_pool as _get_pool

# 会话 schema 初始化状态（仅 memory 层会话表；业务表统一由 app.db.schema 负责）
_schema_lock = threading.Lock()
_schema_ready = False


def _ensure_schema():
    """建表与索引（进程内只执行一次；数据库不可达时降级，不阻断启动）。"""
    global _schema_ready
    if _schema_ready:
        return
    pool = _get_pool()  # 先取池（内部自锁），避免嵌套持锁
    with _schema_lock:
        if _schema_ready:
            return
        try:
            with pool.connection() as conn:
                from langchain_postgres import PostgresChatMessageHistory
                PostgresChatMessageHistory.create_tables(conn, settings.memory_table_name)
                # 会话元数据表：持久化 UUID -> conversation_id 映射
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
                # 兼容旧部署：补充 user_id / 会话摘要列
                conn.execute("ALTER TABLE session_metadata ADD COLUMN IF NOT EXISTS user_id TEXT")
                conn.execute("ALTER TABLE session_metadata ADD COLUMN IF NOT EXISTS summary TEXT DEFAULT ''")
                conn.execute("ALTER TABLE session_metadata ADD COLUMN IF NOT EXISTS last_summary_msg_count INT DEFAULT 0")
                # 会话列表/消息查询的高频过滤列，避免每次全表扫描
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_message_store_session_created
                    ON {} (session_id, created_at DESC)
                """.format(settings.memory_table_name))
                log.info("PG 记忆表已就绪: {}", settings.memory_table_name)
            _schema_ready = True
        except Exception as e:
            # 数据库暂不可达：仅告警，保持 _schema_ready=False，下次调用/重启时重试
            log.warning("PG 记忆表初始化失败（数据库暂不可达，将在重启/首次使用时重试）: {}", e)


def close_global_conn():
    """关闭模块级连接池（应用退出时调用）。"""
    global _schema_ready
    _close_pg_pool()
    _schema_ready = False


class PostgresChatMemory:
    """PostgreSQL 版对话记忆，与 FileBasedChatMemory 接口一致。

    连接从模块级连接池按需检出，实例本身不持有连接，可被多线程安全共享。
    """

    # 固定命名空间，确保同一 conversation_id 始终映射到同一 UUID
    _NAMESPACE = uuid_module.UUID("00000000-0000-0000-0000-000000000001")

    def __init__(self, connection_string: str = None, table_name: str = "message_store"):
        # connection_string 仅保留用于接口兼容，实际连接统一走模块级连接池
        self.connection_string = connection_string or settings.postgres_connection_string
        self.table_name = table_name
        _ensure_schema()

    @staticmethod
    def _to_uuid(conversation_id: str) -> str:
        """将任意 conversation_id 转为确定性 UUID（PostgresChatMessageHistory 要求）。"""
        return str(uuid_module.uuid5(PostgresChatMemory._NAMESPACE, conversation_id))

    @staticmethod
    def _to_session_id(prefix: str, conversation_id: str) -> str:
        return f"{prefix}-{conversation_id}"

    def _history(self, conversation_id: str, conn):
        """基于给定连接构造 PostgresChatMessageHistory 实例（session_uuid 隔离）。"""
        from langchain_postgres import PostgresChatMessageHistory
        session_uuid = self._to_uuid(conversation_id)
        return PostgresChatMessageHistory(
            self.table_name,
            session_uuid,
            sync_connection=conn,
        )

    # 只拉最近 N 条历史，避免长会话每轮全量重传造成 IO 放大（载入后另有 2000 token 截断）
    _GET_HISTORY_LIMIT = 60

    def get(self, conversation_id: str) -> List[BaseMessage]:
        """读取会话最近历史（失败返回空列表）。

        只取最近 _GET_HISTORY_LIMIT 条（DESC 取再反转为时间正序），
        单条消息反序列化失败跳过，防个别脏数据丢整段历史。
        """
        try:
            session_uuid = self._to_uuid(conversation_id)
            with _get_pool().connection() as conn:
                cur = conn.execute(
                    f"SELECT message FROM {self.table_name} WHERE session_id = %s "
                    f"ORDER BY created_at DESC LIMIT {self._GET_HISTORY_LIMIT}",
                    (session_uuid,),
                )
                rows = cur.fetchall()
        except Exception as e:
            log.error("读取PG记忆失败 {} : {}", conversation_id, e)
            _record_error("memory.get")
            return []

        msgs = []
        for row in rows:
            try:
                raw = row[0]
                if isinstance(raw, str):
                    raw = json.loads(raw)
                msgs.extend(messages_from_dict([raw]))
            except Exception:
                continue  # 单条脏消息跳过，不影响其余历史
        return list(reversed(msgs))

    def add(self, conversation_id: str, messages: List[BaseMessage]):
        """写入消息并持久化会话元数据（UUID 映射、模块、user_id）。"""
        try:
            session_uuid = self._to_uuid(conversation_id)
            _session_uuid_map[session_uuid] = conversation_id
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
            # 写入失败 = 丢对话轮次，不静默吞掉：记错误 + 埋点后重抛，由调用方决定降级策略
            log.error("写入PG记忆失败 {} : {}", conversation_id, e)
            _record_error("memory.add")
            raise

    def clear(self, conversation_id: str):
        """清空该会话在 PG 中的全部消息。"""
        try:
            with _get_pool().connection() as conn:
                self._history(conversation_id, conn).clear()
        except Exception as e:
            # 删除是用户显式操作，失败必须可见，不假装成功
            log.error("清空PG记忆失败 {} : {}", conversation_id, e)
            _record_error("memory.clear")
            raise

    def close(self):
        """连接由模块级连接池统一管理，实例无需单独关闭（保留接口兼容）。"""

    def get_summary(self, conversation_id: str) -> str:
        """获取会话摘要。"""
        try:
            session_uuid = self._to_uuid(conversation_id)
            with _get_pool().connection() as conn:
                row = conn.execute(
                    "SELECT summary FROM session_metadata WHERE session_id = %s",
                    (session_uuid,),
                ).fetchone()
                return (row[0] or "").strip() if row else ""
        except Exception as e:
            log.error("获取会话摘要失败 {} : {}", conversation_id, e)
            _record_error("memory.get_summary")
            return ""

    def save_summary(self, conversation_id: str, summary: str, msg_count: int):
        """保存会话摘要及当前消息计数。"""
        try:
            session_uuid = self._to_uuid(conversation_id)
            with _get_pool().connection() as conn:
                conn.execute(
                    """UPDATE session_metadata
                       SET summary = %s, last_summary_msg_count = %s, updated_at = CURRENT_TIMESTAMP
                       WHERE session_id = %s""",
                    (summary, msg_count, session_uuid),
                )
        except Exception as e:
            # 摘要丢失会导致后续上下文窗口失真，重抛由调用方（异步摘要任务）感知
            log.error("保存会话摘要失败 {} : {}", conversation_id, e)
            _record_error("memory.save_summary")
            raise

    def get_message_count(self, conversation_id: str) -> int:
        """获取会话消息总数。"""
        try:
            session_uuid = self._to_uuid(conversation_id)
            with _get_pool().connection() as conn:
                row = conn.execute(
                    f"SELECT COUNT(*) FROM {self.table_name} WHERE session_id = %s",
                    (session_uuid,),
                ).fetchone()
                return row[0] if row else 0
        except Exception as e:
            log.error("获取消息计数失败 {} : {}", conversation_id, e)
            _record_error("memory.get_message_count")
            return 0

    def get_last_summary_count(self, conversation_id: str) -> int:
        """获取上次摘要时的消息计数。"""
        try:
            session_uuid = self._to_uuid(conversation_id)
            with _get_pool().connection() as conn:
                row = conn.execute(
                    "SELECT last_summary_msg_count FROM session_metadata WHERE session_id = %s",
                    (session_uuid,),
                ).fetchone()
                return (row[0] or 0) if row else 0
        except Exception as e:
            log.error("获取上次摘要计数失败 {} : {}", conversation_id, e)
            _record_error("memory.get_last_summary_count")
            return 0


# 反向查找表：UUID -> 原始 conversation_id（由 PostgresChatMemory 实例维护）
_session_uuid_map: dict[str, str] = {}


def _strip_user_input_boundary(content: str) -> str:
    """剥离 base_agent._wrap_user_input 添加的指令注入防护边界标记。

    历史消息从 DB 加载后返回前端时必须调用，否则用户会看到
    --- USER INPUT BEGIN / END --- 等内部标记。
    """
    prefix = "\n--- USER INPUT BEGIN ---\n"
    suffix = "\n--- USER INPUT END ---\n"
    if content.startswith(prefix) and content.endswith(suffix):
        return content[len(prefix):-len(suffix)]
    return content


def _extract_module(conversation_id: str) -> str:
    """从 conversation_id 提取模块前缀。

    格式约定：'web-xianzhi-<ts>' → 'web-xianzhi'；'mp-xianzhi__<userId>__<rand>' → 'mp-xianzhi'；
    'default' / 无连字符 → ''。双下划线分隔 user_id，避免与模块名里的连字符冲突。
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
    """从 conversation_id 提取 user_id（格式 `module__<userId>__<rand>`），旧格式/游客返回空串。"""
    parts = conversation_id.split("__")
    if len(parts) >= 2 and parts[1]:
        return parts[1]
    return ""


def get_session_info(prefix: str = "", user_id: str = None) -> list:
    """获取所有会话信息（前端会话列表），按 prefix/user_id 过滤。

    单条 SQL 完成聚合 + 每个会话最新一条消息提取（DISTINCT ON），消除逐组相关子查询的 N+1；
    module/user_id 过滤下推 SQL，LIMIT 兜底防极端库拖垮接口。
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
            conditions = []
            params: list = []
            if user_id:
                conditions.append("sm.user_id = %s")
                params.append(user_id)
            elif prefix:
                # prefix 下推：优先匹配 sm.module；sm 缺失的旧行保留，由下方 Python 兜底
                conditions.append("(sm.module = %s OR sm.conversation_id IS NULL)")
                params.append(prefix)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            sql += " ORDER BY agg.last_time DESC LIMIT 500"
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
        sessions = []
        for row in rows:
            session_uuid = str(row[0])
            conversation_id = row[1]
            module = row[2]
            # 旧数据/尚未同步时 session_metadata 无记录，用内存映射兜底
            if not conversation_id:
                conversation_id = _session_uuid_map.get(session_uuid, session_uuid)
                module = _extract_module(str(conversation_id))
            if prefix and str(module) != prefix:
                continue
            last_msg_raw = row[4]
            last_msg_text = ""
            if last_msg_raw:
                try:
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
    except Exception:
        log.exception("获取会话列表失败")
        _record_error("memory.get_session_info")
        return []


def _resolve_session_uuid(session_id: str) -> str:
    """解析 conversation_id 为真实 session_uuid：优先查 session_metadata，查不到再用确定性 UUID 计算。"""
    try:
        with _get_pool().connection() as conn:
            row = conn.execute(
                "SELECT session_id FROM session_metadata WHERE conversation_id = %s",
                (session_id,)
            ).fetchone()
        if row:
            return str(row[0])
    except Exception as e:
        # 降级为确定性 UUID 计算（可能指向空会话），但错误必须可见
        log.warning("解析 session_uuid 失败，回退确定性 UUID: {}", e)
        _record_error("memory.resolve_session_uuid")
    return PostgresChatMemory._to_uuid(session_id)


def get_session_owner(session_id: str) -> str:
    """获取会话归属用户 ID（session_metadata.user_id），游客/旧格式会话返回空串。

    供 API 层做会话越权校验：user_id 非空的会话仅限本人 token 访问。
    查询失败时返回空串放行，避免 DB 抖动直接打断正常用户。
    """
    try:
        with _get_pool().connection() as conn:
            row = conn.execute(
                "SELECT user_id FROM session_metadata WHERE conversation_id = %s",
                (session_id,),
            ).fetchone()
        return (row[0] or "") if row else ""
    except Exception as e:
        log.warning("查询会话归属失败 {} : {}", session_id, e)
        return ""


def delete_session(session_id: str):
    """删除指定会话的所有消息。"""
    try:
        session_uuid = _resolve_session_uuid(session_id)
        with _get_pool().connection() as conn:
            conn.execute("DELETE FROM message_store WHERE session_id = %s", (session_uuid,))
            conn.execute("DELETE FROM session_metadata WHERE session_id = %s", (session_uuid,))
    except Exception:
        # 删除失败重抛，API 层返回 5xx，不向用户假装删除成功
        log.exception("删除会话失败: {}", session_id)
        _record_error("memory.delete_session")
        raise


def get_messages(session_id: str) -> list:
    """获取指定会话所有消息（前端 role 格式：user / assistant）。

    过滤 tool/system 消息、tool_call_agent 注入的 next_step_prompt 占位消息及空消息；
    user 消息剥离 base_agent 注入的指令防护边界标记。
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
            if raw_role in ("tool", "system"):
                continue
            # next_step_prompt 占位消息（tool_call_agent 注入的 HumanMessage）不作为用户消息展示，
            # 关键词须与 app.agent.xianzhi.NEXT_STEP_PROMPT 实际文本一致
            if raw_role == "human" and "根据用户需求选最合适的工具，复杂任务分解多步" in content:
                continue
            if not content.strip():
                continue
            role = "user" if raw_role == "human" else "assistant"
            if role == "user":
                content = _strip_user_input_boundary(content)
            messages.append({
                "role": role,
                "content": content,
                "time": str(row[1]) if row[1] else "",
            })
        return messages
    except Exception:
        log.exception("获取会话消息失败: {}", session_id)
        _record_error("memory.get_messages")
        return []


def get_birth_info_from_session(session_id: str) -> dict | None:
    """从会话历史中的排盘工具调用参数提取出生信息。

    用户可能用农历/节日/时辰等自然语言输入（如"2004年端午节 辰时 男"），
    前端正则无法提取；这里从 AIMessage 的 tool_calls 中取 LLM 已解析的标准 birth_time/gender。
    """
    # 排盘工具名单复用 app.tools.bazi.BAZI_BIRTH_TOOLS（含 birth_time 参数的工具全集），
    # 不再本地维护一份拷贝，避免与 agent 层名单漂移
    from app.tools.bazi import BAZI_BIRTH_TOOLS

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
                if name in BAZI_BIRTH_TOOLS:
                    bt = args.get("birth_time")
                    gd = args.get("gender")
                    if bt and gd:
                        try:
                            from app.domain.time_parse import _normalize_birth_time
                            bt = _normalize_birth_time(bt)
                        except Exception:
                            pass
                        return {"time": bt, "gender": gd}
        return None
    except Exception as e:
        log.error("提取会话出生信息失败 {} : {}", session_id, e)
        _record_error("memory.get_birth_info")
        return None
