"""LangSmith 可观测性配置（对应笔记 01_基础调用/大模型接入LangSmith实战）。

通过环境变量开启 LangChain V2 追踪，自动记录：
- LLM 调用（输入/输出/耗时/Token）
- 工具调用
- RAG 检索
- Agent 执行轨迹

访问 https://smith.langchain.com/ 查看追踪数据。
"""
from __future__ import annotations

import os

from app.config import settings
from app.logger import log


def init_observability() -> bool:
    """初始化 LangSmith 可观测性。返回是否启用。

    在应用启动最早阶段调用，确保后续所有 LangChain 调用都被追踪。
    """
    if not settings.langsmith_tracing:
        log.info("LangSmith 追踪未启用（LANGSMITH_TRACING=false）")
        return False

    if not settings.langsmith_api_key:
        log.warning("LANGSMITH_TRACING=true 但未配置 LANGSMITH_API_KEY，追踪未生效")
        return False

    # 设置 LangChain 追踪环境变量（对应笔记的 os.environ 配置）
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project

    log.info("LangSmith 追踪已启用 | 项目: {} | 查看: https://smith.langchain.com/",
             settings.langsmith_project)
    return True


def get_status() -> dict:
    """获取可观测性状态，供接口查询。"""
    return {
        "tracing_enabled": os.environ.get("LANGCHAIN_TRACING_V2") == "true",
        "project": settings.langsmith_project,
        "endpoint": os.environ.get("LANGCHAIN_ENDPOINT", ""),
        "dashboard": "https://smith.langchain.com/",
    }