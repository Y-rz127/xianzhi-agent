"""测试全局夹具：默认关闭付费配额/外部网络，测试数据只去**测试库**。

数据落点分三种情况（这是本文件最重要的约定）：

1. 配了 `TEST_POSTGRES_CONNECTION_STRING`（且库名以 `_test` 结尾）→ 全量跑测改道该库，
   单测/集成测试都照常用 PostgreSQL，种子数据只写进测试库，**绝不动开发库**；
   跑测开始先清空会话类表，避免上一次的残留让"列表/计数"类断言飘。
2. 没配 → 单测退化为文件记忆 + 挡掉出生信息/命盘快照写入（`.env` 里
   MEMORY_STORE_TYPE=postgres 时，构造真实 Agent 的单测会直连开发库）；
   集成测试跳过。
3. 配了但库名不以 `_test` 结尾 → 认为填错（大概是把开发库粘进来了），**不改道**、
   按第 2 条处理并大声提醒，防止把测试数据写进真库。
"""
from __future__ import annotations

import os
import shutil
import socket
import uuid
from pathlib import Path

import pytest

from app.core.config import settings


def _resolve_test_dsn() -> str:
    """测试库连接串：真实环境变量优先，其次 backend/.env（pydantic 已解析进 settings）。"""
    raw = (os.environ.get("TEST_POSTGRES_CONNECTION_STRING") or "").strip()
    if raw:
        return raw
    return (getattr(settings, "test_postgres_connection_string", "") or "").strip()


def _db_name_of(dsn: str) -> str:
    """从 DSN 里取库名（不引第三方解析，够用即可）。"""
    tail = dsn.rsplit("/", 1)[-1]
    return tail.split("?", 1)[0].strip()


_TEST_DSN = _resolve_test_dsn()
# 只有库名以 `_test` 结尾才允许改道：CI 的 xianzhi_test 与本机 xianzhi_test 都符合，
# 而把开发库（.../xianzhi）误填进来时会被拦下。
_TEST_DSN_SAFE = bool(_TEST_DSN) and _db_name_of(_TEST_DSN).endswith("_test")
_TEST_REDIS = (os.environ.get("TEST_REDIS_URL") or "").strip()

# 单测退化为文件记忆时的目录：backend/.pytest-memory/<run-id>/（每次跑测一个，收尾删除）。
# 刻意放在 backend/ 下而不是系统临时目录 —— `memory_dir` 有一条"必须锚在 BACKEND_ROOT"
# 的配置不变量（test_config_kv 钉着），夹具改到别处会把那条守卫打成假失败。
_MEMORY_TMP = Path(__file__).resolve().parents[1] / ".pytest-memory" / uuid.uuid4().hex

# 跑测会写的会话类表：开始前清空（仅测试库；见 _TEST_DSN_SAFE）
_SESSION_TABLES = ("session_metadata", "message_store", "session_birth_info")

# conftest 先于测试模块导入：这里改道后，全量跑测（含 lifespan/DAL）都连测试库
if _TEST_DSN_SAFE:
    settings.postgres_connection_string = _TEST_DSN
if _TEST_REDIS:
    settings.redis_url = _TEST_REDIS


def pytest_sessionstart(session):
    """用测试库时先清会话类表：CI 每次都是新库，本机却是长驻库，残留会让断言飘。"""
    if not _TEST_DSN_SAFE:
        return
    try:
        from app.db.pool import get_pool

        with get_pool().connection() as conn:
            for table in _SESSION_TABLES:
                exists = conn.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()
                if exists and exists[0]:
                    conn.execute(f"TRUNCATE TABLE {table}")
    except Exception as e:  # 清不干净不该拦住整轮测试，但要说出来
        print(f"[conftest] 测试库会话表清理失败（继续跑）: {e}")


@pytest.fixture(autouse=True)
def _isolate_runtime(monkeypatch, request):
    """关闭计费/外部初始化，并重置进程级可变状态，避免用例互相污染。"""
    monkeypatch.setattr(settings, "llm_chain_probe_enabled", False)
    monkeypatch.setattr(settings, "message_retention_days", 0)
    monkeypatch.setattr(settings, "rag_init_enabled", False)
    monkeypatch.setattr(settings, "checkpoint_enabled", False)
    # 单测不启动 MCP 子进程、不初始化 LangSmith（避免 npx/网络拖慢与副作用）
    monkeypatch.setattr(settings, "amap_maps_api_key", "")
    monkeypatch.setattr(settings, "langsmith_tracing", False)
    if not _TEST_DSN_SAFE:
        # 没有可用测试库：单测一律不许碰真库（见模块 docstring 第 2/3 条）
        monkeypatch.setattr(settings, "memory_store_type", "file")
        monkeypatch.setattr(settings, "memory_dir", _MEMORY_TMP)
        # 出生信息 / 命盘快照走的是 postgres_memory 的模块级函数（不经 create_chat_memory），
        # set_chart_context 与 cleanup 会顺手写进 session_birth_info —— 一并挡掉。
        # data_access 里是 import 时就绑好的 _async 包装，得连它一起挡，否则换条路径又能写进去。
        from app.api import data_access as _repo
        from app.memory import postgres_memory as _pg_memory

        def _no_write(*_args, **_kwargs):
            return None

        async def _no_write_async(*_args, **_kwargs):
            return None

        monkeypatch.setattr(_pg_memory, "upsert_session_birth_info", _no_write)
        monkeypatch.setattr(_pg_memory, "set_session_chart", _no_write)
        monkeypatch.setattr(_repo, "upsert_session_birth_info", _no_write_async)
        monkeypatch.setattr(_repo, "set_session_chart", _no_write_async)
    for name in (
        "paid_quota_report_daily",
        "paid_quota_asr_daily",
        "paid_quota_tts_daily",
        "paid_quota_interpret_daily",
        "paid_quota_guest_daily",
    ):
        monkeypatch.setattr(settings, name, 0)

    from app.core import observability, turn_idempotency

    with observability._metrics_lock:
        observability._metrics["endpoints"].clear()
        observability._metrics["recent_errors"].clear()
        observability._metrics["internal_errors"].clear()
        observability._metrics["llm"].clear()
        observability._metrics["status_codes"].update({"2xx": 0, "4xx": 0, "5xx": 0})
    turn_idempotency._local.clear()
    yield
    turn_idempotency._local.clear()


@pytest.fixture(autouse=True)
def _block_external_network(request, monkeypatch):
    """非集成用例禁止访问 external 网络：防止误调真实 LLM/SerpAPI 产生费用。"""
    if "integration" in request.node.keywords:
        return
    original_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host in ("127.0.0.1", "::1", "localhost"):
            return original_connect(self, address)
        raise RuntimeError(f"测试禁止访问外部网络: {address}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


def pytest_sessionfinish(session, exitstatus):
    """收尾清掉本次跑测的记忆临时目录（进程级唯一，跑完即弃）。"""
    shutil.rmtree(_MEMORY_TMP, ignore_errors=True)


def pytest_collection_modifyitems(config, items):
    """没有可用测试库时跳过集成测试，防止误连开发库。"""
    if _TEST_DSN_SAFE:
        return
    reason = (
        "TEST_POSTGRES_CONNECTION_STRING 未配置或库名不以 _test 结尾，集成测试跳过"
        f"（当前值：{_TEST_DSN or '未设置'}）"
    )
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
