"""工具调用代理基类（对应 Java ToolCallAgent）。"""
from __future__ import annotations
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.language_models import BaseChatModel
from app.agent.base_agent import AgentState
from app.agent.react_agent import ReActAgent
from app.logger import log
from app.utils.text_clean import clean_think_tags


class ToolCallAgent(ReActAgent):
    def __init__(self, name, chat_model, tools, system_prompt="", next_step_prompt="", max_steps=5):
        super().__init__(name, chat_model, system_prompt, next_step_prompt, max_steps)
        self.available_tools = tools
        self._llm_with_tools = chat_model.bind_tools(tools) if tools else chat_model
        self.final_answer = ""
        self._current_step = 0

    def think(self):
        self._current_step += 1
        if self.next_step_prompt and len(self.message_list) <= 2:
            self.message_list.append(HumanMessage(content=self.next_step_prompt))
        messages = self._build_messages()
        try:
            ai_msg = self._llm_with_tools.invoke(messages)
            # 过滤 reasoning model 的 <think>...</think> 推理过程
            raw_content = ai_msg.content or ""
            cleaned = clean_think_tags(raw_content)
            if cleaned:
                ai_msg.content = cleaned
            self.final_answer = cleaned or raw_content
            tool_calls = getattr(ai_msg, "tool_calls", None) or []
            log.info("{} Step {}: 选择了 {} 个工具", self.name, self._current_step, len(tool_calls))
            for tc in tool_calls:
                log.info("  工具: {}, 参数: {}", tc.get("name"), tc.get("args"))
            self.message_list.append(ai_msg)
            return len(tool_calls) > 0
        except Exception as e:
            log.exception("{} 思考过程遇到问题", self.name)
            self.message_list.append(AIMessage(content="处理时遇到错误: {}".format(e)))
            # 标记错误状态，让上层（Xianzhi 流式过滤）能识别并把错误推给前端
            self._last_error = str(e)
            self.state = AgentState.ERROR
            return False

    def act(self):
        last_msg = self.message_list[-1]
        tool_calls = getattr(last_msg, "tool_calls", None) or []
        if not tool_calls:
            return "没有工具需要调用"
        results = []
        terminated = False
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            tool_args = tc.get("args", {}) or {}
            tc_id = tc.get("id", "")
            try:
                tool = self._find_tool(tool_name)
                if tool is None:
                    content = "工具 {} 不存在".format(tool_name)
                else:
                    content = str(tool.invoke(tool_args))
                    if tool_name == "do_terminate":
                        terminated = True
            except Exception as e:
                content = "工具 {} 调用失败: {}".format(tool_name, e)
                log.exception("工具调用失败: {}", tool_name)
            self.message_list.append(ToolMessage(content=content, tool_call_id=tc_id))
            preview = content if len(content) <= 120 else content[:120] + "..."
            results.append("工具: {} 返回: {}".format(tool_name, preview))
        if terminated:
            self.state = AgentState.FINISHED
        return "\n".join(results)

    def observe(self, act_result):
        if not act_result:
            return
        if "do_terminate" in act_result:
            log.info("[观察] 任务执行完成")
        elif "bazi_chart" in act_result:
            log.info("[观察] 八字排盘完成")
        elif "bazi_analysis" in act_result:
            log.info("[观察] 五行分析完成")
        elif "search_web" in act_result:
            log.info("[观察] 联网搜索完成")
        elif "scrape_web_page" in act_result:
            log.info("[观察] 网页抓取完成")
        else:
            log.info("[观察] 工具执行完成")

    def _find_tool(self, name):
        for t in self.available_tools:
            if t.name == name:
                return t
        return None

    def _build_messages(self):
        msgs = []
        if self.system_prompt:
            msgs.append(SystemMessage(content=self.system_prompt))
        msgs.extend(self.message_list)
        return msgs

    def run_stream(self, user_prompt):
        """流式执行，返回每一步的思考和结果。"""
        self.reset()
        self.message_list.append(HumanMessage(content=user_prompt))
        yield "[思考] 收到用户请求: {}".format(user_prompt[:50])
        
        while self.state != AgentState.FINISHED and self._step_count < self.max_steps:
            self._step_count += 1
            yield "[思考] Step {}: 分析当前情况...".format(self._step_count)
            
            should_act = self.think()
            if should_act:
                last_msg = self.message_list[-1]
                tool_calls = getattr(last_msg, "tool_calls", None) or []
                for tc in tool_calls:
                    yield "[行动] 调用工具: {} (参数: {})".format(
                        tc.get("name"), tc.get("args")
                    )
                
                act_result = self.act()
                yield "[观察] 工具执行结果: {}".format(act_result[:100])
                self.observe(act_result)
            else:
                yield "[回答] {}".format(self.final_answer)
                break
        
        if self.state == AgentState.FINISHED:
            yield "[结束] 任务完成"