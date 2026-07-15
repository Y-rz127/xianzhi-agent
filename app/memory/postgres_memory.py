"""基于 PostgreSQL 的对话记忆（与 FileBasedChatMemory 同接口）。

利用 langchain_postgres.PostgresChatMessageHistory 持久化对话，
表名默认 message_store，session_id 作为会话隔离键。

注意：PostgresChatMessageHistory 的签名是
  __init__(table_name, session_id, /, *, sync_connection=, async_connection=)
即 table_name/session_id 是位置参数，连接必须传 psycopg.Connection 对象。
"""
from __future__ import annotations

import hashlib
import uuid as uuid_module
from typing import List, Optional

from langchain_core.messages import BaseMessage

from app.config import settings
from app.logger import log


class PostgresChatMemory:
    """PostgreSQL 版对话记忆，与 FileBasedChatMemory 接口一致。"""

    # 固定命名空间，确保同一 conversation_id 始终映射到同一 UUID
    _NAMESPACE = uuid_module.UUID("00000000-0000-0000-0000-000000000001")

    def __init__(self, connection_string: str = None, table_name: str = "message_store"):
        self.connection_string = connection_string or settings.postgres_connection_string
        self.table_name = table_name
        self._conn = None

    @staticmethod
    def _to_uuid(conversation_id: str) -> str:
        """将任意 conversation_id 转为确定性 UUID（PostgresChatMessageHistory 要求）"""
        return str(uuid_module.uuid5(PostgresChatMemory._NAMESPACE, conversation_id))

    @staticmethod
    def _to_session_id(prefix: str, conversation_id: str) -> str:
        return f"{prefix}-{conversation_id}"

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            import psycopg
            self._conn = psycopg.connect(self.connection_string, autocommit=True)
            try:
                from langchain_postgres import PostgresChatMessageHistory
                PostgresChatMessageHistory.create_tables(self._conn, self.table_name)
                # 创建会话元数据表，持久化 UUID -> conversation_id 的映射
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS session_metadata (
                        session_id UUID PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        module TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                log.info("PG 记忆表已就绪: {}", self.table_name)
            except Exception as e:
                log.warning("PG 记忆表创建失败（可能已存在）: {}", e)
        return self._conn

    def _history(self, conversation_id: str):
        from langchain_postgres import PostgresChatMessageHistory
        session_uuid = self._to_uuid(conversation_id)
        return PostgresChatMessageHistory(
            self.table_name,
            session_uuid,
            sync_connection=self._get_conn(),
        )

    def get(self, conversation_id: str) -> List[BaseMessage]:
        try:
            return self._history(conversation_id).messages
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
            conn = self._get_conn()
            conn.execute("""
                INSERT INTO session_metadata (session_id, conversation_id, module)
                VALUES (%s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE
                SET conversation_id = EXCLUDED.conversation_id,
                    module = EXCLUDED.module,
                    updated_at = CURRENT_TIMESTAMP
            """, (session_uuid, conversation_id, module))
            history = self._history(conversation_id)
            for m in messages:
                history.add_message(m)
        except Exception as e:
            log.warning("写入PG记忆失败 {} : {}", conversation_id, e)

    def clear(self, conversation_id: str):
        try:
            self._history(conversation_id).clear()
        except Exception as e:
            log.warning("清空PG记忆失败 {} : {}", conversation_id, e)

    def close(self):
        if self._conn is not None and not self._conn.closed:
            try:
                self._conn.close()
            except Exception:
                pass


_pg_conn = None


def _get_global_conn():
    """获取模块级复用的 PostgreSQL 连接（线程内复用）。"""
    global _pg_conn
    import psycopg
    if _pg_conn is None or _pg_conn.closed:
        _pg_conn = psycopg.connect(settings.postgres_connection_string, autocommit=True)
    return _pg_conn


def close_global_conn():
    """关闭模块级全局连接（应用退出时调用）。"""
    global _pg_conn
    if _pg_conn is not None and not _pg_conn.closed:
        try:
            _pg_conn.close()
        except Exception:
            pass
        finally:
            _pg_conn = None


# 反向查找表：UUID -> 原始 conversation_id（由 PostgresChatMemory 实例维护）
_session_uuid_map: dict[str, str] = {}


def _extract_module(conversation_id: str) -> str:
    """从 conversation_id 提取模块前缀（取前两段）。

    规则：
      - "web-xianzhi-1783429404556" → "web-xianzhi"
      - "mp-love-1783429404556"    → "mp-love"
      - "xianzhi-1783429404556"    → "xianzhi"   （旧格式兼容，只有一段前缀）
      - "default" / 无连字符       → ""

    这样可以让 PC web 和小程序、先知和恋爱四端会话互不干扰。
    """
    if not conversation_id or "-" not in conversation_id:
        return ""
    parts = conversation_id.split("-")
    # 第一段：端类型（web/mp）
    first = parts[0]
    # 第二段：模块名（xianzhi/love）。若第二段是纯数字时间戳，说明是旧格式（只取第一段）
    if len(parts) >= 2 and not parts[1].isdigit():
        return f"{first}-{parts[1]}"
    return first


def get_session_info(prefix: str = "") -> list:
    """获取所有会话信息（用于前端会话列表），按 prefix 过滤。"""
    try:
        conn = _get_global_conn()
        cur = conn.execute("""
            SELECT ms.session_id,
                   sm.conversation_id,
                   sm.module,
                   (SELECT message FROM message_store ms2
                    WHERE ms2.session_id = ms.session_id ORDER BY created_at DESC LIMIT 1) as last_msg,
                   MIN(ms.created_at) as first_time,
                   MAX(ms.created_at) as last_time,
                   COUNT(*) as msg_count
            FROM message_store ms
            LEFT JOIN session_metadata sm ON ms.session_id = sm.session_id
            GROUP BY ms.session_id, sm.conversation_id, sm.module
            ORDER BY last_time DESC
        """)
        sessions = []
        for row in cur:
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
            last_msg_raw = row[3]
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
                "firstTime": str(row[4]) if row[4] else "",
                "lastTime": str(row[5]) if row[5] else "",
                "messageCount": row[6],
            })
        return sessions
    except Exception as e:
        log.exception("获取会话列表失败")
        return []

def _resolve_session_uuid(session_id: str) -> str:
    """解析 conversation_id 为真实的 session_uuid。
    优先查询 session_metadata，找不到再用 _to_uuid 计算。"""
    try:
        conn = _get_global_conn()
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
        conn = _get_global_conn()
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
        conn = _get_global_conn()
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
        conn = _get_global_conn()
        cur = conn.execute("""
            SELECT message, created_at FROM message_store
            WHERE session_id = %s ORDER BY created_at
        """, (session_uuid,))
        messages = []
        for row in cur:
            msg = row[0]
            content = msg.get("data", {}).get("content", "") or ""
            raw_role = msg.get("type", "").replace("_message", "")
            # 过滤：工具调用结果、推理片段、系统消息
            if raw_role in ("tool", "system"):
                continue
            # 过滤 next_step_prompt 占位消息
            if raw_role == "human" and "根据用户需求，主动选择最合适的工具" in content:
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
