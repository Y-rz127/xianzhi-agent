"""工作流数据模型：意图/命盘上下文/事实校验结果/Worker 协议与领域配置。

R9 拆分自 xianzhi_workflow.py。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.bazi_engine import BaziChart

DOMAIN_LABELS = {
    "career": "事业工作",
    "wealth": "财运收入",
    "love": "恋爱感情",
    "marriage": "婚姻关系",
    "health": "健康状态",
    "liunian": "大运流年",
    "study": "学习考试",
    "social": "社交人际",
    "family": "六亲关系",
    "personality": "性格心性",
    "migration": "方位迁移",
    "naming": "起名改名",
    "auspicious": "择吉择日",
    "match": "合婚配对",
    "children": "子女生育",
    "theory": "术语理论",
    "chitchat": "闲聊问候",
    "general": "综合咨询",
}


@dataclass(frozen=True)
class QuestionIntent:
    """用户问题意图分类结果。

    Supervisor 用它决定分派哪个专业 Worker，以及检索哪些知识。
    合婚(match)场景下额外携带对方出生信息/命盘/规则基础数据。
    """
    domain: str
    label: str
    target_years: list[int] = field(default_factory=list)
    wants_report: bool = False
    confidence: float = 0.5
    needs_chart: bool = False  # 用户是否在问自己命盘的具体判断（如"我是不是枭神夺食"）
    queries: tuple[str, ...] = ()  # LLM 拆解出的精准检索词（空=走硬编码 fallback）
    other_birth_time: str = ""  # match 合婚：用户问题中提供的「对方」出生时间
    other_gender: str = ""      # match 合婚：对方的性别（男/女）
    second_chart: Any = None    # match 合婚：解析出的对方命盘（WorkflowChartContext）
    match_basis: str = ""       # match 合婚：系统规则合婚基础数据（bazi_hehun 产出）


@dataclass
class WorkflowChartContext:
    """工作流用的命盘上下文容器。

    保存原始输入（birth_time/gender/sect/yun_sect/user_id/longitude）与已排好的 BaziChart，
    供 Supervisor/Worker/Reviewer 共享同一排盘事实，避免重复计算。
    user_id 用于从命盘画像中加载历史断事知识；
    longitude 为出生地东经度数（0=未提供，不做真太阳时校正），合婚时透传给对方命盘。
    """
    birth_time: str
    gender: str
    sect: int
    yun_sect: int
    chart: BaziChart
    user_id: str = ""
    longitude: float = 0.0


@dataclass(frozen=True)
class FactCheckResult:
    """事实校验结果：ok 表示通过全部校验，issues 为发现的问题列表。"""
    ok: bool
    issues: list[str] = field(default_factory=list)
    source: str = ""  # "regex" | "llm" | "both" | "regex_fallback"


@dataclass(frozen=True)
class WorkerResult:
    """Worker 返回的最小结果协议（不返回完整对话历史，避免上下文爆炸）。"""
    status: str  # "done" | "blocked" | "failed"
    summary: str  # 断语结论
    evidence: list[str] = field(default_factory=list)  # 古籍引用 + 检索片段
    risks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DomainWorker:
    """领域 Worker 配置：专属断法 prompt + 额外检索 query。

    Supervisor（XianzhiWorkflow.answer）按 intent.domain 分派给对应 Worker。
    Worker 只持有"专业领域知识"，执行逻辑复用 Supervisor 的 _retrieve_rules / _build_messages / _invoke。
    """
    domain: str
    label: str
    expertise_prompt: str  # 追加到通用 system prompt 末尾的领域断法规则
    extra_queries: tuple[str, ...] = ()  # 叠加到 DOMAIN_RULE_QUERIES 之外的领域专属检索
    length_rule: str = "默认控制在2-4段，先结论后依据,不要堆砌术语。"
    skip_facts: bool = False  # theory/chitchat 跳过命盘事实注入
