"""先知 - 八字命理分析预测智能体

基于 ToolCallAgent，拥有自主规划能力，可直接使用。
工具集 = 本地工具（八字/搜索/终止）+ MCP 工具（高德地图）。
"""
from __future__ import annotations

import asyncio
import threading
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.core.base_agent import AgentState, BaseAgent
from app.agent.prompts import (
    CHITCHAT_SYSTEM,
    ORACLE_BASE_SYSTEM,
    REACT_FACT_GUARDRAILS,
    REACT_NEXT_STEP_PROMPT,
)
from app.agent.birth_parse import (  # 解耦：生辰解析职责独立成模块
    detect_birth_signal,
    extract_birth_info,
    extract_birth_place,
    extract_pillars,
    resolve_bazi_selection,
)
from app.agent.core.tool_call_agent import ToolCallAgent
from app.agent.workflow.xianzhi_workflow import (
    WorkflowChartContext,
    XianzhiWorkflow,
    _dedupe_content,
    build_chart_context,
    classify_question,
    render_full_fact_context,
)
from app.core.config import settings
from app.domain.bazi_engine import find_birth_dates_from_pillars
from app.core.logger import log
from app.memory import create_chat_memory
from app.tools.bazi import _normalize_birth_time
from app.tools.mcp_client import mcp_manager
from app.tools.text_clean import clean_think_tags

# 生辰解析正则与提取函数已抽离至 app/agent/birth_parse.py（解耦单一职责模块）


# 系统提示词：定义先知角色（八字命理师傅）的人设、行为准则与输出风格
SYSTEM_PROMPT = ORACLE_BASE_SYSTEM

# ReAct 单步提示词：引导 Agent 在每一步选择合适工具或直接回答
NEXT_STEP_PROMPT = REACT_NEXT_STEP_PROMPT

# 事实护栏提示词：约束 Agent 必须基于命盘上下文推理，禁止无凭据断言
FACT_GUARDRAILS = REACT_FACT_GUARDRAILS

class Xianzhi(ToolCallAgent):
    """先知智能体"""

    # 排盘工具名集合：调用这些工具时，从参数中提取 birth_time/gender
    _BAZI_TOOLS = {"bazi_chart", "bazi_full", "bazi_analysis", "bazi_dayun", "bazi_liunian", "bazi_liuyue", "bazi_liuri"}

    def __init__(self, chat_model, local_tools, memory=None, conversation_id="xianzhi-default", max_steps=None,
                 decompose_model=None, reviewer_model=None):
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
        self._lock = asyncio.Lock()

    @property
    def lock(self) -> asyncio.Lock:
        """实例级锁：同一会话串行，不同会话（不同实例）并行。"""
        return self._lock

    def set_conversation_id(self, conversation_id):
        new_id = (
            conversation_id if conversation_id and conversation_id.strip()
            else "xianzhi-default"
        )
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
        self._step_count = 0
        self.message_list = []
        self.final_answer = ""
        self._last_error = None
        self._sect = 2
        self._yun_sect = 1
        self._history_len = 0
        # _bazi_pending 不再重置：交给 mount_chart_context / set_conversation_id 管理生命周期

    def set_chart_context(self, birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1, user_id: str = "", birth_place: str = ""):
        """由外部直接设置当前命盘上下文，AI 回答将基于该盘面。

        Args:
            birth_time: 出生时间，支持公历(YYYY-MM-DD HH:MM)、公历+时辰(YYYY-MM-DD 辰时)、
                       农历(农历1990年四月廿六 14:30)、农历节日(2004年端午节 辰时) 等格式
            gender: 性别，男 或 女
            sect: 日柱计算流派，1=按日期精确，2=按日期精确2（默认）
            yun_sect: 大运计算流派，1=按天数和时辰数（默认），2=按分钟数
            user_id: 用户 ID，用于从命盘画像加载历史断事知识
            birth_place: 出生地（城市名），用于真太阳时校正；无则空字符串
        """
        try:
            birth_time = _normalize_birth_time(birth_time)
            workflow_context = build_chart_context(birth_time, gender, sect, yun_sect, user_id)
            chart = render_full_fact_context(workflow_context)
            self.chart_context = (
                "【当前命盘上下文】\n"
                "以下盘面信息已由系统根据用户提供的出生时间自动排盘生成，"
                "请你在后续回答中优先基于该命盘进行推理与分析，无需再次排盘：\n\n"
                f"{chart}\n"
            )
            self._workflow_context = workflow_context
            self._last_birth_info = {
                "time": birth_time, "gender": gender, "sect": sect,
                "yun_sect": yun_sect, "place": birth_place or "",
            }
            log.info("已挂载命盘上下文: {} {} user={}", birth_time, gender, user_id)
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
            self.set_chart_context(birth_time, gender, sect, yun_sect, birth_place=extract_birth_place(text) or "")
            return True
        # 已有待确认八字候选：尝试把本轮输入解析为用户的选择
        if self._bazi_pending:
            bt = resolve_bazi_selection(text, self._bazi_pending)
            if bt:
                self.set_chart_context(bt, self._bazi_pending["gender"], sect, yun_sect)
                self._bazi_pending = None
                return True
        # 首次检测到八字：反推候选日期，交由 LLM 向用户确认
        pillars, gender = extract_pillars(text)
        if pillars and gender:
            try:
                cands = find_birth_dates_from_pillars(pillars, gender, top_n=3)
            except Exception:
                cands = []
            self._bazi_pending = {"pillars": pillars, "gender": gender, "candidates": cands}
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
                    self._bazi_pending.get("pillars"), self._bazi_pending.get("gender"))
                if cands:
                    for i, c in enumerate(cands, 1):
                        block += "  {}. {}（{}，{}）\n".format(i, c.get("birth_time"), c.get("ganzhi"), c.get("shi_chen"))
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
        """
        if mcp_manager.available:
            self.available_tools = list(self._local_tools) + mcp_manager.get_tools()
            self._llm_with_tools = self.chat_model.bind_tools(self.available_tools)
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

    def _finalize_stream(self, src_stream):
        """包装原 stream，在末尾追加命盘摘要段（若已挂载 chart_context）。"""
        for chunk in src_stream:
            yield chunk
        if not self.chart_context:
            return
        summary = self._extract_chart_summary()
        if summary and "年柱" in summary:
            yield "\n[回答] 命盘四柱关键信息（用于可视化展示）：\n【四柱】\n{}".format(summary)

    def _filter_steps(self, src_iter):
        """包装原始流：内部消费 ReAct 步骤并写入日志，仅产出最终回答。

        - 内部所有 Step/工具输出/观察都只走 `log.info`，不外发
        - 仅当 LLM 在某一步选择不再调用工具（即真正回答用户）时，
          把 final_answer 推给前端
        - 若 LLM 终止时无文本（如直接 do_terminate 且无正文），给出兜底提示
        """
        for _ in src_iter:
            # 步骤输出已通过 ReActAgent.step 内部的 log.info 记录
            # 这里无需再打，避免日志重复
            pass
        final = (self.final_answer or "").strip()
        if final:
            yield final
        elif self.state == AgentState.ERROR or self._last_error:
            err = (self._last_error or "未知错误").strip()
            log.warning("[xianzhi] 终止于错误: {}", err)
            yield "分析过程中遇到错误：{}。请稍后重试。".format(err[:200])
        else:
            # LLM 仅触发 do_terminate 等工具、无文本回答时，
            # 前端已通过 /api/ai/xianzhi/chart 拿到结构化命盘数据
            log.info("[xianzhi] 终止时无文本回答，仅返回工具结果")

    def _run_workflow_once(self, user_prompt: str, history_snapshot=None, summary: str = "") -> str:
        """Run the chart-grounded workflow for one turn."""
        if not self._workflow_context:
            raise RuntimeError("workflow context is not mounted")
        history = list(history_snapshot) if history_snapshot is not None else list(self.message_list)
        answer = self._workflow.answer(user_prompt, self._workflow_context, history, summary)
        return answer

    def _workflow_stream(self, user_prompt: str):
        try:
            self.state = AgentState.RUNNING
            history_snapshot = list(self.message_list)
            summary = self._get_session_summary()
            self.message_list.append(HumanMessage(content=user_prompt))
            answer = self._run_workflow_once(user_prompt, history_snapshot, summary)
            self.final_answer = answer
            self.message_list.append(AIMessage(content=answer))
            self.state = AgentState.FINISHED
            yield answer
        except Exception as e:
            self.state = AgentState.ERROR
            self._last_error = str(e)
            log.exception("Xianzhi workflow error")
            yield "分析过程遇到错误：{}。请稍后重试。".format(str(e)[:200])
        finally:
            self.cleanup()

    async def _aworkflow_stream(self, user_prompt: str):
        try:
            self.state = AgentState.RUNNING
            history_snapshot = list(self.message_list)
            summary = self._get_session_summary()
            self.message_list.append(HumanMessage(content=user_prompt))
            answer = await asyncio.to_thread(self._run_workflow_once, user_prompt, history_snapshot, summary)
            self.final_answer = answer
            self.message_list.append(AIMessage(content=answer))
            self.state = AgentState.FINISHED
            yield answer
        except Exception as e:
            self.state = AgentState.ERROR
            self._last_error = str(e)
            log.exception("Xianzhi workflow error")
            yield "分析过程遇到错误：{}。请稍后重试。".format(str(e)[:200])
        finally:
            self.cleanup()

    def _is_chitchat(self, user_prompt: str) -> bool:
        """判断是否为闲聊场景（无命盘时短路 ReAct，避免无谓工具调用）。

        放行条件（任一命中即不走闲聊短路）：
        - _workflow_context：有完整命盘，走 workflow
        - _bazi_pending：八字待确认候选，走 ReAct 调 bazi_infer_dates
        - _birth_signal：模糊生辰信号（农历/节日/时辰/公历+时辰），走 ReAct 调 bazi_full
        """
        if self._workflow_context:
            return False  # 有命盘走 workflow，chitchat 由 workflow 内部处理
        if self._bazi_pending:
            return False  # 八字待确认候选：必须走 ReAct，让 LLM 调 bazi_infer_dates 展示候选
        if self._birth_signal:
            return False  # 模糊生辰：走 ReAct，让 LLM 调 bazi_full（内部自动转公历）
        intent = classify_question(user_prompt)
        return intent.domain == "chitchat"

    def _chitchat_reply(self, user_prompt: str) -> str:
        """闲聊短路：直接调一次 LLM，不走 ReAct 循环，不调任何工具。"""
        log.info("[xianzhi] 闲聊短路，跳过 ReAct 工具调用")
        self.state = AgentState.RUNNING
        self.message_list.append(HumanMessage(content=user_prompt))
        try:
            history_ctx = "\n".join(
                f"{m.__class__.__name__.replace('Message','')}: {str(getattr(m,'content',''))[:180]}"
                for m in self.message_list[-6:]
                if str(getattr(m, "content", "")).strip()
            ) or "（无）"
            messages = [
                SystemMessage(content=CHITCHAT_SYSTEM),
                HumanMessage(content=(
                    f"【最近对话】\n{history_ctx}\n\n"
                    f"【用户说】\n{user_prompt}\n\n"
                    "请自然回应。"
                )),
            ]
            response = self.chat_model.invoke(messages)
            content = (getattr(response, "content", "") or "").strip()
            content = clean_think_tags(content)
            content = _dedupe_content(content) if content else ""
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
        """同步流式执行。

        Args:
            user_prompt: 用户输入
            verbose: True=透传 ReAct 步骤（调试用），False=只输出最终回答
        """
        self.reset()
        if not self.chart_context:
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
        # 直接调用 BaseAgent.run_stream（绕开 ToolCallAgent.run_stream 的二次 reset，
        # 避免历史被清空；同时让 step 输出走 BaseAgent 的日志逻辑）
        base_stream = BaseAgent.run_stream(self, user_prompt)
        if verbose:
            return self._finalize_stream(base_stream)
        return self._filter_steps(base_stream)

    async def arun_stream(self, user_prompt, verbose: bool = False):
        """异步流式执行。

        Args:
            user_prompt: 用户输入
            verbose: True=透传 ReAct 步骤（调试用），False=只输出最终回答
        """
        self.reset()
        self.mount_chart_context(user_prompt, self._sect, self._yun_sect)
        self._load_history()
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
                self.cleanup()
            return
        if verbose:
            async for chunk in super().arun_stream(user_prompt):
                yield chunk
            # verbose 模式下仍追加 chart 兜底（保持原有行为）
            if self.chart_context:
                summary = self._extract_chart_summary()
                if summary and "年柱" in summary:
                    yield "\n[回答] 命盘四柱关键信息（用于可视化展示）：\n【四柱】\n{}".format(summary)
            return
        # 正常模式：直接走 ReAct 工具循环，LLM 自行决定是否调 search_knowledge
        async for _ in super().arun_stream(user_prompt):
            pass
        final = (self.final_answer or "").strip()
        if final:
            yield _dedupe_content(final)
        elif self.state == AgentState.ERROR or self._last_error:
            err = (self._last_error or "未知错误").strip()
            log.warning("[xianzhi] 终止于错误: {}", err)
            yield "分析过程中遇到错误：{}。请稍后重试。".format(err[:200])
        else:
            log.info("[xianzhi] 终止时无文本回答，仅返回工具结果")

    def _load_history(self):
        history = self._memory.get(self._conversation_id)
        if history:
            max_tokens = 2000
            total_tokens = 0
            selected = []
            for msg in reversed(history):
                content = msg.content if hasattr(msg, "content") else str(msg)
                # 中文场景下 1 字符 ≈ 1.5 token（英文≈0.25），取折中系数
                cn_chars = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
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
        new_messages = self.message_list[self._history_len:]
        if new_messages:
            # 过滤 next_step_prompt 注入的 HumanMessage（其内容以工具调度模板开头）
            filtered = [
                m for m in new_messages
                if not (m.__class__.__name__ == "HumanMessage"
                        and isinstance(getattr(m, "content", ""), str)
                        and ("根据用户需求选最合适的工具，复杂任务分解多步" in m.content
                             or "你是先知，按以下顺序自主规划与调工具完成任务" in m.content))
            ]
            if filtered:
                self._memory.add(self._conversation_id, filtered)
        # 每 6 轮对话（一问一答=1轮，约12条消息）触发摘要（异步，不阻塞主流程）
        self._maybe_summarize()

    def _get_session_summary(self) -> str:
        """从会话元数据中获取历史摘要。"""
        try:
            return self._memory.get_summary(self._conversation_id)
        except Exception as e:
            log.warning("获取会话摘要失败: {}", e)
            return ""

    def _maybe_summarize(self):
        """每 6 轮对话触发一次增量摘要（一问一答=1轮，约12条消息；后台线程异步，不阻塞当次请求）。

        阈值判断与数据快照在主线程完成（线程安全）；
        LLM 调用与落库放进 daemon 线程，避免拖慢用户响应。
        摘要上限 600 字，增量累积：旧摘要 + 最近 12 条（约6轮）消息 → 新摘要。
        """
        try:
            msg_count = self._memory.get_message_count(self._conversation_id)
            last_summary_count = self._memory.get_last_summary_count(self._conversation_id)
            new_since_last = msg_count - last_summary_count
            if new_since_last < 12:
                return

            # ---- 主线程：先取线程安全所需的快照（避免线程内读共享状态）----
            old_summary = self._get_session_summary()
            recent = self.message_list[-12:]
            recent_text = "\n".join(
                f"{m.__class__.__name__.replace('Message', '')}: {str(getattr(m, 'content', ''))[:300]}"
                for m in recent if str(getattr(m, "content", "")).strip()
            )

            # ---- 后台线程：执行 LLM 摘要与落库 ----
            def _run():
                """调用摘要模型，基于旧摘要与最近对话生成不超过 600 字的增量摘要。

                只保留身份/人生事件、对前次分析的修正、待确认事项；丢弃闲聊与非命理内容，
                以缓解长会话的上下文膨胀。
                """
                try:
                    prompt = (
                        "你是一个会话摘要助手。请根据【旧摘要】和【最近对话】，生成不超过 600 字的增量摘要。\n"
                        "只保留以下事实，忽略闲聊、问候、天气、发牢骚、流水账、长文本等非命理内容：\n"
                        "- 用户身份/人生事件：年龄、职业、婚姻、健康、已确认的断事结论；\n"
                        "- 用户对之前分析的修正或反馈（如\"上次说我身弱不对\"）——必须保留，避免重复旧错；\n"
                        "- 待确认事项（如\"用户给了八字但未确认出生日期\"）。\n"
                        "合并同类项，丢弃过时或冗余信息，保持简洁。\n\n"
                        f"【旧摘要】\n{old_summary or '（无）'}\n\n"
                        f"【最近对话】\n{recent_text}\n\n"
                        "请输出新摘要（不超过 600 字）："
                    )
                    log.info("[摘要] 会话 {} 开始生成摘要...", self._conversation_id)
                    resp = self.chat_model.invoke([
                        SystemMessage(content="你是会话摘要助手，只输出摘要文本，不输出任何解释。"),
                        HumanMessage(content=prompt),
                    ])
                    new_summary = (getattr(resp, "content", "") or "").strip()
                    if new_summary and len(new_summary) > 10:
                        # 确保不超过 600 字
                        if len(new_summary) > 600:
                            new_summary = new_summary[:600]
                        self._memory.save_summary(self._conversation_id, new_summary, msg_count)
                        log.info("[摘要] 会话 {} 已生成摘要 ({}字, 消息数={})",
                                 self._conversation_id, len(new_summary), msg_count)
                except Exception as e:
                    log.warning("会话摘要生成失败（后台线程）: {}", e)

            threading.Thread(target=_run, daemon=True).start()
        except Exception as e:
            log.warning("会话摘要触发失败: {}", e)

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
