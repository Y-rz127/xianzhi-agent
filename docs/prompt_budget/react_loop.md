# ReAct 路径 · 工具循环（think → act → observe）

- **所属路径**：ReAct（`app/agent/xianzhi.py` 的 `Xianzhi` → `ToolCallAgent` → `ReActAgent`）
- **触发条件**：`run_stream`/`arun_stream` 中**既不满足**「`_workflow_context` 已挂 → 走 Workflow」**也不满足**「无命盘 + 闲聊意图 → 闲聊短路」时，落入 `BaseAgent.run_stream` 的真正 ReAct 循环。典型场景：① `verbose` 调试模式；② 带命盘但 workflow 编排未启用（`_workflow_context` 未挂）；③ 用户直接问命理但未提供出生信息、需工具补排盘。
- **LLM 调用点**：`app/agent/core/tool_call_agent.py:31` → `self._llm_with_tools.invoke(messages)`（每次 `think` 一次）
- **调用次数**：**每步 1 次，最多 `max_steps` 步**（多步时工具结果逐轮累积回灌）
- **特点**：
  - 独有开销——**工具 schema**（`bind_tools` 的全部工具定义）每次 `think` 都随请求发送。本地工具 17 个（`main.py:128`：bazi 系列 10 + search_web + scrape_web_page + do_terminate + search_knowledge + huangli_today + huangli_zeji + ziwei_chart）+ MCP 高德地图工具
  - 工具结果（bazi 排盘 / search_knowledge 知识片段）以 `ToolMessage` 留在 `message_list`，**后续每一步重新全量发送**，token 逐轮膨胀
  - `REACT_NEXT_STEP_PROMPT`（797 字，prompts.py:59）**仅注入一次**：`tool_call_agent.think:24-28` 按内容查重后作为 HumanMessage 追加，不再像旧版那样前两步重复注入
  - 历史载入 `_load_history`（xianzhi.py:556）按 **token 预算 2000**（中文 1 字≈1.5 token 折算）从 PG 记忆截取，而非固定条数

## 单次 think 的输入 Token 预算（中文 1 字 ≈ 1.8 token）

> 下表为「单步 think」构成；多步时「历史/工具结果」列逐轮累加。

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 1258 | 1258 | 5323 | `ORACLE_BASE_SYSTEM`（1258 字，经 prompts.py 导入，xianzhi.py:26 别名 `SYSTEM_PROMPT`）；若 `bazi_*` 工具中途挂上命盘，`Xianzhi._build_messages`（xianzhi.py:224-231）后续步骤再追加 `chart_context`（实测 ≈3170 字）+ `REACT_FACT_GUARDRAILS`（398 字） |
| 工具 Schema | 900 | 2000 | 3200 | `bind_tools` 全部工具定义（17 个本地工具 + MCP 高德），每次 think 都发 |
| 历史 / 工具结果 | 0 | 1200 | 5000 | 首步 0；后续累积 `AIMessage(tool_calls)` + `ToolMessage`（排盘/知识片段越长越重） |
| 用户问题 | 80 | 100 | 300 | 首条 HumanMessage，`_wrap_user_input` 包裹符实测 50 字（base_agent.py:24-29）+ 问题 N |
| 下一步指引 | 0 | 797 | 797 | `REACT_NEXT_STEP_PROMPT`（797 字），仅第 1 步注入一次 |
| **合计字数（单步）** | **~2238** | **~5355** | **~14620** | |
| **合计 Token（单步）** | **~4028** | **~9639** | **~26316** | |

## 多步累计（示例：跑 3 步）

| 步数 | 该步字数 | 累计字数 | 累计 Token |
|---|---|---|---|
| 第 1 步（首步） | ~2240 | ~2240 | ~4030 |
| 第 2 步 | ~6500 | ~8740 | ~15730 |
| 第 3 步 | ~8000 | ~16740 | ~30130 |

（典型口径：第 2/3 步在首步基础上叠加工具结果与历史；若中途挂盘，System 再 +3560 字/步。）

## 说明

- **最少**：首步、无历史、仅用户问题（1258 + 900 + 80）。
- **典型**：3 步内完成、工具结果中等（排盘 + 1 次检索）、含首步指引。
- **上限**：长链工具调用（bazi_full/ziwei_chart + 多次 search_knowledge）、工具返回超长、逼近 `max_steps`、中途挂载命盘（System 追加 ~3560 字）。
- **这是全系统 token 最容易爆炸的路径**——工具结果逐轮全量回灌 + 工具 schema 常驻。若用户带出生信息，系统会优先走 Workflow 路径（单次重但非循环），反而更省。
