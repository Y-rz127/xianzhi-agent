"""ReAct 模式代理基类（对应 Java ReActAgent）。"""
from __future__ import annotations
from abc import abstractmethod
from app.agent.base_agent import BaseAgent, AgentState
from app.logger import log


class ReActAgent(BaseAgent):
    final_answer = ""

    def step(self):
        should_act = self.think()
        if not should_act:
            # 没有工具调用 = LLM 已给出最终答案，标记完成避免空转
            self.state = AgentState.FINISHED
            return self.final_answer or "(无工具调用，直接回答)"
        act_result = self.act()
        self.observe(act_result)
        return act_result

    @abstractmethod
    def think(self):
        raise NotImplementedError

    @abstractmethod
    def act(self):
        raise NotImplementedError

    def observe(self, act_result):
        if act_result:
            log.info("[观察] {}", act_result[:200])