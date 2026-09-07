# 专业细盘功能 — 调研 / 计划 / 验收基线

> 用途：① 锁定参考站的功能边界，避免遗漏关键模块；② 与 deepseek 对齐实施计划与文件范围；③ 作为代码审核官的逐项验收基线。
> 撰写：可可（代码审核官）　|　日期：2026-09-06
> 状态：**待 deepseek 交付代码** — 本文档只锁定基线，未触碰任何实现文件。

---

## 0. 与乐乐的待确认事项（动手前对齐）

| # | 事项 | 候选 | 备注 |
|---|---|---|---|
| Q1 | 范围 | A. 仅 web 端独立页 /chart　B. web + 小程序 /pages/chart-detail　C. A + 聊天页内嵌细盘入口 | 项目 README 强调"Web + 小程序双端"对齐，B 或 C 更稳 |
| Q2 | 大运/流年每柱交互 | A. 列表平铺　B. 折叠+点击展开详情（神煞/藏干/十神/星运）　C. 弹层 | 问真八字是 B/C 混合 |
| Q3 | "设置项"是否做 | A. 全开放　B. 模拟参考站的 VIP 锁定（仅前端提示）　C. 全部关闭 | 影响路由与持久化 |
| Q4 | "干支关系可视化"是否纳入细盘 | A. 必备（参考站核心卖点）　B. 简化为文字描述 | 工作量差距大 |
| Q5 | 命盘输入方式 | A. URL ?birth_time=&gender= 直接渲染　B. 进入后让用户填写　C. 复用命主档案 | BaziModal 当前是 A |

---

## 1. 参考站调研结论

### 1.1 来源
- **PC 端**：`pcbz.iwzwh.com/#/paipan-result/index?MRType=0&guid=104d08b0-f4d8`（dump DOM 已确认结构）
- **移动端**：`bz.iwzwh.com`（已抓首页布局，供参考）
- **第三方功能介绍**：wanke.pcpop.com / blrc.com.cn / eaeb.cn 多源印证

### 1.2 侧边栏模块清单（PC）
1. 问真官网
2. 基本信息
3. 基本排盘　← 用户给的 URL
4. **专业细盘**　← 本次目标
5. 命理报告
6. 设置
7. 切换手机版

### 1.3 专业细盘 vs 基本命盘 的差异（第三方描述原文要点）
> "专业细盘在基本命盘的框架下，**补充了大运与流年的梳理**，方便大家开展命盘的时空维度探究。"
> "排盘所涵盖的数据包括四柱、十神、藏干、纳音、星运、空亡、神煞、滴天髓、参考用神、袁天罡称骨、八字五行占比，以及**大运流年对应的神煞、纳音和星运**等内容。"

### 1.4 专业细盘完整内容清单
| 分区 | 必含字段 | 可选/进阶 |
|---|---|---|
| **四柱大表** | 天干/地支/藏干/十神/星运/自坐/空亡/纳音/神煞 | 人元司令、藏干透干标识 |
| **命主信息** | 姓名/性别/出生时间/生肖/出生地域 | 真太阳时标注 |
| **衍生要素** | 节气/星座/星宿/**胎元**/空亡/**命宫**/**胎息**/**身宫**/**命卦** | — |
| **五行能量** | 五行个数 + 五行能量 | 五行占比图 |
| **格局用神** | 格局取法（正格/从格/专旺/化格/普通）、参考用神 | 调候、喜忌 |
| **干支关系图层** | 天干：五合/相冲/相克；地支：六合/三合/三会/暗合/相刑/相冲/相破/相害 | 全部 VIP 解锁 |
| **人元司令** | 按月支查当令天干 | — |
| **大运每柱** | 干支/起止年份/起止年龄 + 神煞 + 纳音 + 星运 + 藏干 + 十神 | 折叠展开 |
| **流年每柱** | 年份/干支/虚岁 + 神煞 + 纳音 + 星运 + 藏干 + 十神 | 横向滚动 100 年 |
| **虚实岁** | 生日之前/之后切换显示 | — |
| **命理报告** | 用户自填的笔记 | 与命盘关联存储 |

### 1.5 移动端布局观察（bz.iwzwh.com 首页）
- 顶部 logo + 导航（当前页金色高亮）
- 内容卡片化、圆角、白底
- 多列用横向滚动而非栅格
- 底部留白充足

---

## 2. 本项目现状盘点（避免重复造轮子）

### 2.1 后端 — 已具备 / 缺失
| 模块 | 现状 | 文件 |
|---|---|---|
| Pillar（含藏干/十神/星运/自坐/空亡/纳音） | ✅ | `backend/app/domain/models.py` |
| DayunItem + LiunianItem（含神煞/藏干/十神/星运） | ✅ | 同上 |
| WuxingAnalysis（强弱/用神/特殊格局） | ✅ | 同上 |
| DomainAnalysis（十神统计/合冲刑害/调候/格局提示） | ✅ | 同上 |
| 神煞查表 | ✅ | `backend/app/domain/shensha_calc.py`（13 处已对齐 07_神煞初探.md） |
| chart_to_api_dict（前端契约） | ✅ | `backend/app/domain/chart_builder.py:359` |
| **人元司令** | ❌ 缺 | — |
| **命宫/身宫独立字段** | ⚠️ 仅字符串 `mingGong` 拼接 | models.py `ming_gong_nayin` |
| **胎元/胎息/命卦** | ❌ 缺 | — |
| **格局取法（正格/从格/化格）** | ⚠️ 只有 `special_pattern` 标"专旺/从格"，无"化格/普通" | analysis_calc.py |
| **虚实岁** | ❌ 缺 | — |
| **干支关系图层数据** | ❌ 缺（仅有 combinations/clashes/harm） | analysis_calc.py |
| **独立细盘 API** | ❌ 缺；现有 `/api/ai/xianzhi/ws` 走 Agent | api/xianzhi.py |

### 2.2 前端 web — 已具备 / 缺失
| 模块 | 现状 | 文件 |
|---|---|---|
| BaziCard（基础卡片） | ✅ 94 行 | `frontend/web/src/components/BaziCard.vue` |
| BaziModal（弹窗式细盘） | ✅ 763 行，5 个 tab：四柱/五行/大运/咨询依据/流年 | `frontend/web/src/components/BaziModal.vue` |
| DayunTimeline | ✅ 180 行 | `frontend/web/src/components/DayunTimeline.vue` |
| WuxingChart | ✅ 60 行 | `frontend/web/src/components/WuxingChart.vue` |
| 路由 `/chart` 独立页 | ❌ 缺 | `frontend/web/src/router/index.ts` |
| 大运每柱可展开详情 | ⚠️ 已有 timeline，需改造为可展开 | DayunTimeline.vue |
| 流年可展开详情 | ❌ 缺 | — |
| 神煞弹层 | ✅ 已有 `ps-popover-card` | BaziModal.vue:232 |
| **人元司令展示** | ❌ 缺 | — |
| **命宫/身宫/胎元/胎息/命卦展示** | ❌ 缺（mingGong/shenGong 字段在 api dict 已有但前端未用） | — |
| **干支关系可视化图层** | ❌ 缺 | — |
| **设置项开关** | ❌ 缺 | — |

### 2.3 小程序 — 已具备 / 缺失
| 模块 | 现状 | 文件 |
|---|---|---|
| pages/xianzhi/index（聊天页） | ✅ | `frontend/uniapp/src/pages/xianzhi/index` |
| BaziCard / BaziModal / DayunTimeline / WuxingChart 组件 | ✅ | `frontend/uniapp/src/components/` |
| 独立细盘页 `/pages/chart-detail` | ❌ 缺 | pages.json 无 |
| 小程序入口（聊天抽屉/我的/命例库） | ⚠️ 聊天抽屉已有「八字/紫微/塔罗」快捷入口 | — |

### 2.4 文档/测试
| 项目 | 现状 |
|---|---|
| `backend/app/rag/knowledge_docs/07_神煞初探.md` | ✅ 单一事实源 |
| `backend/tests/test_bazi.py` + `test_knowledge_docs.py` | ✅ 神煞与文档名强绑定（working_memory 已记） |
| `backend/tests/conftest.py` 的 `_make_pillar` | ✅ 已解耦（参考 working_memory Pillar 默认字段教训） |
| `.coveragerc` 排除 api/db/tarot 等胶水层 | ✅ 60% 门槛 |

---

## 3. 实施计划（分阶段 + 文件范围）

### 阶段 0：与乐乐对齐（Q1-Q5）
**负责人：乐乐**　|　**产出**：本文档 Q 表格回填

### 阶段 1：后端领域层扩展
**文件范围**：
```
backend/app/domain/
├── models.py             # 新增字段（带默认值！）
│                          - BirthInfo: xu_shi_sui, tai_yuan, tai_xi, ming_gua
│                          - BaziChart: ren_yuan_si_ling: dict[str,str]  # {柱位: 当令天干}
│                                       ge_ju_qu_fa: str               # 正格/从格/专旺/化格/普通
│                                       dry_branch_relations: dict     # {六合,三合,三会,暗合,相刑,相冲,相破,相害}
│                          - Pillar: 不变
├── analysis_calc.py       # 新增:
│                          - _ren_yuan_si_ling(month_zhi) -> str  按月支查表
│                          - _ge_ju_qu_fa(chart) -> str  综合 special_pattern + 化格判定
│                          - _dry_branch_relations(zhis) -> dict 已有的拆分命名
├── chart_builder.py       # chart_to_api_dict 暴露新字段（camelCase 保持）
│                          - 新增: xuShiSui, taiYuan, taiXi, mingGua
│                          - 新增: renYuanSiLing, geJuQuFa, dryBranchRelations
├── chart_format.py        # 不变（LLM 注入 4 条链路已统一）
└── tables.py              # 查表数据集中（人元司令 / 化格表）

backend/app/domain/tests/ 或 backend/tests/
└── test_chart_detail.py   # 新增（参照 test_bazi.py 风格）
```

**单测要求**（每字段至少 1 fixture）：
- 人元司令：12 个月支各 1 例 → 共 12 例
- 格局取法：正格 1 / 从格 1 / 专旺 1 / 化格 1 / 普通 1 = 5 例
- 虚实岁：生日前 1 / 生日后 1 = 2 例
- 胎元/胎息/命卦：1 例
- 干支关系图层：四柱有六合 + 有三合 + 有相刑 各 1 = 3 例

### 阶段 2：后端 API 层
**文件范围**：
```
backend/app/api/
├── xianzhi.py             # 新增路由:
│                          - GET /api/ai/xianzhi/chart/detail?birth_time=&gender=
│                          - POST /api/ai/xianzhi/chart/settings  (settings 持久化)
└── deps.py                # 复用现有依赖

backend/app/db/ 或 backend/app/memory/
└── user_chart_settings.py # 新增（用户设置持久化，参考现有 schema）
```

### 阶段 3：web 前端（Vue3 + Vite）
**文件范围**：
```
frontend/web/src/
├── views/
│   └── ChartDetail.vue           # 新增（路由 /chart）
├── views/components/chart/
│   ├── ChartPillarsGrid.vue      # 四柱大表 + 藏干透干
│   ├── ChartBirthInfo.vue        # 命主信息
│   ├── ChartDerivedFactors.vue   # 胎元/胎息/命宫/身宫/命卦
│   ├── ChartWuxingPanel.vue      # 五行能量
│   ├── ChartRelationsLayer.vue   # 干支关系可视化（参考站卖点）
│   ├── ChartRenYuanSiLing.vue    # 人元司令
│   ├── ChartPatternPanel.vue     # 格局取法 + 用神 + 调候
│   ├── ChartDayunList.vue        # 大运每柱 + 展开
│   ├── ChartLiunianGrid.vue      # 流年 100 年（虚拟滚动）
│   ├── ChartShenshaPanel.vue     # 神煞全表
│   └── ChartSettings.vue         # 设置开关
├── api/
│   └── chart.ts                  # 新增（fetchChartDetail / saveSettings）
├── router/
│   └── index.ts                  # 注册 /chart
└── components/
    ├── BaziModal.vue             # 改造：增加 /chart 路由链接
    └── DayunTimeline.vue         # 改造：支持点击展开
```

**响应式断点**：≥1024 PC 完整 / 768-1024 折叠 / <768 移动适配

### 阶段 4：小程序（uniapp）
**文件范围**：
```
frontend/uniapp/src/
├── pages/
│   ├── chart-detail/index.vue        # 新增
│   └── chart-detail/components/      # 复刻 web 的子组件（移动端单列）
├── components/
│   └── chart/                        # 复用
├── api/
│   └── chart.ts                      # 新增
├── pages.json                        # 注册 chart-detail
└── pages/xianzhi/index               # 改造：抽屉增加「细盘」入口
```

**真机验证**：iOS + Android 各 1 机型

### 阶段 5：联调 + 可观测性
- web/小程序对接真实 API（curl + 真机双验）
- 错误兜底：API 失败 → toast 重试
- 埋点：detail_view / dayun_expand / liunian_click / shensha_popup / settings_change
- 现有 observability 表增加细盘事件类型

### 阶段 6：测试与验收
见第 5 节

---

## 4. 高可用设计要点

### 4.1 后端
- **纯函数计算**：与现有 `bazi_engine` / `analysis_calc` 同架构，不依赖 LLM/DB
- **单测覆盖**：每个新字段至少 1 张 fixture（参考 `_make_pillar` 工厂）
- **Pillar/DayunItem/LiunianItem 新增字段必须带默认值**（working_memory 教训：frozen dataclass 漏默认值会导致整盘 TypeError）
- **缓存键**：`hash(birth_time) + gender + settings_hash`，5 分钟 TTL
- **错误码**：422（参数校验）/ 500（计算异常）分离

### 4.2 前端
- **骨架屏**：chart 数据未到时显示骨架（参考现有 BaziModal）
- **错误边界**：组件级 try/catch + ErrorBoundary
- **虚拟滚动**：流年 100 年用 `<recycle-scroller>` 或自实现
- **懒加载**：干支关系图层默认折叠，点击展开
- **TypeScript**：`shared/types/chart.ts` 定义完整类型，前后端共用

### 4.3 小程序
- **分包加载**：chart-detail 作独立 chunk
- **API 重试**：失败 1 次后等待 1s 重试，最多 3 次

### 4.4 跨端一致性
- **字段类型定义**放 `shared/types/chart.ts`
- **字段常量**（五行颜色、纳音、神煞分类）放 `shared/constants/chart.ts`

---

## 5. 验收标准（代码审核官的基线清单）

> deepseek 交付后，逐项打勾。任何 ❌ 都要返工。

### 5.1 后端域模型
- [ ] `models.py` 所有新字段有 docstring + 类型注释
- [ ] Pillar/DayunItem/LiunianItem 新增字段**必须带默认值**（防 TypeError）
- [ ] BaziChart 新增 `ren_yuan_si_ling` / `ge_ju_qu_fa` / `dry_branch_relations` 字段
- [ ] BirthInfo 新增 `xu_shi_sui` / `tai_yuan` / `tai_xi` / `ming_gua`

### 5.2 后端计算逻辑
- [ ] `_ren_yuan_si_ling(month_zhi)` 按月支查表，输出当令天干（与人元司令权威源对齐）
- [ ] `_ge_ju_qu_fa(chart)` 综合 special_pattern + 化格判定，输出 5 种之一
- [ ] `_dry_branch_relations(zhis)` 返回 {六合:[], 三合:[], 三会:[], 暗合:[], 相刑:[], 相冲:[], 相破:[], 相害:[]}
- [ ] `chart_to_api_dict` 暴露所有新字段，键名 camelCase 与现有风格一致

### 5.3 后端 API
- [ ] `GET /api/ai/xianzhi/chart/detail` 有 Pydantic 入参校验（birth_time 格式、gender 枚举）
- [ ] `POST /api/ai/xianzhi/chart/settings` 持久化设置
- [ ] 错误响应结构统一 `{code, message, data: null}`
- [ ] 路由注册在 `routes.py` 并挂载到 `/api/ai/xianzhi`

### 5.4 后端单测
- [ ] `tests/test_chart_detail.py` 覆盖：人元司令 12 例、格局取法 5 例、虚实岁 2 例、胎元/胎息/命卦 1 例、干支关系图层 3 例
- [ ] 现有 `test_bazi.py` / `test_knowledge_docs.py` **零回归**
- [ ] `.coveragerc` 不需调整（domain 层本就在覆盖范围内）

### 5.5 前端 web（Vue3）
- [ ] `ChartDetail.vue` 通过 `/chart?birth_time=...&gender=...` 进入，无 console.error
- [ ] 四柱大表 13 字段全部正确渲染（与 chart_to_api_dict 字段一一对应）
- [ ] 大运每柱点击展开详情（藏干/十神/神煞/纳音/星运）
- [ ] 流年 100 年可横向滚动 + 全部可访问
- [ ] 神煞弹层点击打开（含知识库文案回源）
- [ ] 干支关系图层可视化（天干五合/相冲/相克；地支六合/三合/三会/暗合/相刑/相冲/相破/相害）
- [ ] 格局取法 + 调候 + 用神提示
- [ ] 命宫/身宫/胎元/胎息/命卦 展示
- [ ] 人元司令展示
- [ ] 虚实岁：生日之前/之后切换显示
- [ ] 白天/暗夜主题切换不破坏
- [ ] 响应式：≥1024 / 768-1024 / <768 三档断点
- [ ] 加载/错误/空 三态
- [ ] TypeScript 类型完整（无 any 滥用）
- [ ] 无 ESLint error

### 5.6 小程序（uniapp）
- [ ] `pages.json` 注册 `pages/chart-detail/index`
- [ ] 微信开发者工具编译通过（`dist/build/mp-weixin` 无错误）
- [ ] 与 web 同字段同展示
- [ ] 流年横滑卡
- [ ] 暗夜主题生效（themeClass 链路）
- [ ] 真机预览：iOS + Android 各 1 机型
- [ ] 包体积：分包加载（细盘作独立 chunk）

### 5.7 端到端
- [ ] 同一生辰（3 张 fixture：1990 庚午年男、2000 庚辰年女、1985 乙丑年男）web + 小程序展示**完全一致**（字段、文案、配色）
- [ ] 后端日志无 5xx
- [ ] 平均首屏 < 2s（web Lighthouse；小程序秒开率 > 90%）
- [ ] 切换主题/响应式无闪烁

### 5.8 测试用例清单（用例 → 期望）

| ID | 维度 | 用例 | 期望 |
|---|---|---|---|
| T01 | 字段展示 | 1990-庚午年男，进入 `/chart` | 四柱大表全部 13 字段 + 藏干透干标识可见 |
| T02 | 字段展示 | 2000-庚辰年女，进入细盘 | 人元司令按月支"辰"正确显示 |
| T03 | 字段展示 | 1985-乙丑年男，进入细盘 | 胎元/胎息/命卦 全部显示 |
| T04 | 字段展示 | 任一生辰，进入细盘 | 干支关系图层按四柱自动高亮六合/三合/相刑等 |
| T05 | 字段展示 | 任一生辰 | 格局取法：正格/从格/专旺/化格/普通之一 |
| T06 | 字段展示 | 生日前/后边界 | 虚实岁正确切换 ±1 |
| T07 | 交互 | 大运每柱点击 | 展开藏干/十神/神煞/纳音/星运 5 项 |
| T08 | 交互 | 流年横向滚动 | 100 年完整可访问，滚动流畅 |
| T09 | 交互 | 神煞文字点击 | 弹层显示该神煞含义 + 出处 |
| T10 | 交互 | 设置项切换"干支关系图层" | 图层显示/隐藏 |
| T11 | 错误兜底 | API 返回 500 | 友好 toast + 重试按钮，不白屏 |
| T12 | 错误兜底 | birth_time 格式错 | 422 提示，不进入细盘 |
| T13 | 错误兜底 | 网络断开 | 骨架屏 + 重试 |
| T14 | 跨端一致性 | 同生辰 web + 小程序 | 字段、文案、配色完全一致 |
| T15 | 跨端一致性 | web 切换主题 | 小程序同步切（同一用户档案） |
| T16 | 跨端一致性 | 小程序横屏 | 布局不破 |
| T17 | 性能 | web Lighthouse | Performance ≥ 85，LCP < 2.5s |
| T18 | 性能 | 小程序秒开率 | 冷启动 ≤ 3s |
| T19 | 主题/响应式 | 1024/768/375 三档断点 | 布局正确切换 |
| T20 | 主题/响应式 | 白天→暗夜切换 | 全部组件颜色正确 |

---

## 6. 代码审核检查清单（deepseek 交付后逐项跑）

> 引用 `~/.workbuddy/MEMORY.md` / `working_memory_content` 已知陷阱：

### 6.1 命名与结构
- [ ] 函数 snake_case，组件 PascalCase，常量 UPPER_SNAKE
- [ ] 无魔法数字（阈值集中在文件顶部常量）
- [ ] 无 TODO 注释残留（业务代码落地后清理）

### 6.2 dataclass 字段默认值
- [ ] Pillar / DayunItem / LiunianItem 新增字段**全部带默认值**
- [ ] BaziChart / BirthInfo / WuxingAnalysis / DomainAnalysis 新增字段同上

### 6.3 神煞查表
- [ ] 修改 `_compute_shensha` 内部控制流后必须用真实盘走完整路径验证（不只是 AST pass）
- [ ] 新增神煞：参考 `app/rag/knowledge_docs/07_神煞初探.md` 单一事实源
- [ ] 精 X ⊃ 普通 X 神煞互斥：标记顺序"先精后粗"

### 6.4 LLM 注入
- [ ] 若细盘文案走 LLM，需遵守 `REVIEWER_SYSTEM` 红线 + **维度7 宽容度**（"211 本科倾向"等方向性描述放行）
- [ ] 文案不要"为求安全而通篇模糊"

### 6.5 跨端复用
- [ ] 字段类型定义放 `shared/types/chart.ts`，前后端共用
- [ ] 字段常量放 `shared/constants/chart.ts`

### 6.6 单测覆盖
- [ ] 与本验收 §5.4 一一对应
- [ ] 现有 `test_bazi.py` / `test_knowledge_docs.py` 零回归
- [ ] knowledge_docs 文件名若改动，必须同步改测试期望值（working_memory 教训）

### 6.7 API 设计
- [ ] 路由前缀 `/api/ai/xianzhi/`
- [ ] 入参 Pydantic 校验
- [ ] 错误码 422/500 区分
- [ ] WS 与 HTTP 接口并存时，WS 不替代 HTTP（细盘走 HTTP）

### 6.8 前端
- [ ] 路由 lazy-load（避免主 chunk 膨胀）
- [ ] 流年虚拟滚动
- [ ] 主题 class 通过根节点传递（参考小程序 themeClass 链路）
- [ ] 不破坏现有 BaziModal（向后兼容）

### 6.9 小程序
- [ ] manifest.json 配置正确
- [ ] 分包加载（chart-detail 独立 chunk）
- [ ] 微信开发者工具编译零错

### 6.10 文档
- [ ] `docs/` 新增「细盘字段说明.md」
- [ ] README.md 新增「专业细盘」章节（与紫微斗数章节风格一致）

---

## 7. 当前状态

- ✅ 参考站调研完成（菜单 + 模块 + 第三方介绍多源印证）
- ✅ 本项目现状盘点完成（前后端已具备 / 缺失）
- ✅ 实施计划与文件范围锁定
- ✅ 验收基线清单（§5）+ 测试用例（§5.8）锁定
- ✅ 代码审核检查清单（§6）锁定
- ⏳ **等待乐乐回填 §0 的 Q1-Q5**
- ⏳ **等待 deepseek 交付代码**，按 §5/§6 逐项审核