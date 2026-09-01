"""工具调用代理基类（对应 Java ToolCallAgent）。"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.core.base_agent import AgentState
from app.agent.core.react_agent import ReActAgent
from app.core.llm_throttle import llm_tag
from app.core.logger import log
from app.tools.text_clean import clean_think_tags, strip_user_input_boundary


class ToolCallAgent(ReActAgent):
    """工具调用代理（对应 Java ToolCallAgent）：绑定 LLM 工具，实现 think/act/observe。"""
    def __init__(self, name, chat_model, tools, system_prompt="", next_step_prompt="", max_steps=5):
        super().__init__(name, chat_model, system_prompt, next_step_prompt, max_steps)
        self.available_tools = tools
        self._llm_with_tools = chat_model.bind_tools(tools) if tools else chat_model
        self.final_answer = ""
        self._current_step = 0

    def think(self):
        self._current_step += 1
        # 工具指引只注入一次：按内容查重而非消息数判断（历史恢复后消息数不定，固定阈值会漂移）
        if self.next_step_prompt and not any(
            isinstance(m, HumanMessage) and m.content == self.next_step_prompt
            for m in self.message_list
        ):
            self.message_list.append(HumanMessage(content=self.next_step_prompt))
        messages = self._build_messages()
        try:
            with llm_tag("react"):
                ai_msg = self._llm_with_tools.invoke(messages)
            # 过滤推理模型的 thinking 推理块，避免泄漏到回答
            raw_content = ai_msg.content or ""
            cleaned = clean_think_tags(raw_content)
            # 本路径同样可能被模型回显 "--- USER INPUT BEGIN/END ---" 边界标记，
            # 统一走 strip_user_input_boundary 防内部标记泄漏（与 Workflow / 闲聊路径一致）
            cleaned = strip_user_input_boundary(cleaned) if cleaned else ""
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
