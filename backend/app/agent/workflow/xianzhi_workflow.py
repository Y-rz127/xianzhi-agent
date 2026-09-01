"""基于先知图表的确定性工作流（兼容门面）。

R9 拆分：意图/模型/Worker 注册表/Reviewer 已拆至
- workflow_models   数据模型（QuestionIntent/WorkflowChartContext/Worker 协议）
- workflow_support  工具与意图分类（容错 JSON/命理信号正则/classify_question）
- workflow_workers  WORKERS 注册表 + ReviewerWorker

本模块保留 Supervisor（XianzhiWorkflow）与全部原公共符号重导出，既有 import 无需改动。
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import replace

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agent.prompts import (
    domain_sysprompt,
)

# 消息装配 / 事实校验职责已抽离至 workflow_messages（解耦单一职责模块）
from app.agent.workflow.workflow_messages import (  # noqa: F401
    build_messages,
    build_repair_messages,
    check_facts,
    compact_facts,
    compact_history,
    fact_block,
    get_chart_facts_text,
    invoke,
)

# ---- R9 拆分：子模块符号重导出（既有 import 不变） ----
from app.agent.workflow.workflow_models import (  # noqa: F401
    DOMAIN_LABELS,
    DomainWorker,
    FactCheckResult,
    QuestionIntent,
    WorkerResult,
    WorkflowChartContext,
)

# 检索 / 合婚对方盘解析职责已抽离至 workflow_retrieval（解耦单一职责模块）
from app.agent.workflow.workflow_retrieval import (  # noqa: F401
    build_match_basis,
    extend_chart_if_needed,
    parse_other_birth,
    retrieve_rules,
)
from app.agent.workflow.workflow_support import (  # noqa: F401
    _ALL_BAZI_SIGNALS,
    _OTHER_BIRTH_RE1,
    _OTHER_BIRTH_RE2,
    GANZHI_RE,
    YEAR_GANZHI_RE,
    _dedupe_content,
    _looks_off_topic,
    _parse_json,
    build_chart_context,
    classify_question,
    render_full_fact_context,
)
from app.agent.workflow.workflow_workers import (  # noqa: F401
    _REVIEWER_SYSTEM,
    WORKERS,
    ReviewerWorker,
)
from app.core.logger import log
from app.core.thinking_router import use_thinking

# 检索策略（领域关键词/领域检索词/理论术语检索词/术语识别）统一由 app.rag.retrieval 提供，
# 与 ReAct 工具路径（app/tools/rag_search.py）共用一套体系
from app.rag.retrieval import (
    detect_domain,
    detect_theory_topic,  # noqa: F401  # 测试仍从本模块导入
)


class XianzhiWorkflow:
    """Supervisor：意图分类 → 分派专业 Worker → Reviewer 审核 → Reflextion 修复。

    架构参考 学习资料/智能体开发笔记/16_多Agent协作：
    - Supervisor（本类）：决策、分派、验收、合并结果
    - 专业 Worker（WORKERS 注册表）：按领域专注单一断法
    - Reviewer（ReviewerWorker）：独立交叉校验
    """

    def __init__(
        self,
        chat_model: BaseChatModel,
        decompose_model: BaseChatModel | None = None,
        reviewer_model: BaseChatModel | None = None,
    ):
        self.chat_model = chat_model
        self._decompose_model = decompose_model or chat_model
        self._reviewer = ReviewerWorker(reviewer_model or chat_model)
        # 编排后端唯一为 LangGraph：构建失败即快速失败（启动期暴露），
        # 不再保留内置流水线双后端，避免两套实现行为分叉
        try:
            from app.agent.xianzhi_langgraph import create_xianzhi_graph

            self._graph = create_xianzhi_graph(self)
        except Exception as e:
            raise RuntimeError("LangGraph 编排后端构建失败（唯一编排实现，不可降级）: {}".format(e)) from e
        log.info("[workflow] LangGraph 编排已启用（唯一编排后端）")

    @property
    def backend(self) -> str:
        """编排后端（唯一实现：langgraph）。"""
        return "langgraph"

    # ===== LLM 意图拆解 =====
    _DECOMPOSE_SYSTEM = domain_sysprompt

    def _decompose_query(self, user_prompt: str) -> QuestionIntent | None:
        """用 LLM 拆解用户问题 → 意图分类 + 精准检索词。

        失败时返回 None，调用方 fallback 到 classify_question。
        使用独立的拆解模型（轻量快速），而非主模型。
        """
        if not self._decompose_model:
            return None
        try:
            messages = [
                SystemMessage(content=self._DECOMPOSE_SYSTEM),
                HumanMessage(content=user_prompt),
            ]
            resp = self._decompose_model.invoke(messages)
            raw = (getattr(resp, "content", "") or "").strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            data = _parse_json(raw)
            if not data or not isinstance(data, dict):
                return None
            domain = str(data.get("domain", "")).strip()
            if domain not in DOMAIN_LABELS:
                domain = "general"
            queries_raw = data.get("queries", [])
            if not isinstance(queries_raw, list):
                return None
            queries = tuple(str(q).strip() for q in queries_raw if str(q).strip())[:3]
            if not queries and domain != "chitchat":
                return None
            needs_chart = bool(data.get("needs_chart", False))
            other_birth_time = str(data.get("other_birth_time", "") or "").strip()
            other_gender = str(data.get("other_gender", "") or "").strip()
            # 年份提取复用原逻辑
            years = sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", user_prompt)})
            today = _dt.date.today()
            if "今年" in user_prompt:
                years.append(today.year)
            if "明年" in user_prompt:
                years.append(today.year + 1)
            years = sorted(set(years))
            wants_report = any(
                w in user_prompt for w in ("完整报告", "详细报告", "全面分析", "完整分析", "从头到尾")
            )
            intent = QuestionIntent(
                domain=domain,
                label=DOMAIN_LABELS.get(domain, "综合咨询"),
                target_years=years,
                wants_report=wants_report,
                confidence=0.9,
                needs_chart=needs_chart,
                queries=queries,
                other_birth_time=other_birth_time,
                other_gender=other_gender,
            )
            log.info("[LLM拆解] domain={} needs_chart={} queries={}", domain, needs_chart, list(queries))
            return intent
        except Exception as e:
            log.warning("[LLM拆解] 失败，fallback到关键词分类: {}", e)
            return None

    def answer(
        self,
        user_prompt: str,
        chart_context: WorkflowChartContext,
        history: list[BaseMessage] | None = None,
        summary: str = "",
    ) -> str:
        """端到端回答：问题拆解→（按需）补全盘→知识检索→拼装消息→调用 LLM→事实校验。

        闲聊（detect_domain 命中 chitchat）或明显题外话会短路，直接走分类不调 LLM 拆解，
        以节省 API 调用与时延。非闲聊路径会按需扩展命盘、检索知识库规则、组装 system/user
        消息并调用模型，最后用 check_facts 做事实一致性校验。
        """
        # 闲聊短路：关键词命中 chitchat 时直接走分类，不调用 LLM 拆解（节省 API 调用+时间）
        _chitchat_kw = detect_domain(user_prompt)
        if _chitchat_kw == "chitchat":
            intent = classify_question(user_prompt)
            log.info("[LLM拆解] 闲聊识别，跳过 LLM 拆解 → domain={}", intent.domain)
        elif _looks_off_topic(user_prompt):
            # 长文本 + 零命理信号 → 几乎确定是题外话，直接标记为 chitchat
            intent = classify_question(user_prompt)
            intent = replace(intent, domain="chitchat", label="闲聊问候")
            log.info("[LLM拆解] 长文本无命理信号，跳过 LLM 拆解 → domain=chitchat")
        else:
            intent = self._decompose_query(user_prompt) or classify_question(user_prompt)
        # ===== 合婚双盘：解析对方命盘（用户已挂载自己的盘，问题中给出对方盘）=====
        # 必须在 LangGraph 调用之前完成，否则图内节点读取不到 second_chart/match_basis
        if intent.domain == "match":
            ob, og = self._parse_other_birth(user_prompt)
            # LLM 拆解出的优先，正则兜底
            if not (ob and og) and intent.other_birth_time and intent.other_gender:
                ob, og = intent.other_birth_time, intent.other_gender
            if ob and og:
                try:
                    from app.domain.time_parse import _normalize_birth_time

                    ob_n = _normalize_birth_time(ob)
                    # 避免把用户自己的盘当成对方盘
                    if ob_n != chart_context.birth_time:
                        # 经度透传：对方命盘与用户命盘使用同一出生地做真太阳时校正
                        other_ctx = build_chart_context(
                            ob_n, og, chart_context.sect, chart_context.yun_sect,
                            longitude=chart_context.longitude,
                        )
                        basis = self._build_match_basis(chart_context, other_ctx)
                        intent = replace(intent, second_chart=other_ctx, match_basis=basis)
                        log.info("[match] 已解析对方命盘 {} {}，合婚基础数据{}字", ob_n, og, len(basis))
                    else:
                        log.info("[match] 解析出的对方命盘与用户自身盘相同，跳过")
                except Exception as e:
                    log.warning("[match] 解析对方命盘失败: {}", e)

        # ===== LangGraph 图编排：分类→扩盘→检索→生成→校验→修复（唯一执行路径） =====
        # 思考模式：闲聊（intent.domain=="chitchat"）关闭，其他路径开启；
        # 由 use_thinking 写入 contextvar，图内 generate/repair 节点的 chat_model.invoke 自动读取。
        # （llm_tag 在 Xianzhi._run_workflow_once 入口统一设置，覆盖本链路的成本归因）
        with use_thinking(intent.domain != "chitchat"):
            result = self._graph.invoke(
                {
                    "user_prompt": user_prompt,
                    "chart_context": chart_context,
                    "history": history or [],
                    "intent": intent,
                    "summary": summary,
                }
            )
        final = (result.get("final_answer") or "").strip()
        if not final:
            # 图各节点均保证非空 final_answer（_invoke 对空产出有兜底文案），
            # 走到这里说明编排存在缺陷，快速失败而非向用户返回空回复
            log.error("[workflow] LangGraph 未产出最终答案 (state keys={})", list(result.keys()))
            raise RuntimeError("编排工作流未产出最终答案")
        return final

    # ---- 解耦：以下检索/合婚职责已抽离至 app.agent.workflow.workflow_retrieval（纯函数模块） ----
    # 保留瘦委托方法，LangGraph 图节点仍以 workflow.<method> 方式调用，行为不变。
    def _extend_chart_if_needed(
        self, ctx: WorkflowChartContext, intent: QuestionIntent
    ) -> WorkflowChartContext:
        return extend_chart_if_needed(ctx, intent)

    def _parse_other_birth(self, text: str) -> tuple[str, str]:
        return parse_other_birth(text)

    def _build_match_basis(self, self_ctx: WorkflowChartContext, other_ctx: WorkflowChartContext) -> str:
        return build_match_basis(self_ctx, other_ctx)

    def _retrieve_rules(
        self,
        intent: QuestionIntent,
        ctx: WorkflowChartContext,
        worker: DomainWorker | None = None,
        user_text: str = "",
    ) -> str:
        return retrieve_rules(intent, ctx, worker, user_text)

    # ---- 解耦：消息装配 / 事实校验职责已抽离至 app.agent.workflow.workflow_messages（纯函数模块） ----
    # 保留瘦委托方法，LangGraph 图节点仍以 workflow.<method> 方式调用，行为不变。
    def _build_messages(self, user_prompt, intent, ctx, knowledge, history, worker=None, summary=""):
        return build_messages(user_prompt, intent, ctx, knowledge, history, worker, summary)

    def _build_repair_messages(self, raw_answer, checked, user_prompt, intent, ctx, knowledge, worker=None):
        return build_repair_messages(raw_answer, checked, user_prompt, intent, ctx, knowledge, worker)

    def _invoke(self, messages):
        return invoke(self.chat_model, messages)

    def check_facts(self, answer, chart, other_chart=None, needs_chart=True):
        return check_facts(answer, chart, other_chart, needs_chart)
