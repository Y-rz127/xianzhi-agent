# docs 索引

> 约定：**文档按"读它的时机"分目录**，不按作者或日期。
> `architecture/` = 现在该怎么理解系统；`product/`、`plans/` = 现在的需求与方案；
> `reviews/`、`archive/` = 历史证据，只读不改（结论已落地或被取代）。
> 代码里的注释可以引用这些路径，移动文件时请同步改引用（见文末检查脚本）。

## architecture/ —— 现在系统长什么样

| 文档 | 内容 | 什么时候读 |
|---|---|---|
| [`architecture/multi_agent_architecture.md`](architecture/multi_agent_architecture.md) | 先知智能体全貌：入口分流（workflow / ReAct / 闲聊短路）、Supervisor + Worker + Reviewer、工具集、记忆与检索 | 接手项目、改编排逻辑、加 Worker/领域 |
| [`architecture/backend-architecture-review.md`](architecture/backend-architecture-review.md) | 后端架构审查：依赖分层铁律（第四节，`tests/test_architecture.py` 据此断言）、循环依赖与巨函数清单、阶段整改记录 | 动跨包 import、拆大文件前 |
| [`verdict-cache.md`](verdict-cache.md) | 命盘裁决缓存：四柱指纹 vs 出生时刻指纹、三条入口时序、实测耗时、"哪些不能跨人共享" | 改终审/缓存/排盘链路前（**必读**） |
| [`architecture/ws-multiplex.md`](architecture/ws-multiplex.md) | 先知对话 WS 单连接多路复用：为什么不能多开连接、协议帧与 `request_id` 路由、并发上限 `WS_MAX_PARALLEL_SESSIONS`、断线续跑 | 动聊天 WS / 多会话并行 / 断线取回前 |
| [`prompt_budget/INDEX.md`](prompt_budget/INDEX.md) | 每条对话路径发给 LLM 的输入预算（字符数 / token 数）实测总表 | 调提示词、怀疑 token 爆炸时 |

## product/ —— 需求与验收基线

| 文档 | 内容 |
|---|---|
| [`product/professional-chart-prd.md`](product/professional-chart-prd.md) | 专业细盘 PRD：参考站功能边界、字段清单（§1.4）、验收标准（§5）、代码审核清单（§6） |

## plans/ —— 现行方案与路线图

| 文档 | 内容 |
|---|---|
| [`plans/domain-projection-plan-v3.md`](plans/domain-projection-plan-v3.md) | 领域投影 + 岁运关系 + 分析规程（v3 定稿，自包含；v2 已归档） |
| [`plans/continual_learning_roadmap.md`](plans/continual_learning_roadmap.md) | 持续学习优化清单（案例检索 / 反馈沉淀 / K 线校准等） |

## reviews/ —— 一次性评审（历史证据，只读）

| 文档 | 内容 |
|---|---|
| [`reviews/knowledge-base-engineering-review.md`](reviews/knowledge-base-engineering-review.md) | 知识库工程化审查（切分 / 检索参数 / 口径对照 / 古籍引用真实性） |
| [`reviews/professional-chart-review-r1.md`](reviews/professional-chart-review-r1.md) | 专业细盘第一轮审核报告 |
| [`reviews/professional-chart-review-r2.md`](reviews/professional-chart-review-r2.md) | 专业细盘第二轮审核报告（含 R1 遗留项复核） |

## archive/ —— 被取代或纯产物，别再当现状读

| 文档 | 为什么归档 |
|---|---|
| [`archive/domain-projection-plan-v2.md`](archive/domain-projection-plan-v2.md) | 已被 v3 覆盖（v3 自包含） |
| `archive/kb_chunk_audit.txt` | 一次知识库 chunk 审计的**输出文本**，不是文档 |

## 提交前自检（替代早期散落的 review 清单）

- [ ] 本地 `pytest` 全绿（集成用例需 `TEST_POSTGRES_CONNECTION_STRING`，见 `DEPLOY.md` §6.1）
- [ ] 涉及前端时 `vue-tsc --noEmit` 零错误
- [ ] `ruff check app tests scripts main.py` 零问题
- [ ] 新增核心逻辑有单测；改了既有口径的，先核对黄金快照 diff 再 `UPDATE_*` 重生成
- [ ] 安全硬指标：输入校验 / 鉴权不被绕过 / 无注入 / 密钥不落库
- [ ] 涉及 `docs/` 路径的引用已同步（见下）

## 维护脚本

移动/改名文档后，跑一遍引用检查（纯只读）：

```bash
# 在仓库根目录执行：列出所有"提到 docs/xxx 但文件不存在"的引用
python - <<'PY'
import re, pathlib
root = pathlib.Path('.')
refs = {}
for f in list(root.glob('*.md')) + list(root.glob('docs/**/*.md')) + list(root.glob('backend/**/*.py')) \
        + list(root.glob('.github/**/*.md')):
    if any(p in f.as_posix() for p in ('.venv', 'node_modules', '学习资料')):
        continue
    for m in re.finditer(r'docs/[A-Za-z0-9_\-/]+\.(?:md|txt)', f.read_text(encoding='utf-8', errors='ignore')):
        refs.setdefault(m.group(0), set()).add(f.as_posix())
bad = {k: v for k, v in refs.items() if not (root / k).exists()}
print("悬空引用：" if bad else "全部引用有效")
for k, v in sorted(bad.items()):
    print(' ', k, '<-', ', '.join(sorted(v)))
PY
```
