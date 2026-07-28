# ReAct 路径 · 闲聊短路（_chitchat_reply）

> ⚠️ 澄清：本文的"三层判断"指 ReAct 路径 `_is_chitchat` 的三层 gate（verbose / 命盘上下文 / 意图分类）。**用户另指的"三层防护链路"是 Workflow 路径 `answer()` 入口的意图路由**（`detect_domain` → `_looks_off_topic` → `_decompose_query` + `classify_question` 兜底），详见 [`workflow_intent_routing.md`](./workflow_intent_routing.md)。两者不是一回事。

- **所属路径**：ReAct（`app/agent/xianzhi.py` 的 `Xianzhi` 类）
- **触发条件**：`run_stream` / `arun_stream` 到达 `_chitchat_reply()`（xianzhi.py:368）前需经过**三层判断**（此前文档漏写了 verbose 层）：
  1. **verbose 开关层** — `run_stream:423` / `arun_stream:449` 的 `not verbose`。`verbose=True`（调试透传 ReAct 步骤）时，即使是闲聊也强制走完整工具循环，**不做短路**。
  2. **命盘上下文层** — `_is_chitchat:363` 的 `if self._workflow_context: return False`。存在 workflow 命盘上下文（即 `_workflow_context is not None`）时不判为闲聊（此判定在 `run_stream:420` 已被 `if self._workflow_context and not verbose: return workflow` 先挡掉，这里是函数自包含的防御）。
  3. **意图分类层** — `_is_chitchat:365-366` 调 `classify_question(user_prompt).domain == "chitchat"`。只有意图分类器归到 `chitchat` 域才真正短路。
  - 三层全过（`not verbose` **且** `_workflow_context is None` **且** 意图为 chitchat）→ 调用 `_chitchat_reply()`。
- **LLM 调用点**：`xianzhi.py:393` → `self.chat_model.invoke(messages)`
- **调用次数**：固定 **1 次**，不走 ReAct 循环、不挂命盘、不调任何工具
- **特点**：token 最轻的对话方式；无 `SYSTEM_PROMPT`、无 `FACT_GUARDRAILS`、无工具 schema

## 输入 Token 预算（中文 1 字 ≈ 1.8 token）

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 126 | 126 | 126 | `_chitchat_reply` 内联提示（xianzhi.py:380，AST 实测 126 字） |
| 用户问题 | 30 | 50 | 280 | `user_prompt`（N 字，包裹在 HumanMessage 内） |
| 最近对话 | 0 | 900 | 1140 | 最近 6 条消息，每条 `ClassName: ` + `content[:180]`（xianzhi.py:375） |
| 输出要求 | 23 | 23 | 23 | 固定模板「【最近对话】…【用户说】…请自然回应。」（AST 实测 23 字） |
| **合计字数** | **~179** | **~1099** | **~1569** | |
| **合计 Token** | **~322** | **~1978** | **~2824** | |

## 说明

- **最少**：首轮闲聊、无历史（`history_ctx="（无）"` 约 5 字）、问题极短。
- **典型**：已聊过几轮，最近对话累积约 6 条 × 平均 150 字 ≈ 900 字。
- **上限**：最近 6 条均满 180 字（6×190≈1140）+ 长问题 280 字。
- 此方式**不消耗** Workflow 路径的意图拆解、命盘事实、知识库检索等开销，是纯轻量闲聊。
