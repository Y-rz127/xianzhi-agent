# 先知 Agent · LLM 输入 Token 预算总索引

> 目的：把 ReAct 与 Workflow 两条路径里**每一种对话方式**发给大模型（LLM）的全部内容、字符数、Token 数，按"一个方式一个独立文档"列清楚。
> 换算口径：**中文 1 字 ≈ 1.8 token**（仅估算，真实值取决于 tokenizer）。所有固定 prompt 长度均经 AST/import 实测；可变块（排盘事实/知识库/历史）按代码逻辑 + 样本实测估算。
> 首版日期：2026-07-29；更新日期：2026-09-01

---

## 一、路径决策树（一次问答怎么走）

入口统一在 `app/agent/xianzhi.py` 的 `Xianzhi.run_stream / arun_stream`（:499 / :523），按顺序判定：

```
用户提问
  │
  ├─ _workflow_context 已挂 且 not verbose ──► 【Workflow 路径】(_workflow_stream / _aworkflow_stream
  │                                              → XianzhiWorkflow.answer → LangGraph 图编排)
  │
  ├─ 无命盘 且 _is_chitchat()==True ──► 【ReAct·闲聊短路】(_chitchat_reply，1 次 LLM)
  │     （_is_chitchat 现为纯关键词判定：无 _workflow_context / _bazi_pending / _birth_signal
  │       三个信号时，调 classify_question(user_prompt).domain=="chitchat"，零 LLM）
  │
  └─ 其余 ──► 【ReAct·工具循环】(BaseAgent.run_stream → ToolCallAgent.think，多步 LLM)
               （典型：verbose 调试 / 带命盘但 workflow 未启用 / 需工具补排盘）
```

**Workflow 路径内部（`xianzhi_langgraph.py` 图编排，唯一后端）**：

```
answer() 入口（xianzhi_workflow.py:178）
  ├─ detect_domain 关键词命中 chitchat ──► 跳过 LLM 拆解
  ├─ _looks_off_topic 长文本零命理信号 ──► 跳过 LLM 拆解
  └─ 否则 _decompose_query（LLM 拆解，调用 A，用独立 decompose_model）
        ↓
LangGraph 图：classify → chart(扩盘) → retrieve(知识检索) → generate(调用 B)
  → check（正则快筛；非闲聊且快筛通过再走 LLM 深审，调用 D）
  → (issues 非空时) repair（调用 C 修复 + regex 快筛，必要时 LLM 重审）
```

- 编排后端**只有 LangGraph 一种**：`XianzhiWorkflow.__init__` 直接构建图，构建失败即快速失败；`AppContext.workflow_backend()` 固定返回 `"langgraph"`，settings 中已无切换项。旧文档描述的"内置 workflow 可切回"分支已不存在。
- 意图拆解（decompose_model）与 Reviewer 深审（reviewer_model）可配独立轻量模型（`main.py` 构造，缺省复用主模型）。

**两条路径共用的公共调用**：会话跑完后 `_persist_history` 末尾触发【会话摘要】（`shared_summary.md`），异步后台执行，两条路径都会发生。

---

## 二、ReAct 路径文档

| 文档 | 对话方式 | 一句话说明 | LLM 调用 |
|---|---|---|---|
| [react_chitchat.md](./react_chitchat.md) | 闲聊短路 | 无命盘 + 闲聊意图，直接 1 次 LLM，不走循环、无工具（**注意：此"三层"是 ReAct `_is_chitchat` gate，非 Workflow 意图链路**） | 1 次 |
| [react_loop.md](./react_loop.md) | 工具循环 (think→act→observe) | 完整 ReAct 多步循环，17 个本地工具 + MCP 工具 schema 常驻、结果逐轮回灌 | 每步 1 次，≤ max_steps |

## 三、Workflow 路径文档

| 文档 | 对话方式 / 调用 | 一句话说明 | LLM 调用 |
|---|---|---|---|
| [workflow_intent_routing.md](./workflow_intent_routing.md) | 意图分类防护链路（调用 A 之前） | `detect_domain`→`_looks_off_topic`→`_decompose_query`+`classify_question` 兜底；闲聊命中即跳过 LLM 拆解（用户口中的"三层判断"即指此） | 0~1 次 |
| [workflow_decompose.md](./workflow_decompose.md) | 意图拆解（调用 A） | 非闲聊且非离题时，先 LLM 拆 domain/queries；可被短路跳过；用独立 decompose_model | ≤1 次 |
| [workflow_chitchat.md](./workflow_chitchat.md) | Worker 主回答·闲聊（调用 B） | 已挂命盘走 Workflow 的闲聊；跳过事实/命例，知识库固定 15 字占位；**跳过 LLM 深审** | 1 次 |
| [workflow_theory.md](./workflow_theory.md) | Worker 主回答·理论（调用 B） | 纯命理理论/术语；默认跳过事实/命例（needs_chart=True 时仍注入），真检索知识库 | 1 次（+深审 D） |
| [workflow_regular.md](./workflow_regular.md) | Worker 主回答·常规断事（调用 B） | career/wealth/health 等断事；注入排盘事实+断事参考+知识库（相似命例注入已移除） | 1 次（+深审 D） |
| [workflow_match.md](./workflow_match.md) | Worker 主回答·合婚双盘（调用 B） | 双人合婚；双盘事实 + 合婚基础数据，System 最大 | 1 次（+深审 D） |
| [workflow_repair.md](./workflow_repair.md) | Reviewer 深审（调用 D）+ Reflextion 修复（调用 C） | 非闲聊 Worker 产出后：正则快筛通过则 LLM 深审 1 次；被打回才走修复 | D 常规 1 次；C 0~1 次 |

> Workflow 一轮典型 = **A + B + D（+ C 若打回）**。闲聊轮 = 仅 B。各调用独立成表，叠加即总消耗。

## 四、公共调用文档

| 文档 | 说明 | LLM 调用 |
|---|---|---|
| [shared_summary.md](./shared_summary.md) | 会话摘要，后台线程异步；两条路径共用；每新增 12 条消息（6 轮）触发一次增量摘要 | 独立 1 次（异步） |

## 五、子应用独立提示词（不走主问答链路）

塔罗/六爻/紫微/合婚/报告为独立子应用（`app/sub_app/*`、`app/tools/report_generator.py`），各自独立调 LLM，与上面 ReAct/Workflow 主链路互不叠加。共用提示词已收进 `app/agent/prompts.py` 单一事实源：

| 常量 | 值（字） | 消费方 |
|---|---|---|
| `TAROT_SYSTEM_PROMPT` | 793 | `sub_app/tarot/tarot_app.py:298` |
| `LIUYAO_SYSTEM_PROMPT` | 877 | `sub_app/liuyao/routes.py:66` |
| `ZIWEI_SYSTEM_PROMPT` | 926 | `sub_app/ziwei/routes.py:58` |
| `HEHUN_SYSTEM_PROMPT` | 499 | `sub_app/hehun/hehun_app.py:63` |
| `REPORT_SYSTEM_PROMPT`（169）+ `REPORT_PROMPT_TEMPLATE`（396） | — | `tools/report_generator.py:111` |

> 另外 `huangli_tools`（黄历查询）与 `ziwei_tools`（紫微排盘）作为**工具**加入了 ReAct 工具集（main.py:128），仅增大 ReAct 工具 schema，不影响 Workflow 路径。

---

## 六、关键常量速查（实测）

| 常量 | 值（字） | 位置 |
|---|---|---|
| `ORACLE_BASE_SYSTEM`（ReAct 主 persona，xianzhi.py 以 `SYSTEM_PROMPT` 别名导入） | 1258 | prompts.py:99 |
| `REACT_NEXT_STEP_PROMPT`（ReAct 工具指引，仅注入一次） | 797 | prompts.py:59 |
| `REACT_FACT_GUARDRAILS`（有命盘时追加） | 398 | prompts.py:83 |
| `CHITCHAT_SYSTEM`（ReAct 闲聊短路 System） | 581 | prompts.py:127 |
| `domain_sysprompt`（Workflow 拆解 = `_DECOMPOSE_SYSTEM`） | 1221 | prompts.py:361 |
| Workflow 基础 System（ORACLE_BASE + FACT_REDLINE 拼接） | 1823 | workflow_messages.py:74 |
| `WORKFLOW_FACT_REDLINE`（Workflow 事实红线段） | 563 | prompts.py:43 |
| Worker 通用断法抬头 `WORKER_PREAMBLE_TEMPLATE` | 87 | prompts.py:38 |
| `REVIEWER_SYSTEM`（LLM 深审） | 1241 | prompts.py:330 |
| `reflect_sysprompt`（修复器） | 241 | prompts.py:390 |
| 摘要 System（「你是会话摘要助手…」） | 25 | summarizer.py:64 |
| 摘要 Human 固定模板 `_SUMMARY_PROMPT`（去插值） | 246 | summarizer.py:19 |

**Worker expertise 一览（`workflow_workers.py:22`，共 18 个领域，前缀抬头 87 字）**

| worker | expertise（字） | worker | expertise（字） |
|---|---|---|---|
| chitchat 闲聊问候 | 0（skip_facts） | match 合婚配对 | 385（最大） |
| theory 术语理论 | 178（skip_facts） | family 六亲关系 | 332 |
| career 事业工作 | 193 | personality 性格心性 | 271 |
| wealth 财运收入 | 188 | social 社交人际 | 269 |
| love 恋爱感情 | 183 | migration 方位迁移 | 224 |
| marriage 婚姻关系 | 180 | general 综合咨询 | 233 |
| health 健康状态 | 183 | naming 起名改名 | 188 |
| study 学习考试 | 154 | auspicious 择吉择日 | 183 |
| liunian 大运流年 | 187 | children 子女生育 | 193 |

> 各断事 worker System 总长 = 1823 + 87 + expertise，落在 2064~2295 字；chitchat 无抬头 = 1823。

**硬上限（代码卡点）**
- 知识库注入：`_MAX_TEXT_PER_QUERY=600`（workflow_retrieval.py:30，单 query/单 chunk）；query 数 LLM 拆解路径 ≤4、断事路径 ≤4、理论路径 ≤2（`retrieve_for_context` 的 `max_docs=len(queries)`）→ 单轮知识总量 ≤ **~2520 字**（含每片段 ~16~30 字来源头）；旧常量 `_MAX_KNOWLEDGE_TOTAL` 已删除
- 相似命例：**已移除**。`case_library`（rag/case_store.py）仍存在但 workflow 主链路无任何调用方，注入量为 0
- 历史断事参考：`get_chart_facts_for_llm(limit=6)`（workflow_messages.py:115），每条 ≤250 字（chart_store.py:259），**无总上限**（6×250+条目头 ≈ 1570 字）
- 最近对话（Workflow）：`compact_history` 取**最近 3 条**，每条 `content[:250]` + 会话摘要（≤600）→ 段上限 ≈ 1400 字（workflow_messages.py:187）
- 最近对话（ReAct 闲聊短路）：`message_list[-6:]`，每条 `content[:180]` ≈ 1116 字上限
- ReAct 历史载入：`_load_history` 按 token 预算截断（`max_tokens=2000`，中文 1 字≈1.5 token 折算，xianzhi.py:556）
- 排盘事实：单盘 `fact_block` 实测 ≈ 1790~2000 字（含四柱详述/神煞按柱/天干关系，比旧版大幅加长）；双盘 ≈ 3500+；扩盘（target_years 跨多年）流年行增多，单盘可再增
- 会话摘要：每新增 **12 条**消息触发；旧摘要 + 最近 12 条（每条 `[:300]`）；新摘要 ≤600 字

---

## 七、场景总览（单轮总字符数，含调用 A+B+D；C 另算；摘要另算）

| 场景 | 路径 | LLM 调用 | 约字符数 | 约 Token |
|---|---|---|---|---|
| 闲聊（无命盘） | ReAct 短路 | B-chitchat | ~620 – 2000 | ~1120 – 3600 |
| 闲聊（已挂命盘） | Workflow | B-chitchat（跳过 D） | ~2040 – 3680 | ~3670 – 6630 |
| 纯理论 | Workflow | A + B-theory + D | ~8300 – 15800 | ~15000 – 28400 |
| 常规断事 | Workflow | A + B-regular + D | ~9800 – 23800 | ~17700 – 42800 |
| 合婚双盘 | Workflow | A + B-match + D | ~11700 – 27400 | ~21100 – 49400 |
| 工具循环（多步） | ReAct | 多步 think | 单步 ~2240–14100；3 步累计 ~20000–30000+ | 单步 ~4000–25400；3 步 ~36000–54000+ |
| + 会话摘要（第 6/12/18… 轮） | 公共 | 独立异步 | +930 – 4560 | +1680 – 8200 |

> 说明：上表"约字符数"为 A+B+D 合计区间（已含各自下限/上限），未叠加调用 C（修复）与摘要调用。相比 7/29 版本：①非闲聊 Worker 新增 LLM 深审（D）整段开销；②排盘事实块大幅加长；③相似命例注入移除；④知识库单 chunk 上限 850→600；⑤Workflow 最近对话由 6 条改为 3 条。ReAct 工具循环按"单步 + 3 步累计"单列，因其多步特性无法用单次区间表示。
