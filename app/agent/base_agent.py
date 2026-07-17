"""抽象基础代理类（对应 Java BaseAgent）。"""
from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.language_models import BaseChatModel
from app.logger import log


class AgentState(str, Enum):
    """Agent 生命周期状态枚举：IDLE / RUNNING / FINISHED / ERROR。"""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


class BaseAgent(ABC):
    """抽象基础代理（对应 Java BaseAgent）。

    定义统一的执行循环（run / run_stream / arun_stream），子类需实现 step()；
    提供状态校验（_validate）与运行态清理（cleanup）。
    """
    def __init__(self, name, chat_model, system_prompt="", next_step_prompt="", max_steps=5):
        """初始化代理基础属性（名称、模型、提示词、最大步数、运行状态）。"""
        self.name = name
        self.chat_model = chat_model
        self.system_prompt = system_prompt
        self.next_step_prompt = next_step_prompt
        self.max_steps = max_steps
        self.state = AgentState.IDLE
        self.current_step = 0
        self.message_list = []
        self._last_error = None

    def run(self, user_prompt):
        """同步执行 Agent：在 max_steps 内循环 step() 收集结果，异常转 ERROR，finally 清理。"""
        self._validate(user_prompt)
        self.state = AgentState.RUNNING
        self.message_list.append(HumanMessage(content=user_prompt))
        results = []
        try:
            for i in range(self.max_steps):
                if self.state == AgentState.FINISHED:
                    break
                self.current_step = i + 1
                log.info("Executing step {}/{}", self.current_step, self.max_steps)
                step_result = self.step()
                results.append("Step {}: {}".format(self.current_step, step_result))
            if self.current_step >= self.max_steps and self.state != AgentState.FINISHED:
                self.state = AgentState.FINISHED
                results.append("Terminated: Reached max steps ({})".format(self.max_steps))
            return "\n".join(results)
        except Exception as e:
            self.state = AgentState.ERROR
            log.exception("error executing agent")
            return "执行错误: {}".format(e)
        finally:
            self.cleanup()

    def run_stream(self, user_prompt):
        """同步流式执行：后台线程跑执行循环，通过队列逐条产出步骤结果（不推内部状态标记）。"""
        import queue, threading
        q = queue.Queue()
        _SENTINEL = object()

        def _worker():
            try:
                self._validate(user_prompt)
            except Exception as e:
                q.put("错误: {}".format(e)); q.put(_SENTINEL); return
            self.state = AgentState.RUNNING
            self.message_list.append(HumanMessage(content=user_prompt))
            try:
                for i in range(self.max_steps):
                    if self.state == AgentState.FINISHED:
                        break
                    self.current_step = i + 1
                    log.info("Executing step {}/{}", self.current_step, self.max_steps)
                    step_result = self.step()
                    # 步骤结果仅写入日志，不推给前端
                    log.info("Step {}: {}", self.current_step, step_result)
                    q.put(step_result)
                if self.current_step >= self.max_steps and self.state != AgentState.FINISHED:
                    self.state = AgentState.FINISHED
                    log.info("执行结束: 达到最大步骤({})".format(self.max_steps))
                    q.put("__MAX_STEPS__")
            except Exception as e:
                self.state = AgentState.ERROR
                log.exception("error executing agent")
                log.info("执行错误: {}".format(e))
                q.put("__ERROR__:" + str(e))
            finally:
                self.cleanup(); q.put(_SENTINEL)

        def generator():
            t = threading.Thread(target=_worker, daemon=True); t.start()
            while True:
                item = q.get()
                if item is _SENTINEL: break
                if item == "__MAX_STEPS__" or (isinstance(item, str) and item.startswith("__ERROR__:")):
                    continue
                yield item
        return generator()

    async def arun_stream(self, user_prompt):
        """异步流式接口，不阻塞事件循环线程。"""
        import asyncio
        q = asyncio.Queue()
        _SENTINEL = object()
        loop = asyncio.get_event_loop()

        def _worker():
            try:
                self._validate(user_prompt)
            except Exception as e:
                loop.call_soon_threadsafe(q.put_nowait, "错误: {}".format(e))
                loop.call_soon_threadsafe(q.put_nowait, _SENTINEL)
                return
            self.state = AgentState.RUNNING
            self.message_list.append(HumanMessage(content=user_prompt))
            try:
                for i in range(self.max_steps):
                    if self.state == AgentState.FINISHED:
                        break
                    self.current_step = i + 1
                    log.info("Executing step {}/{}".format(self.current_step, self.max_steps))
                    step_result = self.step()
                    # 步骤结果仅写入日志，不推给前端（前端只看最终回答）
                    log.info("Step {}: {}", self.current_step, step_result)
                    loop.call_soon_threadsafe(q.put_nowait, step_result)
                if self.current_step >= self.max_steps and self.state != AgentState.FINISHED:
                    self.state = AgentState.FINISHED
                    log.info("执行结束: 达到最大步骤({})".format(self.max_steps))
                    loop.call_soon_threadsafe(q.put_nowait, "__MAX_STEPS__")
            except Exception as e:
                self.state = AgentState.ERROR
                log.exception("error executing agent")
                log.info("执行错误: {}".format(e))
                loop.call_soon_threadsafe(q.put_nowait, "__ERROR__:" + str(e))
            finally:
                self.cleanup()
                loop.call_soon_threadsafe(q.put_nowait, _SENTINEL)

        loop.run_in_executor(None, _worker)
        while True:
            item = await q.get()
            if item is _SENTINEL:
                break
            if item == "__MAX_STEPS__" or (isinstance(item, str) and item.startswith("__ERROR__:")):
                # 这些是内部状态标记，调用方不应再把它们推给前端
                continue
            yield item

    @abstractmethod
    def step(self):
        """执行一轮 Agent 逻辑（思考 / 工具调用 / 产出），由子类实现。"""
        raise NotImplementedError

    def cleanup(self):
        """清理运行态：重置步数、清空消息列表、回到 IDLE。"""
        self.current_step = 0
        self.message_list = []
        self.state = AgentState.IDLE

    def _validate(self, user_prompt):
        """运行前校验：必须处于 IDLE 且 user_prompt 非空，否则抛 RuntimeError。"""
        if self.state != AgentState.IDLE:
            raise RuntimeError("Cannot run agent from state: {}".format(self.state))
        if not user_prompt or not user_prompt.strip():
            raise RuntimeError("Cannot run agent with empty user prompt")
