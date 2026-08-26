"""抽象基础代理类（对应 Java BaseAgent）。"""
from __future__ import annotations

import asyncio
import queue
import threading
from abc import ABC, abstractmethod
from enum import Enum

from langchain_core.messages import HumanMessage

from app.core.logger import log


class AgentState(str, Enum):
    """Agent 生命周期状态：IDLE / RUNNING / FINISHED / ERROR。"""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


# 指令隔离：用户输入用分隔符包裹，配合 System Prompt 中的隔离规则防止注入
_USER_INPUT_PREFIX = "\n--- USER INPUT BEGIN ---\n"
_USER_INPUT_SUFFIX = "\n--- USER INPUT END ---\n"


def _wrap_user_input(user_prompt: str) -> str:
    return f"{_USER_INPUT_PREFIX}{user_prompt}{_USER_INPUT_SUFFIX}"


class BaseAgent(ABC):
    """抽象基础代理（对应 Java BaseAgent）：run / run_stream / arun_stream 共用同一执行循环。"""
    def __init__(self, name, chat_model, system_prompt="", next_step_prompt="", max_steps=5):
        self.name = name
        self.chat_model = chat_model
        self.system_prompt = system_prompt
        self.next_step_prompt = next_step_prompt
        self.max_steps = max_steps
        self.state = AgentState.IDLE
        self.current_step = 0
        self.message_list = []
        self._last_error = None
        # 取消标志：客户端断开（如 WS 关闭）时置位，执行循环每步之间检查并提前终止，避免白烧 token
        self._cancel_event = threading.Event()

    def request_cancel(self):
        self._cancel_event.set()

    def _cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def _should_stop(self) -> bool:
        return self.state in (AgentState.FINISHED, AgentState.ERROR) or self._cancel_requested()

    def _run_steps(self, user_prompt):
        """执行 ReAct 步骤循环，产出 (status, text) 事件：result / cancelled / max_steps / error。

        三个执行入口共用，避免三份重复实现；finally 统一清理。
        """
        self._validate(user_prompt)
        self.state = AgentState.RUNNING
        self._cancel_event.clear()
        self.message_list.append(HumanMessage(content=_wrap_user_input(user_prompt)))
        try:
            for i in range(self.max_steps):
                if self._should_stop():
                    break
                self.current_step = i + 1
                log.info("Executing step {}/{}", self.current_step, self.max_steps)
                yield "result", self.step()
            if self._cancel_requested():
                log.info("执行终止: 客户端已取消")
                yield "cancelled", "Terminated: Cancelled by client"
            elif self.current_step >= self.max_steps and self.state not in (AgentState.FINISHED, AgentState.ERROR):
                self.state = AgentState.FINISHED
                log.info("执行结束: 达到最大步骤({})".format(self.max_steps))
                yield "max_steps", "Terminated: Reached max steps ({})".format(self.max_steps)
        except Exception as e:
            self.state = AgentState.ERROR
            log.exception("error executing agent")
            yield "error", str(e)
        finally:
            self.cleanup()

    def run(self, user_prompt):
        """同步执行 Agent：在 max_steps 内循环 step() 收集结果。"""
        results = []
        for status, text in self._run_steps(user_prompt):
            if status == "result":
                results.append("Step {}: {}".format(self.current_step, text))
            elif status == "error":
                return "执行错误: {}".format(text)
            else:
                results.append(text)
        return "\n".join(results)

    def run_stream(self, user_prompt):
        """同步流式执行：后台线程跑执行循环，通过队列逐条产出步骤结果。"""
        q = queue.Queue()
        _SENTINEL = object()

        def _worker():
            try:
                for status, text in self._run_steps(user_prompt):
                    if status == "result":
                        log.info("Step {}: {}", self.current_step, text)
                        q.put(text)
                    elif status == "error":
                        log.info("执行错误: {}", text)
                        q.put("__ERROR__:" + text)
                    elif status == "max_steps":
                        q.put("__MAX_STEPS__")
            except Exception as e:
                # _validate 失败等异常
                q.put("错误: {}".format(e))
            finally:
                q.put(_SENTINEL)

        threading.Thread(target=_worker, daemon=True).start()

        def generator():
            while True:
                item = q.get()
                if item is _SENTINEL:
                    break
                # 内部状态标记不外发
                if item == "__MAX_STEPS__" or (isinstance(item, str) and item.startswith("__ERROR__:")):
                    continue
                yield item
        return generator()

    async def arun_stream(self, user_prompt):
        """异步流式执行：线程池跑执行循环，不阻塞事件循环。"""
        q = asyncio.Queue()
        _SENTINEL = object()
        loop = asyncio.get_event_loop()

        def _worker():
            try:
                for status, text in self._run_steps(user_prompt):
                    if status == "result":
                        log.info("Step {}: {}", self.current_step, text)
                        loop.call_soon_threadsafe(q.put_nowait, text)
                    elif status == "error":
                        log.info("执行错误: {}", text)
                        loop.call_soon_threadsafe(q.put_nowait, "__ERROR__:" + text)
                    elif status == "max_steps":
                        loop.call_soon_threadsafe(q.put_nowait, "__MAX_STEPS__")
            except Exception as e:
                loop.call_soon_threadsafe(q.put_nowait, "错误: {}".format(e))
            finally:
                loop.call_soon_threadsafe(q.put_nowait, _SENTINEL)

        loop.run_in_executor(None, _worker)
        while True:
            item = await q.get()
            if item is _SENTINEL:
                break
            if item == "__MAX_STEPS__" or (isinstance(item, str) and item.startswith("__ERROR__:")):
                continue
            yield item

    @abstractmethod
    def step(self):
        """执行一轮 Agent 逻辑（思考 / 工具调用 / 产出），由子类实现。"""
        raise NotImplementedError

    def cleanup(self):
        self.current_step = 0
        self.message_list = []
        self.state = AgentState.IDLE

    def _validate(self, user_prompt):
        """运行前校验：必须处于 IDLE 且 user_prompt 非空，否则抛 RuntimeError。"""
        if self.state != AgentState.IDLE:
            raise RuntimeError("Cannot run agent from state: {}".format(self.state))
        if not user_prompt or not user_prompt.strip():
            raise RuntimeError("Cannot run agent with empty user prompt")
