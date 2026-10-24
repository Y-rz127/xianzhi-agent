"""LangSmith 可观测性：通过环境变量开启 LangChain V2 追踪，并维护进程内 API/LLM 指标供 /metrics 展示。"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any

from app.core.config import settings
from app.core.logger import log

# 进程内 API 指标存储
_metrics_lock = threading.Lock()
# 延迟直方图桶（秒），导出 Prometheus histogram 用
_LATENCY_BUCKETS = (0.1, 0.3, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0, 60.0)
_metrics: dict[str, Any] = {
    "endpoints": defaultdict(lambda: {"count": 0, "total_latency_ms": 0.0, "buckets": defaultdict(int)}),
    "status_codes": {"2xx": 0, "4xx": 0, "5xx": 0},
    "recent_errors": [],
    # DB/记忆层失败等被降级兜住的错误，供 /metrics 观测
    "internal_errors": defaultdict(int),
    # LLM 调用指标：key = "model|tag"
    "llm": defaultdict(lambda: {
        "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_latency_ms": 0.0,
    }),
    "started_at": time.time(),
}

# LLM 单价表：优先 PG app_config（Web 管理端热改），未配置时回退 env LLM_PRICE_MAP。
# 30s TTL 缓存，避免每个 /metrics 请求打一次 DB。
_price_cache: dict[str, tuple[float, float]] | None = None
_price_cache_at: float = 0.0
_price_lock = threading.Lock()
_PRICE_TTL_SECONDS = 30.0


def _load_price_map() -> dict[str, tuple[float, float]]:
    global _price_cache, _price_cache_at
    now = time.monotonic()
    with _price_lock:
        if _price_cache is not None and now - _price_cache_at < _PRICE_TTL_SECONDS:
            return _price_cache
        raw = None
        try:
            from app.core.config.kv import get_config

            stored = get_config("llm_price_map")
            if isinstance(stored, dict):
                raw = stored.get("prices") or {}
        except Exception:
            raw = None
        if raw is None:
            raw = _parse_env_price_map()
        parsed: dict[str, tuple[float, float]] = {}
        for model, p in (raw or {}).items():
            if not isinstance(p, dict):
                continue
            try:
                parsed[str(model)] = (float(p.get("input", 0)), float(p.get("output", 0)))
            except (TypeError, ValueError):
                continue
        _price_cache = parsed
        _price_cache_at = now
        return parsed


def _parse_env_price_map() -> dict:
    try:
        return json.loads(settings.llm_price_map) if settings.llm_price_map.strip() else {}
    except Exception:
        log.warning("LLM_PRICE_MAP 解析失败，成本折算禁用: {}", settings.llm_price_map)
        return {}


def invalidate_price_cache() -> None:
    """管理后台修改单价后立即生效。"""
    global _price_cache, _price_cache_at
    with _price_lock:
        _price_cache = None
        _price_cache_at = 0.0


def current_price_map() -> dict:
    """当前生效单价表 {模型名: {"input": 元/百万token, "output": 元/百万token}}。"""
    return {model: {"input": p[0], "output": p[1]} for model, p in _load_price_map().items()}


def _price_of(model: str) -> tuple[float, float]:
    """模型名前缀最长匹配价格；未配置返回 (0, 0)。"""
    price_map = _load_price_map()
    best = None
    for prefix, price in price_map.items():
        if model.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return price_map[best] if best else (0.0, 0.0)


def record_error(category: str) -> None:
    """记录一次内部错误（如记忆写入失败、DB 读取降级）。降级路径也必须调用，确保静默故障可观测。"""
    with _metrics_lock:
        _metrics["internal_errors"][category] += 1


def record_llm_call(model: str, tag: str, prompt_tokens: int, completion_tokens: int, elapsed_ms: float) -> None:
    """记录一次 LLM 调用（token 用量/耗时/用途）。由 ThrottledModel 在所有调用成功路径上报。"""
    with _metrics_lock:
        entry = _metrics["llm"][f"{model}|{tag}"]
        entry["calls"] += 1
        entry["prompt_tokens"] += prompt_tokens
        entry["completion_tokens"] += completion_tokens
        entry["total_latency_ms"] += elapsed_ms


def record_request(
    method: str, path: str, status: int, duration: float, request_id: str = ""
) -> None:
    """记录一次 API 请求指标（request_id 便于从用户报障定位日志）。"""
    key = f"{method} {path}"
    latency_ms = duration * 1000
    with _metrics_lock:
        ep = _metrics["endpoints"][key]
        ep["count"] += 1
        ep["total_latency_ms"] += latency_ms
        # 每桶记"落在该桶"的原始次数，导出时再累加成 Prometheus 的累计桶
        for i, bound in enumerate(_LATENCY_BUCKETS):
            if duration <= bound:
                ep["buckets"][i] += 1
                break
        else:
            ep["buckets"][len(_LATENCY_BUCKETS)] += 1

        if 200 <= status < 300:
            _metrics["status_codes"]["2xx"] += 1
        elif 400 <= status < 500:
            _metrics["status_codes"]["4xx"] += 1
        elif 500 <= status < 600:
            _metrics["status_codes"]["5xx"] += 1

        if status >= 400:
            _metrics["recent_errors"].append({
                "timestamp": time.time(),
                "request_id": request_id,
                "method": method,
                "path": path,
                "status": status,
                "latency_ms": round(latency_ms, 2),
            })
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

        # LLM 成本汇总：按 model+用途 分组，带可选金额折算
        llm_entries = []
        llm_totals = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "est_cost": 0.0}
        for key, data in _metrics["llm"].items():
            model, tag = key.split("|", 1)
            in_price, out_price = _price_of(model)
            cost = data["prompt_tokens"] / 1e6 * in_price + data["completion_tokens"] / 1e6 * out_price
            avg_ms = round(data["total_latency_ms"] / data["calls"], 1) if data["calls"] else 0.0
            llm_entries.append({
                "model": model,
                "tag": tag,
                "calls": data["calls"],
                "prompt_tokens": data["prompt_tokens"],
                "completion_tokens": data["completion_tokens"],
                "avg_latency_ms": avg_ms,
                "est_cost": round(cost, 4),
            })
            llm_totals["calls"] += data["calls"]
            llm_totals["prompt_tokens"] += data["prompt_tokens"]
            llm_totals["completion_tokens"] += data["completion_tokens"]
            llm_totals["est_cost"] = round(llm_totals["est_cost"] + cost, 4)
        llm_entries.sort(key=lambda x: x["calls"], reverse=True)
        llm_totals["price_configured"] = bool(_load_price_map())

        avg_latency_ms = round(total_latency_ms / total_requests, 2) if total_requests else 0.0
        status = dict(_metrics["status_codes"])
        error_rate = round((status["4xx"] + status["5xx"]) / total_requests * 100, 2) if total_requests else 0.0

        return {
            "total_requests": total_requests,
            "avg_latency_ms": avg_latency_ms,
            "error_rate": error_rate,
            "status_codes": status,
            "endpoints": endpoints,
            "top_endpoints": endpoints[:5],
            "recent_errors": list(_metrics["recent_errors"]),
            "internal_errors": dict(_metrics["internal_errors"]),
            "llm": llm_entries,
            "llm_totals": llm_totals,
            "uptime_seconds": round(time.time() - _metrics["started_at"], 2),
        }


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def prometheus_text() -> str:
    """按 Prometheus 文本格式导出本副本指标。

    进程内聚合无法跨副本汇总，故每副本各暴露一份带 instance 标签的序列，
    由 Prometheus 抓取后统一聚合/告警（见 deploy/prometheus/alerts.yml）。
    """
    lines = [
        "# HELP xianzhi_app_info 实例版本（灰度时用于区分新旧版本）",
        "# TYPE xianzhi_app_info gauge",
        f'xianzhi_app_info{{version="{_escape_label(settings.app_version)}"}} 1',
        "# HELP xianzhi_process_start_time_seconds 进程启动时间（Unix 秒）",
        "# TYPE xianzhi_process_start_time_seconds gauge",
        f"xianzhi_process_start_time_seconds {_metrics['started_at']:.3f}",
    ]
    with _metrics_lock:
        endpoints = [(k, dict(v["buckets"]), v["count"], v["total_latency_ms"]) for k, v in _metrics["endpoints"].items()]
        status_codes = dict(_metrics["status_codes"])
        internal_errors = dict(_metrics["internal_errors"])
        llm_entries = list(_metrics["llm"].items())

    lines += [
        "# HELP xianzhi_http_requests_total HTTP 请求数（按路由模板计数）",
        "# TYPE xianzhi_http_requests_total counter",
    ]
    for key, _buckets, count, _total_ms in endpoints:
        method, path = key.split(" ", 1)
        lines.append(
            f'xianzhi_http_requests_total{{method="{_escape_label(method)}",'
            f'path="{_escape_label(path)}"}} {count}'
        )

    lines += [
        "# HELP xianzhi_http_request_duration_seconds HTTP 请求耗时",
        "# TYPE xianzhi_http_request_duration_seconds histogram",
    ]
    for key, buckets, count, total_ms in endpoints:
        method, path = key.split(" ", 1)
        labels = f'method="{_escape_label(method)}",path="{_escape_label(path)}"'
        cumulative = 0
        for i, bound in enumerate(_LATENCY_BUCKETS):
            cumulative += buckets.get(i, 0)
            lines.append(
                f"xianzhi_http_request_duration_seconds_bucket{{{labels},le=\"{bound}\"}} {cumulative}"
            )
        lines.append(
            f'xianzhi_http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {count}'
        )
        lines.append(f"xianzhi_http_request_duration_seconds_sum{{{labels}}} {total_ms / 1000:.3f}")
        lines.append(f"xianzhi_http_request_duration_seconds_count{{{labels}}} {count}")

    lines += [
        "# HELP xianzhi_http_responses_total HTTP 响应按状态段计数",
        "# TYPE xianzhi_http_responses_total counter",
    ]
    for bucket, count in sorted(status_codes.items()):
        lines.append(f'xianzhi_http_responses_total{{status="{bucket}"}} {count}')

    lines += [
        "# HELP xianzhi_internal_errors_total 被降级兜住的内部错误",
        "# TYPE xianzhi_internal_errors_total counter",
    ]
    for category, count in sorted(internal_errors.items()):
        lines.append(f'xianzhi_internal_errors_total{{category="{_escape_label(category)}"}} {count}')

    lines += [
        "# HELP xianzhi_llm_calls_total LLM 调用次数",
        "# TYPE xianzhi_llm_calls_total counter",
    ]
    for key, data in llm_entries:
        model, tag = key.split("|", 1)
        lines.append(
            f'xianzhi_llm_calls_total{{model="{_escape_label(model)}",'
            f'tag="{_escape_label(tag)}"}} {data["calls"]}'
        )

    lines += [
        "# HELP xianzhi_llm_tokens_total LLM token 用量",
        "# TYPE xianzhi_llm_tokens_total counter",
    ]
    for key, data in llm_entries:
        model, tag = key.split("|", 1)
        labels = f'model="{_escape_label(model)}",tag="{_escape_label(tag)}"'
        lines.append(f'xianzhi_llm_tokens_total{{{labels},kind="prompt"}} {data["prompt_tokens"]}')
        lines.append(f'xianzhi_llm_tokens_total{{{labels},kind="completion"}} {data["completion_tokens"]}')

    lines += [
        "# HELP xianzhi_llm_estimated_cost_yuan_total LLM 估算成本（元，未配单价时为 0）",
        "# TYPE xianzhi_llm_estimated_cost_yuan_total counter",
    ]
    for key, data in llm_entries:
        model, tag = key.split("|", 1)
        in_price, out_price = _price_of(model)
        cost = data["prompt_tokens"] / 1e6 * in_price + data["completion_tokens"] / 1e6 * out_price
        lines.append(
            f'xianzhi_llm_estimated_cost_yuan_total{{model="{_escape_label(model)}",'
            f'tag="{_escape_label(tag)}"}} {cost:.6f}'
        )
    return "\n".join(lines) + "\n"


def init_observability() -> bool:
    """初始化 LangSmith 追踪。须在应用启动最早阶段调用，确保后续所有 LangChain 调用都被追踪。"""
    # 生产强制关闭：trace 会携带用户生辰与问答原文，发往境外 LangSmith
    if settings.langsmith_tracing and settings.app_env.strip().lower() in ("prod", "production"):
        record_error("langsmith_disabled_in_production")
        log.warning(
            "APP_ENV={} 强制禁用 LangSmith 追踪（trace 含生辰/问答原文）",
            settings.app_env,
        )
        return False
    if not settings.langsmith_tracing:
        log.info("LangSmith 追踪未启用（LANGSMITH_TRACING=false）")
        return False
    if not settings.langsmith_api_key:
        log.warning("LANGSMITH_TRACING=true 但未配置 LANGSMITH_API_KEY，追踪未生效")
        return False

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project

    if not _validate_api_key(settings.langsmith_api_key):
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        log.warning("LangSmith API Key 无效（403），已自动关闭追踪，不影响功能")
        return False

    log.info("LangSmith 追踪已启用 | 项目: {} | 查看: https://smith.langchain.com/",
             settings.langsmith_project)
    return True


def _validate_api_key(api_key: str) -> bool:
    """快速校验 LangSmith API Key 是否有效，避免启动后持续刷 403。

    失败关闭：无法确认有效（401/403 或网络异常）一律视为无效并关闭追踪。
    """
    try:
        req = urllib.request.Request(
            "https://api.smith.langchain.com/info",
            headers={"x-api-key": api_key},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False
        log.warning("LangSmith Key 校验返回非预期状态 {}，按无效处理", e.code)
        return False
    except Exception as e:
        log.warning("LangSmith Key 校验失败（{}），按无效处理，关闭追踪", e)
        return False


def get_status() -> dict:
    """获取可观测性状态，供接口查询。"""
    return {
        "tracing_enabled": os.environ.get("LANGCHAIN_TRACING_V2") == "true",
        "project": settings.langsmith_project,
        "endpoint": os.environ.get("LANGCHAIN_ENDPOINT", ""),
        "dashboard": "https://smith.langchain.com/",
    }
