# 先知 Agent · LLM 输入 Token 预算总索引

> 目的：把 ReAct 与 Workflow 两条路径里**每一种对话方式**发给大模型（LLM）的全部内容、字符数、Token 数，按"一个方式一个独立文档"列清楚。
> 换算口径：**中文 1 字 ≈ 1.8 token**（仅估算，真实值取决于 tokenizer）。所有固定 prompt 长度均经 AST 实测；可变块按代码逻辑估算。
> 生成日期：2026-07-29

---

## 一、路径决策树（一次问答怎么走）

入口统一在 `app/agent/xianzhi.py` 的 `Xianzhi.run_stream / arun_stream`，按顺序判定：

```
用户提问
  │
  ├─ _workflow_context 已挂 且 not verbose ──► 【Workflow 路径】(_workflow_stream)
  │
  ├─ 无命盘 且 _is_chitchat()==True ──► 【ReAct·闲聊短路】(_chitchat_reply，1 次 LLM)
  │
  └─ 其余 ──► 【ReAct·工具循环】(BaseAgent.run_stream → ReActAgent，多步 LLM)
               （典型：verbose 调试 / 带命盘但 workflow 未启用 / 需工具补排盘）
```

**两条路径共用的公共调用**：会话跑完后 `_persist_history` 末尾触发【会话摘要】（`shared_summary.md`），异步后台执行，两条路径都会发生。

---

## 二、ReAct 路径文档

| 文档 | 对话方式 | 一句话说明 | LLM 调用 |
|---|---|---|---|
| [react_chitchat.md](./react_chitchat.md) | 闲聊短路 | 无命盘 + 闲聊意图，直接 1 次 LLM，不走循环、无工具（**注意：此"三层"是 ReAct `_is_chitchat` gate，非 Workflow 意图链路**） | 1 次 |
| [react_loop.md](./react_loop.md) | 工具循环 (think→act→observe) | 完整 ReAct 多步循环，工具 schema 常驻、结果逐轮回灌 | 每步 1 次，≤ max_steps |

## 三、Workflow 路径文档

| 文档 | 对话方式 / 调用 | 一句话说明 | LLM 调用 |
|---|---|---|---|
| [workflow_intent_routing.md](./workflow_intent_routing.md) | 意图分类防护链路（调用 A 之前） | `detect_domain`→`_looks_off_topic`→`_decompose_query`+`classify_question` 兜底；闲聊命中即跳过 LLM 拆解（用户口中的"三层判断"即指此） | 0~1 次 |
| [workflow_decompose.md](./workflow_decompose.md) | 意图拆解（调用 A） | 非闲聊且非离题时，先 LLM 拆 domain/queries；可被短路跳过 | ≤1 次 |
| [workflow_chitchat.md](./workflow_chitchat.md) | Worker 主回答·闲聊（调用 B） | 已挂命盘走 Workflow 的闲聊；跳过事实/命例，知识库固定 16 字 | 1 次 |
| [workflow_theory.md](./workflow_theory.md) | Worker 主回答·理论（调用 B） | 纯命理理论/术语；跳过事实/命例，但真检索知识库 | 1 次 |
| [workflow_regular.md](./workflow_regular.md) | Worker 主回答·常规断事（调用 B） | 事业/财运/健康等断事；注入排盘事实+命例+知识库+断事参考 | 1 次 |
| [workflow_match.md](./workflow_match.md) | Worker 主回答·合婚双盘（调用 B） | 双人合婚；双盘事实 + 合婚基础数据，System 最大 | 1 次 |
| [workflow_repair.md](./workflow_repair.md) | Reflextion 修复（调用 C） | 仅当 Reviewer 校验打回时，重放上下文改写；极少触发 | 0~1 次 |

> Workflow 一轮典型 = **A + B（+ C 若打回）**。各调用独立成表，叠加即总消耗。

## 四、公共调用文档

| 文档 | 说明 | LLM 调用 |
|---|---|---|
| [shared_summary.md](./shared_summary.md) | 会话摘要，后台线程异步；两条路径共用；每 6 条消息（3 轮）触发一次增量摘要 | 独立 1 次（异步） |

---

## 五、关键常量速查（AST 实测）

| 常量 | 值（字） | 位置 |
|---|---|---|
| `SYSTEM_PROMPT`（ReAct 主 persona） | 1479 | xianzhi.py:39 |
| `NEXT_STEP_PROMPT`（ReAct 工具指引） | 586 | xianzhi.py:73 |
| `FACT_GUARDRAILS`（有命盘时追加） | 276 | xianzhi.py:91 |
| ReAct 闲聊短路 System | 126 | xianzhi.py:380 |
| `_DECOMPOSE_SYSTEM`（Workflow 拆解） | 1147 | xianzhi_workflow.py |
| Workflow 基础 System（persona+规则+合规+风格） | 1022 | xianzhi_workflow.py `_build_messages` |
| Worker expertise：chitchat/general | 0 | DomainWorker |
| Worker expertise：theory | 178 | DomainWorker |
| Worker expertise：career | 193 | DomainWorker |
| Worker expertise：match | 385 | DomainWorker |
| 摘要 System | 25 | xianzhi.py:556 |

**硬上限（代码卡点）**
- 知识库注入：`_MAX_TEXT_PER_QUERY=850`（单 query）、`_MAX_KNOWLEDGE_TOTAL=2500`（累计）
- 相似命例：`case_library.search(top_k=1)`，单条 `content[:700]` + 标题头 ≈ 795 字上限
- 历史断事参考：`get_chart_facts_for_llm(limit=6)`，每条 `line[:250]`，**无总上限**（6×250+标题 ≈ 1570 字）
- 最近对话：`history[-6:]`，每条 `content[:250]`（ReAct 闲聊短路为 `[-6:]` 每条 `[:180]`）
- 会话摘要：每新增 6 条消息触发；旧摘要 + 最近 6 条（每条 `[:300]`）；新摘要 ≤600 字

---

## 六、场景总览（单轮总字符数，含调用 A+B；C 另算；摘要另算）

| 场景 | 路径 | 主回答调用 | 约字符数 | 约 Token |
|---|---|---|---|---|
| 闲聊（无命盘） | ReAct 短路 | B-chitchat | ~180 – 1570 | ~320 – 2820 |
| 闲聊（已挂命盘） | Workflow | B-chitchat | ~1176 – 3588 | ~2110 – 6460 |
| 纯理论 | Workflow | A + B-theory | ~2500 – 8200 | ~4500 – 14800 |
| 常规断事 | Workflow | A + B-regular | ~3600 – 12000 | ~6500 – 21600 |
| 合婚双盘 | Workflow | A + B-match | ~4800 – 13400 | ~8700 – 24100 |
| 工具循环（多步） | ReAct | 多步 think | 单步 ~2300–9100；3 步累计 ~14400 | 单步 ~4200–16400；3 步 ~26000 |
| + 会话摘要（第 3/6/9… 轮） | 公共 | 独立异步 | +540 – 2634 | +970 – 4740 |

> 说明：上表"约字符数"为调用 A+B 合计区间（已含各自下限/上限），未叠加调用 C（修复）与摘要调用。ReAct 工具循环按"单步 + 3 步累计"单列，因其多步特性无法用单次区间表示。
