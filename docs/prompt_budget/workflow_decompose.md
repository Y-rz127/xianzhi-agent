# Workflow 路径 · 意图拆解（_decompose_query，调用 A）

- **所属路径**：Workflow（`app/agent/xianzhi_workflow.py` 的 `XianzhiWorkflow`）
- **触发条件**：`answer()` 中 `detect_domain` 不是 `chitchat` **且** `_looks_off_topic` 为 False 时才调用（xianzhi_workflow.py:651、:715）；否则用 `classify_question` 关键词兜底，**不消耗这次 LLM**
- **LLM 调用点**：`xianzhi_workflow.py:651` → `self.chat_model.invoke(messages)`
- **调用次数**：每次问答 **最多 1 次**，且可能被短路跳过
- **产出**：结构化 `{domain, target_years, queries, confidence}`，供后续检索与 Worker 路由

## 输入 Token 预算（中文 1 字 ≈ 1.8 token）

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 1147 | 1147 | 1147 | `_DECOMPOSE_SYSTEM`（意图分类规则 + domain 取值表 + 检索词规范，AST 实测 1147 字） |
| 用户问题 | 30 | 50 | 250 | 原始 `user_prompt`（N 字） |
| **合计字数** | **~1177** | **~1197** | **~1397** | |
| **合计 Token** | **~2119** | **~2155** | **~2515** | |

## 说明

- 这是 Workflow 路径中**最轻的一次 LLM 调用**，且**并非每次都发生**（闲聊 / 明显离题时直接跳过，省掉这次）。
- 仅含 System + 用户问题，无任何命盘事实、知识库、命例注入。
- 若被短路，本轮问答的 LLM 调用次数从「A+B(+C)」降为「B(+C)」。
