"""先知 - 八字命理分析预测智能体（对应 Java 的 Manus）。

基于 ToolCallAgent，拥有自主规划能力，可直接使用。
工具集 = 本地工具（八字/搜索/终止）+ MCP 工具（高德地图）。
"""
from __future__ import annotations

import re
from typing import Optional

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langchain_core.language_models import BaseChatModel

from app.agent.base_agent import AgentState, BaseAgent
from app.agent.tool_call_agent import ToolCallAgent
from app.config import settings
from app.logger import log
from app.memory import create_chat_memory
from app.tools.mcp_client import mcp_manager
import asyncio

from app.tools.bazi import bazi_full


# 用于从用户输入中尝试提取出生时间与性别
_BIRTH_INFO_RE = re.compile(
    r"(?P<gender>男|女)[^\d]*(?P<year>\d{4})[-年/](?P<month>\d{1,2})[-月/](?P<day>\d{1,2})[日\s]*(?P<hour>\d{1,2})[:：](?P<minute>\d{1,2})",
    re.UNICODE,
)
_BIRTH_INFO_RE2 = re.compile(
    r"(?P<year>\d{4})[-年/](?P<month>\d{1,2})[-月/](?P<day>\d{1,2})[日\s]*(?P<hour>\d{1,2})[:：](?P<minute>\d{1,2})[^\d]*(?P<gender>男|女)",
    re.UNICODE,
)


SYSTEM_PROMPT = """你是先知，一位精通八字命理的预测师，旨在解决用户提出的命理分析需求。
你拥有多种工具可以调用，以高效完成复杂请求。

能力范围：
- 根据出生时间排八字四柱（年柱、月柱、日柱、时柱）
- 分析五行强弱、十神关系、用神喜忌
- 推算大运（每10年一柱）、流年（逐年）、流月（逐月）、流日（逐日）
- 合婚分析：对比两个人的八字，分析五行互补程度
- 解答事业、感情、财运、健康等命理问题
- 通过高德地图 MCP 工具查询地理/天气信息（如出生地相关分析）
- 检索命理知识库（天干地支、五行生克、十神详解、用神喜忌等）

回答原则：
- 客观中立，不做绝对化断言
- 引导用户理性看待命理，命由天定、运由己造
- 需要排盘时先调用工具获取准确四柱，再行分析

- 排盘必须确认用户提供了：出生时间（年月日时）和性别
"""

NEXT_STEP_PROMPT = """根据用户需求，主动选择最合适的工具或组合工具。
对于复杂任务，可以分解问题、逐步使用工具解决。
若希望停止交互，调用 do_terminate 工具。

工具使用指引：
- bazi_chart: 排四柱基础信息（需 birth_time + gender）
- bazi_analysis: 五行十神分析（需 birth_time + gender + question）
- bazi_dayun: 推大运（需 birth_time + gender）
- bazi_liunian: 推流年（需 birth_time + gender）
- bazi_liuyue: 推流月（需 birth_time + gender + year）
- bazi_liuri: 推流日（需 birth_time + gender + year + month）
- bazi_hehun: 合婚分析（需 birth_time_a + gender_a + birth_time_b + gender_b）
- bazi_full: 一次性完整排盘（信息最全，推荐首调用）
- search_web: 联网搜索命理资料
- search_knowledge: 检索命理知识库（天干地支/五行/十神/用神/大运流年等专业理论）
- do_terminate: 任务完成时调用

排盘前请确认用户提供了完整的出生时间（年月日时）和性别，如缺失请先询问。
合婚分析需要双方的出生时间和性别。
"""


FACT_GUARDRAILS = """
【事实与表达护栏】
- 四柱、大运、流年、起运时间等硬事实只能引用上方系统排盘结果，不要自行推算或改写。
- 若用户问某一年、某阶段，先定位对应大运与流年，再解释影响。
- 回答要像真实命理师聊天：先直接给判断，再说2-4个关键依据，最后给具体建议或追问一个必要信息。
- 不要机械倾倒完整报告；除非用户要求“完整报告/详细分析”，默认保持短而有重点。
- 对不确定项要说明口径，例如立春边界、子时流派、出生地真太阳时，而不是强行断定。
"""

class Xianzhi(ToolCallAgent):
    """先知智能体（对应 Java Manus）。"""

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
        self._last_birth_info: Optional[dict] = None
        self._sect = 2
        self._yun_sect = 1
        self._lock = asyncio.Lock()

    def set_conversation_id(self, conversation_id):
        self._conversation_id = (
            conversation_id if conversation_id and conversation_id.strip()
            else "xianzhi-default"
        )

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

    def set_chart_context(self, birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1):
        """由外部直接设置当前命盘上下文，AI 回答将基于该盘面。

        Args:
            birth_time: 出生时间，格式 YYYY-MM-DD HH:MM
            gender: 性别，男 或 女
            sect: 日柱计算流派，1=按日期精确，2=按日期精确2（默认）
            yun_sect: 大运计算流派，1=按天数和时辰数（默认），2=按分钟数
        """
        try:
            chart = bazi_full.invoke({"birth_time": birth_time, "gender": gender, "sect": sect, "yun_sect": yun_sect})
            self.chart_context = (
                "【当前命盘上下文】\n"
                "以下盘面信息已由系统根据用户提供的出生时间自动排盘生成，"
                "请你在后续回答中优先基于该命盘进行推理与分析，无需再次排盘：\n\n"
                f"{chart}\n"
            )
            self._last_birth_info = {"time": birth_time, "gender": gender, "sect": sect, "yun_sect": yun_sect}
            log.info("已挂载命盘上下文: {} {}", birth_time, gender)
        except Exception as e:
            log.warning("挂载命盘上下文失败: {}", e)
            self.chart_context = ""
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
        return super().run(user_prompt)

    def think(self):
        if mcp_manager.available:
            self.available_tools = list(self._local_tools) + mcp_manager.get_tools()
            self._llm_with_tools = self.chat_model.bind_tools(self.available_tools)
        return super().think()

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

    def run_stream(self, user_prompt, verbose: bool = False):
        """同步流式执行。

        Args:
            user_prompt: 用户输入
            verbose: True=透传 ReAct 步骤（调试用），False=只输出最终回答
        """
        self.reset()
        self.mount_chart_context(user_prompt, self._sect, self._yun_sect)
        self._load_history()
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
            yield final
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
                token_count = len(content) // 4
                if total_tokens + token_count <= max_tokens:
                    selected.append(msg)
                    total_tokens += token_count
                else:
                    break
            self.message_list = list(reversed(selected))

    def _persist_history(self):
        """持久化当前轮次新消息（追加模式，避免 clear+add 丢历史）。"""
        if self.message_list:
            self._memory.add(self._conversation_id, self.message_list)

    def cleanup(self):
        self._persist_history()
        # 清理当前轮次的命盘上下文，避免跨会话污染
        self.chart_context = ""
        self._last_birth_info = None
        super().cleanup()
