# ReAct 路径 · 工具循环（think → act → observe）

- **所属路径**：ReAct（`app/agent/xianzhi.py` 的 `Xianzhi` → `ToolCallAgent` → `ReActAgent`）
- **触发条件**：`run_stream`/`arun_stream` 中**既不满足**「`_workflow_context` 已挂 → 走 Workflow」**也不满足**「无命盘 + 闲聊意图 → 闲聊短路」时，落入 `BaseAgent.run_stream` 的真正 ReAct 循环（xianzhi.py 分支 C）。典型场景：① `verbose` 调试模式；② 带命盘但 workflow 编排未启用（`_workflow_context` 未挂）；③ 用户直接问命理但未提供出生信息、需工具补排盘。
- **LLM 调用点**：`tool_call_agent.py:27` → `self._llm_with_tools.invoke(messages)`（每次 `think` 一次）
- **调用次数**：**每步 1 次，最多 `max_steps` 步**（多步时工具结果逐轮累积回灌）
- **特点**：
  - 独有开销——**工具 schema**（`bind_tools` 的全部工具定义）每次 `think` 都随请求发送
  - 工具结果（bazi 排盘 / rag_search 命例规则）以 `ToolMessage` 留在 `message_list`，**后续每一步重新全量发送**，token 逐轮膨胀
  - `NEXT_STEP_PROMPT`（586 字）仅在前两步作为 HumanMessage 注入

## 单次 think 的输入 Token 预算（中文 1 字 ≈ 1.8 token）

> 下表为「单步 think」构成；多步时「历史/工具结果」列逐轮累加。

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 1479 | 1479 | 1761 | `SYSTEM_PROMPT`（1479 字）；若 `bazi_*` 工具中途挂上命盘，后续步骤再 +`FACT_GUARDRAILS`（276 字） |
| 工具 Schema | 800 | 1800 | 2500 | `bind_tools` 全部工具定义（bazi 系列 + search_knowledge + search_web + do_terminate + lunar_to_solar + MCP 高德），每次 think 都发 |
| 历史 / 工具结果 | 0 | 1200 | 4000 | 首步 0；后续累积 `AIMessage(tool_calls)` + `ToolMessage`（排盘/命例/规则越长越重） |
| 用户问题 | 30 | 50 | 250 | 首条 HumanMessage(`user_prompt`) |
| 下一步指引 | 0 | 586 | 586 | `NEXT_STEP_PROMPT`，仅前两步注入 |
| **合计字数（单步）** | **~2309** | **~5115** | **~9097** | |
| **合计 Token（单步）** | **~4156** | **~9207** | **~16374** | |

## 多步累计（示例：跑 3 步）

| 步数 | 该步字数 | 累计字数 | 累计 Token |
|---|---|---|---|
| 第 1 步（首步） | ~2309 | ~2309 | ~4156 |
| 第 2 步 | ~5115 | ~7424 | ~13363 |
| 第 3 步 | ~7000 | ~14424 | ~25963 |

## 说明

- **最少**：首步、无历史、仅用户问题（1479 + 800 + 30）。
- **典型**：3 步内完成、工具结果中等（排盘+1 次检索）、含前两步指引。
- **上限**：长链工具调用（如 bazi_full + 多次 rag_search）、工具返回超长、逼近 `max_steps`。
- **这是全系统 token 最容易爆炸的路径**——工具结果逐轮全量回灌 + 工具 schema 常驻。若用户带出生信息，系统会优先走 Workflow 路径（单次重但非循环），反而更省。
