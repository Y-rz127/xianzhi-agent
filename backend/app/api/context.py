"""应用上下文（AppContext）：共享运行时依赖的单一持有者。

R5 解耦全局 state：原 app/api/state.py 的模块级可变单例收敛为
lifespan 内构造的 AppContext 实例，HTTP handler 经 FastAPI 依赖注入获取；
WebSocket 等无法使用 Depends 的场景经模块级 get_app_context() 获取同一实例。

Xianzhi 智能体按会话池化（池为 AppContext 实例态）：
- 每个 conversation_id 对应一个独立的 Xianzhi 实例 + 独立 asyncio.Lock；
- 同一会话内请求串行（保证命盘上下文、消息列表一致性），
  不同会话并行处理，不再被全局锁串行化；
- 池容量有限（LRU 淘汰最久未用实例），对话历史与出生信息均可从
  持久化记忆（PG/文件）恢复，淘汰无数据损失。

TarotApp 本身不持有会话级可变状态
（历史均从记忆存储按会话读取），保持单例即可。
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request

from app.core.logger import log

# 会话 Agent 池容量上限（超出后 LRU 淘汰最久未使用实例）
_MAX_AGENTS = 100


@dataclass
class AppContext:
    """lifespan 内构造一次的共享依赖容器（替代原模块级全局单例）。"""

    chat_model: Any
    local_tools: Any
    memory: Any
    tarot_app: Any = None
    decompose_model: Any = None
    reviewer_model: Any = None
    # conversation_id -> (agent, lock)
    _agents: "OrderedDict[str, tuple]" = field(default_factory=OrderedDict, repr=False)
    _pool_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        # 留空则复用主模型（与原 set_instances 语义一致）
        if self.decompose_model is None:
            self.decompose_model = self.chat_model
        if self.reviewer_model is None:
            self.reviewer_model = self.chat_model

    def get_xianzhi(self, conversation_id: str):
        """获取（或创建）指定会话的 Xianzhi 实例及其专用锁（调用方在锁内完成会话操作，避免并发污染）。"""
        cid = conversation_id if conversation_id and conversation_id.strip() else "xianzhi-default"
        with self._pool_lock:
            hit = self._agents.get(cid)
            if hit is not None:
                self._agents.move_to_end(cid)
                return hit
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
            entry = (agent, agent.lock)
            self._agents[cid] = entry
            while len(self._agents) > _MAX_AGENTS:
                evicted_cid, _ = self._agents.popitem(last=False)
                log.info("会话 Agent 池 LRU 淘汰: {} (pool_size={})", evicted_cid, len(self._agents))
            log.info("会话 Agent 创建: {} (pool_size={})", cid, len(self._agents))
            return entry

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


async def app_context_dependency(request: Request) -> AppContext:
    """FastAPI 依赖：HTTP handler 经此注入 AppContext。

    未初始化返回 503（服务尚未就绪），而非 500。
    """
    ctx = getattr(request.app.state, "app_context", None)
    if ctx is None:
        raise HTTPException(status_code=503, detail="服务尚未就绪")
    return ctx
