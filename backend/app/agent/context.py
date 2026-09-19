"""运行时上下文（AppContext）与会话锁：共享依赖的单一持有者。

原位于 ``app/api/context.py``：``sub_app`` 需要 ``get_app_context()`` 取 ``chat_model`` /
``tarot_app``，只能反向 import api 层（报告 P0-4 的倒置边来源）。

**为什么归 agent 层而不是 core**：``AppContext.get_xianzhi`` 会构造
``app.agent.xianzhi`` 的 Xianzhi 实例，而 ``SessionLock`` 的语义正是"同一会话的
agent 操作串行化" —— 两者都是 agent 层职责。放 core 会让 core 反向依赖 agent，
把倒置边从一处搬到另一处。``api`` 与 ``sub_app`` 同为上层，均可合法 import agent。

FastAPI 依赖（``app_context_dependency``）属 HTTP 装配细节，已移到 ``app/api/deps.py``。

Xianzhi 智能体按会话池化（池为 AppContext 实例态）：
- 每个 conversation_id 对应一个独立的 Xianzhi 实例 + 会话锁；
- 同一会话内请求串行（保证命盘上下文、消息列表一致性），
  不同会话并行处理，不再被全局锁串行化；
- 池容量有限（LRU 淘汰最久未用实例），对话历史与出生信息均可从
  持久化记忆（PG/文件）恢复，淘汰无数据损失。

会话锁（SessionLock）为双层互斥：
- 进程内 asyncio.Lock：同副本内的快速路径
- Redis 分布式锁：跨副本互斥（多副本部署时同一会话可能落到不同副本）
- Redis 不可用时自动降级为仅进程内锁（单副本语义不变）

TarotApp 本身不持有会话级可变状态
（历史均从记忆存储按会话读取），保持单例即可。
"""
from __future__ import annotations

import asyncio
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from app.core.logger import log

# 会话 Agent 池容量上限（超出后 LRU 淘汰最久未使用实例）
_MAX_AGENTS = 100

# 分布式锁 TTL：覆盖最坏持有场景（LLM 排队 120s + 生成 180s + 审核/修复多轮）；
# 进程崩溃无法走到释放时靠 TTL 兜底自动解锁
_REDIS_LOCK_TTL_MS = 900_000
_REDIS_LOCK_KEY_PREFIX = "lock:session:"
# 他人持锁时的轮询间隔（与原 asyncio.Lock 的等待语义一致）
_LOCK_WAIT_INTERVAL = 0.5


class SessionLock:
    """会话级互斥锁：进程内锁快路径 + Redis 分布式锁跨副本互斥。"""

    def __init__(self, conversation_id: str, local: asyncio.Lock) -> None:
        self._key = f"{_REDIS_LOCK_KEY_PREFIX}{conversation_id}"
        self._local = local
        self._token = ""

    async def __aenter__(self) -> "SessionLock":
        await self._local.acquire()
        try:
            await self._acquire_redis()
        except Exception:
            self._local.release()
            raise
        return self

    async def __aexit__(self, *exc_info) -> None:
        try:
            if self._token:
                from app.core.redis_client import release_lock

                await release_lock(self._key, self._token)
                self._token = ""
        finally:
            self._local.release()

    async def _acquire_redis(self) -> None:
        from app.core.redis_client import acquire_lock

        while True:
            token = secrets.token_hex(16)
            got = await acquire_lock(self._key, token, _REDIS_LOCK_TTL_MS)
            if got is None:
                # Redis 不可用：仅本地锁兜底
                return
            if got:
                self._token = token
                return
            await asyncio.sleep(_LOCK_WAIT_INTERVAL)


@dataclass
class AppContext:
    """lifespan 内构造一次的共享依赖容器（替代原模块级全局单例）。"""

    chat_model: Any
    local_tools: Any
    memory: Any
    tarot_app: Any = None
    decompose_model: Any = None
    reviewer_model: Any = None
    # 子应用（塔罗/紫微/六爻/合婚）解读模型：空则回落主问答模型（见 get_sub_app_model）
    sub_app_model: Any = None
    # conversation_id -> Xianzhi 实例（会话锁为 agent.lock 上的 SessionLock，获取时现构）
    _agents: "OrderedDict[str, Any]" = field(default_factory=OrderedDict, repr=False)
    _pool_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        # 留空则复用主模型（与原 set_instances 语义一致）
        if self.decompose_model is None:
            self.decompose_model = self.chat_model
        if self.reviewer_model is None:
            self.reviewer_model = self.chat_model
        if self.sub_app_model is None:
            self.sub_app_model = self.chat_model

    def get_xianzhi(self, conversation_id: str):
        """获取（或创建）指定会话的 Xianzhi 实例及其会话锁（调用方在锁内完成会话操作，避免并发污染）。

        返回的锁为 SessionLock（进程内锁 + Redis 分布式锁双层互斥）。
        """
        cid = conversation_id if conversation_id and conversation_id.strip() else "xianzhi-default"
        with self._pool_lock:
            hit = self._agents.get(cid)
            if hit is not None:
                self._agents.move_to_end(cid)
                return hit, SessionLock(cid, hit.lock)
            if self.chat_model is None:
                raise RuntimeError("Xianzhi not initialized")
            from app.agent.xianzhi import create_xianzhi_agent

            agent = create_xianzhi_agent(
                chat_model=self.chat_model,
                local_tools=self.local_tools,
                memory=self.memory,
                conversation_id=cid,
                decompose_model=self.decompose_model,
                reviewer_model=self.reviewer_model,
            )
            self._agents[cid] = agent
            while len(self._agents) > _MAX_AGENTS:
                evicted_cid, _agent = self._agents.popitem(last=False)
                log.info("会话 Agent 池 LRU 淘汰: {} (pool_size={})", evicted_cid, len(self._agents))
            log.info("会话 Agent 创建: {} (pool_size={})", cid, len(self._agents))
            return agent, SessionLock(cid, agent.lock)

    def agent_pool_stats(self) -> dict:
        """会话池状态（监控/调试接口用）。"""
        with self._pool_lock:
            return {"pool_size": len(self._agents), "max_agents": _MAX_AGENTS}

    @staticmethod
    def workflow_backend() -> str:
        """返回当前编排后端（LangGraph 为唯一编排实现）。"""
        return "langgraph"


# ---------------- 进程内当前实例（lifespan 内写入） ----------------

_app_context: AppContext | None = None


def set_app_context(ctx: AppContext | None) -> None:
    """lifespan 启动时注册当前 AppContext（关停时传 None 清理）。"""
    global _app_context
    _app_context = ctx


def get_app_context() -> AppContext:
    """模块级获取器：供 WebSocket 等无法走依赖注入的路径使用。"""
    if _app_context is None:
        raise RuntimeError("AppContext not initialized")
    return _app_context


def get_sub_app_model() -> Any:
    """子应用（塔罗/紫微/六爻/合婚）解读用模型。

    优先取 `SUB_APP_MODEL` 配出来的独立实例，未配置时回落主问答模型（＝旧行为）。
    子应用一律**按请求调用本函数**而不是在装配期注入：模型实例可能被启动探活纠正后
    整体替换（见 `app/core/llm_health.py`），提前抓住引用会让纠正对子应用失效。

    用 getattr 取字段而不是直接属性访问：测试里存在只塞了 `chat_model` 的 AppContext 替身。
    """
    ctx = get_app_context()
    return getattr(ctx, "sub_app_model", None) or ctx.chat_model
