# Workflow 路径 · 意图分类防护链路（answer() 入口）

- **所属路径**：Workflow（`app/agent/xianzhi_workflow.py` 的 `XianzhiWorkflow.answer`）
- **代码位置**：`xianzhi_workflow.py:704-715`（`answer()` 开头，`_decompose_query` 即"调用 A"之前）
- **作用**：在调用 LLM 拆解（调用 A）之前，先用轻量规则判定是否为闲聊。命中则**跳过 LLM 拆解**，直接走 chitchat Worker，节省 token 与延迟。
- **与 ReAct 路径的关系**：这是 Workflow 自己的意图路由，**不是** ReAct 路径的 `_is_chitchat`（后者见 `react_chitchat.md`）。用户口中"三层判断"通常指本文件描述的这条链路。

## 三层防护 + 兜底（按代码真实执行顺序）

> 用户常把这条链路画成 `0→1→2`，但代码实际执行顺序是 **第1层 → 第0层 → 第2层**（先查闲聊词，再查长文本无信号，最后才调 LLM）。作为"防护层级"概念二者等价。

| 层 | 机制/函数 | 代码位置 | 判定条件 | 是否调 LLM | 命中后的走向 |
|---|---|---|---|---|---|
| **第1层**（闲聊词短路） | `detect_domain` | `retrieval.py:55` + 关键词表 `retrieval.py:49` | `DOMAIN_KEYWORDS["chitchat"]` 命中任一闲聊词：`你好 / 在吗 / 谢谢 / 辛苦 / 早上好 / 晚上好 / 晚安 / 最近怎么样 / 吃饭了吗 / 在干嘛 / 无聊 / 心情 / 压力大 / 烦 / 累 / 开心 / 难过 / 生日快乐 / 新年好` | 否（纯关键词） | 走 `classify_question`（关键词兜底，domain 已锁定 chitchat） |
| **第0层**（长文本无信号） | `_looks_off_topic` | `xianzhi_workflow.py:72` | `len(text) > 100` **且** 不含任何 `_ALL_BAZI_SIGNALS` 命理信号词（八字/命理/干支/五行/十神/事业…见 `:62-69`） | 否（纯规则） | 强制 `domain=chitchat, label="闲聊问候"` |
| **第2层**（LLM 拆解） | `_decompose_query` | `xianzhi_workflow.py:639` | 前两层均未命中时调用 | **是（调用 A）** | LLM 返回 `domain/queries/needs_chart`；其 prompt（`_DECOMPOSE_SYSTEM:619-622`）已明确告知：**诗歌/故事/闲聊/日常流水账 → chitchat 且 `queries=[]`** |
| **兜底** | `classify_question` | `xianzhi_workflow.py:439` | 第2层 LLM 抛异常 / JSON 解析失败 → 返回 `None` | 否（纯关键词） | `intent = self._decompose_query(...) or classify_question(...)`（`:715`），关键词兜底 |

### 关键要点

1. **第0层、第1层都是"零 LLM"短路**。命中即省掉调用 A（约 1147 字 System + 问题 N ≈ 1177–1397 字）那次 LLM 拆解。
2. **第2层 LLM 拆解的 prompt 内已内置闲聊识别**：即便走到 LLM，诗歌/故事/流水账等也会被 LLM 判为 `chitchat` 且 `queries=[]`，后续命理规则检索注入量为 0（`xianzhi_workflow.py:666` 允许 `chitchat` 域空 queries 不报错）。
3. **兜底 `classify_question` 也是零 LLM**：它内部还有一组 `CHITCHAT_STRONG`（你好/在吗/谢谢…，`:465-468`）与年份/领域关键词打分，作为 LLM 拆解失败时的最后保障。
4. 三层全部未命中（即真实命理问题）→ 正常进入调用 A（LLM 拆解）+ 调用 B（Worker 主回答）。

## 对 Token 预算的影响

| 场景 | 走到的层 | 额外 LLM 调用 | 说明 |
|---|---|---|---|
| 短闲聊（"你好""在吗"） | 第1层命中 | 0（省调用 A） | 直接进入调用 B 的 chitchat Worker（约 1200 字） |
| 长题外话（>100字且零命理词） | 第0层命中 | 0（省调用 A） | 同上 |
| 诗歌/故事/流水账 | 第2层 LLM 识别 | 1（调用 A） | LLM 判 chitchat + 空 queries，调用 B 仍为轻量闲聊 |
| 真实命理问题 | 三层均未命中 | 1（调用 A）+ 1（调用 B） | 完整流程 |

> 结论：闲聊类输入在 Workflow 路径下**最多只产生 1 次 LLM 调用（调用 B）**；只有走到第2层且 LLM 拆解成功时才多 1 次调用 A。这与 ReAct 闲聊短路（`react_chitchat.md`）的"1 次 LLM"结论一致，只是路由机制不同。

## 相关文档

- `workflow_decompose.md`：调用 A（`_decompose_query`）的完整输入 Token 预算
- `workflow_chitchat.md`：调用 B 在 chitchat 域下的 Token 预算
- `react_chitchat.md`：ReAct 路径 `_is_chitchat` 的另三层 gate（勿与本文件混淆）
