"""ReAct 模式代理基类（对应 Java ReActAgent）。"""
from __future__ import annotations

from abc import abstractmethod

from app.agent.core.base_agent import AgentState, BaseAgent
from app.core.logger import log


class ReActAgent(BaseAgent):
    """ReAct 模式代理：每轮先 think() 决策，无工具则结束，否则 act() 后 observe()。"""
    final_answer = ""

    def step(self):
        should_act = self.think()
        # think() 异常时子类已置 ERROR，此处不覆盖
        if self.state == AgentState.ERROR:
            return self.final_answer or "(执行出错)"
        if not should_act:
            self.state = AgentState.FINISHED
            return self.final_answer or "(无工具调用，直接回答)"
        act_result = self.act()
        self.observe(act_result)
        return act_result

    @abstractmethod
    def think(self):
        """决策是否调用工具；返回 True 表示需要 act()。"""
        raise NotImplementedError

    @abstractmethod
    def act(self):
        """执行工具调用；返回工具执行结果文本。"""
        raise NotImplementedError

    def observe(self, act_result):
        if act_result:
            log.info("[观察] {}", act_result[:200])
