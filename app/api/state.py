"""共享运行时状态。

Xianzhi 智能体按会话池化：
- 每个 conversation_id 对应一个独立的 Xianzhi 实例 + 独立 asyncio.Lock；
- 同一会话内请求串行（保证命盘上下文、消息列表一致性），
  不同会话并行处理，不再被全局锁串行化；
- 池容量有限（LRU 淘汰最久未用实例），对话历史与出生信息均可从
  持久化记忆（PG/文件）恢复，淘汰无数据损失。

RagChatChain / TarotApp 本身不持有会话级可变状态
（历史均从记忆存储按会话读取），保持单例即可。
"""
from __future__ import annotations

import threading
from collections import OrderedDict

from app.logger import log

_rag_chain = None
_tarot_app = None
_chat_model = None
_local_tools = None
_memory = None

# 会话 Agent 池容量上限（超出后 LRU 淘汰最久未使用实例）
_MAX_AGENTS = 100
# conversation_id -> (agent, lock)
_agents: "OrderedDict[str, tuple]" = OrderedDict()
_pool_lock = threading.Lock()


def set_instances(chat_model, local_tools, memory, rag_chain=None, tarot_app=None):
    """保存 Agent 工厂所需的共享依赖（启动时调用一次）。"""
    global _chat_model, _local_tools, _memory, _rag_chain, _tarot_app
    _chat_model = chat_model
    _local_tools = local_tools
    _memory = memory
    _rag_chain = rag_chain
    _tarot_app = tarot_app


def get_chat_model():
    """获取共享 LLM 实例（报告生成、合婚解读等无会话场景使用）。"""
    return _chat_model


def get_xianzhi(conversation_id: str):
    """获取（或创建）指定会话的 Xianzhi 实例及其专用锁。

    Returns:
        (agent, asyncio.Lock) 元组。调用方应在锁内完成
        sect 设置、命盘挂载、流式执行这一组操作，避免并发污染。
    """
    cid = conversation_id if conversation_id and conversation_id.strip() else "xianzhi-default"
    with _pool_lock:
        hit = _agents.get(cid)
        if hit is not None:
            _agents.move_to_end(cid)
            return hit
        if _chat_model is None:
            raise RuntimeError("Xianzhi not initialized")
        from app.agent.xianzhi import Xianzhi
        agent = Xianzhi(
            chat_model=_chat_model,
            local_tools=_local_tools,
            memory=_memory,
            conversation_id=cid,
        )
        entry = (agent, agent.lock)
        _agents[cid] = entry
        while len(_agents) > _MAX_AGENTS:
            evicted_cid, _ = _agents.popitem(last=False)
            log.info("会话 Agent 池 LRU 淘汰: {} (pool_size={})", evicted_cid, len(_agents))
        log.info("会话 Agent 创建: {} (pool_size={})", cid, len(_agents))
        return entry


def agent_pool_stats() -> dict:
    """会话池状态（监控/调试接口用）。"""
    with _pool_lock:
        return {"pool_size": len(_agents), "max_agents": _MAX_AGENTS}


_backend_cache: str | None = None


def workflow_backend() -> str:
    """返回当前编排后端（langgraph/builtin），供健康检查暴露启用状态。

    优先读池中已有 Agent 的 workflow 实例；池为空时创建临时 workflow 探测一次
    （进程级缓存，避免重复建图与重复告警日志）。
    """
    global _backend_cache
    with _pool_lock:
        for agent, _ in _agents.values():
            wf = getattr(agent, "_workflow", None)
            if wf is not None:
                return wf.backend
    if _backend_cache is None:
        from app.agent.xianzhi_workflow import XianzhiWorkflow
        _backend_cache = XianzhiWorkflow(chat_model=None).backend
    return _backend_cache
