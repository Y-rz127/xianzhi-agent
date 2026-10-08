# Workflow 路径 · 意图分类防护链路（answer() 入口）

> 注：当前默认编排后端为 **LangGraph（唯一实现）**（`xianzhi_langgraph.py`，`XianzhiWorkflow.__init__` 构建失败即快速失败，settings 已无 `workflow_backend` 切换项）。本文描述的意图防护发生在图编排**之前**（`answer()` 入口），其后才进入 classify→chart→retrieve→generate→check→repair 的图流程。

- **所属路径**：Workflow（`app/agent/workflow/xianzhi_workflow.py` 的 `XianzhiWorkflow.answer`，:178）
- **代码位置**：`xianzhi_workflow.py:191-202`（`answer()` 开头，`_decompose_query` 即"调用 A"之前）
- **作用**：在调用 LLM 拆解（调用 A）之前，先用轻量规则判定是否为闲聊。命中则**跳过 LLM 拆解**，直接走 chitchat Worker，节省 token 与延迟。
- **与 ReAct 路径的关系**：这是 Workflow 自己的意图路由，**不是** ReAct 路径的 `_is_chitchat`（后者见 `react_chitchat.md`）。用户口中"三层判断"通常指本文件描述的这条链路。

## 三层防护 + 兜底（按代码真实执行顺序）

> 用户常把这条链路画成 `0→1→2`，但代码实际执行顺序是 **第1层 → 第0层 → 第2层**（先查闲聊词，再查长文本无信号，最后才调 LLM）。作为"防护层级"概念二者等价。

| 层 | 机制/函数 | 代码位置 | 判定条件 | 是否调 LLM | 命中后的走向 |
|---|---|---|---|---|---|
| **第1层**（闲聊词短路） | `detect_domain` | `app/rag/retrieval.py:54` + 关键词表 `retrieval.py:48` | `DOMAIN_KEYWORDS["chitchat"]` 命中任一闲聊词：`你好 / 在吗 / 谢谢 / 辛苦 / 早上好 / 晚上好 / 晚安 / 最近怎么样 / 吃饭了吗 / 在干嘛 / 无聊 / 心情 / 压力大 / 烦 / 累 / 开心 / 难过 / 生日快乐 / 新年好` | 否（纯关键词） | 走 `classify_question`（关键词兜底，domain 已锁定 chitchat） |
| **第0层**（长文本无信号） | `_looks_off_topic` | `workflow_support.py:111` | `len(text) > 100` **且** 不含任何 `_ALL_BAZI_SIGNALS` 命理信号词（八字/命理/干支/五行/十神/事业…约 50 个，见 `workflow_support.py:54-108`） | 否（纯规则） | 强制 `domain=chitchat, label="闲聊问候"` |
| **第2层**（LLM 拆解） | `_decompose_query` | `xianzhi_workflow.py:118` | 前两层均未命中时调用 | **是（调用 A，用独立 decompose_model）** | LLM 返回 `domain/queries/needs_chart`；其 prompt（`domain_sysprompt`，prompts.py:361）已明确告知：**诗歌/故事/闲聊/日常流水账 → chitchat 且 `queries=[]`** |
| **兜底** | `classify_question` | `workflow_support.py:137` | 第2层 LLM 抛异常 / JSON 解析失败 → 返回 `None` | 否（纯关键词） | `intent = self._decompose_query(...) or classify_question(...)`（`xianzhi_workflow.py:202`），关键词兜底（含 `CHITCHAT_STRONG` 强闲聊词、天气/搜索工具型查询保护、年份→liunian 规则） |

### 关键要点

1. **第0层、第1层都是"零 LLM"短路**。命中即省掉调用 A（约 1221 字 System + 问题 N ≈ 1231–1471 字）那次 LLM 拆解。
2. **第2层 LLM 拆解的 prompt 内已内置闲聊识别**：即便走到 LLM，诗歌/故事/流水账等也会被 LLM 判为 `chitchat` 且 `queries=[]`，后续知识检索直接返回 15 字占位（`workflow_retrieval.py:77` 允许 chitchat 短路）。
3. **兜底 `classify_question` 也是零 LLM**：它内部有 `CHITCHAT_STRONG`（你好/在吗/谢谢…，`workflow_support.py:163-176`）与天气/搜索 hint 保护、年份/领域关键词打分，作为 LLM 拆解失败时的最后保障。
4. 三层全部未命中（即真实命理问题）→ 正常进入调用 A（LLM 拆解）+ 调用 B（Worker 主回答）+ 调用 D（Reviewer LLM 深审）。

## 对 Token 预算的影响

| 场景 | 走到的层 | 额外 LLM 调用 | 说明 |
|---|---|---|---|
| 短闲聊（"你好""在吗"） | 第1层命中 | 0（省调用 A） | 直接进入调用 B 的 chitchat Worker（约 2040–3680 字） |
| 长题外话（>100字且零命理词） | 第0层命中 | 0（省调用 A） | 同上 |
| 诗歌/故事/流水账 | 第2层 LLM 识别 | 1（调用 A） | LLM 判 chitchat + 空 queries，调用 B 仍为轻量闲聊 |
| 真实命理问题 | 三层均未命中 | 1（调用 A）+ 1（调用 B）+ 1（深审 D） | 完整流程 |

> 结论：闲聊类输入在 Workflow 路径下**最多只产生 1 次 LLM 调用（调用 B）**；只有走到第2层且 LLM 拆解成功时才多 1 次调用 A。这与 ReAct 闲聊短路（`react_chitchat.md`）的"1 次 LLM"结论一致，只是路由机制不同。

## 相关文档

- `workflow_decompose.md`：调用 A（`_decompose_query`）的完整输入 Token 预算
- `workflow_chitchat.md`：调用 B 在 chitchat 域下的 Token 预算
- `react_chitchat.md`：ReAct 路径 `_is_chitchat` 的另三层 gate（勿与本文件混淆）
