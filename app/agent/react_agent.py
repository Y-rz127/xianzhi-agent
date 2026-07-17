"""ReAct 模式代理基类（对应 Java ReActAgent）。"""
from __future__ import annotations
from abc import abstractmethod
from app.agent.base_agent import BaseAgent, AgentState
from app.logger import log


class ReActAgent(BaseAgent):
    """ReAct 模式代理：每轮先 think() 决策，无工具则结束，否则 act() 后 observe()。"""
    final_answer = ""

    def step(self):
        """执行一轮 ReAct：think() 决策；无需工具则标记完成并返回最终答案，否则 act()+observe()。"""
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
        """思考并决定下一步是否需要调用工具；返回 True 表示需要 act()。"""
        raise NotImplementedError

    @abstractmethod
    def act(self):
        """执行工具调用；返回工具执行结果文本。"""
        raise NotImplementedError

    def observe(self, act_result):
        """记录工具执行结果日志（供调试追溯）。"""
        if act_result:
            log.info("[观察] {}", act_result[:200])