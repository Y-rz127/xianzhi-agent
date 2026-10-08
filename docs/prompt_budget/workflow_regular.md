# Workflow 路径 · Worker 主回答（常规断事场景，调用 B-regular）

> 注：当前默认编排后端为 **LangGraph（唯一实现）**。消息拼装在图内 `generate_node` 完成，实际逻辑在 `workflow_messages.py` 的 `build_messages`（:50）；非闲聊 Worker 产出后 Reviewer LLM 深审恒定追加 1 次（见 `workflow_repair.md` 调用 D）。

- **所属路径**：Workflow（LangGraph 图编排，节点逻辑委托 `XianzhiWorkflow`）
- **触发条件**：用户意图为断事类（`domain` ∈ career / wealth / love / marriage / health / study / social / family / liunian / personality / migration / naming / auspicious / children / general 等，**非** chitchat / theory / match）→ `WORKERS`（`workflow_workers.py:22`，共 18 个领域）选用对应 worker。本表以 `career` 为代表，expertise = 193 字（其余断事 worker 的 expertise 见 INDEX 速查表，System 总长落在 2064~2295 字区间）
- **LLM 调用点**：`workflow_messages.py:172` 的 `invoke()` → `chat_model.bind(timeout=180).invoke(messages)`
- **调用次数**：每次问答 1 次（Reviewer 深审 D 恒定 1 次；仅被打回才追加修复 C）
- **特点**：断事类 worker `skip_facts=False` → **注入系统排盘事实**（新版 fact_block 含四柱详述/神煞按柱/天干关系，实测远重于旧版）；~~注入相似命例~~（**已移除**：`case_library` 无调用方）；**检索知识库**（≤4 query）；读取历史断事参考（`get_chart_facts_for_llm(limit=6)`、每条 ≤250 字、无总上限）

## 输入 Token 预算（中文 1 字 ≈ 1.8 token）

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 2103 | 2103 | 2295 | 基础(1823) + 断法抬头(87) + `worker.expertise`（career 193，实测 2103 字；worker 间差异 ±230） |
| 用户问题 | 67 | 107 | 307 | 「【用户问题】」7 + 包裹符 50 + 原问题(N≈10~250) |
| 识别意图 | 34 | 42 | 52 | 领域+目标年份+置信度，固定模板 |
| 历史摘要+最近对话 | 3 | 400 | 1386 | 会话摘要 ≤600 + 最近 3 条（每条 `content[:250]`，workflow_messages.py:187） |
| 系统排盘事实 | 1790 | 1800 | 2500 | 单盘 `fact_block` 实测：指定目标年份 1790、默认近 4 年 2008；扩盘跨多年流年行增多（workflow_messages.py:208） |
| 合婚基础数据 | 0 | 0 | 0 | 仅 match 域，此处为 0 |
| 历史断事参考 | 0 | 400 | 1570 | `limit=6`、每条 ≤250、无总上限（6×250+条目头≈1570，workflow_messages.py:101-125） |
| 相似命例 | 0 | 0 | 0 | **已移除**（旧版 `top_k=1` 注入逻辑已删除） |
| 命理规则检索 | 16 | 1300 | 2520 | ≤4 query（用户原句+个性化+领域规则+worker 专属，workflow_retrieval.py:146-177），每 chunk ≤600 + 片段头 ~16~30 |
| 输出要求 | 58 | 58 | 58 | 「【输出要求】」+ length_rule(24) + 年份核对提醒(27) |
| **合计字数** | **~4071** | **~6210** | **~10708** | |
| **合计 Token** | **~7328** | **~11178** | **~19274** | |

## 说明

- **最少**：首轮断事、无摘要/历史/断事参考、知识库仅命中 1 条小结果 → 约 4071 字 / 7328 token（主要由 2103 系统 + 1790 排盘事实构成）。
- **典型**：中等历史 + 命盘事实 + 1 条历史断事 + 1~2 条知识库检索。
- **上限**：历史摘要 600 + 最近对话 ~1400 + 知识库满 2520 + 断事参考 1570 + 长排盘 2500，几乎不可能同时打满，属理论峰值。
- 相比 7/29 版本：System 1215→2103 字；排盘事实 850~1000 → 1790~2500（四柱详述/神煞按柱/天干关系段新增）；相似命例注入移除；知识库单 chunk 850→600（但 query 上限 3→4）；最近对话 6 条→3 条。
- 与 `workflow_theory.md` 差异：本场景注入排盘事实/断事参考（理论场景默认跳过）；System 比理论多 15 字（career 193 vs theory 178）。
- 与 `workflow_match.md` 差异：本场景单盘（事实 ≤2500），合婚双盘（事实 ~3500+）+ 合婚基础数据(~300~900)。
- **本表仅算调用 B**；加上调用 A（拆解，~1231~1471 字）与调用 D（Reviewer LLM 深审，~4600~11800 字，见 `workflow_repair.md`），常规断事一轮 A+B+D 约 9900~23800 字 / 17800~42800 token。
