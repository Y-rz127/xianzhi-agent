# 先知智能体 · 多 Agent 协作架构

> **Supervisor + 专业 Worker + Reviewer** 三层架构，用于提升命理分析的准确性与严谨性。

## 架构概览

```
                    ┌─────────────┐
   用户问题 ───────► │  Supervisor │  意图分类(复用 classify_question)
                    │             │  任务分派 + 结果验收
                    └──────┬──────┘
                           │ 按领域分派
          ┌────────┬───────┼────────┬────────┐
          ▼        ▼       ▼        ▼        ▼
      ┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐
      │事业   ││财运   ││婚姻   ││健康   ││理论   │  ← 专业 Worker（示意）
      │Worker ││Worker ││Worker ││Worker ││Worker │  专属断法 prompt
      │  …（实际共 18 个领域 Worker，见下方注册表）…                       │
      └───┬──┘└───┬──┘└───┬──┘└───┬──┘└───┬──┘  专属检索 query
          └────────┴───┬──┴────────┴────────┘
                       ▼
                ┌─────────────┐
                │  Reviewer   │  三重交叉校验
                │             │  事实 + 古籍真实性 + 合规
                └──────┬──────┘
                       │ ok?
                  ┌────┴────┐
                 yes        no
                  │         │ 回退 Worker 修复 (Reflextion)
                  ▼
              最终回答
```
完整数据流总结：
用户："我最近事业不太顺，想换工作，什么时候有机会？"
                    │
      ┌─────────────┼─────────────┐
      ▼             ▼             ▼
  意图分类        构造4条query    命盘事实注入
  domain=career   (前文已详述)    四柱/大运/流年/十神
      │             │             │
      ▼             ▼             │
  查WORKERS表    每条query →      │
  取career Worker  embedding检索  │
      │            → 2-gram重排   │
      │            → 跨query去重   │
      │            → 截断2500字    │
      │             │             │
      ▼             ▼             ▼
  expertise_prompt  knowledge片段  facts事实
  (拼入System)     (拼入Human)    (拼入Human)
      │             │             │
      └─────────────┼─────────────┘
                    ▼
           拼接完整 Prompt → 发给 LLM
拼接完整Prompt发给LLM：
System:
  你是先知，拥有数十年实战经验的八字命理师傅...
  硬性规则（事实红线）：...
  知识库规则：...
  合规红线：...
  说话风格：...
  篇幅规范：...
  【事业专项断法】                          ← Worker.expertise_prompt
  - 官杀为事业主星：正官主稳定公职、体制内...
  - 印星为权力依托：印星生扶则职位稳...
  ...

Human:
  【用户问题】
  我最近事业不太顺，想换工作，什么时候有机会？

  【识别意图】
  领域=事业工作; 目标年份=未指定; 置信度=0.68

  【最近对话摘要】
  （无）

  【系统排盘事实】
  八字：甲子 丙寅 甲午 庚午
  大运：丁卯(1-10岁) 戊辰(11-20岁) ...
  当前大运：庚午(31-40岁)
  日主：甲木，身旺
  十神：...
  神煞：...

  【命理规则检索】
  [片段1] (来源:事业断法规则卡): ...
  [片段2] (来源:流年断法): ...
  ...（共9个片段，2500字符）

  【输出要求】
  常规分析2-3段≤400字，口语化，一针见血。
  如果提到具体年份，必须同时核对该年流年干支和所在大运。

两条路径对比
ReAct 路径（rag_search.py + retrieval.py）
LLM 主动调用 search_knowledge 工具时触发：
search_knowledge(query="什么是伤官见官")
  │
  ▼
expand_knowledge_queries(query)     ← retrieval.py:276
  │
  ├─ query 1: "什么是伤官见官"          ← 用户原句
  ├─ query 2: (理论术语精准query，如果命中)
  └─ query 3: "八字事业 官杀 印星 食伤 大运流年 命理"  ← DOMAIN_RULE_QUERIES（我们的改动生效）
  │
  ▼
search_deduped(queries, max_docs=6)  ← retrieval.py:295
  │
  └─ 逐条调用 knowledge_base.search(query)
       │
       └─ _search_reranked() → fetch_k=6 粗排 → 2-gram 取 top 2
       │
  └─ 跨 query 去重（来源+前120字），最多6条文档
  │
  ▼
返回格式化文本给 LLM（无单query/总字符限制）

Workflow 路径（xianzhi_workflow.py）
确定性流程，不走 LLM 工具调用：
_retrieve_rules()
  │
  ▼
_build_duxing_queries()             ← workflow:899
  │
  ├─ query 1: 用户原句
  ├─ query 2: "事业工作 甲日主 身旺 大运流年"     ← 个性化（日主+强弱）
  ├─ query 3: "八字事业 官杀 印星 食伤 大运流年 命理"  ← DOMAIN_RULE_QUERIES
  └─ query 4: "事业 升职 换工作 跳槽 伤官见官 官杀混杂 断法"  ← Worker.extra_queries
  │
  ▼
knowledge_base.search() × 4（每条query）
  │
  └─ _search_reranked() → fetch_k=6 粗排 → 2-gram 取 top 2
  │
  ▼
手动去重 + 控量：单query≤750字，总≤2800字
  │
  ▼
拼入 _build_messages() 的【命理规则检索】字段 → 发给 LLM
### 三种角色

| 角色 | 实现 | 职责 |
|------|------|------|
| **Supervisor** | `XianzhiWorkflow` | 意图分类、Worker 分派、Reviewer 验收、Reflextion 修复 |
| **专业 Worker** | `DomainWorker` + `WORKERS` 注册表 | 按领域专注单一断法，带专属 prompt 和检索 query |
| **Reviewer** | `ReviewerWorker` | 独立交叉校验，不通过则触发回退修复 |

## 核心组件

### 1. WorkerResult（最小结果协议）

参考 `学习资料/智能体开发笔记/16_多Agent协作/多Agent状态边界.md` 的最小结果协议，Worker 只返回结构化摘要，不返回完整对话历史，避免上下文爆炸。

```python
@dataclass(frozen=True)
class WorkerResult:
    status: str           # "done" | "blocked" | "failed"
    summary: str          # 断语结论
    evidence: list[str]  # 古籍引用 + 检索片段
    risks: list[str]
```

### 2. DomainWorker（领域 Worker 配置）

每个 Worker 有六样专属配置（`domain`/`label` 为身份字段，其余为行为配置）：

| 字段 | 说明 |
|------|------|
| `domain` | 领域标识（如 `"career"`），与 `WORKERS` 注册表的 key 一致 |
| `label` | 领域中文名（如 `"事业工作"`），用于日志与展示 |
| `expertise_prompt` | 追加到通用 system prompt 末尾的领域断法规则 |
| `extra_queries` | 叠加到 `DOMAIN_RULE_QUERIES` 之外的领域专属检索 query |
| `length_rule` | 领域专属篇幅规则 |
| `skip_facts` | theory/chitchat 跳过命盘事实注入 |

### 3. 专业 Worker 注册表

共 18 个领域 Worker：

| Worker | 领域 | 专属断法覆盖 |
|--------|------|------------|
| `career` | 事业工作 | 官杀/印星/食伤论事业、格局清浊 |
| `wealth` | 财运收入 | 正偏财/食伤生财/财库/比劫夺财 |
| `love` | 恋爱感情 | 配偶星/桃花/日支/红艳咸池 |
| `marriage` | 婚姻关系 | 配偶宫/夫妻星/合冲刑害/克配偶 |
| `health` | 健康状态 | 五行失衡/寒暖燥湿/七杀攻身 |
| `study` | 学习考试 | 印星/食伤/官星/文昌 |
| `social` | 社交人际 | 比劫/贵人星/七杀小人/日支合化 |
| `family` | 六亲关系 | 十神六亲/宫位/印财比劫食伤官杀 |
| `liunian` | 大运流年 | 大运流年作用/太岁/立春换年 |
| `theory` | 术语理论 | 术语解释规范/古籍引用格式 |
| `chitchat` | 闲聊问候 | 空（跳过检索+命盘） |
| `personality` | 性格心性 | 日主/十神组合/强弱/格局 |
| `migration` | 方位迁移 | 用神方位/驿马/迁移 |
| `naming` | 起名改名 | 用神喜忌/日主强弱/字形字义/调候 |
| `auspicious` | 择吉择日 | 用事人喜用神/事项用神/避凶煞/吉神 |
| `match` | 合婚配对 | 双盘对比/配偶宫夫妻星/刑冲合害/五行互补 |
| `children` | 子女生育 | 子女星/子女宫/生育时机/受克 |
| `general` | 综合咨询 | 兜底 |

### 4. ReviewerWorker（三重校验）

| 校验维度 | 实现 | 失败示例 |
|---------|------|---------|
| **事实校验** | 复用 `check_facts`（四柱/大运/流年） | "2024年甲辰" 写成 "2024年乙巳" |
| **古籍真实性** | 比对 `《XXX》原文：` 标注是否在检索结果中出现 | 检索结果无《XX书》，回答却引用了 |
| **合规校验** | 扫描死期/赌博/符咒/堕胎等红线关键词 | 回答含"死期""买彩票必赢" |

**古籍白名单**：渊海子平、子平真诠、滴天髓、穷通宝鉴、三命通会、神峰通考、盲派口诀——这些经典古籍即使未命中检索也允许引用（知识库已收录，检索可能未命中但属合理引用）。

## 执行流程

```
1. classify_question          → 意图分类（含 chitchat 强信号短路）
2. WORKERS.get(domain)         → Supervisor 分派专业 Worker
3. _retrieve_rules(worker)     → Worker 专属检索（叠加 extra_queries）
4. _build_messages(worker)     → Worker 专属断法 prompt
5. _invoke                    → Worker 生成回答
6. _reviewer.review()         → Reviewer 三重校验
7. 通过 → 返回 / 未通过 → Reflextion 回退修复
```

### 日志链路

控制台完整日志输出：

```
[Supervisor] 意图=事业工作 置信度=0.65 → 分派给 事业工作 Worker
[workflow检索] 领域=career 命主=甲木身旺 构造query数=5
[workflow检索] [1/5] query=八字事业 官杀 印星 食伤 大运流年
  返回=《渊海子平》论官杀：正官主稳定公职…
[workflow检索] [2/5] query=工作变动 跳槽 流年 大运 命理
  返回=（无匹配）
[Reviewer] 事业工作 Worker 产出通过三重校验
```

## 闲聊短路机制

闲聊场景有双重短路，分别在 ReAct 路径和 workflow 路径生效。

### ReAct 路径（无命盘时）

在 [xianzhi.py](app/agent/xianzhi.py) 的 `run_stream` / `arun_stream` 前置短路：

```python
if not verbose and self._is_chitchat(user_prompt):
    reply = await asyncio.to_thread(self._chitchat_reply, user_prompt)
    yield reply
    return
```

- `_is_chitchat()`：无命盘 + `classify_question` 判定 chitchat → True
- `_chitchat_reply()`：直接调一次 LLM，用闲聊专属 prompt（1-3句≤150字、老友口吻），不调任何工具
- 日志：`[xianzhi] 闲聊短路，跳过 ReAct 工具调用`

### workflow 路径（有命盘时）

在 [xianzhi_workflow.py](app/agent/xianzhi_workflow.py) 的 `_retrieve_rules` 最优先短路：

```python
if intent.domain == "chitchat":
    return "（闲聊场景，无需命理知识检索）"
```

加上 `chitchat` Worker 的 `skip_facts=True`，闲聊时不注入命盘事实、不检索知识库，但仍走 Reviewer 合规校验。

### 闲聊判定规则

`classify_question` 的 chitchat 优先判定（[xianzhi_workflow.py L436-L437](app/agent/xianzhi_workflow.py#L436-L437)）：

```python
CHITCHAT_STRONG = ("哈哈", "你好", "在吗", "谢谢", "辛苦", "早上好", "晚上好", "晚安",
                   "吃饭了吗", "在干嘛", "生日快乐", "新年好")
if any(w in text for w in CHITCHAT_STRONG) and not years:
    best_domain = "chitchat"
```

命中强信号词且无年份 → 直接判 chitchat，避免被 liunian 的"最近"等词抢走。

## 双路径架构

先知智能体有两条执行路径，根据命盘上下文自动切换：

| 条件 | 路径 | 架构 |
|------|------|------|
| 有命盘 (`_workflow_context`) | workflow | Supervisor + Worker + Reviewer |
| 无命盘 | ReAct | LLM 自主调工具（bazi/search_knowledge/search_web） |

### 切换逻辑

[xianzhi.py arun_stream](app/agent/xianzhi.py#L428) 的分流：

```python
if self._workflow_context and not verbose:
    async for chunk in self._aworkflow_stream(user_prompt):
        yield chunk
    return
# ReAct 路径
if not verbose and self._is_chitchat(user_prompt):
    reply = await asyncio.to_thread(self._chitchat_reply, user_prompt)
    yield reply
    return
async for _ in super().arun_stream(user_prompt):
    pass
```

### 适用场景

- **workflow 路径**：已挂载命盘后的所有对话（含闲聊、术语、专项断事）
- **ReAct 路径**：第一次对话没命盘、用户主动提供生辰让 LLM 排盘、纯术语问答
- **闲聊短路**：两条路径都有，避免"你好"也触发工具调用

## 知识检索的分层（RAG）

两条路径的知识检索都遵循「Layer 1 单 query MMR + Layer 2 多 query 编排」的两层结构，但上层的编排逻辑在两条路径里是**两套独立实现**，预算口径也不同。

### Layer 1 — 单 query 向量检索（`app/rag/vector_store.py`）

- `knowledge_base.search(q)` 走 MMR：`k=2`、`fetch_k=6`、`lambda_mult=0.5`，即由 6 个候选选出 2 条「相关且多样」的片段。
- 只解决「给定一条成型 query，返回最相关且多样的 2 条」；不负责查询改写、多意图合并、跨 query 去重与预算。同时也是 Layer 2 的内层原语。

### Layer 2 — 多 query 编排（扩展 + 跨 query 去重 + 预算）

解决 Layer 1 管不了的事：用户口语化问题 embedding 后检索差 → 扩展为多个角度提升召回；不同 query 命中同一片段需去重；并控制送进 LLM 的上下文预算。两套实现如下：

| 路径 | 上层实现 | query 来源 | 去重键 | 预算上限 |
|------|---------|-----------|--------|---------|
| ReAct 工具（`tools/rag_search.py`） | `search_deduped(expand_knowledge_queries(query), max_docs=6)` | 原文 + 理论术语精准 query + 领域规则 query（最多 4 条） | `(来源, 内容前120字)` | **最多 6 条文档** |
| 工作流（`xianzhi_workflow._retrieve_rules`） | 自研循环（不调用 `search_deduped`） | LLM 拆解 `intent.queries`（限 2 条）/ theory 路径 / 断事路径（`DOMAIN_RULE_QUERIES[domain]` + `worker.extra_queries`） | 内容前 120 字 | **`_MAX_KNOWLEDGE_TOTAL=3500` 字符**（单 query 还受 `_MAX_TEXT_PER_QUERY` 截断） |

> 注意：ReAct 工具路径的 Layer 2 即文档常说的 `search_deduped`（6 条文档上限）；但真正产出答案的**工作流路径并未调用 `search_deduped`**，而是用 3500 字符预算的自研循环。两者都会把每条 query 交给 Layer 1 的 `search_as_text` 执行 MMR，再跨 query 去重。

## LangGraph 集成

[xianzhi_langgraph.py](app/agent/xianzhi_langgraph.py) 是可选的 LangGraph 封装，已接入新架构：

- `classify_node`：分类 + 分派 Worker（存入 state）
- `retrieve_node`：Worker 专属检索
- `generate_node`：Worker 专属断法 prompt 生成
- `check_node`：用 ReviewerWorker 做三重校验（替代旧的 check_facts）
- `repair_node`：Reflextion 回退修复

如果 LangGraph 未安装，自动回退到 `XianzhiWorkflow.answer()` 的原生流程，两者行为一致。

## 文件结构

```
app/agent/
├── xianzhi.py                  # 先知智能体主类（ReAct + workflow 分流 + 闲聊短路）
├── xianzhi_workflow.py          # Supervisor + Worker + Reviewer 核心
│   ├── WorkerResult             # 最小结果协议
│   ├── DomainWorker             # Worker 配置 dataclass
│   ├── WORKERS                  # 18 个领域 Worker 注册表
│   ├── ReviewerWorker           # 三重校验审核员
│   └── XianzhiWorkflow          # Supervisor（answer 方法）
└── xianzhi_langgraph.py         # 可选 LangGraph 封装（已接入新架构）
```

## 与学习资料的对应关系

参考 `学习资料/智能体开发笔记/16_多Agent协作/`：

| 学习资料概念 | 本实现 |
|------------|--------|
| Supervisor（单层监管者） | `XianzhiWorkflow` |
| 专业 Worker | `DomainWorker` + `WORKERS` 注册表 |
| Review Worker | `ReviewerWorker` |
| WorkerResult 最小协议 | `WorkerResult` dataclass |
| Reflextion 反思机制 | `_build_repair_messages` 回退修复 |
| 状态边界（Worker 不返回完整历史） | Worker 只返回 summary，不传递 message_list |

参考 `学习资料/智能体开发笔记/00_学习路线与总览/技术原理.md` 1.4 节的 6 种架构对比：

- **单智能体**：能力天花板低，一个 prompt 塞不下所有领域断法
- **网状网络**：命理要确定性，不需要辩论协商
- **单层监管者**：流程可控，Supervisor 分派+验收 ✓
- **监管工具调用**：轻量版，主 LLM 按需调专业子 Agent
- **分层多级**：过重，命理场景不需要企业级多层树形
- **自定义混合**：单层监管 + Reflextion 反思，贴合命理的"事实校验"刚需 ✓

**最终选择**：单层监管者 + Reviewer 反思闭环的混合架构。命理的核心痛点是**严谨性**而非**创意性**，价值来自**交叉验证**（Reviewer 审 Worker），不是多视角协商。

## 扩展 Worker

新增领域 Worker 只需在 `WORKERS` 注册表添加配置：

```python
WORKERS["new_domain"] = DomainWorker(
    domain="new_domain",
    label="新领域",
    expertise_prompt=(
        "【新领域专项断法】\n"
        "- 专属断法规则1\n"
        "- 专属断法规则2\n"
    ),
    extra_queries=("新领域 专属检索 query",),
    length_rule="新领域专属篇幅规则",
    skip_facts=False,
)
```

并在 `DOMAIN_KEYWORDS` 和 `DOMAIN_RULE_QUERIES` 添加对应配置即可。

## 测试

运行架构测试（不依赖真实 LLM）：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_xianzhi_workflow.py -q
```

测试覆盖：
1. 模块导入完整性
2. Worker 注册表完整性（18 个领域）
3. ReviewerWorker 三重校验（事实/古籍真实性/合规）
4. classify_question 闲聊判定
5. XianzhiWorkflow 实例化 + Reviewer 注入
6. chitchat Worker 跳过检索
7. Worker expertise_prompt 注入到 system message
8. LangGraph 图编译与 invoke

## 设计原则

1. **最小侵入**：所有改动集中在 `xianzhi_workflow.py` 和 `xianzhi.py`，不新建文件
2. **向后兼容**：`_retrieve_rules` / `_build_messages` / `_build_repair_messages` 都加了可选参数，LangGraph 节点和 eval 脚本无需改动
3. **确定性优先**：命理事实是客观的（排盘结果确定），不需要多 Agent 协商投票
4. **专业深度 + 交叉校验**：单领域 Worker 更短更专业，Reviewer 用不同视角审视避免盲区
5. **闲聊双重短路**：ReAct 路径和 workflow 路径都有短路，避免无谓工具调用
