"""先知 - 八字命理分析预测智能体

基于 ToolCallAgent，拥有自主规划能力，可直接使用。
工具集 = 本地工具（八字/搜索/终止）+ MCP 工具（高德地图）。
"""
from __future__ import annotations

import re
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_core.language_models import BaseChatModel

from app.agent.base_agent import AgentState, BaseAgent
from app.agent.tool_call_agent import ToolCallAgent
from app.config import settings
from app.logger import log
from app.memory import create_chat_memory
from app.tools.mcp_client import mcp_manager
import asyncio


def _dedupe_final(text: str) -> str:
    """检测并移除完全重复的内容（推理模型 think 块泄漏的兜底）。"""
    text = text.strip()
    if len(text) < 100:
        return text
    mid = len(text) // 2
    if text[:mid].strip() == text[mid:].strip() and len(text[:mid].strip()) > 50:
        log.warning("[xianzhi] 检测到 LLM 输出内容重复，已去重")
        return text[:mid].strip()
    return text

from app.agent.xianzhi_workflow import XianzhiWorkflow, WorkflowChartContext, build_chart_context, render_full_fact_context, classify_question
from app.tools.bazi import _normalize_birth_time


# 用于从用户输入中尝试提取出生时间与性别
_BIRTH_INFO_RE = re.compile(
    r"(?P<gender>男|女)[^\d]*(?P<year>\d{4})[-年/](?P<month>\d{1,2})[-月/](?P<day>\d{1,2})[日\s]*(?P<hour>\d{1,2})[:：](?P<minute>\d{1,2})",
    re.UNICODE,
)
_BIRTH_INFO_RE2 = re.compile(
    r"(?P<year>\d{4})[-年/](?P<month>\d{1,2})[-月/](?P<day>\d{1,2})[日\s]*(?P<hour>\d{1,2})[:：](?P<minute>\d{1,2})[^\d]*(?P<gender>男|女)",
    re.UNICODE,
)


SYSTEM_PROMPT = """你是先知，拥有数十年实战经验的八字命理师傅，气质通透沉稳，像阅历丰富的老友。

身份与能力：
- 精通四柱八字、五行十神、大运流年、合婚择日；熟读渊海子平、子平真诠、滴天髓、穷通宝鉴、三命通会，论命引经据典但不堆砌古文

知识库强制规则：
1. 解释术语、排盘规则、专项断事（婚姻/健康/官非/学业）前，必须调用search_knowledge检索知识库；
2. 分析具体命局时主动检索古籍论断、同类命例作为判断佐证；
3. 所有引用古籍原文、断语必须来源于检索结果，严禁自行编造；
4. 知识库取用优先级：调候参考《穷通宝鉴》、格局以《子平真诠》为准、基础理论取自《渊海子平》、神煞杂断参考《三命通会》；多流派理论冲突时，以调候+扶抑格局为核心折中判断；
5. 典籍引用统一格式：论断后标注「《典籍名》原文：XXX」，简短自然嵌入，不单独大段摘抄。
6. 引用边界：检索结果来源含「古籍·《XXX》」标签的才能以「《典籍名》原文：」格式引用；来源是「规则卡/断法/流程/命例库/术语表」等内部参考文档时，只能意译其要点融入回答，禁止以「《XX规则卡》原文：」「《XX断法》原文：」等格式引用，也禁止在回答中出现「婚恋关系规则卡」「大运流年咨询规则卡」等内部文档标题。

合规红线（严格遵守）：
不推断生死、不指导赌博投机、不宣扬符咒改运、不提供堕胎择时；涉及重病、牢狱等凶险信息，优先劝导用户寻求医院、律师等现实专业帮助。

说话风格：
- 真人聊天感，不用表格、多层标题、emoji；该幽默幽默（调侃桃花旺、财来财去等），该严肃严肃（健康、刑冲等）
- 闲聊时回复不围绕命盘，根据心境适当回应，可参杂人生哲理、处世良言，引发情感共鸣
- 篇幅规范：闲聊1-3句≤150字；简单问题≤200字；常规分析2-3段≤350字；用户主动要求完整详批、终身格局，可放宽篇幅
- 用"你"不用"您"，自然口语化，可适当用语气词；不确定直说"这个要看具体情况"，不绝对化
- 避免AI腔：不要"总结一下""需要注意的是""好消息/需要注意"这种模板

核心原则：
- 客观理性，秉持命由天定、运由己造，不制造焦虑
- 排盘必须确认用户提供了：出生时间（年月日时）和性别
- 日期处理（重要）：所有排盘工具（bazi_chart/bazi_full/bazi_analysis 等）均直接支持公历、农历、传统时辰、农历节日（如"端午""中秋"）等多种输入格式，可直接将用户原始表达传给工具，无需预先换算。示例：bazi_chart 可直接接收 "农历2004年五月初五 辰时" 或 "1990-05-20 辰时"。仅当需要向用户展示公历对照或自行校验换算结果时，才调用 lunar_to_solar 辅助工具
- 知识库检索技巧：search_knowledge 的 query 用泛化关键词（如"男命婚姻 财星 劫财"），不要带具体日柱或干支组合
"""

NEXT_STEP_PROMPT = """根据用户需求选择最合适的工具，复杂任务可分解逐步解决。任务完成时调用 do_terminate。

执行顺序：
1. 纯理论/术语问题 → 仅调 search_knowledge
2. 命局分析 → 先确认生辰性别 → 排盘工具（可直接接收农历/时辰/节日表达）→ search_knowledge 查佐证 → 回答
3. 合婚 → 需双方生辰性别

工具用途：
- lunar_to_solar: 农历日期/节日/时辰转公历的辅助工具（如"2004年端午节 辰时" → "2004-06-22 08:00"）。需向用户展示公历对照或自行校验换算时调用；排盘工具已内置农历支持，无需强制先调本工具
- bazi_full: 完整排盘（详批/终身格局首调，信息最全）。支持公历、农历、时辰输入
- bazi_chart/bazi_analysis/bazi_dayun/bazi_liunian/bazi_liuyue/bazi_liuri: 单项查询（简单问某项时用，勿与 bazi_full 同轮重复调用）
- bazi_hehun: 合婚分析
- search_knowledge: 命理知识库（术语/理论/断法/古籍/命例）；query 用泛化词，不带具体干支
- search_web: 联网查询（实时信息、非命理问题）
- do_terminate: 任务完成
"""


FACT_GUARDRAILS = """
【事实与表达护栏】
- 四柱、大运、流年、起运时间等硬事实只能引用上方系统排盘结果，不要自行推算或改写。
- 若用户问某一年、某阶段，先定位对应大运与流年，再解释影响。
- 知识库检索无匹配古籍条文时，如实告知暂无对应古法论断，仅依靠五行十神基础逻辑分析，不杜撰古文。
- 纳音、神煞仅作辅助参考，所有核心吉凶判断必须以正五行、十神、格局、用神、月令节气、原局流通为根基。
- 涉及重疾、官非、离异等重大负面信息，先给出现实层面解决建议，再讲命理参考，不放大恐慌。
- 遇到立春换年、早/夜子时、真太阳时争议，主动说明不同流派口径，不单方面下定论。
"""

class Xianzhi(ToolCallAgent):
    """先知智能体"""

    # 排盘工具名集合：调用这些工具时，从参数中提取 birth_time/gender
    _BAZI_TOOLS = {"bazi_chart", "bazi_full", "bazi_analysis", "bazi_dayun", "bazi_liunian", "bazi_liuyue", "bazi_liuri"}

    def __init__(self, chat_model, local_tools, max_steps=None):
        super().__init__(
            name="Xianzhi",
            chat_model=chat_model,
            tools=local_tools,
            system_prompt=SYSTEM_PROMPT,
            next_step_prompt=NEXT_STEP_PROMPT,
            max_steps=max_steps or settings.agent_max_steps,
        )
        self._local_tools = local_tools
        self._conversation_id = "xianzhi-default"
        self._memory = create_chat_memory()
        self.chart_context = ""
        self._workflow = XianzhiWorkflow(chat_model)
        self._workflow_context: WorkflowChartContext | None = None
        self._last_birth_info: Optional[dict] = None
        self._sect = 2
        self._yun_sect = 1
        self._lock = asyncio.Lock()

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
        self._conversation_id = new_id

    def reset(self):
        """重置 Agent 运行状态（父类 run_stream 会调用，需补齐）。"""
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

    def set_chart_context(self, birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1):
        """由外部直接设置当前命盘上下文，AI 回答将基于该盘面。

        Args:
            birth_time: 出生时间，支持公历(YYYY-MM-DD HH:MM)、公历+时辰(YYYY-MM-DD 辰时)、
                       农历(农历1990年四月廿六 14:30)、农历节日(2004年端午节 辰时) 等格式
            gender: 性别，男 或 女
            sect: 日柱计算流派，1=按日期精确，2=按日期精确2（默认）
            yun_sect: 大运计算流派，1=按天数和时辰数（默认），2=按分钟数
        """
        try:
            # 与 bazi_chart 工具入口一致：先标准化为公历，支持农历/时辰/节日输入
            birth_time = _normalize_birth_time(birth_time)
            workflow_context = build_chart_context(birth_time, gender, sect, yun_sect)
            chart = render_full_fact_context(workflow_context)
            self.chart_context = (
                "【当前命盘上下文】\n"
                "以下盘面信息已由系统根据用户提供的出生时间自动排盘生成，"
                "请你在后续回答中优先基于该命盘进行推理与分析，无需再次排盘：\n\n"
                f"{chart}\n"
            )
            self._workflow_context = workflow_context
            self._last_birth_info = {"time": birth_time, "gender": gender, "sect": sect, "yun_sect": yun_sect}
            log.info("已挂载命盘上下文: {} {}", birth_time, gender)
        except Exception as e:
            log.warning("挂载命盘上下文失败: {}", e)
            self.chart_context = ""
            self._workflow_context = None
            self._last_birth_info = None

    def _extract_birth_info(self, text: str):
        """从用户输入中提取出生时间和性别。"""
        for pattern in (_BIRTH_INFO_RE, _BIRTH_INFO_RE2):
            m = pattern.search(text)
            if m:
                d = m.groupdict()
                birth_time = "{}-{:02d}-{:02d} {:02d}:{:02d}".format(
                    int(d["year"]), int(d["month"]), int(d["day"]),
                    int(d["hour"]), int(d["minute"]),
                )
                return birth_time, d["gender"]
        return None, None

    def mount_chart_context(self, text: str, sect: int = 2, yun_sect: int = 1):
        """如果用户输入包含出生信息，自动挂载命盘上下文。"""
        birth_time, gender = self._extract_birth_info(text)
        if birth_time and gender:
            self.set_chart_context(birth_time, gender, sect, yun_sect)
            return True
        return False

    def _build_messages(self):
        """构建发送给 LLM 的消息列表，附加命盘上下文到 system prompt。"""
        msgs = []
        if self.system_prompt:
            content = self.system_prompt
            if self.chart_context:
                content += "\n\n" + self.chart_context
                content += "\n\n" + FACT_GUARDRAILS
            msgs.append(SystemMessage(content=content))
        msgs.extend(self.message_list)
        return msgs

    def run(self, user_prompt):
        self.reset()
        self.mount_chart_context(user_prompt, self._sect, self._yun_sect)
        self._load_history()
        if self._workflow_context:
            chunks = list(self._workflow_stream(user_prompt))
            return chunks[-1] if chunks else ""
        return super().run(user_prompt)

    def think(self):
        if mcp_manager.available:
            self.available_tools = list(self._local_tools) + mcp_manager.get_tools()
            self._llm_with_tools = self.chat_model.bind_tools(self.available_tools)
        result = super().think()
        # 拦截排盘工具调用，从参数中提取 birth_time/gender（覆盖自然语言输入场景）
        self._capture_birth_from_tool_calls()
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
                        self.set_chart_context(bt, gd, self._sect, self._yun_sect)
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

    def _run_workflow_once(self, user_prompt: str, history_snapshot=None) -> str:
        """Run the chart-grounded workflow for one turn."""
        if not self._workflow_context:
            raise RuntimeError("workflow context is not mounted")
        history = list(history_snapshot) if history_snapshot is not None else list(self.message_list)
        answer = self._workflow.answer(user_prompt, self._workflow_context, history)
        return answer

    def _workflow_stream(self, user_prompt: str):
        try:
            self.state = AgentState.RUNNING
            history_snapshot = list(self.message_list)
            self.message_list.append(HumanMessage(content=user_prompt))
            answer = self._run_workflow_once(user_prompt, history_snapshot)
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
            self.message_list.append(HumanMessage(content=user_prompt))
            answer = await asyncio.to_thread(self._run_workflow_once, user_prompt, history_snapshot)
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
        """判断是否为闲聊场景（无命盘时短路 ReAct，避免无谓工具调用）。"""
        if self._workflow_context:
            return False  # 有命盘走 workflow，chitchat 由 workflow 内部处理
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
                SystemMessage(content=(
                    "你是先知，一位通透沉稳、阅历丰富的老友。"
                    "用户现在和你闲聊，不问命理问题。"
                    "根据用户心境自然回应，可参杂人生哲理、处世良言，引发情感共鸣。"
                    "1-3句，≤150字，像朋友聊天，不用表格、标题、emoji。"
                    "用'你'不用'您'，口语化。不要'总结一下'这种AI腔。"
                )),
                HumanMessage(content=(
                    f"【最近对话】\n{history_ctx}\n\n"
                    f"【用户说】\n{user_prompt}\n\n"
                    "请自然回应。"
                )),
            ]
            response = self.chat_model.invoke(messages)
            content = (getattr(response, "content", "") or "").strip()
            content = re.sub(r"<think>[\s\S]*?</think>\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(r"<think>[\s\S]*$", "", content, flags=re.IGNORECASE)
            content = _dedupe_final(content) if content else ""
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
                yield self._chitchat_reply(user_prompt)
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
            reply = await asyncio.to_thread(self._chitchat_reply, user_prompt)
            yield reply
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
        # 正常模式：仅返回 LLM 的最终回答
        async for _ in super().arun_stream(user_prompt):
            pass
        final = (self.final_answer or "").strip()
        if final:
            yield _dedupe_final(final)
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
        from app.agent.tool_call_agent import ToolCallAgent
        new_messages = self.message_list[self._history_len:]
        if new_messages:
            # 过滤 next_step_prompt 注入的 HumanMessage（其内容以工具调度模板开头）
            filtered = [
                m for m in new_messages
                if not (m.__class__.__name__ == "HumanMessage"
                        and isinstance(getattr(m, "content", ""), str)
                        and "根据用户需求，主动选择最合适的工具" in m.content)
            ]
            if filtered:
                self._memory.add(self._conversation_id, filtered)

    def cleanup(self):
        self._persist_history()
        # 命盘上下文持久化到会话：不清空，下一轮同会话仍可用
        # 仅在切换会话（set_conversation_id）时才主动清空
        super().cleanup()
