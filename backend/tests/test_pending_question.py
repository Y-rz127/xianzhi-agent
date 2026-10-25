""""提问即时落库 + 失败标已结束" 回归测试（不依赖真实 PG/LLM）。

背景：完整一轮（问+答）是 cleanup 里 `_persist_history` 一次性落库的，生成期间
服务端什么都没有。于是用户在生成期间切到别的会话、或小程序被系统回收再打开，
这一问就只剩前端内存兜着 —— 页面一重建就没了。

修法：
- 轮次开始时就把提问写进 `message_store`，标 `turn_status='running'`；
- cleanup 无论成功/失败/中止都把它改成 `ended`（**不删行**：用户仍能看到问过什么）；
- 读取侧（`get_messages`）带回 `status`，前端据此区分"还在生成"与"已结束的孤立提问"；
- 进程崩溃没人收尾时，靠写入时间 + 单轮预算兜底判成 ended。

验证点：
① `pending_status` 的状态换算（含超时兜底、老数据空状态）；
② `add_pending_question` / `end_pending_question` 的 SQL 与容错；
③ `get_messages` 把状态带进前端 payload；
④ agent 侧：提问先落库、cleanup 时标 ended、`_persist_history` 不重复写同一问。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.core.config import settings
from app.memory import postgres_memory as pg


# ---------------- ① 状态换算 ----------------
def test_pending_status_maps_three_states():
    now = datetime.now(timezone.utc)
    assert pg.pending_status("ended", now, now=now) == "ended"
    assert pg.pending_status("running", now, now=now) == "running"
    # 没有标记的老数据：交给调用方沿用旧判断
    assert pg.pending_status(None, now, now=now) == ""
    assert pg.pending_status("", now, now=now) == ""


def test_pending_status_treats_stale_running_as_ended():
    """进程被杀时没人来收尾：超过单轮预算 + 余量就当已结束，别让前端永远等。"""
    now = datetime.now(timezone.utc)
    fresh = now - timedelta(seconds=settings.chat_turn_budget)
    stale = now - timedelta(
        seconds=settings.chat_turn_budget + pg.PENDING_STALE_SLACK_SECONDS + 1
    )
    assert pg.pending_status("running", fresh, now=now) == "running"
    assert pg.pending_status("running", stale, now=now) == "ended"
    # naive 时间（手工塞的数据）按 UTC 处理，不能因此永远判 running
    assert pg.pending_status("running", stale.replace(tzinfo=None), now=now) == "ended"


def test_pending_status_keeps_running_when_time_unknown():
    assert pg.pending_status("running", None) == "running"
    assert pg.pending_status("running", datetime.now(timezone.utc), now=None) == "running"


# ---------------- ② 写入 / 收尾 ----------------
class _Exec:
    def __init__(self, rows):
        self._rows = rows
        self.sql = ""
        self.params = None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _Conn:
    """按调用顺序返回预设结果集的假连接（每次 execute 弹出一组 rows）。"""

    def __init__(self, rows=None, fail=False):
        # rows 支持两种写法：单组 rows（所有 execute 都返回它）或 rows 列表
        if rows and isinstance(rows[0], list):
            self._rowsets = list(rows)
        else:
            self._rowsets = None
            self._rows = rows or []
        self.executed: list[tuple[str, object]] = []
        self._fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if self._fail:
            raise RuntimeError("db down")
        self.executed.append((sql, params))
        if self._rowsets is None:
            return _Exec(self._rows)
        return _Exec(self._rowsets.pop(0) if self._rowsets else [])


class _Pool:
    def __init__(self, conn):
        self._conn = conn
        self.conn = conn

    def connection(self):
        return self._conn


def _memory(monkeypatch, conn: _Conn) -> pg.PostgresChatMemory:
    monkeypatch.setattr(pg, "_get_pool", lambda: _Pool(conn))
    monkeypatch.setattr(pg, "_ensure_schema", lambda: None)
    return pg.PostgresChatMemory()


def test_add_pending_question_inserts_running_row(monkeypatch):
    # 依次：元数据 upsert、复用检查（无命中）、INSERT、（收尾其他 running，无返回）
    conn = _Conn(rows=[[], [], [(42,)]])
    mem = _memory(monkeypatch, conn)

    row_id = mem.add_pending_question("mp-xianzhi-test", HumanMessage(content="帮我看看今年"))

    assert row_id == 42
    inserts = [(sql, p) for sql, p in conn.executed if "RETURNING id" in sql and "INSERT INTO" in sql]
    assert len(inserts) == 1
    sql, params = inserts[0]
    assert "'running'" in sql
    assert params[0] == pg.PostgresChatMemory._to_uuid("mp-xianzhi-test")
    # 序列化格式必须是 langchain 认的那套（{type, data:{content}}），否则历史读不回来
    payload = json.loads(params[1])
    assert payload["type"] == "human"
    assert payload["data"]["content"] == "帮我看看今年"
    # 新开一轮时也要把上次崩溃留下的其他"生成中"收尾（一个会话最多一条 running）
    assert any("id <> %s" in sql for sql, _ in conn.executed)


def test_add_pending_question_reuses_orphan_row_from_crashed_attempt(monkeypatch):
    """崩溃后重试同一个问题：复用上一次留下的"生成中"行，别把同一问存两遍。"""
    # 元数据 upsert（无返回）→ 复用检查命中 → 收尾其余残留（无返回）
    conn = _Conn(rows=[[], [(42,)]])
    mem = _memory(monkeypatch, conn)

    row_id = mem.add_pending_question("mp-xianzhi-test", HumanMessage(content="帮我看看今年"))

    assert row_id == 42
    reuse_sql, reuse_params = conn.executed[1]
    assert "created_at = NOW()" in reuse_sql and "turn_status = 'running'" in reuse_sql
    assert reuse_params[1] == "帮我看看今年"
    # 其余内容不同的残留一并收尾：一个会话最多一条 running
    close_sql, close_params = conn.executed[2]
    assert "turn_status = 'ended'" in close_sql and close_params[1] == 42
    # 没有新增消息行（元数据 upsert 的 INSERT 不算）
    assert not any(
        f"INSERT INTO {settings.memory_table_name} (session_id, message, turn_status)" in sql
        for sql, _ in conn.executed
    )


def test_add_pending_question_failure_does_not_raise(monkeypatch):
    mem = _memory(monkeypatch, _Conn(fail=True))
    assert mem.add_pending_question("mp-xianzhi-test", HumanMessage(content="问题")) is None


def test_end_pending_question_marks_ended_without_deleting(monkeypatch):
    conn = _Conn()
    mem = _memory(monkeypatch, conn)

    assert mem.end_pending_question(42) is True
    sql, params = conn.executed[-1]
    assert sql.strip().startswith("UPDATE")
    assert "turn_status = 'ended'" in sql
    # 只改 running 的行，且**不删行**（表里没有 DELETE）
    assert "turn_status = 'running'" in sql
    assert params == (42,)
    # 没落过库（None）= 空操作，也不该去连库
    assert mem.end_pending_question(None) is False
    assert len(conn.executed) == 1


def test_end_pending_question_failure_returns_false(monkeypatch):
    mem = _memory(monkeypatch, _Conn(fail=True))
    assert mem.end_pending_question(42) is False


# ---------------- ③ 读取侧带状态 ----------------
def test_get_messages_surfaces_turn_status(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        ({"type": "human", "data": {"content": "在生成的一问"}}, now, "running"),
        ({"type": "human", "data": {"content": "失败留下的一问"}}, now, "ended"),
        ({"type": "human", "data": {"content": "老数据"}}, now, None),
        ({"type": "ai", "data": {"content": "回答"}}, now, None),
    ]
    conn = _Conn(rows=rows)
    monkeypatch.setattr(pg, "_get_pool", lambda: _Pool(conn))
    store = pg.PostgresMemoryStore()
    monkeypatch.setattr(store, "_resolve_session_uuid", lambda sid: "uuid")

    out = store.get_messages("mp-xianzhi-test")

    assert [m["content"] for m in out] == ["在生成的一问", "失败留下的一问", "老数据", "回答"]
    assert out[0]["status"] == "running"
    assert out[1]["status"] == "ended"  # 孤立提问：明确已结束，前端不再轮询
    assert "status" not in out[2]  # 老数据：不返回字段，沿用旧判断
    assert "status" not in out[3]  # 回答本身没有轮次状态


def test_get_messages_keeps_only_final_assistant_per_turn(monkeypatch):
    """ReAct 一轮会落多条 assistant（中间步骤 + 最终回答），前端只该看到最终那条。

    2026-10-25 现场：同一个问题下挂着 3~4 个气泡（"我先翻翻书"、"再查一次"…），
    点朗读还会逐段读。`xianzhi._filter_steps` 的约定本来就是"只产出最终回答"，
    展示侧要跟上，否则刷一次页面就把 ReAct 的内心戏全暴露给用户。
    """
    now = datetime.now(timezone.utc)
    rows = [
        ({"type": "human", "data": {"content": "什么是飞天禄马格？"}}, now, "ended"),
        ({"type": "ai", "data": {"content": "我先翻翻书"}}, now, None),
        ({"type": "tool", "data": {"content": "资料"}}, now, None),
        ({"type": "ai", "data": {"content": "再查一次"}}, now, None),
        ({"type": "ai", "data": {"content": "最终回答"}}, now, None),
        ({"type": "human", "data": {"content": "下一问"}}, now, "ended"),
        ({"type": "ai", "data": {"content": "下一答"}}, now, None),
    ]
    conn = _Conn(rows=rows)
    monkeypatch.setattr(pg, "_get_pool", lambda: _Pool(conn))
    store = pg.PostgresMemoryStore()
    monkeypatch.setattr(store, "_resolve_session_uuid", lambda sid: "uuid")

    out = store.get_messages("mp-xianzhi-test")

    assert [(m["role"], m["content"]) for m in out] == [
        ("user", "什么是飞天禄马格？"),
        ("assistant", "最终回答"),
        ("user", "下一问"),
        ("assistant", "下一答"),
    ]


# ---------------- ④ agent 侧 ----------------
def _agent(memory) -> object:
    from app.agent.xianzhi import Xianzhi

    with patch("app.agent.xianzhi.create_chat_memory", return_value=memory):
        return Xianzhi(chat_model=MagicMock(), local_tools=[])


class _Mem:
    """记录 add / add_pending_question / end_pending_question 的假记忆层。"""

    def __init__(self, row_id=7, raise_on_add=False):
        self.row_id = row_id
        self.raise_on_add = raise_on_add
        self.added: list = []
        self.pending: list = []
        self.ended: list = []

    def add(self, conversation_id, messages, user_id=""):
        self.added.extend(messages)

    def add_pending_question(self, conversation_id, message):
        if self.raise_on_add:
            raise RuntimeError("boom")
        self.pending.append(message.content)
        return self.row_id

    def end_pending_question(self, message_id):
        self.ended.append(message_id)
        return True

    def get_summary(self, conversation_id):
        return ""


def test_question_is_persisted_when_turn_starts():
    mem = _Mem()
    agent = _agent(mem)
    agent._history_len = 0

    agent._persist_pending_question("帮我看看今年")

    assert mem.pending == ["帮我看看今年"]
    assert agent._pending_question_id == 7
    assert agent._persisted_question == "帮我看看今年"


def test_persist_history_does_not_write_the_question_twice():
    """提问已在轮次开始时落库，cleanup 只追加回答，否则同一问会写两遍。"""
    mem = _Mem()
    agent = _agent(mem)
    agent._history_len = 0
    agent._persist_pending_question("帮我看看今年")
    agent.message_list = [HumanMessage(content="帮我看看今年"), AIMessage(content="回答")]

    with patch("app.memory.summarizer.maybe_summarize"):
        agent._persist_history()

    assert [m.content for m in mem.added] == ["回答"]


def test_persist_history_skips_wrapped_question():
    """ReAct 路径的输入被 BaseAgent 包了防注入边界，去重也得认得出来。

    2026-10-25 现场：`message_list` 里存的是
    `\\n--- USER INPUT BEGIN ---\\nQ\\n--- USER INPUT END ---\\n`，而 `_persisted_question`
    是原文 `Q`，直接比永远不等 → 同一问写两遍，前端会话里连着两条
    "我：什么是飞天禄马格?"。workflow 路径不包边界，所以那边一直是好的。
    """
    from app.agent.core.base_agent import _wrap_user_input

    mem = _Mem()
    agent = _agent(mem)
    agent._history_len = 0
    agent._persist_pending_question("什么是飞天禄马格？")
    agent.message_list = [
        HumanMessage(content=_wrap_user_input("什么是飞天禄马格？")),
        AIMessage(content="回答"),
    ]

    with patch("app.memory.summarizer.maybe_summarize"):
        agent._persist_history()

    assert [m.content for m in mem.added] == ["回答"]


def test_boundary_strip_implementations_agree():
    """`base_agent` 与 `postgres_memory` 各有一份剥标记实现，行为必须一致。

    漂移的后果特别隐蔽：展示侧剥了（前端看着正常）、去重侧没剥（库里悄悄多一条），
    排查时只看界面根本发现不了。
    """
    from app.agent.core.base_agent import _wrap_user_input, unwrap_user_input
    from app.memory.postgres_memory import _strip_user_input_boundary as memory_strip

    samples = [
        _wrap_user_input("什么是飞天禄马格？"),
        _wrap_user_input(""),
        "裸文本",
        "",
        "前半段\n--- USER INPUT END ---\n",  # 只有后半个标记，不该被剥
        "\n--- USER INPUT BEGIN ---\n缺后标记",  # 只有前半个标记，不该被剥
    ]
    for sample in samples:
        assert unwrap_user_input(sample) == memory_strip(sample), repr(sample)


def test_persist_history_writes_question_when_early_write_failed():
    """提前落库失败 → 退回旧行为，cleanup 照常把问和答都写进去。"""
    mem = _Mem(raise_on_add=True)
    agent = _agent(mem)
    agent._history_len = 0
    agent._persist_pending_question("帮我看看今年")
    agent.message_list = [HumanMessage(content="帮我看看今年"), AIMessage(content="回答")]

    with patch("app.memory.summarizer.maybe_summarize"):
        agent._persist_history()

    assert [m.content for m in mem.added] == ["帮我看看今年", "回答"]


def test_cleanup_marks_question_ended_even_on_failure():
    mem = _Mem()
    agent = _agent(mem)
    agent._history_len = 0
    agent._persist_pending_question("帮我看看今年")
    # 本轮失败：没有回答入历史
    agent.message_list = [HumanMessage(content="帮我看看今年")]

    with patch("app.memory.summarizer.maybe_summarize"), patch.object(
        agent, "_persist_birth_info"
    ), patch("app.agent.xianzhi.record_bazi_display_order"):
        agent.cleanup()

    assert mem.ended == [7]
    assert agent._pending_question_id is None
    assert agent._persisted_question == ""


def test_memory_without_pending_support_keeps_old_behaviour():
    """文件记忆后端没有这个方法：跳过即时落库，cleanup 照常写全量。"""
    from app.memory.chat_memory import FileBasedChatMemory

    agent = _agent(FileBasedChatMemory.__new__(FileBasedChatMemory))
    agent._history_len = 0

    agent._persist_pending_question("帮我看看今年")

    assert agent._pending_question_id is None
    assert agent._persisted_question == ""
