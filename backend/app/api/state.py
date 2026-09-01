"""共享运行时状态（兼容层）。

真正状态持有者为 app.api.context.AppContext（lifespan 内构造，
经 app.state.app_context 暴露）；本模块仅保留旧函数签名做兼容转发，
新代码请直接使用 app.api.context（AppContext / get_app_context）。
"""
from __future__ import annotations

from app.api.context import AppContext, get_app_context, set_app_context
from app.core.logger import log


def set_instances(chat_model, local_tools, memory, tarot_app=None, decompose_model=None, reviewer_model=None):
    """兼容入口：构造并注册 AppContext（等价于 lifespan 内显式构造）。"""
    ctx = AppContext(
        chat_model=chat_model,
        local_tools=local_tools,
        memory=memory,
        tarot_app=tarot_app,
        decompose_model=decompose_model,
        reviewer_model=reviewer_model,
    )
    set_app_context(ctx)
    log.info("AppContext 已注册（经 state.set_instances 兼容入口）")
    return ctx


def get_chat_model():
    """获取共享 LLM 实例（报告生成、合婚解读等无会话场景使用）。"""
    try:
        return get_app_context().chat_model
    except RuntimeError:
        return None


def get_xianzhi(conversation_id: str):
    """获取（或创建）指定会话的 Xianzhi 实例及其专用锁（转发 AppContext）。"""
    return get_app_context().get_xianzhi(conversation_id)


def agent_pool_stats() -> dict:
    """会话池状态（监控/调试接口用）。"""
    try:
        return get_app_context().agent_pool_stats()
    except RuntimeError:
        return {"pool_size": 0, "max_agents": 0}


def workflow_backend() -> str:
    """返回当前编排后端（LangGraph）。"""
    return AppContext.workflow_backend()
