"""轻量并发压测：health / chart / chat / report-submit。

示例（后端需先指向 mock LLM 并关闭限流）：
    python scripts/load_test.py --scenario chat --n 200 --c 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid

import httpx

BIRTH_TIME = "1990-05-20 14:30"
GENDER = "男"


def _conversation_id() -> str:
    return "load-xianzhi-" + uuid.uuid4().hex


def _msg_id() -> str:
    return uuid.uuid4().hex[:16]


async def _request(client: httpx.AsyncClient, scenario: str, base: str, token: str, conv: str) -> tuple[int, float]:
    start = time.perf_counter()
    if scenario == "health":
        resp = await client.get(f"{base}/health/live")
        await resp.aread()
        return resp.status_code, time.perf_counter() - start

    if scenario == "chart":
        resp = await client.get(
            f"{base}/ai/xianzhi/chart",
            params={"birth_time": BIRTH_TIME, "gender": GENDER},
        )
        await resp.aread()
        return resp.status_code, time.perf_counter() - start

    if scenario == "chat":
        params = {
            "message": "我今年事业怎么样？",
            "conversation_id": conv,
            "client_msg_id": _msg_id(),
            "birth_time": BIRTH_TIME,
            "gender": GENDER,
        }
        if token:
            params["token"] = token
        async with client.stream("GET", f"{base}/ai/xianzhi/chat", params=params) as resp:
            if resp.status_code == 200:
                async for line in resp.aiter_lines():
                    if line.strip() == "data: [DONE]":
                        break
            else:
                await resp.aread()
            return resp.status_code, time.perf_counter() - start

    if scenario == "report-submit":
        if not token:
            raise RuntimeError("report-submit 需要 --token")
        resp = await client.post(
            f"{base}/ai/xianzhi/report/tasks",
            params={"token": token},
            json={"kind": "basic_report", "birth_time": BIRTH_TIME, "gender": GENDER},
        )
        await resp.aread()
        return resp.status_code, time.perf_counter() - start

    raise ValueError(f"未知场景: {scenario}")


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, int(round((len(values) - 1) * p)))
    return round(values[idx] * 1000, 2)


async def run(args) -> dict:
    semaphore = asyncio.Semaphore(args.c)
    shared_conv = _conversation_id()
    statuses: dict[int, int] = {}
    latencies: list[float] = []
    errors: list[str] = []

    timeout = httpx.Timeout(args.timeout, connect=10.0)
    limits = httpx.Limits(max_connections=args.c + 10, max_keepalive_connections=args.c)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, trust_env=False) as client:

        async def worker(i: int) -> None:
            async with semaphore:
                conv = shared_conv if args.same_conversation else _conversation_id()
                try:
                    status, elapsed = await _request(client, args.scenario, args.base_url, args.token, conv)
                    statuses[status] = statuses.get(status, 0) + 1
                    if 200 <= status < 300:
                        latencies.append(elapsed)
                    else:
                        errors.append(f"HTTP {status}")
                except Exception as e:  # noqa: BLE001 - 压测脚本记录所有失败
                    errors.append(f"{type(e).__name__}: {str(e)[:120]}")

        start = time.perf_counter()
        await asyncio.gather(*(worker(i) for i in range(args.n)))
        wall = time.perf_counter() - start

    successes = len(latencies)
    return {
        "scenario": args.scenario,
        "requests": args.n,
        "concurrency": args.c,
        "wall_seconds": round(wall, 2),
        "rps": round(args.n / wall, 2) if wall else 0.0,
        "success": successes,
        "failed": len(errors),
        "status_codes": statuses,
        "latency_ms": {
            "avg": round(statistics.mean(latencies) * 1000, 2) if latencies else 0.0,
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
            "max": round(max(latencies) * 1000, 2) if latencies else 0.0,
        },
        "errors_sample": errors[:10],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="轻量并发压测")
    parser.add_argument("--base-url", default="http://127.0.0.1:8123/api")
    parser.add_argument("--scenario", choices=("health", "chart", "chat", "report-submit"), default="health")
    parser.add_argument("--n", type=int, default=100, help="总请求数")
    parser.add_argument("--c", type=int, default=10, help="并发数")
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--token", default="", help="登录用户 token（report-submit 必填；chat 可选）")
    parser.add_argument("--same-conversation", action="store_true", help="chat 走同一会话（测会话串行）")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
