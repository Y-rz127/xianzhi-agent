# 先知智能体 · 多 Agent 协作架构

> **更新日期：2026-09-01**（按当前代码全面刷新；后端已整体迁入 `backend/` 子目录）
>
> **Supervisor + 专业 Worker + Reviewer** 三层架构，用于提升命理分析的准确性与严谨性。
> 编排后端**唯一为 LangGraph**（硬依赖，不再有内置流水线双后端与切换开关）。

## 架构概览

先知智能体对外有两条**入口路径**（按是否已挂载命盘分流，见下文「入口分流」），
其中 workflow 路径的编排**只由 LangGraph StateGraph 承担**：
`backend/app/agent/xianzhi_langgraph.py` 构建六节点有向图，节点逻辑委托
`XianzhiWorkflow` 的既有方法。`AppContext.workflow_backend()` 硬编码返回
`"langgraph"`（`app/api/context.py`），`XianzhiWorkflow.backend` 属性同值，
settings 中已无 workflow_backend 切换项；langgraph 为硬依赖
（`requirements.txt: langgraph>=1.0.0,<2.0.0`），图构建失败会在
`XianzhiWorkflow` 构造期直接抛 `RuntimeError` 快速失败，**不存在降级路径**。

```
用户问题
   │
   ▼
Xianzhi.run_stream / arun_stream（xianzhi.py）
   │ mount_chart_context：正则/模糊生辰/八字反推 → 挂载命盘？
   │
   ├─ 有命盘(_workflow_context) 且非 verbose ──► workflow 路径
   │      │  answer()：闲聊关键词短路 / 长文本题外话短路 / LLM 拆解意图
   │      │  （match 场景：图外先解析对方命盘 + 规则合婚基础数据）
   │      ▼
   │  LangGraph 图（唯一编排后端）：
   │  classify → chart → retrieve → generate → check ─(有 issues)→ repair → END
   │                                            └───(无 issues)──────────► END
   │
   ├─ 无命盘 + 闲聊意图(_is_chitchat) ──────────► 闲聊短路：单次 LLM 直答
   │
   └─ 其余 ────────────────────────────────────► ReAct 路径（LLM 自主调工具）
          bazi_full / search_knowledge / search_web / do_terminate …
```

```
                    ┌──────────────────────────────────┐
                    │     XianzhiGraphState (共享状态)    │
                    │  user_prompt / chart_context      │
                    │  history / summary                │
                    │  intent:   QuestionIntent         │
                    │  worker:   DomainWorker           │
                    │  knowledge: "检索到的知识片段"      │
                    │  raw_answer: "LLM 原始回答"        │
                    │  final_answer: "最终回答"          │
                    │  issues: ["问题1", "问题2"]        │
                    └──────────────────────────────────┘
                    每个节点只返回需要修改的字段，
                    框架自动 merge 到全局 State
```

图结构与路由（与 `create_xianzhi_graph` 一一对应）：

| 节点 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `classify` | user_prompt / intent | intent, worker | 优先复用 `answer()` 已拆解的 intent，缺失时 `classify_question` 关键词兜底；按 domain 查 `WORKERS`（未匹配落到 general） |
| `chart` | chart_context, intent | chart_context | `extend_chart_if_needed`：目标年份不在流年范围时按范围重建盘（大运扩到 12 柱） |
| `retrieve` | intent, worker | knowledge | **闲聊短路**：domain=chitchat 直接返回占位文本，不查知识库 |
| `generate` | 上述全部 | raw_answer | `build_messages` 组装 system/human 后 `_invoke` 调 LLM（180s 超时，过滤 think 块，去重，空产出有兜底文案） |
| `check` | raw_answer | issues, final_answer | Reviewer 两层审核（正则快筛 + LLM 深审，闲聊 skip_llm）；通过则定稿，否则 final_answer 置空 |
| `repair` | raw_answer, issues | final_answer | Reflextion 修复（闲聊直接短路返回原答案）；修复后先正则快筛、通过则免 LLM 重审 |

边：`classify→chart→retrieve→generate→check` 为普通边；
`check` 挂条件路由 `route_after_check`（`issues 非空 → repair`，否则 `END`）；`repair→END`。
当前 `graph.compile()` **未配置 checkpointer**（断点续跑/人工中断属 LangGraph 框架原生能力，
代码暂未启用，为全自动流水线）。

### 三种角色

| 角色 | 实现 | 职责 |
|------|------|------|
| **Supervisor** | `XianzhiWorkflow`（`workflow/xianzhi_workflow.py`） | 入口分流（闲聊/题外话短路）、LLM 意图拆解、合婚对方盘预解析、按会话开关思考模式、驱动 LangGraph 图、验收最终答案 |
| **专业 Worker** | `DomainWorker` + `WORKERS` 注册表（`workflow/workflow_workers.py`） | 按领域专注单一断法，带专属 prompt 与检索 query；执行逻辑（检索/拼消息/调用）复用 Supervisor 方法 |
| **Reviewer** | `ReviewerWorker`（`workflow/workflow_workers.py`） | 正则快筛 + LLM 深审两层校验，不通过则触发 Reflextion 修复循环 |

## 核心组件

> R9 拆分：原单文件 `xianzhi_workflow.py` 已拆为 `workflow/` 子包——
> `workflow_models`（数据模型）、`workflow_support`（分类/正则/容错 JSON）、
> `workflow_workers`（注册表 + Reviewer）、`workflow_retrieval`（检索纯函数）、
> `workflow_messages`（消息装配/事实校验纯函数）；`xianzhi_workflow.py` 保留
> `XianzhiWorkflow` Supervisor 并重导出全部原公共符号，既有 import 无需改动。

### 1. WorkerResult（最小结果协议）

Worker 只返回结构化摘要，不返回完整对话历史，避免上下文爆炸
（`workflow_models.WorkerResult`）：

```python
@dataclass(frozen=True)
class WorkerResult:
    status: str           # "done" | "blocked" | "failed"
    summary: str          # 断语结论
    evidence: list[str]   # 古籍引用 + 检索片段
    risks: list[str]
```

### 2. DomainWorker（领域 Worker 配置）

每个 Worker 有六样专属配置（`domain`/`label` 为身份字段，其余为行为配置）：

| 字段 | 说明 |
|------|------|
| `domain` | 领域标识（如 `"career"`），与 `WORKERS` 注册表的 key 一致 |
| `label` | 领域中文名（如 `"事业工作"`），用于日志与展示 |
| `expertise_prompt` | 追加到通用 system prompt 末尾的领域断法规则（装配时统一加 `WORKER_PREAMBLE_TEMPLATE` 抬头：「以下为传统命理的通用倾向，须结合原局具体组合灵活判断，不可当作绝对公式」） |
| `extra_queries` | 领域专属检索 query（断事路径仅取首条叠加） |
| `length_rule` | 领域专属篇幅规则（用户要求完整详批时被放宽规则覆盖） |
| `skip_facts` | theory/chitchat 跳过命盘事实注入（`intent.needs_chart=True` 时被覆盖，仍注入） |

### 3. 专业 Worker 注册表

`WORKERS` 注册表共 **18 个领域 Worker**（逐一核对自 `workflow_workers.py`，
与 `DOMAIN_LABELS`、意图拆解 prompt 的 domain 枚举完全一致）：

| Worker | 领域 | 专属断法覆盖 |
|--------|------|------------|
| `career` | 事业工作 | 官杀/印星/食伤论事业、格局清浊 |
| `wealth` | 财运收入 | 正偏财/食伤生财/财库/比劫夺财 |
| `love` | 恋爱感情 | 配偶星/桃花/日支/红艳咸池孤辰寡宿 |
| `marriage` | 婚姻关系 | 配偶宫/夫妻星/合冲刑害/克配偶 |
| `health` | 健康状态 | 五行失衡/寒暖燥湿/七杀攻身 + 就医劝导合规提示 |
| `study` | 学习考试 | 印星/食伤/官星/文昌 |
| `social` | 社交人际 | 比劫/贵人星/七杀小人/日支合化/格局清浊 |
| `family` | 六亲关系 | 十神六亲/宫位/印财比劫食伤官杀/宫位冲刑 |
| `liunian` | 大运流年 | 大运流年作用/太岁/岁运并临/立春换年 |
| `theory` | 术语理论 | 术语解释规范/古籍引用格式（skip_facts=True） |
| `chitchat` | 闲聊问候 | 空（跳过检索 + 命盘） |
| `personality` | 性格心性 | 日主/十神组合/强弱/格局 |
| `migration` | 方位迁移 | 用神方位/驿马/迁移 + 现实决策合规提示 |
| `naming` | 起名改名 | 用神喜忌/日主强弱/字形字义/调候 |
| `auspicious` | 择吉择日 | 用事人喜用神/事项用神/避凶煞/吉神 |
| `match` | 合婚配对 | 双盘对比/配偶宫夫妻星/刑冲合害/五行互补（消费【合婚基础数据】评分锚点） |
| `children` | 子女生育 | 子女星/子女宫/生育时机/受克 |
| `general` | 综合咨询 | 鸟瞰式综述（格局用神→强弱喜忌→事业财运→婚恋健康），兜底 |

> 注意：六爻、黄历、紫微、塔罗、合婚工具页**不是** workflow 领域 Worker，
> 而是独立子应用（`app/sub_app/{liuyao,huangli,ziwei,tarot,hehun}`），
> 各自的系统提示同样收口在 `prompts.py`（`LIUYAO_SYSTEM_PROMPT` /
> `ZIWEI_SYSTEM_PROMPT` / `TAROT_SYSTEM_PROMPT` / `HEHUN_SYSTEM_PROMPT`）。

### 4. ReviewerWorker（两层审核：正则快筛 + LLM 深审）

`ReviewerWorker.review()` 两层结构：

**第 1 层：正则快筛（零 LLM、零 token）**——发现任何 issue 直接返回
（`source="regex"`），省掉 LLM 调用：

| 校验维度 | 实现 | 失败示例 |
|---------|------|---------|
| **事实校验** | 复用 `check_facts`（四柱干支/大运流年/十神存在性/神煞存在性与柱位归属）；合婚双盘时任一合法盘命中即放行 | "2024年甲辰" 写成 "2024年乙巳"；排盘无七杀却说"七杀攻身"；年柱神煞说成日柱 |
| **古籍真实性** | `ANCIENT_CITATION_RE` 抽取「《XXX》原文：」标注，书名须在检索结果或白名单 `{渊海子平, 子平真诠, 滴天髓, 穷通宝鉴, 三命通会, 神峰通考, 千里命稿}` 中出现 | 检索结果无《XX书》，回答却引用了 |
| **合规校验** | `COMPLIANCE_RISKS` 红线关键词扫描（生死断言/堕胎择时/改运改命/诅咒蛊术/赌博包赚等 15 组） | 回答含"你的死期是""买彩票必中" |

事实校验的宽严两档由 `needs_chart` 控制：True（命盘分析/合婚/流年推演）严格校验
十神/神煞的存在性与柱位归属；False（纯理论/术语解释）只校验"绑定命盘的归属断言"
（"你命盘有X""年柱X"），纯术语定义放行，避免误杀理论问答。

**第 2 层：LLM 深审（1 次调用）**——正则全通过后，用
`prompts.REVIEWER_SYSTEM`（实测 1241 字）做深度审核，维度覆盖：
逻辑自洽、断法准确性、知识一致性、古籍真实性（识别检索未提供的**伪造古文句子**，
正则只能查书名）、表达质量、事实复查、十神事实复查、神煞事实复查、
表述宽容度（倾向性/方向性描述放行，仅绝对化确证词与凭空捏造判问题）、
审核范围边界（对话连贯的"之前我断过"不判幻觉）。输出 JSON
`{"pass": bool, "issues": [...]}`；返回非 JSON 或 LLM 异常时降级为通过
（`source="regex_fallback"`），不影响主流程。

**短路开关**：调用方传 `skip_llm=True`（闲聊/题外话场景）时，正则通过即视为整体通过，
跳过 LLM 深审，节省 1 次调用。

### 5. Prompt 中枢（`app/agent/prompts.py`）

所有命理路径（ReAct / Workflow / 塔罗 / 六爻 / 紫微 / 合婚 / 报告 / Reviewer）的
提示词常量统一收口在本模块（单一事实源，消除旧版 `xianzhi.py::SYSTEM_PROMPT`
与 workflow 内 system 的双份漂移）：

| 常量 | 用途 | 实测字数 |
|------|------|---------|
| `ORACLE_BASE_SYSTEM` | ReAct 与 Workflow 共用的"先知"人设基座（含指令隔离、合规红线、古籍引用规则、表达风格、篇幅规范） | 1258 |
| `INJECTION_GUARD` / `COMPLIANCE_REDLINES` / `LENGTH_RULES` | 共享片段常量 | — |
| `WORKFLOW_FACT_REDLINE` | Workflow 路径追加的干支/十神/神煞事实硬红线 | — |
| `REACT_NEXT_STEP_PROMPT` / `REACT_FACT_GUARDRAILS` | ReAct 路径工具调度提示 + 事实护栏 | — |
| `WORKER_PREAMBLE_TEMPLATE` | Worker 专属断法统一抬头（防绝对化） | — |
| `CHITCHAT_SYSTEM` | 闲聊短路专属 prompt | 581 |
| `TAROT/LIUYAO/ZIWEI/HEHUN/REPORT_*_PROMPT` | 塔罗/六爻/紫微/合婚/报告各子应用系统提示 | — |
| `REVIEWER_SYSTEM` | LLM 深审提示（10 维度） | 1241 |
| `domain_sysprompt` | LLM 意图拆解提示（输出 domain/queries/needs_chart/对方生辰 JSON） | 1221 |
| `reflect_sysprompt` | Reflextion 修复改写器提示 | 241 |

## 执行流程

```
1. mount_chart_context           → 挂载命盘（正则/模糊生辰/八字反推候选确认）
2. answer() 入口分流             → 闲聊关键词 / 长文本题外话短路，否则 LLM 拆解意图
3. （match）图外预解析对方命盘    → bazi_hehun 规则合婚基础数据注入 intent
4. self._graph.invoke(...)       → LangGraph：分类→扩盘→检索→生成→校验→（修复）
5. 通过 → 返回 / 未通过 → Reflextion 修复 → 正则快筛（通过则免 LLM 重审）
6. 图产出 final_answer 为空      → 快速失败 RuntimeError（不向用户返回空回复）
```

意图拆解的优先级：`detect_domain`/`_looks_off_topic` 命中短路 → `classify_question`
（纯规则零 LLM）；否则 `_decompose_query`（LLM，独立轻量拆解模型，
`domain_sysprompt` 约束输出 JSON）失败时回退 `classify_question`。

### 数据流（以"我最近事业不太顺，想换工作，什么时候有机会？"为例）

```
意图拆解 domain=career → 分派 career Worker（查 WORKERS 表）
   │
检索（retrieve_rules，断事路径）：
   query1 用户原句
   query2 "事业工作 甲木日主 身旺 大运流年"     ← 个性化（日主+强弱）
   query3 "事业工作 断法 官杀 印星 食伤 升职"   ← DOMAIN_RULE_QUERIES
   query4 "事业工作 升职 跳槽 伤官见官 官杀混杂" ← Worker.extra_queries
   （部分领域再叠古籍 query 与断法体系 query，最终截断为 ≤4 条）
   每条 query 并发经统一检索入口 retrieve_for_context
   │
拼装消息（build_messages）：
System: ORACLE_BASE_SYSTEM + WORKFLOW_FACT_REDLINE
        + 【事业专项断法 · 通用准则】抬头 + Worker.expertise_prompt
Human:  【用户问题】(边界包裹) / 【识别意图】/【最近对话摘要】
        /【系统排盘事实】(四柱详述/神煞按柱/天干地支关系/调候/起运/大运/流年)
        /【历史断事参考】(命盘画像已验证·已否定断事)
        /【命理规则检索】/【输出要求】
   │
LLM 生成 → Reviewer 两层审核 → 定稿或修复
```

### 日志链路

```
[LLM拆解] domain=career needs_chart=True queries=[...]
[workflow检索] LLM拆解路径 queries=[...] (共N条)
[检索] [1/4] query=... 命中=XXX字
[Worker] 事业工作 生成回答 XXX字
[Reviewer] 开始审核 事业工作 Worker 产出 (XXX字)...
[Reviewer] LLM 深审通过 ✓ (source=llm)
```

## 入口分流：ReAct 与 LangGraph 编排

先知智能体有两条**入口路径**，在 `Xianzhi.run_stream / arun_stream` 内分流；
**workflow 路径的编排后端唯一为 LangGraph**——`AppContext.workflow_backend()`
硬编码返回 `"langgraph"`，settings 已无 workflow_backend 切换项，
`XianzhiWorkflow` 构造期即构建图，失败直接抛错，无内置流水线降级。

| 条件 | 路径 | 架构 |
|------|------|------|
| 有命盘 (`_workflow_context`) 且非 verbose | workflow | LangGraph 编排：Supervisor + Worker + Reviewer |
| 无命盘 + 闲聊意图 | 闲聊短路 | 单次 LLM 直答（`CHITCHAT_SYSTEM`），不调工具 |
| 其余（无命盘 / verbose 调试） | ReAct | LLM 自主调工具（bazi_full/bazi_hehun/search_knowledge/search_web/do_terminate 等，调度提示 `REACT_NEXT_STEP_PROMPT`） |

### 适用场景

- **workflow 路径**：已挂载命盘后的所有对话（含闲聊、术语、专项断事）
- **ReAct 路径**：第一次对话没命盘、用户主动提供生辰让 LLM 排盘、纯术语问答
- **闲聊短路**：两条入口都有，避免"你好"也触发工具调用

## 闲聊短路机制

闲聊短路分布在三个层级：ReAct 入口、workflow 入口（图外）、LangGraph 图内。

### ReAct 路径（无命盘时）

在 `xianzhi.py` 的 `run_stream` / `arun_stream` 前置短路：

```python
if not verbose and self._is_chitchat(user_prompt):
    reply = await asyncio.to_thread(self._chitchat_reply, user_prompt)
    yield reply
    return
```

- `_is_chitchat()`：无命盘、无八字待确认候选（`_bazi_pending`）、无模糊生辰信号
  （`_birth_signal`），且 `classify_question`（纯规则，零 LLM）判定
  `intent.domain == "chitchat"` → True
- `_chitchat_reply()`：直接调一次 LLM，用 `CHITCHAT_SYSTEM` 闲聊专属 prompt
  （1-3 句 ≤150 字、老友口吻），关闭思考模式，不调任何工具
- 日志：`[xianzhi] 闲聊短路，跳过 ReAct 工具调用`

### workflow 路径（有命盘时）

三层短路：

1. **图外入口**（`XianzhiWorkflow.answer`）：`detect_domain` 命中 chitchat，
   或 `_looks_off_topic`（文本 >100 字 + 零命理信号词）命中，均跳过 LLM 拆解，
   直接 `classify_question` 定意图；
2. **图内 retrieve 节点**：`intent.domain == "chitchat"` 直接返回
   "（闲聊场景，无需命理知识检索）"，不查知识库；
3. **图内 check / repair 节点**：闲聊场景 `skip_llm=True` 跳过 LLM 深审；
   repair 节点对闲聊直接返回原答案（无 issues 可修）。

加上 `chitchat` Worker 的 `skip_facts=True`，闲聊时不注入命盘事实、不检索知识库，
但仍保留正则快筛（合规红线）兜底。

### 闲聊判定规则（`classify_question`，纯规则零 LLM）

```python
CHITCHAT_STRONG = ("哈哈", "你好", "在吗", "谢谢", "辛苦", "早上好", "晚上好", "晚安",
                   "吃饭了吗", "在干嘛", "生日快乐", "新年好")
if any(w in text for w in CHITCHAT_STRONG) and not years:
    best_domain = "chitchat"
```

优先级链路：

1. 强闲聊信号词 + 无年份 → chitchat（避免被 liunian 的"最近"等词抢走）；
2. 天气/搜索类工具查询词（"天气""查一下"等）+ 无年份 → 强制回 general，
   不被闲聊短路（保住 ReAct / 联网搜索路径）；
3. 零关键词命中 + 无年份 + 非工具查询 → chitchat（如"为什么这么多人执着西藏"）；
4. 有年份且原判 general → liunian。

**已知的误报边界**：判定完全基于关键词规则，存在边界误判——例如
"哈哈，今天天气不错"含强闲聊词"哈哈"，但"天气"命中工具查询保护规则被救回
general，从而不走闲聊短路。对应测试
`tests/test_react_bazi_pending_fix.py::test_pure_chitchat_no_false_positive`
当前在干净 HEAD 上也失败（历史遗留问题，尚未修复），使用时应意识到
"闲聊判定存在误报边界"这一事实。

## 知识检索的分层（RAG）

两条路径共用一套检索体系（`app/rag/retrieval.py` 统一提供领域识别、query 构造、
去重检索），上层编排因路径而异。

### Layer 1 — 单 query 检索（`app/rag/vector_store.py`）

`knowledge_base.search(q)` 已**由 MMR 改为 rerank 管线**：

1. 向量召回 `fetch_k=3` 候选（`similarity_search_with_score`）；
2. Chroma 后端按距离阈值过滤（`rag_distance_threshold`，仅 Chroma L2 语义）；
3. 关键词重叠 rerank：`keyword_overlap(query, doc) × doc_type 权重`
   （断法文档优先、模板库降权），覆盖率 < 0.25 视为不相关直接丢弃（宁缺毋滥）；
4. 取 top `k`（`settings.rag_k`，默认 1）。

同 query 结果带 TTL 缓存（`RAG_SEARCH_CACHE_TTL`）。MMR 检索器
（`k=rag_k, fetch_k=rag_k*3, lambda_mult=0.7`）仅作后端不支持 score 检索时的回退。

### Layer 2 — 多 query 编排（统一入口 `retrieve_for_context`）

ReAct 工具与 workflow 都经 `app/rag/retrieval.py::retrieve_for_context`：
多 query **并发检索**（线程池），每条 query 只取 top-1 最相关 chunk
（与已选结果重复则该 query 放弃），去重键 `(来源文件, 内容前120字)`，
单 chunk 截断 ≤ `max_chars_per_chunk`（默认 600 字），总条数 ≤ `max_docs`。

| 路径 | query 来源 | max_docs |
|------|-----------|----------|
| ReAct 工具（`tools/rag_search.py`） | `expand_knowledge_queries`：原文 → 理论术语精准 query → 领域规则 query → 流年补充 | 4 |
| workflow（`workflow_retrieval.retrieve_rules`） | ① LLM 拆解 `intent.queries`（≤4 条，短 query 拼领域术语前缀增强区分度）；② theory 路径（术语精准 query，1-2 条）；③ 断事路径 `build_duxing_queries`（用户原句 + 个性化 + 领域规则 + Worker 专属，≤4 条） | `len(queries)`（≤4） |

> 与旧版差异：ReAct 工具的文档上限由 6 降为 4；workflow 不再有独立的
> `_MAX_KNOWLEDGE_TOTAL=2800` 总预算，改由统一入口的
> "单 chunk 600 字 × 最多 4 条"口径控制。

## 领域计算层（纯函数，不依赖 LLM/DB）

排盘等确定性计算已下沉到 `backend/app/domain/`，供 workflow、工具、
子应用与 /chart API 共用同一套事实：

| 模块 | 说明 |
|------|------|
| `bazi_engine.py` | 八字引擎（兼容门面），重导出 `analysis_calc`（强弱/格局/十神统计）、`chart_builder`（排盘/大运/流年）、`chart_format`（事实上下文/八字反推日期）、`shensha_calc`（神煞）、`tables`、`time_parse`（公历/农历/节日/时辰解析）、`models` |
| `huangli_calc.py` | 黄历领域计算（宜忌/冲煞/吉凶神/彭祖/五神方位/值神/建星/九星/二十八宿/时辰吉凶、择吉筛选），基于 lunar-python 1.4.8，覆盖 1900-2100 |
| `city_longitude.py` | 出生地城市 → 东经度数，用于真太阳时校正（与 /chart API 口径一致） |
| `ziwei/` | 紫微斗数**Python 自研引擎**（`engine.py`/`tables.py`/`models.py`），零运行时依赖，安星法/四化表/年分界逐项对齐 iztro 2.6.0 默认配置，由 `tests/test_ziwei.py` 的 45 组 iztro 黄金快照逐宫逐曜断言钉死 |

确定性优先是整套架构的基石：四柱/大运/流年/神煞由引擎计算，
LLM 只做解读，不得自行推算干支（`WORKFLOW_FACT_REDLINE` 与 Reviewer 事实校验双向兜底）。

## LangGraph 集成

`backend/app/agent/xianzhi_langgraph.py` 是**唯一的编排实现**（不再是可选封装）：

- `XianzhiGraphState`：TypedDict 共享状态（含 `summary` 会话摘要透传）
- 六节点：`classify` / `chart` / `retrieve` / `generate` / `check` / `repair`
- 条件路由：`check` 之后 `route_after_check`（issues 非空 → repair，否则 END）
- langgraph 为硬依赖（`langgraph>=1.0.0,<2.0.0`），图构建失败即
  `RuntimeError`，**没有降级路径**；`XianzhiWorkflow.backend` 恒为 `"langgraph"`
- 思考模式由 `use_thinking` 写入 contextvar：闲聊关闭、其他路径开启，
  图内 `generate`/`repair` 的 LLM 调用自动读取

当前为单层 Graph（6 节点）。`create_xianzhi_graph()` 返回编译后的图，
结构上可作为一个节点嵌入更大的 Supervisor Graph（子图嵌套为 LangGraph 原生能力，
代码暂未使用）；checkpointer 与 Human-in-the-Loop 亦为框架原生支持，暂未启用。

## 文件结构

```
backend/
├── main.py                              # FastAPI 入口（/health 暴露 workflow_backend）
├── requirements.txt                     # langgraph>=1.0.0,<2.0.0（硬依赖）
└── app/
    ├── agent/
    │   ├── xianzhi.py                   # 先知主类：入口分流（workflow/闲聊短路/ReAct）+ 命盘挂载 + 记忆
    │   ├── xianzhi_langgraph.py         # 唯一 LangGraph 编排：XianzhiGraphState + create_xianzhi_graph
    │   ├── prompts.py                   # 提示词中枢（ORACLE_BASE_SYSTEM/REVIEWER_SYSTEM/domain_sysprompt 等）
    │   ├── birth_parse.py               # 生辰解析（正则/模糊信号/八字反推/出生地经度）
    │   ├── core/                        # Agent 基类（BaseAgent/ToolCallAgent/ReactAgent）
    │   └── workflow/                    # R9 拆分后的 workflow 子包
    │       ├── workflow_models.py       # QuestionIntent / WorkflowChartContext / DomainWorker / WorkerResult / FactCheckResult
    │       ├── workflow_support.py      # classify_question / _looks_off_topic / 容错 JSON / build_chart_context
    │       ├── workflow_workers.py      # WORKERS 注册表（18 个）+ ReviewerWorker（两层审核）
    │       ├── workflow_retrieval.py    # retrieve_rules / build_duxing_queries / 扩盘 / 合婚对方盘解析
    │       ├── workflow_messages.py     # build_messages / build_repair_messages / check_facts（事实校验）
    │       └── xianzhi_workflow.py      # XianzhiWorkflow Supervisor（兼容门面，重导出原符号）
    ├── api/
    │   ├── context.py                   # AppContext（会话池/会话锁/workflow_backend()="langgraph"）
    │   └── xianzhi.py / routes.py / …   # API 层
    ├── domain/                          # 领域计算层（纯函数）
    │   ├── bazi_engine.py + analysis/chart_builder/chart_format/shensha_calc/tables/time_parse/models
    │   ├── huangli_calc.py / city_longitude.py
    │   └── ziwei/                       # 紫微自研引擎（对齐 iztro 2.6.0 黄金快照）
    ├── rag/                             # vector_store（rerank 管线）/ retrieval（统一检索策略）/ knowledge / embeddings
    ├── tools/                           # bazi / rag_search / huangli / ziwei / web_search / mcp_client / text_clean / report_generator
    ├── sub_app/                         # 独立子应用：tarot / liuyao / huangli / ziwei / hehun
    ├── memory/                          # PG 会话记忆 / 摘要
    ├── evaluation/                      # xianzhi_eval
    └── core/                            # config / logger / thinking_router / observability / security
```

## 与学习资料的对应关系

> 历史注解，精简保留。参考 `学习资料/智能体开发笔记/16_多Agent协作/`：

| 学习资料概念 | 本实现 |
|------------|--------|
| Supervisor（单层监管者） | `XianzhiWorkflow` |
| 专业 Worker | `DomainWorker` + `WORKERS` 注册表 |
| Review Worker | `ReviewerWorker` |
| WorkerResult 最小协议 | `WorkerResult` dataclass |
| Reflextion 反思机制 | `build_repair_messages` 回退修复 + LangGraph `repair` 节点 |
| 状态边界（Worker 不返回完整历史） | Worker 只持有配置与断语结论，不传递 message_list |

技术选型结论不变：命理的核心痛点是**严谨性**而非**创意性**，
选择"单层监管者 + Reviewer 反思闭环"的混合架构，
价值来自交叉验证（Reviewer 审 Worker），不是多视角协商；
确定性事实（排盘）由领域计算层承担，编排交给 LangGraph StateGraph。

## 扩展 Worker

新增领域 Worker 需要四处同步：

1. `workflow/workflow_workers.py` 的 `WORKERS` 注册表添加配置：

```python
WORKERS["new_domain"] = DomainWorker(
    domain="new_domain",
    label="新领域",
    expertise_prompt=(
        "【新领域专项断法】\n"
        "- 专属断法规则1\n"
        "- 专属断法规则2\n"
    ),
    extra_queries=("新领域 专属检索 query",),
    length_rule="新领域专属篇幅规则",
    skip_facts=False,
)
```

2. `app/rag/retrieval.py` 的 `DOMAIN_KEYWORDS` 添加关键词；
3. `DOMAIN_RULE_QUERIES` 添加领域检索 query（前缀对齐知识库文档标题）；
4. `workflow/workflow_models.py` 的 `DOMAIN_LABELS` 与 `prompts.py`
   `domain_sysprompt` 的 domain 枚举同步登记（否则 LLM 拆解不会输出该领域）。

如需知识库新增文档，同步维护 `tools/rag_search.py` 的 `_SOURCE_LABEL_MAP`
（来源标签决定 LLM 能否加书名号引用）。

## 测试

运行架构测试（不依赖真实 LLM，在 `backend/` 目录下）：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_xianzhi_workflow.py -q
.venv\Scripts\python.exe -m pytest tests/test_xianzhi_langgraph.py tests/test_ziwei.py -q
```

主要覆盖（`test_xianzhi_workflow.py` 共 19 个用例）：

1. classify_question 意图/年份/闲聊/天气与搜索查询保护
2. 流年扩盘（目标年份超出默认范围）
3. detect_theory_topic 术语识别与 query 构造
4. _decompose_query 的 LLM JSON 解析与失败回退
5. needs_chart 覆盖 skip_facts、断事场景不注入相似案例
6. check_facts 事实校验（错误流年/柱位捕获与正确事实放行）
7. workflow 优先于 ReAct（有命盘时）
8. `test_xianzhi_langgraph.py`：图编译与可执行、backend 恒为 langgraph、
   state 支持 summary 透传
9. `test_ziwei.py`：紫微引擎 45 组 iztro 黄金快照
10. `test_liuyao.py` / `test_huangli.py`：六爻与黄历领域计算

> 已知历史失败：`test_react_bazi_pending_fix.py::test_pure_chitchat_no_false_positive`
> 在干净 HEAD 上也失败（闲聊判定的关键词误报边界，见「闲聊短路机制」一节）。

## 设计原则

1. **单一编排后端**：workflow 只由 LangGraph 承担，构建失败快速失败，
   不保留双实现避免行为分叉；`AppContext.workflow_backend()` 硬编码 `"langgraph"`
2. **单一事实源**：提示词收口 `prompts.py`（一处改全路径生效）；检索策略收口
   `rag/retrieval.py`（两条路径共用同一检索入口与口径）；排盘事实收口 `app/domain/`
3. **确定性优先**：四柱/大运/流年/神煞由纯函数引擎计算，LLM 不得自行推算干支，
   Reviewer 事实校验双向兜底
4. **专业深度 + 交叉校验**：单领域 Worker 更短更专业，Reviewer 用
   "正则快筛 + LLM 深审"两层视角审视，修复循环先快筛省 token
5. **闲聊多重短路**：ReAct 入口、workflow 图外入口、图内 retrieve/check/repair
   均有短路，避免无谓工具调用与 LLM 深审开销（判定为纯规则，存在已知的误报边界）
6. **模块化拆分**：workflow 家族按"模型/支撑/注册表/检索/消息"单一职责拆为子包，
   `xianzhi_workflow.py` 作兼容门面重导出，既有 import 不受影响
