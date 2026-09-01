# Workflow 路径 · Reviewer 两层审核（调用 D）+ Reflextion 修复（调用 C）

> 注：当前默认编排后端为 **LangGraph（唯一实现）**。审核在图内 `check_node`（`xianzhi_langgraph.py:92`），修复在 `repair_node`（:132）；Reviewer 实现在 `workflow_workers.py` 的 `ReviewerWorker`（:272），修复消息拼装在 `workflow_messages.py` 的 `build_repair_messages`（:131）。旧版"Reviewer 纯正则校验、零 LLM"的描述已过期——现在是**正则快筛 + LLM 深审两层架构**。

- **所属路径**：Workflow（LangGraph 图编排）
- **触发条件与频率**：
  - **调用 D（LLM 深审）**：非闲聊 Worker 产出（调用 B）后，正则快筛（零 LLM）**通过**时调用；闲聊场景 `skip_llm=True` 整体跳过。**常规断事/理论/合婚轮次基本每轮 1 次**。
  - **调用 C（修复）**：仅当审核（正则快筛命中红线，或 LLM 深审打回）发现事实红线 / 古籍杜撰 / 合规词等问题时触发；修复后先 regex 快筛，仍不过才再走一次 LLM 重审。绝大多数轮次不触发。
- **LLM 调用点**：D 在 `workflow_workers.py:413`（`_llm_review` → `self._chat_model.invoke`，用独立 reviewer_model）；C 在 `xianzhi_langgraph.py:157` 经 `workflow_messages.invoke` 调用
- **调用次数**：D 常规 **1 次**（闲聊 0 次）；C **0 或 1 次**（极少 +1 次 LLM 重审）

## 调用 D · LLM 深审输入预算（中文 1 字 ≈ 1.8 token）

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 1241 | 1241 | 1241 | `REVIEWER_SYSTEM`（prompts.py:330，实测 1241 字：逻辑自洽/断法/知识一致/古籍真实性/表达/事实/十神/神煞/宽容度/范围边界 10 维 + JSON 输出格式） |
| 系统排盘事实 | 3106 | 3106 | 6210 | `_llm_review` 用 `format_fact_context` 全量渲染（实测单盘 3097 + 头 9）；合婚双盘追加「【对方命盘事实】」再 +3097 |
| 命理规则检索 | 25 | 1300 | 2529 | 与调用 B 同一份 knowledge 重放（含 9 字段头） |
| 用户问题 | 17 | 57 | 307 | 「【用户问题】」+ 原问题 |
| 待审核回答 | 208 | 600 | 1508 | 调用 B 产出的完整回答（含 8 字段头） |
| **合计字数** | **~4597** | **~6300** | **~11800** | |
| **合计 Token** | **~8275** | **~11340** | **~21240** | |

> 注意：深审 D 的排盘事实用 `format_fact_context` 全量渲染（比调用 B 里按需精简的 fact_block 更长），**闲聊场景跳过本调用**，是 Workflow 主链路相对 7/29 版本新增的最大固定开销。

## 调用 C · 修复输入预算（中文 1 字 ≈ 1.8 token）

| 段落 | 最少 | 典型 | 上限 | 说明 |
|---|---|---|---|---|
| System Prompt | 241 | 523 | 715 | `reflect_sysprompt`(241) + 断法抬头(87) + `worker.expertise`（chitchat/theory 类 241~508；career 523；match 715 最大，实测值） |
| 用户问题 | 67 | 107 | 307 | 「【用户问题】」7 + 包裹符 50 + 原问题 |
| 原回答（被打回） | 200 | 600 | 1500 | B 产出的完整回答 |
| Reviewer 问题列表 | 100 | 100 | 100 | 命中的红线/杜撰/合规问题（「【发现的问题】」固定格式） |
| 正确排盘事实 | 0 | 1800 | 5100 | `worker.skip_facts` 为真（chitchat/theory）时为 0；断事单盘 ~1800；合婚双盘 ~5100 |
| 合婚基础数据 | 0 | 0 | 900 | 仅 match 域重放 |
| 可用规则（知识重放） | 0 | 1300 | 2520 | 与 B 同一份 knowledge |
| 输出要求 | 12 | 12 | 12 | 「请输出修正后的最终回答。」 |
| **合计字数** | **~903** | **~4442** | **~11154** | |
| **合计 Token** | **~1625** | **~7996** | **~20077** | |

## 说明

- **两层架构省 token 的设计**：正则快筛发现问题 → 直接打回修复（省 1 次 D）；正则全通过 → 才花 1 次 D 深审；修复后再发现问题 → 先 regex 后 LLM 分级重审。
- **闲聊全跳过**：`check_node` 对 `intent.domain=="chitchat"` 传 `skip_llm=True`，且 `repair_node` 对闲聊直接返回原答案——闲聊轮总 LLM 调用恒为 1（调用 B）。
- **C 的最少场景**：theory 类被打回（skip_facts → 无事实重放）+ 极短原回答 → 约 903 字 / 1625 token。
- **C 的上限**：合婚双盘（事实 5100 + 合婚基础 900）+ 知识库满 2520 + 长原回答 1500。
- **出现频率**：D 每个非闲聊轮次固定 1 次；C 仅在被打回时出现，多数会话全程不触发。
- 与 `workflow_chitchat/theory/regular/match.md` 是**叠加**关系：一轮非闲聊会话的总 token = 调用 A + 调用 B + 调用 D（+ 若打回再 + 调用 C）。
