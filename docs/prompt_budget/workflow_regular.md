# Workflow 路径 · Worker 主回答（常规断事场景，调用 B-regular）

- **所属路径**：Workflow（`app/agent/xianzhi_workflow.py` 的 `XianzhiWorkflow`）
- **触发条件**：用户意图为断事类（`domain` ∈ career / wealth / health / study / general 等，**非** chitchat / theory / match）→ `_build_messages` 选用对应 worker（以 `career` 为代表，expertise = 193 字）
- **LLM 调用点**：`xianzhi_workflow.py:1152` → `self.chat_model.invoke(messages)`（由 `_build_messages` 拼装）
- **调用次数**：每次问答 1 次（仅当 Reviewer 校验失败才追加 1 次修复，见 `workflow_repair` 说明）
- **特点**：断事类 worker `skip_facts=False` → **注入系统排盘事实**；**注入相似命例**（`top_k=1`）；**检索知识库**（1~3 query）；读取历史断事参考（`get_chart_facts_for_llm`，`limit=6`、每条 250 字、无总上限）

## 输入 Token 预算（中文 1 字 ≈ 1.8 token）

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 1215 | 1215 | 1215 | 基础 persona+规则+合规+风格(1022) + `career.expertise`(193) |
| 用户问题 | 62 | 100 | 302 | 包裹符 52 字 + 原问题(N≈10~250) |
| 识别意图 | 38 | 42 | 50 | 领域+目标年份+置信度，固定模板 |
| 历史摘要 | 0 | 150 | 600 | `ctx.summary`，本函数不截断（上游控制） |
| 最近对话 | 0 | 400 | 1542 | 最近 6 条消息，每条 `content[:250]` |
| 系统排盘事实 | 850 | 950 | 1000 | 四柱+大运+流年+五行（单盘，断事必注入） |
| 合婚基础数据 | 0 | 0 | 0 | 仅 match 域，此处为 0 |
| 历史断事参考 | 0 | 400 | 1570 | `limit=6`、每条 250、无总上限（6×250+标题≈1570） |
| 相似命例 | 0 | 600 | 795 | `top_k=1`，`content[:700]`+标题头；chitchat/theory 跳过，此处注入 |
| 命理规则检索 | 200 | 1500 | 2500 | 1~3 query×≤850，总封顶 2500（`_MAX_KNOWLEDGE_TOTAL`） |
| 输出要求 | 40 | 50 | 58 | length_rule(40~58) + 年份核对提醒 |
| **合计字数** | **~2405** | **~5407** | **~10632** | |
| **合计 Token** | **~4329** | **~9733** | **~19138** | |

## 说明

- **最少**：首轮断事、无摘要/历史/命例/断事参考、知识库仅命中 1 条小结果 → 约 2405 字 / 4329 token（主要由 1215 系统 + 850 排盘事实构成）。
- **典型**：中等历史 + 命盘事实 + 1 条历史断事 + 1 条相似命例 + 1~2 条知识库检索。
- **上限**：历史摘要 600 + 最近对话 1542 + 知识库满 2500 + 相似命例 795 + 断事参考 1570 + 长排盘 1000，几乎不可能同时打满，属理论峰值。
- 与 `workflow_theory.md` 差异：本场景注入排盘事实/相似命例/断事参考（理论场景全部跳过）；System 比理论多 15 字（career 193 vs theory 178）。
- 与 `workflow_match.md` 差异：本场景单盘（事实 ≤1000），合婚双盘（事实 ≤2200）+ 合婚基础数据(≤1500)。
- **本表仅算调用 B**；若加上调用 A（意图拆解，见 `workflow_decompose.md`，~1177~1397 字）或调用 C（修复，失败时出现），总 token 再叠加。常规断事通常 A+B 两次调用。
