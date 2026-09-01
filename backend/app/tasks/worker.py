"""报告任务 worker：从 Redis 队列消费任务，在线程池执行并回写状态。

- BRPOP 原子取号，多副本部署时任务天然只被一个副本消费
- 同步生成逻辑经 asyncio.to_thread 执行（不阻塞事件循环）
- LLM 并发仍受 ThrottledModel 全局信号量约束（报告与聊天共享 DashScope 配额）
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.logger import log
from app.core.redis_client import get_redis
from app.db import report_tasks
from app.tools.report_tasks import run_task

_QUEUE_KEY = "xianzhi:report:queue"
_POLL_INTERVAL = 0.5


async def enqueue(task_id: str) -> None:
    """入队；Redis 不可用时拒绝提交（不产生永远 pending 的孤儿任务）。"""
    r = await get_redis()
    if r is None:
        raise RuntimeError("任务队列不可用，请稍后再试")
    await r.lpush(_QUEUE_KEY, task_id)


async def worker_loop(chat_model: Any, stop_event: asyncio.Event) -> None:
    """单 worker 循环：RPOP 非阻塞轮询（阻塞式 BRPOP 会与 Redis 连接读超时冲突），
    收到 stop 信号后当轮退出。"""
    log.info("报告任务 worker 启动")
    while not stop_event.is_set():
        r = await get_redis()
        if r is None:
            # Redis 暂不可用：退避等待，避免空转刷日志
            await asyncio.sleep(5)
            continue
        try:
            task_id = await r.rpop(_QUEUE_KEY)
        except Exception as e:
            log.warning("[report-worker] 队列读取异常，退避重试: {}", e)
            await asyncio.sleep(5)
            continue
        if not task_id:
            await asyncio.sleep(_POLL_INTERVAL)
            continue
        try:
            await _process(chat_model, task_id)
        except Exception as e:
            # _process 内部已尽力回写失败状态；此处兜底防单个任务打崩循环
            log.exception("[report-worker] 处理异常 task={}", task_id)
            try:
                await asyncio.to_thread(report_tasks.fail, task_id, str(e))
            except Exception:
                pass
    log.info("报告任务 worker 退出")


async def _process(chat_model: Any, task_id: str) -> None:
    row = await asyncio.to_thread(report_tasks.get_task, task_id)
    if row is None or row["status"] != "pending":
        return
    # 抢占 running；重复消费时放弃（幂等保护）
    claimed = await asyncio.to_thread(report_tasks.mark_running, task_id)
    if not claimed:
        return
    log.info("[report-worker] 开始执行 task={} kind={}", task_id, row["kind"])
    try:
        payload = await asyncio.to_thread(run_task, chat_model, row["kind"], row["params"])
        await asyncio.to_thread(report_tasks.complete, task_id, payload)
        log.info("[report-worker] 执行完成 task={} size={}B", task_id, len(payload))
    except Exception as e:
        log.exception("[report-worker] 执行失败 task={}", task_id)
        await asyncio.to_thread(report_tasks.fail, task_id, str(e))