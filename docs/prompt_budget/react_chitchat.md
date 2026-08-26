# ReAct 路径 · 闲聊短路（_chitchat_reply）

> ⚠️ 澄清：本文的"三层判断"指 ReAct 路径 `_is_chitchat` 的三层 gate（verbose / 命盘上下文 / 意图分类）。**用户另指的"三层防护链路"是 Workflow 路径 `answer()` 入口的意图路由**（`detect_domain` → `_looks_off_topic` → `_decompose_query` + `classify_question` 兜底），详见 [`workflow_intent_routing.md`](./workflow_intent_routing.md)。两者不是一回事。

- **所属路径**：ReAct（`app/agent/xianzhi.py` 的 `Xianzhi` 类）
- **触发条件**：`run_stream` / `arun_stream` 到达 `_chitchat_reply()`（xianzhi.py:462）前需经过**三层判断**（此前文档漏写了 verbose 层）：
  1. **verbose 开关层** — `run_stream:509` / `arun_stream:535` 的 `not verbose`。`verbose=True`（调试透传 ReAct 步骤）时，即使是闲聊也强制走完整工具循环，**不做短路**。
  2. **命盘上下文层** — `_is_chitchat:453-458` 的 `if self._workflow_context: return False` 等三个放行条件（另有 `_bazi_pending` 八字待确认、`_birth_signal` 模糊生辰信号，命中任一则走 ReAct 调排盘工具）。存在 workflow 命盘上下文时不判为闲聊（此判定在 `run_stream:506` 已被 `if self._workflow_context and not verbose: return workflow` 先挡掉，这里是函数自包含的防御）。
  3. **意图分类层** — `_is_chitchat:459` 调 `classify_question(user_prompt).domain == "chitchat"`。只有意图分类器归到 `chitchat` 域才真正短路。
  - 三层全过（`not verbose` **且** 无命盘/排盘信号 **且** 意图为 chitchat）→ 调用 `_chitchat_reply()`。
- **LLM 调用点**：`xianzhi.py:484` → `self.chat_model.invoke(messages)`
- **调用次数**：固定 **1 次**，不走 ReAct 循环、不挂命盘、不调任何工具
- **特点**：token 最轻的对话方式；无 `SYSTEM_PROMPT`、无 `FACT_GUARDRAILS`、无工具 schema

## 输入 Token 预算（中文 1 字 ≈ 1.8 token）

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 347 | 347 | 347 | `CHITCHAT_SYSTEM` 常量（prompts.py:124，含 INJECTION_GUARD，len 实测 347 字） |
| 用户问题 | 30 | 50 | 280 | `user_prompt`（N 字，包裹在 HumanMessage 内） |
| 最近对话 | 0 | 900 | 1140 | 最近 6 条消息，每条 `ClassName: ` + `content[:180]`（xianzhi.py:470-477） |
| 输出要求 | 28 | 28 | 28 | 固定模板「【最近对话】…【用户说】…请正面回应，简短直接。」（字面量实测 28 字） |
| **合计字数** | **~405** | **~1325** | **~1795** | |
| **合计 Token** | **~729** | **~2385** | **~3231** | |

## 说明

- **最少**：首轮闲聊、无历史（`history_ctx="（无）"` 约 5 字）、问题极短。
- **典型**：已聊过几轮，最近对话累积约 6 条 × 平均 150 字 ≈ 900 字。
- **上限**：最近 6 条均满 180 字（6×190≈1140）+ 长问题 280 字。
- 此方式**不消耗** Workflow 路径的意图拆解、命盘事实、知识库检索等开销，是纯轻量闲聊。
