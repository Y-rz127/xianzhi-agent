# Workflow 路径 · Worker 主回答（闲聊场景，调用 B-chitchat）

> 注：当前默认编排后端为 **LangGraph（唯一实现）**。消息拼装在图内 `generate_node`（`xianzhi_langgraph.py:76`）完成，实际拼装逻辑在 `app/agent/workflow/workflow_messages.py` 的 `build_messages`（:50）；闲聊场景 `check_node` 以 `skip_llm=True` 跳过 LLM 深审（`xianzhi_langgraph.py:113`）。

- **所属路径**：Workflow（LangGraph 图编排，节点逻辑委托 `XianzhiWorkflow`）
- **触发条件**：用户意图 `domain == "chitchat"` 且已挂命盘上下文（或其他非断事意图走 Workflow）→ `WORKERS` 选用 `chitchat` worker（expertise = 0 字，`workflow_workers.py:167`）
- **LLM 调用点**：`workflow_messages.py:172` 的 `invoke()` → `chat_model.bind(timeout=180).invoke(messages)`（闲聊时 `use_thinking(False)` 关闭思考模式）
- **调用次数**：每次问答 1 次（闲聊跳过 LLM 深审，也不会触发修复，见 `workflow_repair.md`）
- **特点**：`chitchat` worker `skip_facts=True` → **不注入系统排盘事实**（除非 LLM 拆解判定 `needs_chart=True`）；跳过历史断事参考；知识库走固定 15 字占位（不检索）

## 输入 Token 预算（中文 1 字 ≈ 1.8 token）

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 1823 | 1823 | 1823 | `ORACLE_BASE_SYSTEM`(1258) + `WORKFLOW_FACT_REDLINE`(563) 拼接（workflow_messages.py:74，实测 1823 字）；chitchat 无专属断法抬头 |
| 用户问题 | 67 | 107 | 307 | 「【用户问题】」7 字 + 包裹符 50 字（`_wrap_user_input` 实测）+ 原问题(N≈10~250) |
| 识别意图 | 34 | 42 | 52 | 「【识别意图】领域=…; 目标年份=…; 置信度=…」固定模板 |
| 历史摘要+最近对话 | 3 | 500 | 1386 | `compact_history`（workflow_messages.py:187）：会话摘要 ≤600 + **最近 3 条**（每条 `content[:250]`），空时"（无）"3 字 |
| 系统排盘事实 | 0 | 0 | 0 | chitchat 跳过 |
| 相似命例 | 0 | 0 | 0 | 已移除（全路径均为 0） |
| 命理规则检索 | 15 | 15 | 15 | 闲聊固定 15 字占位「（闲聊场景，无需命理知识检索）」，不检索知识库 |
| 输出要求 | 100 | 100 | 100 | 「【输出要求】」+ chitchat.length_rule(65) + 年份核对提醒(27) |
| **合计字数** | **~2042** | **~2587** | **~3683** | |
| **合计 Token** | **~3676** | **~4657** | **~6629** | |

## 说明

- **最少**：首轮闲聊、无摘要、无历史、短问题 → 约 2042 字 / 3676 token。
- **典型**：已聊数轮，最近 3 条对话中等填充 + 固定知识库占位。
- **上限**：历史摘要 600 + 最近 3 条满 250（≈1386 含头）+ 长问题 250；系统排盘事实始终为 0（闲聊不参与命理分析）。
- 相比 7/29 版本：基础 System 1022→1823 字（合并人设基座与事实红线）；最近对话由 6 条改为 3 条；知识库占位 16→15 字；LLM 深审对闲聊整体跳过。
- 与 `react_chitchat.md` 的区别：此处走 Workflow 编排（已挂命盘上下文时），System 用 Workflow 的 1823 字规则集而非 ReAct 的 581 字；但同样跳过命理事实注入。
