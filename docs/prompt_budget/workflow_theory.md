# Workflow 路径 · Worker 主回答（理论场景，调用 B-theory）

> 注：当前默认编排后端为 **LangGraph（唯一实现）**。消息拼装在图内 `generate_node` 完成，实际逻辑在 `workflow_messages.py` 的 `build_messages`（:50）；理论场景**不跳过** LLM 深审（仅 chitchat 跳过），非闲聊 Worker 产出后会追加 1 次 Reviewer LLM 深审（见 `workflow_repair.md` 调用 D）。

- **所属路径**：Workflow（LangGraph 图编排，节点逻辑委托 `XianzhiWorkflow`）
- **触发条件**：用户意图 `domain == "theory"`（纯命理理论/术语/古籍问法）→ `WORKERS` 选用 `theory` worker（expertise = 178 字，`workflow_workers.py:153`）
- **LLM 调用点**：`workflow_messages.py:172` 的 `invoke()` → `chat_model.bind(timeout=180).invoke(messages)`
- **调用次数**：每次问答 1 次（Reviewer 深审 D 恒定 1 次；仅被打回才追加修复 C）
- **特点**：`theory` worker `skip_facts=True` → **默认不注入系统排盘事实**；但 `skip = worker.skip_facts and not intent.needs_chart`（workflow_messages.py:66）——当 LLM 拆解判定用户在问自己命盘（needs_chart=True，如"我是不是伤官见官"）时**仍会注入排盘事实**；跳过历史断事参考；**会检索知识库**（理论路径 query 构造见 `workflow_retrieval.py:126`）

## 输入 Token 预算（中文 1 字 ≈ 1.8 token）

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 2088 | 2088 | 2088 | 基础(1823) + 断法抬头(87) + `theory.expertise`(178)（实测 2088 字） |
| 用户问题 | 67 | 107 | 307 | 「【用户问题】」7 + 包裹符 50 + 原问题(N≈10~250) |
| 识别意图 | 34 | 42 | 52 | 领域+目标年份+置信度，固定模板 |
| 历史摘要+最近对话 | 3 | 400 | 1386 | 会话摘要 ≤600 + 最近 3 条（每条 `[:250]`） |
| 系统排盘事实 | 0 | 0 | ~2000 | theory 默认跳过；仅 needs_chart=True 时注入单盘事实（实测 ≈1790~2000 字） |
| 相似命例 | 0 | 0 | 0 | 已移除（全路径均为 0） |
| 命理规则检索 | 16 | 700 | 1260 | 理论路径 query ≤2 条（用户原句 + 命中术语的精准 query），每 chunk ≤600 + 片段头；`_MAX_TEXT_PER_QUERY=600`（workflow_retrieval.py:30） |
| 输出要求 | 68 | 68 | 68 | 「【输出要求】」+ theory.length_rule(33) + 年份核对提醒(27) |
| **合计字数** | **~2276** | **~3405** | **~5161** | |
| **合计 Token** | **~4097** | **~6129** | **~9290** | |

## 说明

- **最少**：首次理论提问、无历史摘要、知识库仅命中 1 条小结果 → 约 2276 字 / 4097 token。
- **典型**：理论问题触发 1~2 条知识库检索（古籍论断数百字）+ 中等历史。
- **上限**：知识库检索 ~1260（2 chunk 各 600 含头）+ 历史摘要 600 + 最近对话 3 条满 250；若叠加 needs_chart 的事实注入再 +2000。
- 相比 7/29 版本：System 1200→2088 字；知识库由"1~3 query×≤850、封顶 2500"改为"≤2 query×≤600"；最近对话 6 条→3 条。
- 与 `workflow_chitchat.md` 的关键差异：System 多 265 字理论断法（含抬头）；**知识库检索会真正执行**（上限 ~1260），而闲聊固定 15 字。
- **别忘了深审 D**：本表仅算调用 B；非闲聊场景 Reviewer LLM 深审恒定追加 1 次（约 4600~9200 字，见 `workflow_repair.md`）。
