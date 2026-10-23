"""P1-01 断点恢复：工作流异常中断后，同一 turn_id 从最后完成节点续跑。"""
from __future__ import annotations

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.workflow.orchestrator import XianzhiWorkflow
from app.agent.workflow.workflow_support import build_chart_context


class _FailOnceModel:
    """首次生成抛异常，续跑时成功；记录拆解/生成调用次数。"""

    def __init__(self):
        self.decompose_calls = 0
        self.generate_calls = 0
        self.fail_generate = True

    def bind(self, **kwargs):
        return self

    def invoke(self, messages, **kwargs):
        text = "\n".join(str(getattr(m, "content", "")) for m in messages)
        if "意图分析模块" in text:
            self.decompose_calls += 1
            return AIMessage(
                content=(
                    '{"domain":"personality","queries":["性格 十神 格局"],'
                    '"needs_chart":true,"other_birth_time":"","other_gender":"",'
                    '"target_dayun":""}'
                )
            )
        if "【待审核回答】" in text:
            return AIMessage(content='{"pass": true, "issues": []}')
        if "【原回答】" in text:
            return AIMessage(content="修复稿")
        self.generate_calls += 1
        if self.fail_generate:
            self.fail_generate = False
            raise RuntimeError("generate boom")
        return AIMessage(content="续跑后的最终回答")


def test_resume_from_checkpoint_skips_completed_nodes():
    model = _FailOnceModel()
    workflow = XianzhiWorkflow(chat_model=model, checkpointer=InMemorySaver())
    ctx = build_chart_context("2004-06-22 08:00", "男")
    turn_id = "test-conversation:turn-001"

    try:
        workflow.answer("我性格怎么样？", ctx, turn_id=turn_id)
    except RuntimeError as e:
        assert "generate boom" in str(e)
    else:
        raise AssertionError("首次生成应抛出异常以模拟进程中断")

    assert model.decompose_calls == 1
    assert model.generate_calls == 1

    answer = workflow.answer("我性格怎么样？", ctx, turn_id=turn_id)

    assert answer == "续跑后的最终回答"
    assert model.decompose_calls == 1, "续跑不应重新拆解意图"
    assert model.generate_calls == 2, "只应重跑中断的生成节点"


class _FakeConn:
    """记录 SQL 的假连接：SELECT 返回预设 stale thread。"""

    def __init__(self, stale):
        self._stale = stale
        self.sqls = []

    def execute(self, sql, params=None):
        self.sqls.append((sql, params))
        if "HAVING max" in sql:
            return [{"thread_id": t} for t in self._stale]
        return []

    def transaction(self):
        import contextlib

        return contextlib.nullcontext()


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def connection(self):
        import contextlib

        return contextlib.nullcontext(self._conn)


def test_purge_stale_checkpoints_deletes_thread_rows(monkeypatch):
    import app.agent.checkpoint as checkpoint

    conn = _FakeConn(["conv-a:turn-1", "conv-b:turn-2"])
    monkeypatch.setattr(checkpoint, "_saver", object())
    monkeypatch.setattr(checkpoint, "get_checkpoint_pool", lambda: _FakePool(conn))

    assert checkpoint.purge_stale_checkpoints(24) == 2
    sqls = "\n".join(sql for sql, _ in conn.sqls)
    assert "from checkpoints" in sqls.lower()
    assert "checkpoint_writes" in sqls
    assert "checkpoint_blobs" in sqls
    assert conn.sqls[0][1] == (24,)


def test_purge_stale_checkpoints_noop_without_checkpointer(monkeypatch):
    import app.agent.checkpoint as checkpoint

    monkeypatch.setattr(checkpoint, "_saver", None)
    assert checkpoint.purge_stale_checkpoints(24) == 0
    assert checkpoint.purge_stale_checkpoints(0) == 0


def test_fresh_turn_does_not_resume_previous_checkpoint():
    model = _FailOnceModel()
    model.fail_generate = False
    workflow = XianzhiWorkflow(chat_model=model, checkpointer=InMemorySaver())
    ctx = build_chart_context("2004-06-22 08:00", "男")

    first = workflow.answer("我性格怎么样？", ctx, turn_id="conv:turn-a")
    second = workflow.answer("我性格怎么样？", ctx, turn_id="conv:turn-b")

    assert first == "续跑后的最终回答"
    assert second == "续跑后的最终回答"
    assert model.decompose_calls == 2, "不同 turn_id 必须各自完整执行"
