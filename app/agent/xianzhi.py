"""先知 - 八字命理分析预测智能体

基于 ToolCallAgent，拥有自主规划能力，可直接使用。
工具集 = 本地工具（八字/搜索/终止）+ MCP 工具（高德地图）。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.birth_parse import (  # 解耦：生辰解析职责独立成模块
    birth_place_to_longitude,
    detect_birth_signal,
    extract_birth_info,
    extract_birth_place,
    extract_pillars,
    resolve_bazi_selection,
)
from app.agent.core.base_agent import AgentState, BaseAgent
from app.agent.core.tool_call_agent import ToolCallAgent
from app.agent.prompts import (
    CHITCHAT_SYSTEM,
    ORACLE_BASE_SYSTEM as SYSTEM_PROMPT,
    REACT_FACT_GUARDRAILS as FACT_GUARDRAILS,
    REACT_NEXT_STEP_PROMPT as NEXT_STEP_PROMPT,
)
from app.agent.workflow.xianzhi_workflow import (
    WorkflowChartContext,
    XianzhiWorkflow,
    build_chart_context,
    classify_question,
    render_full_fact_context,
)
from app.core.config import settings
from app.core.logger import log
from app.core.thinking_router import use_thinking
from app.domain.bazi_engine import find_birth_dates_from_pillars
from app.memory import create_chat_memory
from app.tools.bazi import BAZI_BIRTH_TOOLS, _normalize_birth_time
from app.tools.mcp_client import mcp_manager
from app.tools.text_clean import clean_think_tags, dedupe_content, strip_user_input_boundary


class Xianzhi(ToolCallAgent):
    """先知智能体"""

    # 排盘工具名集合：调用这些工具时，从参数中提取 birth_time/gender
    _BAZI_TOOLS = BAZI_BIRTH_TOOLS

    def __init__(
        self,
        chat_model,
        local_tools,
        memory=None,
        conversation_id="xianzhi-default",
        max_steps=None,
        decompose_model=None,
        reviewer_model=None,
    ):
        super().__init__(
            name="Xianzhi",
            chat_model=chat_model,
            tools=local_tools,
            system_prompt=SYSTEM_PROMPT,
            next_step_prompt=NEXT_STEP_PROMPT,
            max_steps=max_steps or settings.agent_max_steps,
        )
        self._local_tools = local_tools
        self._conversation_id = conversation_id
        # 记忆实例由会话池共享注入（避免每 Agent 各持一个 PG 连接）；未注入时自建（测试场景）
        self._memory = memory if memory is not None else create_chat_memory()
        self.chart_context = ""
        self._workflow = XianzhiWorkflow(chat_model, decompose_model, reviewer_model)
        self._workflow_context: WorkflowChartContext | None = None
        self._last_birth_info: Optional[dict] = None
        self._last_user_text: str = ""
        self._sect = 2
        self._yun_sect = 1
        self._bazi_pending: Optional[dict] = None  # 八字待确认候选: {"pillars","gender","candidates"}
        self._birth_signal: bool = False  # 模糊生辰信号：精确正则没抓到但疑似在提供生辰
        self._history_len = 0  # 本轮载入的历史消息数，_persist_history 据此只落盘新增消息
        # MCP 工具签名缓存：None=尚未绑定；仅签名变化时才重新 bind_tools（见 think）
        self._mcp_tool_signature: Optional[tuple] = None
        self._lock = asyncio.Lock()

    @property
    def lock(self) -> asyncio.Lock:
        """实例级锁：同一会话串行，不同会话（不同实例）并行。"""
        return self._lock

    def set_conversation_id(self, conversation_id):
        new_id = conversation_id if conversation_id and conversation_id.strip() else "xianzhi-default"
        # 切换会话时清空命盘上下文，避免跨会话污染
        if new_id != self._conversation_id:
            self.chart_context = ""
            self._workflow_context = None
            self._last_birth_info = None
            self._bazi_pending = None
        self._conversation_id = new_id

    def reset(self):
        """重置 Agent 运行状态（父类 run_stream 会调用，需补齐）。

        注意：_bazi_pending 必须跨 turn 保留，否则下一轮用户回复"第一个/1992年"时，
        mount_chart_context 里 if self._bazi_pending 这个分支永远进不去，
        _resolve_bazi_selection 拿不到候选，只能依赖 LLM 盲排（参见 2026-08-11 小程序截图问题）。
        与 _workflow_context / _last_birth_info 同级别，只在切换会话（set_conversation_id）
        时才清空。
        """
        self.state = AgentState.IDLE
        self.current_step = 0
        self._current_step = 0
        self.message_list = []
        # 清理取消标志：取消只作用于"当前这一次执行"（WS 断开置位），
        # 下一轮请求必须从头开始。workflow/闲聊路径不走 BaseAgent 的 worker，
        # 不会经过其内部的 clear，故统一在此清理。
        self._cancel_event.clear()
        self.final_answer = ""
        self._last_error = None
        self._sect = 2
        self._yun_sect = 1
        self._history_len = 0
        # _bazi_pending 不再重置：交给 mount_chart_context / set_conversation_id 管理生命周期

    def set_chart_context(
        self,
        birth_time: str,
        gender: str,
        sect: int = 2,
        yun_sect: int = 1,
        user_id: str = "",
        birth_place: str = "",
    ):
        """挂载命盘上下文：外部（API/会话恢复）直接设置，AI 回答基于该盘面。

        出生时间支持公历(YYYY-MM-DD HH:MM)、公历+时辰、农历、农历节日等格式；
        birth_place 为出生地城市名，用于真太阳时校正（与 /chart API 行为一致）。
        """
        try:
            birth_time = _normalize_birth_time(birth_time)
            longitude = birth_place_to_longitude(birth_place)
            workflow_context = build_chart_context(
                birth_time, gender, sect, yun_sect, user_id, longitude=longitude
            )
            chart = render_full_fact_context(workflow_context)
            self.chart_context = (
                "【当前命盘上下文】\n"
                "以下盘面信息已由系统根据用户提供的出生时间自动排盘生成，"
                "请你在后续回答中优先基于该命盘进行推理与分析，无需再次排盘：\n\n"
                f"{chart}\n"
            )
            self._workflow_context = workflow_context
            self._last_birth_info = {
                "time": birth_time,
                "gender": gender,
                "sect": sect,
                "yun_sect": yun_sect,
                "place": birth_place or "",
                "longitude": longitude,
            }
            log.info("已挂载命盘上下文: {} {} user={} longitude={}", birth_time, gender, user_id, longitude)
        except Exception as e:
            log.warning("挂载命盘上下文失败: {}", e)
            self.chart_context = ""
            self._workflow_context = None
            self._last_birth_info = None

    def mount_chart_context(self, text: str, sect: int = 2, yun_sect: int = 1):
        """如果用户输入包含出生信息，自动挂载命盘上下文。

        支持三类输入：
        1. 完整出生时间（年-月-日 时:分）+ 性别 -> 直接排盘；
        2. 仅八字四柱（如"甲申庚午壬申甲辰"）+ 性别 -> 反推候选出生日期，
           交由用户确认其一后，再用选定日期排盘（见 _resolve_bazi_selection）。
        3. 农历/节日/时辰/公历+时辰等模糊生辰 -> 设 _birth_signal 标志，
           不走闲聊短路，让 ReAct 路径的 LLM 调 bazi_full（内部 _normalize_birth_time 自动转公历）。
        """
        self._last_user_text = text or ""
        self._birth_signal = False  # 每轮重置
        birth_time, gender = extract_birth_info(text)
        if birth_time and gender:
            self.set_chart_context(
                birth_time, gender, sect, yun_sect, birth_place=extract_birth_place(text) or ""
            )
            return True
        # 已有待确认八字候选：尝试把本轮输入解析为用户的选择
        if self._bazi_pending:
            bt = resolve_bazi_selection(text, self._bazi_pending)
            if bt:
                # 候选确认排盘时带上当初提供的出生地（真太阳时校正）
                self.set_chart_context(
                    bt,
                    self._bazi_pending["gender"],
                    sect,
                    yun_sect,
                    birth_place=self._bazi_pending.get("place") or "",
                )
                self._bazi_pending = None
                return True
        # 首次检测到八字：反推候选日期，交由 LLM 向用户确认
        pillars, gender = extract_pillars(text)
        if pillars and gender:
            try:
                cands = find_birth_dates_from_pillars(pillars, gender, top_n=3)
            except Exception:
                cands = []
            self._bazi_pending = {
                "pillars": pillars,
                "gender": gender,
                "candidates": cands,
                "place": extract_birth_place(text) or "",  # 出生地随候选保留，确认排盘时使用
            }
            return True
        # 模糊生辰检测：精确正则没抓到但用户确实在提供生辰信息
        if detect_birth_signal(text):
            self._birth_signal = True
            log.info("[xianzhi] 检测到疑似生辰信号，不走闲聊短路: {}", (text or "")[:80])
        return False

    def _build_messages(self):
        """构建发送给 LLM 的消息列表，附加命盘上下文到 system prompt。"""
        msgs = []
        if self.system_prompt:
            content = self.system_prompt
            if self.chart_context:
                content += "\n\n" + self.chart_context
                content += "\n\n" + FACT_GUARDRAILS
            if self._bazi_pending:
                cands = self._bazi_pending.get("candidates") or []
                block = "\n\n【待确认八字】用户提供了八字 {}（{}），已反推以下候选出生日期：\n".format(
                    self._bazi_pending.get("pillars"), self._bazi_pending.get("gender")
                )
                if cands:
                    for i, c in enumerate(cands, 1):
                        block += "  {}. {}（{}，{}）\n".format(
                            i, c.get("birth_time"), c.get("ganzhi"), c.get("shi_chen")
                        )
                    block += "请直接向用户展示以上候选，请其确认实际出生日期（回复序号『第一个』或具体年份『2004年』均可）。待用户确认后，用对应 birth_time 调用排盘工具，不要自行猜测日期排盘。\n"
                else:
                    block += "  未能反推出候选日期，请直接向用户说明并索取精确出生时间或确认八字是否有误。\n"
                content += block
            msgs.append(SystemMessage(content=content))
        msgs.extend(self.message_list)
        return msgs

    def run(self, user_prompt):
        """非流式入口：重置状态→挂载命盘上下文→载入历史→执行（工作流或基类）。"""
        self.reset()
        self.mount_chart_context(user_prompt, self._sect, self._yun_sect)
        self._load_history()
        if self._workflow_context:
            chunks = list(self._workflow_stream(user_prompt))
            return chunks[-1] if chunks else ""
        return super().run(user_prompt)

    def think(self):
        """决策步：若 MCP 工具可用则合并到本地工具并重新 bind，再调用基类 think。

        基类 think 后额外拦截 LLM 的工具调用：从排盘工具参数中提取 birth_time/gender
        （覆盖自然语言输入场景），并同步八字反推候选，供后续解析用户选择。

        工具集按签名缓存：仅当 MCP 工具集合变化时才重新 bind_tools，
        避免每个 ReAct 步骤都重建工具列表与绑定。
        """
        if mcp_manager.available:
            mcp_tools = mcp_manager.get_tools()
            signature = tuple(t.name for t in mcp_tools)
            if signature != self._mcp_tool_signature:
                self.available_tools = list(self._local_tools) + mcp_tools
                self._llm_with_tools = self.chat_model.bind_tools(self.available_tools)
                self._mcp_tool_signature = signature
        result = super().think()
        # 拦截排盘工具调用，从参数中提取 birth_time/gender（覆盖自然语言输入场景）
        self._capture_birth_from_tool_calls()
        # 同步八字反推候选（LLM 主动调用 bazi_infer_dates 时也记录，便于后续解析用户选择）
        self._capture_pending_from_tool_calls()
        return result

    def _capture_birth_from_tool_calls(self):
        """从 LLM 的工具调用中提取 birth_time/gender，挂载命盘上下文。

        当用户用自然语言（如"04年端午节辰时"）输入时，正则无法提取，
        但 LLM 能理解并调用 bazi 工具，此时从工具参数中拿到标准格式的 birth_time。
        """
        if self._last_birth_info:
            return  # 已有命盘上下文，无需重复提取
        for msg in reversed(self.message_list):
            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("args", {}) or {}
                if name in self._BAZI_TOOLS:
                    bt = args.get("birth_time")
                    gd = args.get("gender")
                    if bt and gd:
                        log.info("[xianzhi] 从工具调用提取出生信息: {} {}", bt, gd)
                        # 工具调用不含出生地，从用户原始输入补充提取（用于真太阳时校正）
                        bp = extract_birth_place(self._last_user_text) if self._last_user_text else None
                        self.set_chart_context(bt, gd, self._sect, self._yun_sect, birth_place=bp or "")
                        return

    def _capture_pending_from_tool_calls(self):
        """当 LLM 主动调用 bazi_infer_dates 时，记录候选以便解析用户后续选择。"""
        if self._bazi_pending:
            return
        for msg in reversed(self.message_list):
            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                if tc.get("name") == "bazi_infer_dates":
                    args = tc.get("args", {}) or {}
                    p = args.get("pillars")
                    g = args.get("gender")
                    if p and g:
                        try:
                            cands = find_birth_dates_from_pillars(p, g, top_n=int(args.get("top_n") or 3))
                        except Exception:
                            cands = []
                        self._bazi_pending = {"pillars": p, "gender": g, "candidates": cands}
                        return

    def _extract_chart_summary(self) -> str:
        """从已挂载的 chart_context 中提取「四柱」段，作为可视化兜底。"""
        if not self.chart_context:
            return ""
        lines = self.chart_context.splitlines()
        out = []
        in_pillars = False
        for line in lines:
            if "【四柱】" in line:
                in_pillars = True
                continue
            if in_pillars:
                if line.strip().startswith("【") or not line.strip():
                    if line.strip():
                        in_pillars = False
                    else:
                        continue
                else:
                    out.append(line.strip())
        return "\n".join(out)

    def _chart_summary_chunk(self):
        """命盘四柱摘要段（可视化兜底），未挂载或无可提取时无产出。"""
        if not self.chart_context:
            return
        summary = self._extract_chart_summary()
        if summary and "年柱" in summary:
            yield "\n[回答] 命盘四柱关键信息（用于可视化展示）：\n【四柱】\n{}".format(summary)

    def _finalize_stream(self, src_stream):
        """包装原 stream，在末尾追加命盘摘要段（若已挂载 chart_context）。"""
        for chunk in src_stream:
            yield chunk
        yield from self._chart_summary_chunk()

    def _final_answer_or_error(self) -> Optional[str]:
        """从本轮执行状态提取最终回答（或错误兜底文案），无文本返回 None。

        _filter_steps（同步路径）与 arun_stream（异步路径）共用，
        统一"final → 错误兜底 → 无文本"三段式收尾口径（含 _dedupe_content 去重）。
        """
        final = (self.final_answer or "").strip()
        if final:
            return dedupe_content(final)
        if self.state == AgentState.ERROR or self._last_error:
            err = (self._last_error or "未知错误").strip()
            log.warning("[xianzhi] 终止于错误: {}", err)
            return "分析过程中遇到错误，请稍后重试。"
        # LLM 仅触发 do_terminate 等工具、无文本回答时，
        # 前端已通过 /api/ai/xianzhi/chart 拿到结构化命盘数据
        log.info("[xianzhi] 终止时无文本回答，仅返回工具结果")
        return None

    def _filter_steps(self, src_iter):
        """内部消费 ReAct 步骤（仅写日志不外发），只产出最终回答。"""
        for _ in src_iter:
            pass
        final = self._final_answer_or_error()
        if final:
            yield final

    def _run_workflow_once(self, user_prompt: str, history_snapshot=None, summary: str = "") -> str:
        if not self._workflow_context:
            raise RuntimeError("workflow context is not mounted")
        history = list(history_snapshot) if history_snapshot is not None else list(self.message_list)
        return self._workflow.answer(user_prompt, self._workflow_context, history, summary)

    def _execute_workflow(self, user_prompt: str, history_snapshot, summary: str) -> str:
        """执行一轮 workflow 并更新 agent 状态，返回回答文本（同步/异步路径共用）。"""
        self.state = AgentState.RUNNING
        self.message_list.append(HumanMessage(content=user_prompt))
        answer = self._run_workflow_once(user_prompt, history_snapshot, summary)
        self.final_answer = answer
        self.message_list.append(AIMessage(content=answer))
        self.state = AgentState.FINISHED
        return answer

    def _workflow_stream(self, user_prompt: str):
        try:
            history_snapshot = list(self.message_list)
            summary = self._get_session_summary()
            yield self._execute_workflow(user_prompt, history_snapshot, summary)
        except Exception as e:
            self.state = AgentState.ERROR
            self._last_error = str(e)
            log.exception("Xianzhi workflow error")
            yield "分析过程遇到错误，请稍后重试。"
        finally:
            self.cleanup()

    async def _aworkflow_stream(self, user_prompt: str):
        try:
            # 客户端已断开（如 WS 关闭触发 request_cancel）则不再启动整条 LLM 链
            if self._cancel_requested():
                log.info("[xianzhi] workflow 执行前检测到取消，跳过本轮")
                return
            history_snapshot = list(self.message_list)
            # 会话摘要来自 PG 同步查询，放线程池避免阻塞事件循环
            summary = await asyncio.to_thread(self._get_session_summary)
            answer = await asyncio.to_thread(self._execute_workflow, user_prompt, history_snapshot, summary)
            yield answer
        except Exception as e:
            self.state = AgentState.ERROR
            self._last_error = str(e)
            log.exception("Xianzhi workflow error")
            yield "分析过程遇到错误，请稍后重试。"
        finally:
            # cleanup 内含 PG 落盘（_persist_history），放线程池避免阻塞事件循环
            await asyncio.to_thread(self.cleanup)

    def _is_chitchat(self, user_prompt: str) -> bool:
        """判断是否为闲聊场景（无命盘时短路 ReAct，避免无谓工具调用）。

        放行条件（任一命中即不走闲聊短路）：
        - _workflow_context：有完整命盘，走 workflow
        - _bazi_pending：八字待确认候选，走 ReAct 调 bazi_infer_dates
        - _birth_signal：模糊生辰信号（农历/节日/时辰/公历+时辰），走 ReAct 调 bazi_full
        """
        if self._workflow_context:
            return False
        if self._bazi_pending:
            return False
        if self._birth_signal:
            return False
        intent = classify_question(user_prompt)
        return intent.domain == "chitchat"

    def _chitchat_reply(self, user_prompt: str) -> str:
        """闲聊短路：直接调一次 LLM，不走 ReAct 循环，不调任何工具。"""
        log.info("[xianzhi] 闲聊短路，跳过 ReAct 工具调用")
        # 闲聊关闭思考模式（在调用线程内设置，确保 run_stream / arun_stream 两种路径都生效）
        with use_thinking(False):
            self.state = AgentState.RUNNING
            self.message_list.append(HumanMessage(content=user_prompt))
            try:
                history_ctx = (
                    "\n".join(
                        f"{m.__class__.__name__.replace('Message', '')}: {str(getattr(m, 'content', ''))[:180]}"
                        for m in self.message_list[-6:]
                        if str(getattr(m, "content", "")).strip()
                    )
                    or "（无）"
                )
                messages = [
                    SystemMessage(content=CHITCHAT_SYSTEM),
                    HumanMessage(
                        content=(f"【最近对话】\n{history_ctx}\n\n【用户说】\n{user_prompt}\n\n请正面回应，简短直接。")
                    ),
                ]
                response = self.chat_model.invoke(messages)
                content = (getattr(response, "content", "") or "").strip()
                content = clean_think_tags(content)
                # 闲聊路径同样可能被模型回显 "--- USER INPUT BEGIN/END ---" 边界标记，
                # 与 Workflow 路径统一走 strip_user_input_boundary，防止内部标记泄漏给用户
                content = strip_user_input_boundary(content)
                content = dedupe_content(content) if content else ""
                if not content:
                    content = "嗯，我在听，你继续说。"
                self.final_answer = content
                self.message_list.append(AIMessage(content=content))
                self.state = AgentState.FINISHED
                return content
            except Exception as e:
                self.state = AgentState.ERROR
                self._last_error = str(e)
                log.exception("[xianzhi] 闲聊短路失败")
                return "我刚才走神了，你再说一遍？"

    def run_stream(self, user_prompt, verbose: bool = False):
        """同步流式执行；verbose=True 透传 ReAct 步骤（调试用），False 只输出最终回答。"""
        self.reset()
        # 与 arun_stream 保持一致：无条件尝试挂载（用户中途更新生辰时覆盖旧盘）
        self.mount_chart_context(user_prompt, self._sect, self._yun_sect)
        self._load_history()
        if self._workflow_context and not verbose:
            return self._workflow_stream(user_prompt)
        # 闲聊短路：无命盘 + 闲聊意图 → 直接调一次 LLM，不走 ReAct 工具循环
        if not verbose and self._is_chitchat(user_prompt):

            def _chitchat_gen():
                try:
                    yield self._chitchat_reply(user_prompt)
                finally:
                    self.cleanup()

            return _chitchat_gen()
        # 走 BaseAgent.run_stream（绕开 ToolCallAgent.run_stream 的二次 reset，避免历史被清空）
        base_stream = BaseAgent.run_stream(self, user_prompt)
        if verbose:
            return self._finalize_stream(base_stream)
        return self._filter_steps(base_stream)

    async def arun_stream(self, user_prompt, verbose: bool = False):
        """异步流式执行；verbose=True 透传 ReAct 步骤，False 只输出最终回答。"""
        self.reset()
        # 挂载与历史载入含正则解析/排盘/PG IO，放线程池避免阻塞事件循环
        await asyncio.to_thread(self.mount_chart_context, user_prompt, self._sect, self._yun_sect)
        await asyncio.to_thread(self._load_history)
        if self._workflow_context and not verbose:
            async for chunk in self._aworkflow_stream(user_prompt):
                yield chunk
            return
        # 闲聊短路：无命盘 + 闲聊意图 → 直接调一次 LLM，不走 ReAct 工具循环
        if not verbose and self._is_chitchat(user_prompt):
            try:
                reply = await asyncio.to_thread(self._chitchat_reply, user_prompt)
                yield reply
            finally:
                # cleanup 内含 PG 落盘（_persist_history），同样放线程池
                await asyncio.to_thread(self.cleanup)
            return
        if verbose:
            async for chunk in super().arun_stream(user_prompt):
                yield chunk
            # verbose 模式下仍追加 chart 兜底（保持原有行为）
            for _summary in self._chart_summary_chunk():
                yield _summary
            return
        # 正常模式：走 ReAct 工具循环，LLM 自行决定是否调 search_knowledge
        async for _ in super().arun_stream(user_prompt):
            pass
        final = self._final_answer_or_error()
        if final:
            yield final

    def _load_history(self):
        history = self._memory.get(self._conversation_id)
        if history:
            max_tokens = 2000
            total_tokens = 0
            selected = []
            for msg in reversed(history):
                content = msg.content if hasattr(msg, "content") else str(msg)
                # 中文场景下 1 字符 ≈ 1.5 token（英文≈0.25），取折中系数
                cn_chars = sum(1 for c in content if "\u4e00" <= c <= "\u9fff")
                en_chars = len(content) - cn_chars
                token_count = int(cn_chars * 1.5 + en_chars * 0.25)
                if total_tokens + token_count <= max_tokens:
                    selected.append(msg)
                    total_tokens += token_count
                else:
                    break
            self.message_list = list(reversed(selected))
        self._history_len = len(self.message_list)

    def _persist_history(self):
        """仅持久化本轮新增的消息，避免重复追加历史导致消息指数级重复。
        同时过滤掉 next_step_prompt 占位消息（tool_call_agent.think 注入的 HumanMessage），
        防止历史会话恢复时把"工具指引"内容当作用户消息显示在左边。
        """
        new_messages = self.message_list[self._history_len :]
        if new_messages:
            # 过滤 next_step_prompt 注入的 HumanMessage（其内容以工具调度模板开头）
            filtered = [
                m
                for m in new_messages
                if not (
                    m.__class__.__name__ == "HumanMessage"
                    and isinstance(getattr(m, "content", ""), str)
                    and (
                        "根据用户需求选最合适的工具，复杂任务分解多步" in m.content
                        or "你是先知，按以下顺序自主规划与调工具完成任务" in m.content
                    )
                )
            ]
            if filtered:
                self._memory.add(self._conversation_id, filtered)
        # 每 6 轮对话（一问一答=1轮，约12条消息）触发摘要（异步线程，不阻塞主流程）
        from app.memory.summarizer import maybe_summarize

        maybe_summarize(self._memory, self.chat_model, self._conversation_id, self.message_list)

    def _get_session_summary(self) -> str:
        """从会话元数据中获取历史摘要。"""
        try:
            return self._memory.get_summary(self._conversation_id)
        except Exception as e:
            log.warning("获取会话摘要失败: {}", e)
            return ""

    def cleanup(self):
        # 持久化失败不应阻断状态重置，否则实例永久卡死在 RUNNING
        try:
            self._persist_history()
        except Exception as e:
            # 持久化失败 = 本轮对话丢失，错误级可见（记忆层已同步埋点）
            log.error("[xianzhi] cleanup 持久化历史失败: {}", e)
        # 命盘上下文持久化到会话：不清空，下一轮同会话仍可用
        # 仅在切换会话（set_conversation_id）时才主动清空
        super().cleanup()


def create_xianzhi_agent(
    chat_model,
    local_tools,
    memory=None,
    conversation_id: str = "xianzhi-default",
    decompose_model=None,
    reviewer_model=None,
) -> "Xianzhi":
    """构造先知智能体（会话池统一入口，透传参数给 Xianzhi）。"""
    return Xianzhi(
        chat_model=chat_model,
        local_tools=local_tools,
        memory=memory,
        conversation_id=conversation_id,
        decompose_model=decompose_model,
        reviewer_model=reviewer_model,
    )
