"""LangSmith 可观测性配置（对应笔记 01_基础调用/大模型接入LangSmith实战）。

通过环境变量开启 LangChain V2 追踪，自动记录：
- LLM 调用（输入/输出/耗时/Token）
- 工具调用
- RAG 检索
- Agent 执行轨迹

访问 https://smith.langchain.com/ 查看追踪数据。

此外维护一份进程内 API 指标统计，供 /metrics 接口展示。
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from typing import Any

from app.config import settings
from app.logger import log

# 进程内 API 指标存储
_metrics_lock = threading.Lock()
_metrics: dict[str, Any] = {
    "endpoints": defaultdict(lambda: {"count": 0, "total_latency_ms": 0.0}),
    "status_codes": {"2xx": 0, "4xx": 0, "5xx": 0},
    "recent_errors": [],
    "started_at": time.time(),
}


def record_request(method: str, path: str, status: int, duration: float) -> None:
    """记录一次 API 请求指标。

    Args:
        method: HTTP 方法，如 GET / POST。
        path: 请求路径。
        status: HTTP 状态码。
        duration: 请求耗时（秒）。
    """
    key = f"{method} {path}"
    latency_ms = duration * 1000
    with _metrics_lock:
        ep = _metrics["endpoints"][key]
        ep["count"] += 1
        ep["total_latency_ms"] += latency_ms

        if 200 <= status < 300:
            _metrics["status_codes"]["2xx"] += 1
        elif 400 <= status < 500:
            _metrics["status_codes"]["4xx"] += 1
        elif 500 <= status < 600:
            _metrics["status_codes"]["5xx"] += 1

        if status >= 400:
            error_record = {
                "timestamp": time.time(),
                "method": method,
                "path": path,
                "status": status,
                "latency_ms": round(latency_ms, 2),
            }
            _metrics["recent_errors"].append(error_record)
            if len(_metrics["recent_errors"]) > 50:
                _metrics["recent_errors"].pop(0)


def get_metrics() -> dict[str, Any]:
    """获取当前 API 指标快照。"""
    with _metrics_lock:
        endpoints = []
        total_requests = 0
        total_latency_ms = 0.0
        for key, data in _metrics["endpoints"].items():
            method, path = key.split(" ", 1)
            count = data["count"]
            total_latency_ms += data["total_latency_ms"]
            total_requests += count
            avg_ms = round(data["total_latency_ms"] / count, 2) if count else 0.0
            endpoints.append({
                "method": method,
                "path": path,
                "count": count,
                "avg_latency_ms": avg_ms,
                "total_latency_ms": round(data["total_latency_ms"], 2),
            })

        # 按调用量降序
        endpoints.sort(key=lambda x: x["count"], reverse=True)

        avg_latency_ms = round(total_latency_ms / total_requests, 2) if total_requests else 0.0
        status = dict(_metrics["status_codes"])
        error_count = status["4xx"] + status["5xx"]
        error_rate = round(error_count / total_requests * 100, 2) if total_requests else 0.0

        return {
            "total_requests": total_requests,
            "avg_latency_ms": avg_latency_ms,
            "error_rate": error_rate,
            "status_codes": status,
            "endpoints": endpoints,
            "top_endpoints": endpoints[:5],
            "recent_errors": list(_metrics["recent_errors"]),
            "uptime_seconds": round(time.time() - _metrics["started_at"], 2),
        }


def reset_metrics() -> None:
    """重置所有 API 指标。"""
    with _metrics_lock:
        _metrics["endpoints"] = defaultdict(lambda: {"count": 0, "total_latency_ms": 0.0})
        _metrics["status_codes"] = {"2xx": 0, "4xx": 0, "5xx": 0}
        _metrics["recent_errors"] = []
        _metrics["started_at"] = time.time()


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