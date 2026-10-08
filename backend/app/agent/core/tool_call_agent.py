"""工具调用代理基类（对应 Java ToolCallAgent）。"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.core.base_agent import AgentState
from app.agent.core.react_agent import ReActAgent
from app.core.llm_throttle import llm_tag
from app.core.logger import log
from app.tools.dsml import has_text_tool_calls, parse_text_tool_calls
from app.tools.text_clean import clean_think_tags, strip_user_input_boundary


def _value_fits_spec(value, spec: dict) -> bool:
    """值是否与参数的 schema 类型声明兼容（用于参数名漂移时的安全配对）。

    spec 形如 ``{"title": "Pillars", "type": "string"}``。只认 JSON Schema 的基础类型；
    声明缺失或类型不认识时返回 False——**配对宁缺勿滥**，猜错位比报缺参更难排查。
    """
    if not isinstance(spec, dict):
        return False
    declared = str(spec.get("type") or "").lower()
    if declared == "string":
        return isinstance(value, str)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "array":
        return isinstance(value, list)
    if declared == "object":
        return isinstance(value, dict)
    return False


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
            # DeepSeek 系模型（降级链上的 deepseek-v4.1-flash）bind_tools 后**不走**
            # tool_calls 通道，而是把调用以文本形式（DSML / 裸 tool_call 标签）写进
            # content。这种响应 tool_calls 为空 + finish_reason=stop，若直接返回会被
            # 判「无工具调用」并把协议原文当最终回答吐给用户（2026-10-08 小程序现场）。
            # 这里还原成标准 tool_calls，剩余正文才是真正的回答文本。
            tool_calls = getattr(ai_msg, "tool_calls", None) or []
            if not tool_calls and has_text_tool_calls(cleaned):
                tool_calls, cleaned = parse_text_tool_calls(cleaned)
                if tool_calls:
                    ai_msg = AIMessage(
                        content=cleaned,
                        tool_calls=tool_calls,
                        response_metadata=getattr(ai_msg, "response_metadata", None) or {},
                    )
            # 本路径同样可能被模型回显 "--- USER INPUT BEGIN/END ---" 边界标记，
            # 统一走 strip_user_input_boundary 防内部标记泄漏（与 Workflow / 闲聊路径一致）
            cleaned = strip_user_input_boundary(cleaned) if cleaned else ""
            if cleaned:
                ai_msg.content = cleaned
            self.final_answer = cleaned or ("" if tool_calls else raw_content)
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
                    tool_args = self._align_args(tool, tool_args)
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

    def _align_args(self, tool, tool_args: dict) -> dict:
        """把模型给的参数名对齐到工具真实签名。

        文本形式的工具调用（DeepSeek 系走 ``content`` 通道）经常自造参数名，
        实测 ``bazi_infer_dates`` 的 ``pillars`` 被写成 ``four_pillars``，
        以及完全无公共子串的 ``bazi``（2026-10-08 现场两次）。

        两级对齐：
        ① **子串匹配**：``four_pillars`` ⊃ ``pillars``，命中即用（高置信）。
        ② **唯一空缺配对**：子串匹配不到时（``bazi`` ↔ ``pillars`` 无公共子串），
           若「未识别键」与「未填充的必填参数」都是一对一，且值类型与该参数声明
           兼容，则配对。多对多或类型不符一律不动——宁可让工具报缺参，
           也不猜错位（错误信息比静默塞错值更可查）。
        匹配不上的键原样保留，交由工具自己报错。
        """
        if not tool_args:
            return tool_args
        try:
            specs = dict(getattr(tool, "args", None) or {})
        except Exception:
            return tool_args
        if not specs:
            return tool_args

        aligned: dict = {}
        unknown: dict = {}
        for key, value in tool_args.items():
            (aligned if key in specs else unknown)[key] = value
        if not unknown:
            return aligned

        # ① 子串匹配（取最长的空缺席位）
        for key in list(unknown):
            candidates = [
                name for name in specs if name not in aligned and (name in key or key in name)
            ]
            if candidates:
                target = max(candidates, key=len)
                log.info("  参数名对齐(子串): {} → {}", key, target)
                aligned[target] = unknown.pop(key)

        # ② 唯一空缺配对：仅当各剩一个、且值类型与目标参数声明兼容
        if len(unknown) == 1:
            missing = [
                name
                for name, spec in specs.items()
                if name not in aligned and "default" not in (spec or {})
            ]
            if len(missing) == 1:
                key, value = next(iter(unknown.items()))
                if _value_fits_spec(value, specs.get(missing[0]) or {}):
                    target = missing[0]
                    log.info("  参数名对齐(唯一空缺): {} → {}", key, target)
                    aligned[target] = unknown.pop(key)

        aligned.update(unknown)
        return aligned

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
