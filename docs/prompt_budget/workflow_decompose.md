# Workflow 路径 · 意图拆解（_decompose_query，调用 A）

> 注：当前默认编排后端为 **LangGraph（唯一实现）**（`xianzhi_langgraph.py`）。拆解发生在图编排之前的 `answer()` 入口；图内 `classify_node` 优先复用本次拆解结果，不再重复调用。

- **所属路径**：Workflow（`app/agent/workflow/xianzhi_workflow.py` 的 `XianzhiWorkflow`）
- **触发条件**：`answer()` 中 `detect_domain` 不是 `chitchat` **且** `_looks_off_topic` 为 False 时才调用（xianzhi_workflow.py:191-202）；否则用 `classify_question` 关键词兜底，**不消耗这次 LLM**
- **LLM 调用点**：`xianzhi_workflow.py:131` → `self._decompose_model.invoke(messages)`。拆解模型为**独立轻量模型**（`main.py` 按 `settings.decompose_model` 构造，temperature 0.1，thinking 由 `DECOMPOSE_ENABLE_THINKING` 按模型能力配、启动探活会纠正；未配置时复用主模型）
- **调用次数**：每次问答 **最多 1 次**，且可能被短路跳过
- **产出**：结构化 `{domain, target_years, queries, needs_chart, other_birth_time, other_gender, confidence}`，供后续检索与 LangGraph 路由（queries ≤3 条）

## 输入 Token 预算（中文 1 字 ≈ 1.8 token）

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 1694 | 1694 | 1694 | `_DECOMPOSE_SYSTEM = domain_sysprompt`（prompts.py，意图分类规则 + 18 个 domain 取值表 + 检索词规范 + match 对方生辰字段说明 + 前文使用规则，实测 1694 字） |
| 用户问题 | 10 | 50 | 250 | 原始 `user_prompt`；**有历史时**包在【当前用户消息】块里 |
| 前文对话 | 0 | ~400 | ~1700 | `compact_history`（最近 3 轮 × 每条截 250 字 + 会话摘要）；**无历史时为 0**（保持纯问题格式） |
| **合计字数** | **~1704** | **~2144** | **~3644** | |
| **合计 Token** | **~3067** | **~3859** | **~6559** | |

## 说明

- 这是 Workflow 路径中**最轻的一次 LLM 调用**，且**并非每次都发生**（闲聊 / 明显离题时直接跳过，省掉这次）。
- 无命盘事实、知识库、命例注入；**前文对话**（2026-10-08 新增）仅用于指代消解与话题延续。
- 若被短路，本轮问答的 LLM 调用次数从「A+B+D(+C)」降为「B(+C)」。
- 相比 7/29 版本：拆解 System 由 1147 字扩到 1221 字（补 needs_chart / other_birth_time 字段说明与 query 构造示例），且拆解可走独立轻量模型，成本与主模型解耦。
- **2026-10-08 追加**：拆解请求注入最近 3 轮对话 + 会话摘要。起因：短追问（「继续」「那我的呢」「还有呢」）
  脱离前文无法判定领域 —— 实测无前文时拆解**失败**（「继续」「那我的呢」）或**误判 chitchat**（「还有呢」「详细说说」），
  带前文后全部正确识别为 `love` 并给出正缘相关检索词。前文块措辞强调「仅供指代消解、意图以当前消息为准」，
  防两类误判（前文聊命理≠当前也命理；不得把前文 domain 直接搬过来）。复用生成阶段的
  `compact_history`（同一压缩口径，不引入第二套历史格式化），无历史时不注入、保持原格式。
