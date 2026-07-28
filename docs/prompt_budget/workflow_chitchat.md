# Workflow 路径 · Worker 主回答（闲聊场景，调用 B-chitchat）

- **所属路径**：Workflow（`app/agent/xianzhi_workflow.py` 的 `XianzhiWorkflow`）
- **触发条件**：用户意图 `domain == "chitchat"` 且已挂命盘上下文（或其他非断事意图走 Workflow）→ `_build_messages` 选用 `chitchat` worker（expertise = 0 字）
- **LLM 调用点**：`xianzhi_workflow.py:1152` → `self.chat_model.invoke(messages)`（由 `_build_messages` 拼装）
- **调用次数**：每次问答 1 次（仅当 Reviewer 校验失败才追加 1 次修复，见 `workflow_repair.md`）
- **特点**：`chitchat` worker 的 `skip_facts=True` → **不注入系统排盘事实**；跳过相似命例；知识库走固定 16 字提示（不检索）

## 输入 Token 预算（中文 1 字 ≈ 1.8 token）

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 1022 | 1022 | 1022 | 基础 persona+规则+合规+风格（1022 字） + `chitchat.expertise`(0) |
| 用户问题 | 60 | 100 | 300 | 包裹符 52 字 + 原问题(N≈10~250) |
| 识别意图 | 38 | 42 | 50 | 领域+目标年份+置信度，固定模板 |
| 历史摘要 | 0 | 0 | 600 | `ctx.summary`，本函数不截断（上游控制） |
| 最近对话 | 0 | 200 | 1542 | 最近 6 条消息，每条 `content[:250]`（非 3 轮/200） |
| 系统排盘事实 | 0 | 0 | 0 | chitchat 跳过 |
| 相似命例 | 0 | 0 | 0 | chitchat 跳过 |
| 命理规则检索 | 16 | 16 | 16 | 闲聊固定 16 字提示，不检索知识库 |
| 输出要求 | 40 | 50 | 58 | length_rule(40~58) + 年份核对提醒 |
| **合计字数** | **~1176** | **~1430** | **~3588** | |
| **合计 Token** | **~2117** | **~2574** | **~6458** | |

## 说明

- **最少**：首轮闲聊、无摘要、无历史、短问题 → 约 1176 字 / 2117 token。
- **典型**：已聊数轮，最近对话中等填充 + 固定知识库提示。
- **上限**：历史摘要打满 600 + 最近对话 6 条满 250（1542）+ 长问题；系统排盘事实始终为 0（闲聊不参与命理分析）。
- 与 `react_chitchat.md` 的区别：此处走 Workflow 编排（已挂命盘上下文时），System 用 Workflow 的 1022 字规则集而非 ReAct 的 1479 字；但同样跳过命理事实注入。
