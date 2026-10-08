"""报告任务 worker：从 Redis 队列消费任务，在线程池执行并回写状态。

- BRPOP 原子取号，多副本部署时任务天然只被一个副本消费
- 同步生成逻辑经 asyncio.to_thread 执行（不阻塞事件循环）
- LLM 并发仍受 ThrottledModel 全局信号量约束（报告与聊天共享 DashScope 配额）
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.agent.context import get_sub_app_model
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


async def worker_loop(chat_model: Any | None, stop_event: asyncio.Event) -> None:
    """单 worker 循环：RPOP 非阻塞轮询（阻塞式 BRPOP 会与 Redis 连接读超时冲突），
    收到 stop 信号后当轮退出。

    `chat_model` 传 **None ＝ 按任务解析「子应用解读模型」**（生产路径）：命理报告属于
    子应用解读，与问答主模型分开配（`SUB_APP_MODEL`，未配置则回落主模型）。
    显式传入实例只用于测试/特殊装配。
    """
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


async def _process(chat_model: Any | None, task_id: str) -> None:
    row = await asyncio.to_thread(report_tasks.get_task, task_id)
    if row is None or row["status"] != "pending":
        return
    # 抢占 running；重复消费时放弃（幂等保护）
    claimed = await asyncio.to_thread(report_tasks.mark_running, task_id)
    if not claimed:
        return
    log.info("[report-worker] 开始执行 task={} kind={}", task_id, row["kind"])
    try:
        payload = await asyncio.to_thread(
            run_task, resolve_report_model(chat_model), row["kind"], row["params"]
        )
        await asyncio.to_thread(report_tasks.complete, task_id, payload)
        log.info("[report-worker] 执行完成 task={} size={}B", task_id, len(payload))
    except Exception as e:
        log.exception("[report-worker] 执行失败 task={}", task_id)
        await asyncio.to_thread(report_tasks.fail, task_id, str(e))


def resolve_report_model(chat_model: Any | None = None) -> Any:
    """报告任务用哪个模型：显式传入优先（测试/特殊装配），否则按需取子应用解读模型。

    为什么不把实例抓在循环外：模型实例可能被启动探活整体替换（`core/llm_health.py`），
    抓死引用会让纠正失效 —— 与 `app/sub_app` 侧同一条规矩（按需解析，不装配期注入）。
    """
    return chat_model if chat_model is not None else get_sub_app_model()
