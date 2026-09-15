# 先知智能体 后端架构审查报告

> 审查对象：`backend/app/` 全部 Python 代码
> 审查方法：AST 静态解析（依赖图谱 / 扇入扇出 / 循环检测 / 归一化去重 / 零引用扫描）
> 结论口径：所有问题均给出 `文件:行号` 实证，不含印象式判断

---

## 执行进度（2026-09-15 更新）

本报告同时是执行清单。截至当前，**阶段 0 / 1 / 2 已完成**，阶段 3 / 4 未开始。

| 阶段 | 内容 | 状态 | 回归 |
|---|---|---|---|
| 阶段 0 | 清死代码 + 建架构断言 | ✅ 完成 | 全绿 |
| 阶段 1 | 去重（纯搬运） | ✅ 完成 | 全绿 |
| 阶段 2 | 打破层级倒置 | ✅ 完成 | 全绿 + 端到端 |
| **前置** | **黄金命盘快照（§7.2 防线 2）** | ✅ **完成** | 全绿 + 变异验证 |
| 阶段 3 | 拆巨型函数 / 巨型文件 | ✅ 主体完成（4 项已拆；仅 `postgres_memory` / `tables` 待拆） | 快照 + 黄金样本 |
| 阶段 4 | 统一口径 + 门面拆除 | 🟡 门面拆除**已完成**（bazi_engine / xianzhi_workflow 两处，调用方直连）；P1-4 干支关系统一**已实施**（口径需需求方确认拍板） | 基线已清零（star/dual）+ 36 例黄金盘 |

**量化结果**（由 `tests/test_architecture.py` 的基线棘轮给出）：

| 指标 | 阶段 2 前 | 现在 |
|---|---|---|
| 分层倒置边 | 16 条 | **2 条**（`memory→tools`、`tools→agent`） |
| 包级循环依赖 | 5 组 | **2 组**（`agent⟷tools`、`db⟷rag`） |
| 双导入路径符号 | 28 个 | **0 个**（阶段 4 已拆两门面，符号统一直连） |
| `import *` | 1 处 | **0 处**（`domain.bazi_engine` 的 `import *` 随门面拆除消除） |
| 连接池实例 | 2 个 | **1 个** |

已消除的倒置边：`core→db`(2)、`sub_app→api`(11)、`tools→sub_app`(1)、`db→memory`(1)。

**验证口径**：`ruff check app/ tests/ scripts/` 0 error；`pytest -m "not integration"` **668 passed / 0 failed**；
并起真实服务打 8123 做了端到端核对（`/api/ai/huangli/*`、`/api/ai/admin/llm/chain` 读写 `app_config`、
`/api/ai/xianzhi/chart` 排盘、`/api/ai/metrics`、`/api/health`）。

**守卫有效性都用变异测试证明过**，不做"看起来有断言"的自证：
- 往 `domain/` 注入 `import core` → 分层断言失败；把已修条目留在基线 → 报"基线未同步"。
- 改 `shensha_calc` 灾煞描述串 → 黄金快照 24/24 用例失败，报错精确到字段路径。
- **拆完 `_compute_shensha` 后在新结构上重做变异**：把 `_year_branch.py` 的 `if i == 0:`
  全改成 `if i <= 1:`（模拟"跳过范围多一格 → 神煞静默消失"这一历史事故形态）→
  4 个用例失败，报错首行 `shensha_pillars[name=病符]: 条目消失` + `fact_context: 值已变`。

**阶段 3 首个成果**：`_compute_shensha` 513 行 → `domain/shensha_calc/` 包（6 族 + 70 行编排，
共 714 行含 docstring）。每一步拆分后跑快照，**全程零差异**。
配套新增三道神煞名册守卫（源码声明名册 / 冻结名册 / 黄金盘触发覆盖，59 名全覆盖），
并用贪心补 4 个用例把覆盖从 51/59 补到 59/59。

**阶段 3 后续三项也已落地**（2026-09-15，工作区）：

- **`check_facts` 451 行 → `agent/workflow/fact_check.py`（653 行）**：拆为模块级常量 +
  辅助函数 + 7 个维度校验（`_check_liunian_ganzhi / _check_dayun_ganzhi / _check_pillar_ganzhi /
  _check_shishen_pairs / _check_shishen_single / _check_shensha_existence / _check_shensha_pillar`）+
  `check_facts` 编排器。`workflow_messages.py`（480 行）不再持有该函数；`XianzhiWorkflow` 绑定
  `def check_facts(self, ...)`（`xianzhi_workflow.py:327`）委托给 fact_check，调用方
  `xianzhi_langgraph.py:137/216`、`xianzhi_eval.py:46` 走 `workflow.check_facts`。
  配套黄金样本防线：`tests/fact_check_golden.py` + `tests/test_fact_check_golden.py`
  + `scripts/fact_check_golden.py` + `tests/fixtures/fact_check_{cases,snapshots}.json`。
- **`api/xianzhi.py` 701 行 → 5 文件**：`xianzhi_chat.py`(261) / `xianzhi_chart.py`(196) /
  `xianzhi_report.py`(103) / `_xianzhi_common.py`(109)，`xianzhi.py` 收缩为 router 聚合 + 会话路由
  + 少量 re-export（115 行）。
- **`db/user_records.py` 608 行 → 包**：`db/user_records/{ai_interpretation,answer_feedback,
  favorites,feedback}.py`，`__init__.py` 显式 re-export 兼容既有导入路径。

**阶段 3 剩余**：`memory/postgres_memory.py`（612 行，类/模块级函数并存）、`domain/tables.py`
（864 行，约 568 行纯数据）尚未拆。

### 附：从格判定口径修复（2026-09-15，需求方拍板后实施）

**这不是重构，是口径变更**，故单列。原实现 `analysis_calc._detect_conging` 有一条
结构性不可满足的守卫：

```python
if weighted.get(day_wx, 0.0) > _CONG_SELF_WX_MAX:   # 0.50
    return None
```

`weighted` 把四柱**天干**都计入（各 1.0），而日干自身即日主 → `weighted[day_wx]` 恒 ≥ 1.0
（6 万样本实测最小值就是 1.0）。**该守卫恒真 ⇒ 从格是死代码**，而非"判定过严"。

需求方确认四项口径后实施（口径依据项目自有知识库 `33_从格专旺化气体系.md`）：

| 项 | 变更 |
|---|---|
| 自权重阈值 | **删除** `_CONG_SELF_WX_MAX`（与 `_root_profile` 重复） |
| 月令条件 | **补齐**「月令须为所从之神当令」（原完全缺失） |
| 真假从 | **补第三档**，`kind` 扩为 `"专旺" / "从格"(真从) / "假从"` |
| 从势阈值 | `_CONG_SECOND_RATIO` 0.60 → 0.80（从势占比 57% → 27%） |
| 破格之神 | **补齐**各子格第 4 条：从财忌官杀 / 从杀忌食伤 / 从儿忌印 / 从势无。<br>"有力" = 透干 或 地支见其本气（仅藏干余气不算） |

`_has_root()` 的 bool 升级为 `_RootProfile`（`verdict` 出 `有力 / 微根 / 无根` 三档）。
关键修正：知识库明确"藏干中**只要**有日主微根即为假从"，故根气门槛是**有一丝**，
而非原实现的本气级 0.30。

**验证**：真从不变量扫描 43,800 样本**零违反**（无禄刃库根 / 无藏干日主五行与印星 /
无透干印比 / 月令当令）；60 年 87,600 样本下 真从 18% / 假从 82%，
与知识库"假从居多、真从极少"一致；黄金快照**一例未变**（原先无任何从格用例）→ 据此补 8 例覆盖
从格八子格，用例 28 → 36；API 端到端确认 `analysis.special_pattern` 正确输出。

> **两个过程教训**：
> ① 写阈值前先确认被比较量的**取值域不含常项** —— 本例中"日主五行权重"含日干自身的固定 1.0，
> 任何 < 1.0 的阈值都是废的。同文件专旺侧用**占比**、从格侧用**绝对量**，两套量纲并存即是征兆。
> ② 快照工具的 `UPDATE_GOLDEN` 原先**无条件写盘**，刷新全部文件 mtime，使"哪些用例受影响"
> 无法从版本控制读出。已改为内容无变化则不落盘 —— 工具本身的可核对性也是防线的一部分。

**与初版报告的两处修正**：

1. `domain/ziwei/tables.py::branch_yinyang()` **不是死代码** —— 它由 `engine.py:300` 以
   `T.branch_yinyang(year_branch)` 属性形式调用，初版零引用扫描漏掉了属性调用形式（§六 已改注）。
2. **`memory` 的连接池早已统一** —— `app/memory/postgres_memory.py` 原本就 `from app.db.pool import get_pool`，
   初版"db 与 memory 各持一套池"的描述不准确。真实重复池在 `app/rag/fingerprint.py`（已修）。

---

## 一、审查范围与方法

| 项目 | 数值 |
|---|---|
| Python 文件数 | 120 |
| 总代码行数 | 22,471 |
| 顶层包数 | 11（core / domain / db / memory / rag / tools / agent / api / sub_app / tasks / evaluation） |
| 测试文件数 | 27 |

扫描使用的 5 类判定：

1. **依赖图谱**：AST 解析全部 `import` / `from ... import`，归一化 `app.x` 与相对导入为同一节点，产出扇入/扇出与跨层矩阵。
2. **循环检测**：在模块级有向图上做有界 DFS（深度 ≤ 7），用 frozenset 去重并剔除子集环。
3. **重复代码**：对 ≥8 行的函数做「去字面量 + 去变量名」的 AST dump 归一化，跨文件比对同构哈希。
4. **零引用扫描**：全 `backend/` 语料（含 tests / migrations）词边界计数，剔除路由装饰器与 `__init__` 再导出。
5. **巨型函数**：按 `end_lineno - lineno` 统计。

> 说明：初版扫描曾把 `module.func()` 形式的属性调用误判为零引用（正则负向断言错误排除了点号），`db/report_tasks.py`、`domain/ziwei/engine.py::cast_chart` 等被误报为死代码。本报告只保留修正后经二次人工核实的结果。

---

## 二、现状测绘

### 2.1 规模分布

| 包 | 文件 | 行数 | 占比 | 定位 |
|---|---:|---:|---:|---|
| `domain` | 18 | 5,782 | 25.7% | 命理计算引擎（纯算法） |
| `agent` | 16 | 4,754 | 21.2% | 编排层（ReAct + LangGraph workflow） |
| `api` | 21 | 2,766 | 12.3% | HTTP / WS 接口 |
| `db` | 10 | 1,989 | 8.9% | 持久化访问 |
| `tools` | 13 | 1,869 | 8.3% | 工具与报告生成 |
| `sub_app` | 16 | 1,788 | 8.0% | 子应用（塔罗/六爻/合婚/紫微/黄历） |
| `core` | 9 | 1,318 | 5.9% | 基础设施 |
| `rag` | 8 | 1,268 | 5.6% | 检索增强 |
| `memory` | 4 | 803 | 3.6% | 会话记忆 |
| `tasks` | 2 | 76 | 0.3% | 后台 worker |
| `evaluation` | 2 | 56 | 0.2% | 离线评估 |

### 2.2 实际依赖矩阵

行 = 依赖方，列 = 被依赖方，数字为该方向上的 import 语句数：

```
             core     domain         db     memory        rag      tools      agent        api    sub_app      tasks
   core         ·          ·          2          ·          ·          ·          ·          ·          ·          ·
 domain         ·          ·          ·          ·          ·          ·          ·          ·          ·          ·
     db         7          3          ·          ·          1          ·          ·          ·          ·          ·
 memory         8          1          1          ·          ·          1          ·          ·          ·          ·
    rag        10          1          1          ·          ·          ·          ·          ·          ·          ·
  tools         7          6          ·          ·          3          ·          1          ·          ·          ·
  agent        18          8          1          2          4          7          ·          ·          ·          ·
    api        28          9          6          ·          3          4          1          ·          5          1
sub_app        15          2          ·          ·          ·          2          6         11          ·          ·
  tasks         2          ·          ·          ·          ·          1          ·          ·          ·          ·
```

### 2.3 高扇入模块（改动影响面排名）

| 扇入 | 模块 | 评价 |
|---:|---|---|
| 56 | `core.logger` | 正常，日志是横切关注点 |
| 24 | `core.config` | 正常 |
| 14 | `api.common` | ⚠️ 校验工具放在 api 层，被 sub_app 反向依赖 |
| 12 | ~~`domain.bazi_engine`~~ | ~~⚠️ 纯重导出门面~~ → ✅ 已拆除（P0-1），扇入归零 |
| 11 | `core.llm_throttle` / `agent.prompts` | prompts 作为单一事实源，设计合理 |
| 10 | `api.context` | ⚠️ 上下文容器放在 api 层，见 P0-4 |

### 2.4 值得肯定之处

- **`domain` 层零越层依赖**：18 个文件全部只依赖 `domain` 内部 + 标准库/`lunar_python`，纯函数无 IO。这是全仓最干净的一层，分层纪律良好。
- **`core` 层对业务几乎零依赖**：仅有 2 处函数内 `import db.app_config`（见 P0-3）。
- **无模块级循环导入**：唯一一处 `agent.xianzhi_langgraph ⟷ agent.workflow.xianzhi_workflow` 环，实为门面重导出导致，非真环。
- 已完成的 R1（数据访问异步门面）/ R5（全局 state → AppContext）/ R9（workflow 拆分）三件重构方向正确，问题在于**收尾未完成**（旧门面未删）。

---

## 三、问题诊断

### P0-1 · 门面模块造成"双导入路径"（最高优先级） → ✅ 已拆除（2026-09-15）

**拆除结果**：`domain/bazi_engine.py`（71 行转发）与 `agent/workflow/xianzhi_workflow.py`（59 行 re-export）
两处门面文件已删除，20 处调用方 + 3 个测试文件统一改为各定义子模块直连导入（`orchestrator.py` 承载
`XianzhiWorkflow` 编排核心）。`import *`（`tables`）与全部双路径符号随之消除，`test_architecture.py` 的
`BASELINE_STAR_IMPORTS` / `BASELINE_DUAL_PATH_SYMBOLS` 已清零。

**证据**：

```
domain/bazi_engine.py        共 71 行 | import/re-export 占 65 行 | 自定义符号 0 个
agent/workflow/xianzhi_workflow.py  共 329 行 | re-export 占 59 行 | 仅 1 个类 XianzhiWorkflow(245行)
```

`bazi_engine.py` 是**零逻辑的纯转发文件**，把 9 个子模块（`analysis_calc` / `chart_builder` / `chart_format` / `domain_brief` / `models` / `shensha_calc` / `tables` / `xipan` / `yun_relations`）的 60+ 个符号全部重导出，并靠 `# noqa: F401` 压制 lint。

**问题**：同一个符号存在两条合法导入路径，且 20 处调用方分散在两条路径上：

| 消费方 | 走门面 | 走子模块 |
|---|---|---|
| `api/xianzhi.py` | 4 处 | — |
| `agent/workflow/*`（5 文件） | 5 处 | — |
| `tools/bazi.py` | 2 处 | — |
| `tests/` | 3 处 | 有（`chart_builder` 直连）|

后果：

1. **重构风险翻倍**：把 `build_bazi_chart` 从 `chart_builder` 移到别处，门面静默继续工作，但直连子模块的 3 处会断；反之亦然。
2. **IDE 跳转失效**：Go-to-definition 只能到门面那行 `import`，不能到实现。
3. **`tables.py` 的 `import *`**（`bazi_engine.py:39`）让符号来源完全不可追踪。
4. 新增字段/函数时开发者无法判断该加在哪，门面会持续膨胀。

**解耦方案**：

- **不要一次性删除门面**（20 处调用方 + 3 个测试文件会同时爆）。
- 分两步：① 先把门面降级为**显式 `__all__` + 单一职责标记**，把 `import *` 展开为显式列表；② 每动一个子模块，顺手把该符号的调用方改为直连，门面只保留未迁移的符号，用 `# DEPRECATED: 迁移完成后删除` 标注。当门面只剩转发而无消费者时删除文件。
- 长期口径：`domain/` 下不设门面，消费者一律直连子模块。若确需聚合入口，放在 `domain/__init__.py` 并配 `__all__`，同时**禁止**任何 `app.domain.*` 之外的模块从两个路径同时导入同一符号（可用一条 CI 断言防回归）。

---

### P0-2 · 存储层归属循环：`db` ⟷ `memory`  ✅ 已消除（2026-09-15）

**证据**：

```
app/db/repository.py:22        from app.memory import postgres_memory
app/memory/postgres_memory.py:22   from app.db.pool import close_pool as _close_pg_pool, get_pool as _get_pool
```

`memory/postgres_memory.py:111` 的 `PostgresChatMemory.__init__` 接受连接串，但实际取连接走的是 `db.pool` 的模块级全局池。而 `db/users.py` 的模块 docstring 又声明「复用 `app.memory.postgres_memory` 的模块级连接池」。

**问题**：连接池这一基础设施的**归属权在 db，使用方却在 memory**，同时 db 的异步门面又依赖 memory 的模块级函数。形成包级双向依赖。这解释了为什么 `db` 既被 `core`/`domain`/`rag` 当作低层依赖（10 处），又在内部反向依赖 memory。

更实际的隐患：`main.py` 关停时需**分别**关闭 `memory.postgres_memory.close_global_conn()` 和 `rag.fingerprint.close_pool()` 两套池（见 `main.py` lifespan 尾部），说明池的生命周期管理是割裂的。

**解耦方案**：

- 把连接池提升为独立基础设施：`app/infra/postgres/pool.py`（或保留 `db/pool.py` 但**明确其为唯一池持有者**）。
- `memory/` 与 `rag/fingerprint.py` 一律**只接受注入的池/连接**，不再各自建立或关闭全局池。
- 在 `main.py` 的 lifespan 中统一 `init_pool()` / `close_pool()` 一次，而不是两处分别关。
- `db/repository.py` 只应依赖 `db.*` 与 `memory` 的**协议**（抽象接口），而非反向被 memory 依赖。若 `repository` 的职责是「把同步 DB 函数包成 async」，它不该同时包装 `memory` 的函数——那是 memory 自己的门面职责。

---

### P0-3 · `core` 反向依赖 `db`  ✅ 已消除（2026-09-15）

**证据**：

```
app/core/llm_failover.py:90     from app.db.app_config import get_config
app/core/observability.py:47    from app.db.app_config import get_config
```

两处都是函数内延迟导入（规避导入期循环），是典型的「为了能用而绕开分层」的妥协痕迹。

**问题**：`core` 是全仓最底层，被 9 个包共 28 处依赖。它依赖 `db` 意味着任何 `db` 层的导入期错误、或未来把 `db` 换成 MySQL/Redis，都会向上波及整个 `core`。

**解耦方案**：

- 在 `core` 定义一个最小的配置读取协议：

```python
# core/config/kv.py
class KVStore(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...

_store: KVStore | None = None

def bind_kv(store: KVStore) -> None: ...
def get_kv(key, default=None): ...   # 未绑定则返回 default
```

- `main.py` 启动时用 `db.app_config` 的实现 `bind_kv(...)` 注入。`core` 只认协议，不认 `db`。
- 若嫌重，最小改动是把 `app_config` 从 `db/` 移到 `core/config/`——它只有 29 行，语义上本就是「运行时 KV 配置」而非「业务数据访问」。

---

### P0-4 · 上下文容器放在 `api` 层导致全员倒置依赖  ✅ 已消除（2026-09-15）

**证据**（`sub_app` → `api` 共 11 处）：

```
sub_app/hehun/hehun_app.py:14    from app.api.context import get_app_context
sub_app/hehun/routes.py:11       from app.api.context import get_app_context
sub_app/liuyao/liuyao_app.py:11  from app.api.context import get_app_context
sub_app/ziwei/routes.py:12       from app.api.context import get_app_context
sub_app/ziwei/ziwei_app.py:8     from app.api.context import get_app_context
                               （+ routes 层 4 处 from app.api.common import client_error）
                               （+ tarot/routes.py:7 import client_error, is_message_too_long, ...）
```

**问题**：`AppContext` 是**应用级依赖容器**（持有 chat_model / memory / tools），却被放在 `api/` 包内。后果：

1. 所有需要拿上下文的模块（含 `sub_app/*_app.py` 这类非 API 模块）都必须 import `app.api.*`，`api` 从"最上层"变成"被最广泛依赖的枢纽"。
2. `client_error` 这类纯 HTTP 响应构造工具也放在 `api/common.py`，被 4 个 sub_app routes 反向依赖。
3. `sub_app` 因此无法独立于 `api` 演进。

**解耦方案**：

- `AppContext` / `SessionLock` / `get_app_context()` 迁至 `app/core/context.py`（或 `app/runtime/context.py`）。它本就是运行时容器，与 HTTP 无关。
- `api/context.py` 只保留 FastAPI 依赖注入适配（`app_context_dependency`）。
- `client_error` 若无 FastAPI 依赖则迁至 `core/http.py`；若含 `HTTPException` 则保留在 api，但改由 sub_app 的 routes 层引用**接口自身的依赖**而非其他模块的私有工具——更彻底的做法是让 sub_app 抛出领域异常，由统一的异常处理器转 HTTP 响应。
- `api/state.py`（51 行兼容层）同步删除，见 P2-1。

---

### P1-1 · `tools/` 目录语义混淆：两类别混装

**证据**：13 个文件中，只有 6 个真正是「Agent 工具」（含 `@tool` 装饰器）：

| 文件 | 是 Agent 工具？ | 实际职责 |
|---|:---:|---|
| `bazi.py` (551) | ✅ 11 个 `@tool` | 八字工具 |
| `huangli.py` (104) | ✅ 2 个 | 黄历工具 |
| `ziwei.py` | ✅ | 紫微工具 |
| `rag_search.py` (125) | ✅ 2 个 | 检索工具 |
| `web_search.py` (?) | ✅ 2 个 | 联网搜索 |
| `terminate.py` (?) | ✅ 1 个 | 终止工具 |
| **`pdf_report.py` (344)** | ❌ | PDF 渲染（reportlab） |
| **`report_generator.py` (117)** | ❌ | 分节报告生成 |
| **`report_tasks.py` (142)** | ❌ | 任务执行器 |
| **`cache.py`** | ❌ | LRU 排盘缓存 |
| **`mcp_client.py` (192)** | ❌ | MCP 客户端管理 |
| **`text_clean.py`** | ❌ | LLM 输出后处理 |
| `mcp_client.py` | ❌ | 服务生命周期管理 |

**问题**：`tools/` 同时容纳了「LLM 可见的工具」与「纯后端能力 / 基础设施」，边界不清。`tools/cache.py` 是缓存基础设施（应在 core），`tools/mcp_client.py` 是外部服务客户端（应在 infra）。

**解耦方案**：

- `tools/` 只保留**含 `@tool` 装饰器的 LLM 可见工具**。
- 报告链路三件套（`pdf_report` + `report_generator` + `report_tasks`）归并为 `capabilities/report/`。
- `cache.py`（排盘缓存是领域计算缓存）→ `domain/bazi/cache.py`；若视为通用缓存 → `core/cache/`。
- `mcp_client.py` → `infra/mcp/client.py`。
- `text_clean.py` 被 5 处引用且是 LLM 输出后处理 → `core/llm/postprocess.py`。

---

### P1-2 · `sub_app` 三胞胎复制粘贴

**证据**（归一化 AST 哈希命中的逐字节同构函数）：

```
_normalize_chunk_text()  28 行 × 3 份（字节级完全相同）
  sub_app/hehun/hehun_app.py:91
  sub_app/liuyao/liuyao_app.py:108
  sub_app/ziwei/ziwei_app.py:91

_normalize_ws_payload_text()  28 行 × 3 份（字节级完全相同）
  sub_app/hehun/routes.py:18
  sub_app/liuyao/routes.py:19
  sub_app/ziwei/routes.py:20
```

**问题**：两个共 56 行的函数被复制 6 份。这两个函数处理的是「LLM 流式 chunk 的多格式归一」与「WebSocket 入参归一」，属于**基础设施关注点**，与塔罗/六爻/紫微的业务无关。任何一处修 bug（例如新增一种 chunk 格式）都不会同步到另外两处——这是已实测出的重复，不是理论风险。

**解耦方案**：

- `_normalize_chunk_text` → `core/llm/stream_normalize.py`，三个 `*_app.py` 改为导入。
- `_normalize_ws_payload_text` → `api/ws_utils.py`（或 `core/http/ws.py`），三个 routes 改为导入。
- 进一步：`sub_app` 五子应用的目录形状高度同构（`*_app.py` + `routes.py`），可抽一个 `SubAppBase` 或统一为 `apps/<name>/{service.py, routes.py}` 契约，把「SSE/WS 流式转发 + 文本归一 + 错误上报」的共同骨架收进基类。

---

### P1-3 · 三个 LLM 代理类重复实现同一套 Runnable 转发面

**证据**（同名方法散落 3 个文件）：

```
bind() / bind_tools() / with_config() / invoke() / ainvoke() / stream() / astream() / __getattr__()
  core/llm_failover.py     FailoverModel      (218 行)
  core/llm_throttle.py     ThrottledModel     (206 行)
  core/thinking_router.py  ThinkingRouter     (113 行)
```

三者都是「装饰器式模型包装」，都必须完整转发 LangChain `Runnable` 接口。每个类各写一份 8 个方法的样板，约 90 行重复。

**问题**：LangChain 升级若新增需转发的方法（如其历史上的 `batch` / `abatch`），三处都要改，且 `ThinkingRouter` 已经漏了 `with_config`，`FailoverModel.with_config` 还丢弃了传入的 `config` 参数（`llm_failover.py`: `def with_config(self, config=None, **kwargs)` → 只传 `self._primary`，`config` 未透传）。

**解耦方案**：

- 抽 `core/llm/_delegating.py`：

```python
class DelegatingRunnable:
    """Runnable 接口默认转发：子类只需覆写需要拦截的方法。"""
    _target: Any   # 由子类提供「当前应转发到的内层模型」

    def bind(self, **kw):        return type(self)(self._target.bind(**kw))
    def bind_tools(self, t, **kw): return type(self)(self._target.bind_tools(t, **kw))
    def with_config(self, config=None, **kw): return type(self)(self._target.with_config(config, **kw))
    def invoke(self, *a, **kw):  return self._target.invoke(*a, **kw)
    async def ainvoke(self, *a, **kw): return await self._target.ainvoke(*a, **kw)
    def stream(self, *a, **kw):  yield from self._target.stream(*a, **kw)
    async def astream(self, *a, **kw):
        async for c in self._target.astream(*a, **kw): yield c
    def __getattr__(self, n):    return getattr(self._target, n)
```

- 三个类继承之，只覆写各自真正差异化的逻辑（failover 的降级链遍历、throttle 的信号量/熔断、router 的 ON/OFF 切换）。
- 顺带修掉 `with_config` 丢参数的问题。

---

### P1-4 · 干支关系两套实现，口径已漂移 → ✅ 已统一（2026-09-15，口径按知识库落地）

> ⚠️ **这是口径变更，非纯重构**：原结论「`analysis_calc` 不识别半合/拱合」在两个视图间矛盾。现按项目知识库
> `12_合冲刑害规则卡.md` 与 `古籍05_三命通会精选条文.md` 统一为**「支持半合/拱合 + 两支半刑」**。
> 因此会改变部分既有命盘的原局分析结论。若尚未经需求方拍板，需确认后再合入主线。

**证据**：

| | 全盘聚合视图 | 岁运视图 |
|---|---|---|
| 文件 | `domain/analysis_calc.py` | `domain/xipan.py` |
| 天干 | `_stem_relations` (L354) 五合+四冲 | `_gan_rel` (L573) 五合+四冲 |
| 地支两两 | `_branch_relations` (L311) 六合/六冲/六害 | `_zhi_pair_rel` (L617) 六合/六冲/六害/**六破** |
| 三合 | `_branch_combinations` (L336) **仅三支全** | `_zhi_group_rel` (L598) 三支全 + **半合 + 拱合** |
| 三刑 | `_branch_relations` 内联 | `_zhi_xing` (L625) |
| 第三份 | `domain/yun_relations.py` `_tian_ke_di_chong` (L80) / `relations_for` | |

**问题**：同一份命理规则在两个文件里各写一遍。已出现**可观测的口径差异**：

1. `analysis_calc` 只识别三支齐全的三合局；`xipan` 额外识别**半合**（申子半合水）与**拱合**（申辰拱子）。同一个盘在原局分析里说「无三合」，在细盘关系里说「申辰拱合子」。
2. `_branch_relations` 报六害，`_zhi_pair_rel` 报六破（`LIU_PO`），两者覆盖的表集合不同。

命理产品的核心资产就是口径一致性——同一用户在原局分析与细盘看到矛盾结论，是产品级事故。

**表定义也重复**：`domain/tables.py:161` 定义 `SAN_HE = {frozenset(("申","子","辰")): "申子辰合水局", ...}`，而 `domain/xipan.py:584` 又定义了带五行的 `_SAN_HE_GROUPS = (("申","子","辰","水"), ...)`。同一批数据两处维护——`tables.py` 的 docstring 已声明自己是「单一事实源」，`xipan.py` 违反了它。

**解耦方案 → 已落地（2026-09-15）**：新增单一事实源 `domain/ganzhi_relations.py`，被 `analysis_calc`
与 `xipan` 共同引用（`analysis_calc.py:418/427`、`xipan.py:571`），并提供「一个算法、两个视图」：
底层原子查询 + 上层视图映射（分析分入 6 字段、细盘汇总一栏文字）。实测 36 例黄金命盘里
**34 个原两套结论不一致**，统一后消除。配套 `tests/test_ganzhi_relations.py`。

- **表定义收敛**：`SAN_HE` 与 `_SAN_HE_GROUPS` 合并为带五行的单一定义，两处引用同一常量。
- **当前实现口径**：统一为「支持半合/拱合」（细盘口径上翻到原局分析）；是否确认为最终产品口径需需求方拍板。
- **回归防线**：`test_ganzhi_relations` +（`test_xipan.py` / `test_yun_relations.py` 基础上）。
- **仍待确认**：若需求方后续要求原局分析回退为"仅三支全"，需在 `ganzhi_relations` 单独开视图开关。

---

### P1-5 · 纯数据与代码混放

**证据**：

| 文件 | 行数 | 内容构成 |
|---|---:|---|
| `domain/tables.py` | 840 | 约 568 行纯字面量（59+ 个 `GAN_WUXING` / `LIU_HE` / `TIAN_YI` / `HUA_GAI` … 字典与元组） |
| `domain/city_longitude.py` | 390 | 城市经度查找表（纯数据） |
| `domain/ziwei/tables.py` | 150 | 紫微星曜表（纯数据） |

**问题**：`tables.py` 840 行让 `domain/` 目录的可读性变差——读者无法一眼看出「哪些文件是算法，哪些是数据」。它同时被 7 处依赖，且 `bazi_engine.py:39` 用 `import *` 全量导出，符号来源完全不可追踪。

**解耦方案**：

- `domain/bazi/data/` 子包：按主题拆分 `tables.py`（五行/纳音/长生）、`shensha_tables.py`（神煞）、`relations_tables.py`（合冲刑害）。
- 纯数据文件加 `_tables.py` 后缀或置于 `data/` 目录，形成视觉边界。
- 禁止 `import *`；`data/` 下每个模块顶部配 `__all__`。
- `city_longitude.py` → `domain/data/city_longitude.py` 或独立 `data/` 目录。

---

### P1-6 · 巨型函数

**≥60 行的函数 27 个，Top 10**：

| 行数 | 位置 | 函数 |
|---:|---|---|
| ~~**513**~~ | `domain/shensha_calc.py:71` | `_compute_shensha()` → **已拆包**，编排在 `shensha_calc/_core.py:24` |
| ~~**451**~~ | ~~`agent/workflow/workflow_messages.py:560`~~ | `check_facts()` → **已拆** `agent/workflow/fact_check.py`（7 维度）+ `XianzhiWorkflow.check_facts` 委托 |
| **252** | `agent/xianzhi_langgraph.py:63` | `create_xianzhi_graph()` |
| **178** | `db/schema.py:29` | `_do_ensure_tables()` |
| 149 | `tools/pdf_report.py:195` | `generate_bazi_report()` |
| 148 | `domain/chart_builder.py:296` | `build_bazi_chart()` |
| 140 | `agent/workflow/workflow_messages.py:241` | `fact_block()` |
| 130 | `agent/xianzhi_langgraph.py:165` | `repair_node()` |
| 115 | `tools/bazi.py:359` | `bazi_hehun()` |
| 109 | `api/xianzhi.py:204` → `xianzhi_chat.py:117` | `ws_chat_with_xianzhi()` |

**重点分析**：

- **`_compute_shensha` 513 行** → **✅ 已拆包**（2026-09-15）：按神煞族拆为 `_context/_day_stem/_month_branch/_year_branch/_combinations`，主函数 `_compute_shensha` 降为 70 行调度。历史教训（改 description 时缩进错位 → `continue` 后命中判断变死代码）已被黄金快照 + 变异测试钉死。
- **`check_facts` 451 行** → **✅ 已拆**（2026-09-15）：迁至 `agent/workflow/fact_check.py`，7 个维度校验各成函数（`_check_liunian_ganzhi` / `_check_dayun_ganzhi` / `_check_pillar_ganzhi` / `_check_shishen_pairs` / `_check_shishen_single` / `_check_shensha_existence` / `_check_shensha_pillar`），`check_facts` 仅做编排；维度可独立单测，并配了黄金样本防线。
- **`_do_ensure_tables` 178 行**：把全库 DDL 塞进一个函数。**建议**：按表族拆为 `_ensure_user_tables` / `_ensure_chart_tables` / `_ensure_task_tables`，各自独立可重入。

---

### P1-7 · 单文件多职责

#### `api/xianzhi.py`（701 行，`api/` 最大文件）→ **✅ 已拆**（2026-09-15）

拆为平铺的 `api/xianzhi_chat.py`（SSE+WS）/ `xianzhi_chart.py`（查询+计算）/ `xianzhi_report.py`（任务队列）/ `_xianzhi_common.py`（共享辅助）。`xianzhi.py` 降为 115 行的 router 聚合，兼容既有导入路径。

#### `db/user_records.py`（608 行）→ **✅ 已拆**（2026-09-15）

拆为 `db/user_records/{ai_interpretation,answer_feedback,favorites,feedback}.py`，`__init__.py` 显式 re-export 兼容既有导入路径 `from app.db.user_records import ...`。

#### `memory/postgres_memory.py`（619 行）

`PostgresChatMemory` 类只占 L102–L261，其余 ~360 行是模块级函数（`get_session_info` / `get_messages` / `get_birth_info_from_session` / `upsert_session_birth_info` …）。**同一个存储实体同时以「类」和「模块级函数」两套接口并存**。

**建议**：统一为一个 repository 类，模块级函数作为薄适配层或直接删除（`db/repository.py` 已提供异步门面）。

---

### P2 · 死代码与冗余清单

#### P2-1 完全死文件

| 文件 | 证据 | 处置 |
|---|---|---|
| `app/api/tarot_records.py` | **0 字节**，全仓零引用；`tests/test_exception_tightening.py:95` 甚至有断言「该路由未注册」 | **直接删除**（同时该测试的断言可保留为「文件不存在」的守卫，或一并清理） |

#### P2-2 零引用的函数

| 符号 | 位置 | 行数 | 证据 |
|---|---|---:|---|
| `evaluate_answer_cases()` | `evaluation/xianzhi_eval.py:52` | 3 | 全仓仅定义处出现；`tests/test_xianzhi_eval.py` 只导入单数 `evaluate_answer_case` |
| `set_instances()` | `api/state.py:11` | 15 | 仅被 `api/context.py:103` 的注释提及，无调用者 |
| `get_xianzhi()` / `agent_pool_stats()` / `workflow_backend()` | `api/state.py` | ~15 | 零引用（真实调用走 `AppContext` 上的同名方法，非本兼容层） |
| `get_chat_model()` | `api/state.py:28` | 6 | **仅** `tests/test_api_integration.py:153` 使用 |

> 勘误：初版报告曾把 `domain/ziwei/tables.py:93 branch_yinyang()` 列为零引用，属误报——它在 `domain/ziwei/engine.py:300` 以 `T.branch_yinyang(year_branch)` 形式被调用。原因是初版扫描的正则用 `(?<![\w.])` 排除了点号，导致所有 `模块别名.函数()` 形式的属性调用不被计入。**不应删除**。

#### P2-3 兼容层（重构收尾遗留）

**`app/api/state.py`（51 行）**：docstring 明写「本模块仅保留旧函数签名做兼容转发，新代码请直接使用 `app.api.context`」。但 `api/context.py` 注释又说这是「R5 解耦全局 state」的产物——即 R5 已完成，兼容层却没删。

处置：迁移 `tests/test_api_integration.py:153` 到 `get_app_context().chat_model`，然后**删除整个 `api/state.py`**。

#### P2-4 未使用 import

| 位置 | 符号 |
|---|---|
| `core/llm_throttle.py:19` | `log` |
| `rag/knowledge.py:14` | `settings` |

另有 `domain/bazi_engine.py` 的 `build_domain_brief` / `_compute_shensha` / `_zhi_to_month_index` / `build_xipan` / `ten_god` / `zizuo`（6 个符号在本文件内零使用，靠 `# noqa: F401` 保留）——这些是**门面的转发项**，随 P0-1 清理一并消失，不应单独删。

#### P2-5 目录错位（非死代码但属冗余层次）

| 链路 | 问题 |
|---|---|
| `tools/huangli.py` → `sub_app/huangli/huangli_app.py` → `domain/huangli_calc.py` | `huangli_app.py`（27 行）**全是 no-op 转发**：`huangli_day()` 只是 `build_huangli_day(date or today)`。中间层无任何业务价值，且造成 `tools` → `sub_app` 的层级倒置。**建议**：`tools/huangli.py` 直连 `domain.huangli_calc`，`sub_app/huangli/huangli_app.py` 删除（其 `routes.py` 同步直连 domain）。 |
| `db/chart_store.py` (425) vs `rag/case_store.py` (109) | 两者管理同一批「结构化命例」数据：`db/chart_store.py:268/297/308` 是 `add_chart_case` / `delete_chart_case` / `search_chart_cases` 的 **CRUD**；`rag/case_store.py:46` 又 `from app.db.chart_store import search_cases_for_rag, search_chart_cases` 读取同一批数据并封装 `CaseLibrary`。职责本身合理（一个存、一个用），但 `CaseLibrary` 的读写路径应显式声明为「依赖 db 层的只读视图」，建议 `rag/case_store.py` 重命名为 `rag/case_retriever.py` 并在 docstring 声明依赖方向，避免后续被误当第二个存储。 |

#### P2-6 文件内重复逻辑

`tools/report_tasks.py` 的 `build_basic_report_pdf` 与 `build_full_report_pdf` 中各有一份**完全相同的 4 次排盘工具调用块**：

```python
chart_text   = bazi_chart.invoke({...})
analysis_text= bazi_analysis.invoke({..., "question": "整体命盘"})
dayun_text   = bazi_dayun.invoke({..., "count": 12})
liunian_text = bazi_liunian.invoke({..., "years": 10})
```

**建议**：抽 `_collect_chart_texts(birth_time, gender) -> dict`，两处共用。

---

## 四、目标目录架构

### 4.1 目标分层（自下而上，箭头表示允许的依赖方向）

```
      ┌─────────────── app/api/ ───────────────┐   HTTP/WS 接口 + DI 适配
      │                                         │
      ├─────── app/apps/（原 sub_app）──────────┤   子应用（塔罗/六爻/…）
      │                                         │
      └──── app/agent/ ──── app/capabilities/ ──┘   编排 / 领域能力
                    │
              app/tools/          ← 仅含 @tool 的 LLM 可见工具
                    │
        app/rag/    app/memory/
                    │
    ┌─────── app/domain/（纯计算，零 IO）────────┐
    │                                           │
    └──── app/infra/（原 db + 池 + MCP）────────┘
                    │
              app/core/          ← 零业务依赖：config/logging/llm/cache/security/context
```

**铁律**：依赖只能向上。任何 `core` 依赖 `db`、`domain` 依赖 `agent`、`tools` 依赖 `sub_app` 的边都必须消除。

### 4.2 目标目录树

```
backend/app/
├── core/                        # 基础设施，零业务依赖
│   ├── config/
│   │   ├── settings.py
│   │   └── kv.py                # 原 db/app_config.py（29行）+ KVStore 协议  ← 修 P0-3
│   ├── logging.py
│   ├── context.py               # 原 api/context.py（AppContext/SessionLock）  ← 修 P0-4
│   ├── llm/
│   │   ├── _delegating.py       # DelegatingRunnable 基类                     ← 修 P1-3
│   │   ├── failover.py
│   │   ├── throttle.py
│   │   ├── thinking.py
│   │   ├── postprocess.py       # 原 tools/text_clean.py
│   │   └── stream_normalize.py  # 原 3 份 _normalize_chunk_text 合一          ← 修 P1-2
│   ├── cache/redis.py
│   ├── http/
│   │   ├── errors.py            # 原 api/common.py 的 client_error
│   │   └── ws.py                # 原 3 份 _normalize_ws_payload_text 合一     ← 修 P1-2
│   ├── security.py
│   └── observability.py
│
├── infra/                       # 外部依赖实现（唯一持有连接池）             ← 修 P0-2
│   ├── postgres/
│   │   ├── pool.py              # 原 db/pool.py，唯一池持有者
│   │   ├── schema.py            # _do_ensure_tables 拆分
│   │   ├── users.py
│   │   ├── profiles.py
│   │   ├── chart_store.py
│   │   ├── records/             # 原 db/user_records.py 608行按实体拆分
│   │   │   ├── favorites.py
│   │   │   ├── ai_interpretations.py
│   │   │   ├── feedback.py
│   │   │   └── answer_feedback.py
│   │   └── tasks.py             # 原 db/report_tasks.py
│   └── mcp/client.py            # 原 tools/mcp_client.py
│
├── domain/                      # 纯计算，零 IO，零跨层
│   ├── bazi/
│   │   ├── models.py
│   │   ├── builder.py           # 原 chart_builder.py
│   │   ├── analysis.py          # 原 analysis_calc.py
│   │   ├── shensha/             # _compute_shensha 513行按神煞族拆分
│   │   ├── xipan.py
│   │   ├── format.py
│   │   ├── brief.py
│   │   ├── time_parse.py
│   │   ├── cache.py             # 原 tools/cache.py（领域计算缓存）
│   │   └── data/                # 原 tables.py 840行按主题拆分           ← 修 P1-5
│   │       ├── wuxing.py
│   │       ├── shensha_tables.py
│   │       └── relations_tables.py
│   ├── relations/               # 干支关系单一事实源                     ← 修 P1-4
│   │   ├── atoms.py             # gan_relation / zhi_relation / zhi_group_relations
│   │   ├── aggregate.py         # 原局聚合视图
│   │   └── transit.py           # 岁运视图（原 yun_relations.py + xipan 关系部分）
│   ├── ziwei/{engine,models,tables}.py
│   ├── huangli/calc.py
│   └── data/city_longitude.py
│
├── rag/
│   ├── vector_store.py
│   ├── embeddings.py
│   ├── retrieval.py             # 含 DOMAIN_KEYWORDS / DOMAIN_RULE_QUERIES
│   ├── case_retriever.py        # 原 case_store.py（声明为 db 的只读视图）
│   ├── fingerprint.py
│   ├── relevance.py
│   └── knowledge_docs/*.md
│
├── memory/                      # 只消费注入的池，不自建             ← 修 P0-2
│   ├── store.py                 # 原 postgres_memory.py：统一为 repository 类
│   ├── file_store.py            # 原 chat_memory.py
│   └── summarizer.py
│
├── capabilities/report/         # 原 tools 中的报告三件套
│   ├── render_pdf.py            # 原 pdf_report.py
│   ├── generator.py             # 原 report_generator.py
│   └── executor.py              # 原 report_tasks.py
│
├── tools/                       # 仅 @tool 装饰的 LLM 可见工具
│   ├── bazi.py  huangli.py  ziwei.py  rag_search.py  web_search.py  terminate.py
│
├── agent/
│   ├── xianzhi.py
│   ├── birth_parse.py
│   ├── prompts.py               # 单一事实源（保持现状）
│   ├── core/{base,react,tool_call}_agent.py
│   └── workflow/
│       ├── graph.py             # 原 xianzhi_langgraph.py
│       ├── supervisor.py        # 原 xianzhi_workflow.py（去掉门面，只留 XianzhiWorkflow）
│       ├── messages.py          # check_facts 451行按维度拆分
│       ├── models.py  support.py  workers.py  retrieval.py
│
├── evaluation/
├── tasks/worker.py
├── api/
│   ├── deps.py  routes.py
│   ├── xianzhi/{chat,chart,sessions,report}.py     # 原 701行单文件拆分
│   └── admin/  cases.py  feedback.py  auth.py ...
└── apps/                        # 原 sub_app，去 api 依赖         ← 修 P0-4
    ├── _base.py                 # 共同骨架（含去重后的归一化函数引用）
    ├── tarot/ liuyao/ hehun/ ziwei/ huangli/
```

### 4.3 关键迁移映射表

| 现状 | 目标 | 解决的问题 |
|---|---|---|
| `domain/bazi_engine.py` | **删除**（消费者改直连子模块） | P0-1 |
| `agent/workflow/xianzhi_workflow.py` 的门面部分 | **删除**，只留 `supervisor.py` | P0-1 |
| `db/pool.py` | `infra/postgres/pool.py`（唯一池持有者） | P0-2 |
| `db/app_config.py` | `core/config/kv.py` | P0-3 |
| `api/context.py` | `core/context.py` + `api/deps.py` 适配 | P0-4 |
| `api/common.py` | `core/http/errors.py` | P0-4 |
| `api/state.py` | **删除** | P2-3 |
| `api/tarot_records.py` | **删除**（0 字节） | P2-1 |
| `tools/{cache,mcp_client,text_clean}.py` | `domain/bazi/cache.py` / `infra/mcp/` / `core/llm/postprocess.py` | P1-1 |
| `tools/{pdf_report,report_generator,report_tasks}.py` | `capabilities/report/` | P1-1 |
| 3× `_normalize_chunk_text` | `core/llm/stream_normalize.py` | P1-2 |
| 3× `_normalize_ws_payload_text` | `core/http/ws.py` | P1-2 |
| 3× LLM 代理样板 | `core/llm/_delegating.py` | P1-3 |
| `analysis_calc` + `xipan` + `yun_relations` 的关系逻辑 | `domain/relations/` | P1-4 |
| `domain/tables.py` 840行 | `domain/bazi/data/` | P1-5 |
| `sub_app/huangli/huangli_app.py` | **删除**（no-op 转发层） | P2-5 |

---

## 五、分阶段重构路线

原则：**每一阶段结束后系统可运行、测试可全绿**。禁止一次性大爆炸迁移。

### 阶段 0 · 清理与防线（低风险，先做）  ✅ 已完成

1. 删除 `api/tarot_records.py`（0 字节）、`api/state.py`（迁移测试后删除）。
2. 删除 `evaluate_answer_cases`、`ziwei/tables.branch_yinyang`、两处未使用 import。
3. 抽出 `tools/report_tasks.py` 的重复排盘调用块。
4. **建立架构防回归断言**（新增 `tests/test_architecture.py`）：
   - `app.core` 不得 import `app.db` / `app.domain` / `app.agent` / `app.api`
   - `app.domain` 不得 import 除 `app.domain` 外的任何 app 包
   - `app.tools` 不得 import `app.sub_app` / `app.apps`
   - `app.apps`（sub_app）不得 import `app.api`
   - 禁止 `import *`
   - 同一符号不得同时从门面与子模块导入
   这条测试是后续所有阶段的安全网——先有断言，再动刀。

### 阶段 1 · 去重（纯搬运，零行为变更）  ✅ 已完成

5. 三份 `_normalize_chunk_text` → `core/llm/stream_normalize.py`。
6. 三份 `_normalize_ws_payload_text` → `core/http/ws.py`。
7. `core/llm/_delegating.py` 抽出代理基类，三个 LLM 包装类继承之；顺带修 `FailoverModel.with_config` 丢参。
8. 补测：为归一化函数写参数化单测（覆盖 list / dict / 超长 / `<__` 对象串四类输入），确保搬运无行为漂移。

### 阶段 2 · 打破层级倒置（中风险，逐个消除倒置边）  ✅ 已完成

9. `db/app_config.py` → `core/config/kv.py`，消除 `core → db`（P0-3）。
   验证：`tests/test_llm_failover.py`、`tests/test_llm_chain_admin.py` 全绿。
10. `api/context.py` → `core/context.py`，`api/common.py` 的错误构造 → `core/http/errors.py`；改全部 sub_app 的 11 处 import（P0-4）。
    验证：`tests/test_api_integration.py`、`tests/test_session_birth_info_api.py` 全绿。
11. `tools/huangli.py` 直连 `domain.huangli_calc`，删除 `sub_app/huangli/huangli_app.py`。
    验证：`tests/test_huangli.py` 全绿。
12. 连接池统一为 `infra/postgres/pool.py`，`memory` 与 `rag.fingerprint` 改为消费注入池（P0-2）。
    验证：本机打 8123 起服务，确认 `/api/health` 的 `agent_pool` 与记忆读写正常。

### 阶段 3 · 拆巨型函数与巨型文件（高风险，需逐项回归）

13. ✅ `_compute_shensha` 513 行按神煞族拆分 → 已拆包 `shensha_calc/`，编排函数降为 70 行。
    逐族重构后跑 24 例黄金快照 + 变异测试，输出全等。
14. ✅ `check_facts` 451 行按校验维度拆分 → 迁至 `fact_check.py`，7 维度各成函数，「表述宽容度」可独立单测。
15. ✅ `api/xianzhi.py` 701 行拆为平铺 `xianzhi_chat` / `xianzhi_chart` / `xianzhi_report` + `_xianzhi_common`。
16. ✅ `db/user_records.py` 608 行按实体拆为包内 `favorites` / `ai_interpretation` / `feedback` / `answer_feedback`。

### 阶段 4 · 统一口径与领域重组（门面部分已完成，口径待确认）

17. ✅ P1-4 干支关系统一已实施（`domain/ganzhi_relations.py`），`analysis_calc` / `xipan` 共用同一套算法。
    ⚠️ **前置本应为产品决策**：当前按「纳入半合/拱合（含两支半刑）」口径实施，会改变部分原局结论，需需求方确认拍板。
18. ✅ `domain/bazi_engine.py` 与 `xianzhi_workflow.py` 门面拆除完成，20 处调用方 + 3 个测试文件已改直连。
19. ⬜ `sub_app` → `apps/`，引入 `_base.py` 收敛共同骨架。

---

## 六、清理清单（可勾选）

> 勾选状态截至 2026-09-15；未勾选项属阶段 3 / 4。

### 立即删除（零风险）

- [x] `app/api/tarot_records.py` — 0 字节空文件，全仓零引用
- [x] `app/api/state.py` — 兼容层（`tests/test_api_integration.py` 已改走 `api.context`/`api.deps`）
- [x] `app/evaluation/xianzhi_eval.py` `evaluate_answer_cases()` — 零引用
- [x] `app/core/llm_throttle.py` 未使用的 `log` import
- [x] `app/rag/knowledge.py` 未使用的 `settings` import
- [x] `app/sub_app/huangli/huangli_app.py` — no-op 转发层（`tools/huangli.py` 直连 `domain.huangli_calc`）
- [x] `app/db/app_config.py` — 迁为 `core/config/kv.py`(协议) + `db/kv_store.py`(PG 实现)
- [x] `app/api/context.py` / `app/api/common.py` — 按层归位后删空
- [x] `app/memory/postgres_memory.py::close_global_conn()` — 池统一后零调用

> 修正：`domain/ziwei/tables.py::branch_yinyang()` **不在删除清单** —— 它由 `engine.py:300` 以
> `T.branch_yinyang(year_branch)` 调用，初版零引用扫描漏判了属性调用形式。

### 合并去重

- [x] `_normalize_chunk_text` × 3 + `_normalize_ws_payload_text` × 3 → **`core/text_extract.py`**
      （初版计划拆成 `core/llm/stream_normalize.py` + `core/http/ws.py` 两个模块；实际合并为一个，
      因为两者同属"文本归一"、参数族一致，拆开反而多一层跳转。tarot 的 4 参变体刻意不同，未合并）
- [x] LLM 代理 Runnable 样板 × 3（`llm_failover` / `llm_throttle` / `thinking_router`）→ **`core/llm_delegate.py::DelegatingRunnable`**
- [x] `tools/report_tasks.py` 两个 `build_*_pdf` 中的 4 次排盘调用块 → `_collect_chart_texts()`
- [x] 干支关系算法 × 2 套（`analysis_calc` / `xipan`）+ `yun_relations` → **`domain/ganzhi_relations.py`**
      （2026-09-15 已落地，两视图共用同一套算法；口径含半合/拱合，需需求方确认拍板）
- [x] 三合表 × 2（`tables.SAN_HE` / `xipan._SAN_HE_GROUPS`）→ 收敛为 `ganzhi_relations` 内单一定义

### 巨型函数拆分

- [x] `domain/shensha_calc.py:71` `_compute_shensha`（513 行）→ **拆为包 + 6 族**
      （`_core` 70 行编排 / `_context` / `_day_stem` / `_month_branch` / `_year_branch` / `_combinations`），
      `__init__.py` 重导出使 8 处调用方零改动。**每一步拆分后 24 例黄金快照均零差异**。
- [x] `agent/workflow/workflow_messages.py:560` `check_facts`（451 行）→ **拆至 `agent/workflow/fact_check.py`**
      `__init__.py` 重导出使调用方零改动；配 22 条审核黄金样本 + 7 维度 + 变异验证。
      `XianzhiWorkflow.check_facts`（`xianzhi_workflow.py:327`）委托转发。
- [ ] `agent/xianzhi_langgraph.py:63` `create_xianzhi_graph`（252 行）→ 节点函数外提
- [ ] `db/schema.py:29` `_do_ensure_tables`（178 行）→ 按表族拆 3 个
- [ ] `agent/workflow/workflow_messages.py:238` `fact_block`（140 行）
- [ ] `tools/pdf_report.py:195` `generate_bazi_report`（149 行）

### 巨型文件拆分

- [x] `api/xianzhi.py`（701 行）→ **平铺 `xianzhi_chat` / `xianzhi_chart` / `xianzhi_report` + `_xianzhi_common`**
- [x] `db/user_records.py`（608 行）→ **`db/user_records/{favorites, ai_interpretation, feedback, answer_feedback}`**
- [ ] `memory/postgres_memory.py`（619 行）→ 统一为类接口，消除模块级函数与类并存
- [ ] `domain/tables.py`（840 行，568 行纯数据）→ `domain/bazi/data/`

### 层级倒置消除

- [x] `core/llm_failover.py` + `core/observability.py` `import db.app_config` → **`core/config/kv.py`**
      （core 只认 `KVStore` 协议；PG 实现在 `db/kv_store.py`，由 `app/db/__init__.py` 导入即注册）
- [x] `sub_app` → `api` 的 11 处 import → `AppContext` 归 **`app/agent/context.py`**、
      `client_error` / 长度限额归 **`app/core/http/errors.py`**、FastAPI 依赖归 `api/deps.py`
- [x] `tools/huangli.py` → `sub_app.huangli` → 直连 `domain.huangli_calc`
- [x] `db/repository.py` → `memory` 反向依赖 → 门面归位 **`app/api/data_access.py`**；全仓连接池统一到 `db/pool.py`
- [ ] `db/user_records.py:497` → `rag.retrieval.detect_domain`（db 依赖 rag）→ 领域识别下沉 domain 或经协议注入

> 两处与初版计划的偏差（实际比计划更贴层）：
> ① `AppContext` **不能**放 `core/` —— 它的 `get_xianzhi()` 会构造 `app.agent.xianzhi`，放 core 会把倒置边
> 从 `sub_app→api` 搬成 `core→agent`；而 `SessionLock` 的语义本就是"同一会话的 agent 操作串行化"，
> 归 agent 层名实相符。
> ② 初版称"db 与 memory 各持一套池"**不准确** —— `memory` 早已 `from app.db.pool import get_pool`。
> 真实重复池在 `app/rag/fingerprint.py`（同 DSN 自建第二个 ConnectionPool，min=1/max=2）。

### 门面拆除

- [x] `domain/bazi_engine.py`（71 行全转发）→ 已删除，20 处调用方改直连子模块
- [x] `agent/workflow/xianzhi_workflow.py` 的 59 行 re-export → 已删除，5 处调用方改直连（`orchestrator.py` 承载编排核心）
- [x] `domain/bazi_engine.py:39` `from app.domain.tables import *` → 随门面删除消除

---

## 七、风险与回归防线

### 7.1 已识别的重构风险

| 风险 | 说明 | 缓解措施 |
|---|---|---|
| **神煞计算静默回归** | `_compute_shensha` 513 行拆分时，缩进错位会让 `continue` 后的命中判断变成永不执行的死代码。AST 仍能解析、import 仍成功、测试若覆盖不全则完全不报错。历史上灾煞/吊客/病符三段曾全中招。 | 拆分后用**真实命盘 fixture 直接调用**并做重构前后输出逐字段全等断言，不能只跑 AST 检查。 |
| **口径变更引发产品事故** | P1-4 的半合/拱合统一会改变已有命盘的输出。 | 先做产品决策，再准备一组「已知答案」的黄金命盘快照；变更前后 diff 输出，人工确认每处差异是否符合预期。 |
| **测试硬编码路径** | 27 个测试文件共依赖 35 条 `app.*` 导入路径，其中 `tests/test_knowledge_docs.py` 还硬编码了 knowledge_docs 文件名。 | 每次移动模块须同步改测试；把「模块路径」纳入阶段 0 的架构断言测试，使路径漂移在 CI 立刻暴露。 |
| **门面拆除范围失控** | `bazi_engine` 门面有 20 处调用方，一次性删除会同时爆掉 app 与 tests。 | 严格按「先降级、逐符号迁移、无消费者后删文件」三步走，禁止批量 sed 替换。 |
| **覆盖率门槛** | CI 要求整体覆盖率 60%（当前约 68%）。大量搬运会稀释分母或引入未覆盖新代码。 | 阶段 1 的纯搬运补参数化单测；每次拆分后跑覆盖率，留出 ≥5% 余量。 |
| **路径锚点静默漂移**（实测命中） | `core/config.py` 改成包 `core/config/settings.py` 后，`BACKEND_ROOT = Path(__file__).resolve().parents[2]` 会指到 `app/` 而非 `backend/` —— `.env` 加载不到、`data/` 与 `vector_db/` 写到错误位置，**全程不报错**。 | 已改为向上查找 `pyproject.toml` 定位根目录（不依赖层数），并用 `test_config_kv.py::test_backend_root_points_at_backend_dir` 钉死。**凡移动带路径计算的模块必须复查 `parents[N]`。** |
| **同名模块与包并存** | 单文件改包后若旧 `.py` 残留，导入结果取决于文件系统顺序。 | `test_architecture.py::test_no_shadow_module_beside_converted_package` 对已包化目录做断言。 |
| **关停路径漏关连接池** | 池分散在多处时，`main.py` 关停要逐处调用，新增一处池就多一处漏关点（表现为连接缓慢泄漏，重启才恢复）。 | 已统一为单一池 + `test_architecture.py::test_only_pool_module_holds_connection_pool` 禁止任何模块自建 `ConnectionPool`。 |

### 7.2 建议新增的防线

1. **`tests/test_architecture.py`（阶段 0 必做）✅ 已落地**：把第四节的依赖铁律写成断言，用 AST 扫描 `app/` 全部文件。这是本项目最有价值的一条投资——它让后续所有分层决策自动化执行，而不是靠人记住。
   实现要点：违规**按 (源包, 目标包) 计数入基线**，测试同时断言"不新增"与**基线不得高于实际**（棘轮只许收紧）。
   没有后半条，重构把违规修掉后基线会静默失效、守卫退化成摆设。
   已用变异验证：注入 `domain → core` 依赖会挂；把已修条目留在基线里会报"基线未同步"。
2. **黄金命盘快照 ✅ 已落地（2026-09-15）**：24 个用例覆盖 10 日干 × 专旺五格 × 边界（子时/立春前后/经度校正/女命逆排）× 强弱五档，
   固化 `build_bazi_chart` 全量输出 + 原局神煞 + LLM 事实上下文全文。
   落地位置：`tests/fixtures/bazi_golden/`、`tests/bazi_golden.py`、`tests/test_bazi_golden.py`、`scripts/golden_bazi.py`。
   与工作记忆中「命例库覆盖 10 天干/10 标准格局/专旺格/从格」的目标一致。

   三个落地时才发现的必要前提，值得记下来：
   - **基准时间必须显式注入**。`build_bazi_chart` 的细盘含"当前岁运"快照，取自系统当天；
     原实现没把 `today` 透传给 `build_xipan`，因此快照会随系统日期漂移。已补 `today` 参数
     （生产默认行为不变），并断言"换基准日输出必变"，否则钉死会失效而无人察觉。
   - **原局神煞不在 `BaziChart.to_dict()` 里**。`_compute_shensha(pillars)` 只在
     `chart_to_api_dict`（`chart_builder.py:534`）挂上，而它正是阶段 3 的拆分目标，
     故快照必须显式单独取一份。
   - **超大且低信息量的段只存指纹**。`xipan.liuyue`(151KB) + `xipan.liunian`(22KB)
     + `xipan.ganzhiMeta`(14KB) 占单例 218KB 的 86%，逐字段存会让快照不可读；
     改存 `{_count, _sha256}`，仍能捕获任何变化，并提供 `--show` 导出实际内容。

   守卫有效性已用**变异测试**证明：把 `shensha_calc.py` 里灾煞的描述串改掉 →
   24/24 用例失败，报错精确到 `chart.dayun[5].shensha[4].description: 值已变`。
   （刻意选灾煞段：灾煞/吊客/病符三段历史上曾因缩进错位变成永不命中的死代码。）

   **顺带发现一个产品级观察**：`_detect_conging`（从格）在真实出生样本里几乎打不到 ——
   扫描 1900-2099 × 每天 6 时辰共 **438,000 个样本，从格 0 命中**
   （同期专旺 786 例、判"极弱"但未成从格 4,248 例）。43,800 样本子集上的短路点分布：
   295 例有禄/刃/库根支、176 例日主五行权重 > `_CONG_SELF_WX_MAX`(0.50)、
   93 例藏干印星 ≥0.30、9 例藏干本气根 ≥0.30。
   这属阈值口径问题（同 P1-4），**不是 bug**，故不动阈值；改用合成输入直测
   `_detect_conging` / `_detect_zhuanwang` 的契约
   （`tests/test_bazi_golden_patterns.py`），保证该分支被守住。

3. **门面消费者计数守卫**：CI 中断言 `domain/bazi_engine` 的调用方数量单调递减，防止重构期间有人反向新增依赖。
   —— 这道防线已由 `test_architecture.py::test_no_dual_path_symbol_imports` 覆盖大半：
   它断言"同一符号的第二条导入路径"只减不增，比单看调用方数量更精确。

---

## 八、优先级总览

| 优先级 | 项 | 影响 | 工作量 | 状态 |
|---|---|---|---|---|
| **P0** | P0-2 db⟷memory 循环 | 部署与生命周期管理 | 中 | ✅ 已消除 |
| **P0** | P0-3 core→db 倒置 | 底层稳定性 | 小 | ✅ 已消除 |
| **P0** | P0-4 api 层被全员依赖 | 架构清晰度 | 中（11 处 import） | ✅ 已消除 |
| **P1** | P1-2 sub_app 三胞胎复制 | 已实测的重复 56 行 | 小 | ✅ 已合并 |
| **P1** | P1-3 LLM 代理样板重复 | 已实测的重复 ~90 行 | 小 | ✅ 已合并 |
| **P1** | P1-1 tools 目录语义混淆 | 目录清晰度 | 小 | 🟡 部分（`tools→sub_app` 已断；`tools→agent` 未断） |
| **P0** | P0-1 门面双路径 | 重构风险、可维护性 | 大（20 处调用方） | ✅ 已拆除（bazi_engine / xianzhi_workflow） |
| **P1** | P1-4 干支关系两套实现 | **口径一致性（产品风险）** | 中 | ✅ 已统一（`ganzhi_relations.py`；⚠️ 口径需需求方确认） |
| **P1** | P1-6 巨型函数（2 个 500 行级） | 可维护性、事故风险 | 大 | ✅ shensha / check_facts 已拆；剩 create_xianzhi_graph / _do_ensure_tables 等 |
| **P1** | P1-7 巨型文件（4 个 600 行级） | 可维护性 | 中 | ✅ xianzhi / user_records 已拆；剩 postgres_memory / tables |
| **P2** | P2 死代码与冗余 | 代码卫生 | 小 | ✅ 已完成 |

**建议起手顺序**：阶段 0（清理 + 架构断言）→ 阶段 1（去重）→ 阶段 2（破倒置）→ 黄金命盘快照 → 阶段 3（巨型拆分）。
前四步已全部完成；阶段 3 主体已完成，仅 `postgres_memory` / `tables` 待拆。
阶段 4 拆门面可开始；P1-4 干支关系统一已实施，**其口径（含半合/拱合）需需求方确认拍板**后方可视为终态。

> **阶段 3 / 4 的前置条件已满足**：§7.2 的「黄金命盘快照」已于 2026-09-15 落地并通过变异验证，
> `_compute_shensha`（513 行）与 `check_facts`（451 行）在拆分时已有"改动前后逐字段全等"的锚点，
> 现已全部拆分完成。
>
> **当前一个关口**：
> - ① **P1-4 干支口径待确认**：`ganzhi_relations.py` 已按「纳入半合/拱合（含两支半刑）」实施，
>   会改变部分原局结论，需需求方拍板是否接受该口径（或回退为"仅三支全"）。属口径变更而非重构。
>   （P0-1 门面拆除与阶段 3 巨型拆分均已落地，`BASELINE_STAR_IMPORTS` / `BASELINE_DUAL_PATH_SYMBOLS` 已清零。）
