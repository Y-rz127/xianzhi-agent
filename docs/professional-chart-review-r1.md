# 专业细盘 — 审核报告 R1（deepseek 首次交付）

> 审核人：可可　|　日期：2026-09-06
> 审核基线：`docs/professional-chart-prd.md`（§1.4 字段清单 + §5 验收 + §6 代码审核清单）
> 交付范围：`git status --short` 显示：3 个文件（2 改 + 1 新），**前端/API/测试 一项未动**

---

## 1. 完成度速览

| 模块 | PRD §1.4 要求 | 实际交付 | 完成度 |
|---|---|---|---|
| 宫位六亲（4 柱 → 祖上/父母/夫妻/子女宫） | ✅ 必含 | ✅ `_build_palaces` | 100% |
| 亲属六亲（男/女命区分） | ✅ 必含 | ✅ `_KINSHIP_MALE/FEMALE` | 100% |
| 社会关系（十神 → 角色） | ✅ 必含 | ✅ `_SOCIAL` | 100% |
| 拱合/半合/暗合 | ✅ 必含 | ✅ `_build_combos` | 100% |
| 调候用神（穷通宝鉴表） | ✅ 必含 | ✅ `_TIAOHOU` 10干×12支 | 100% |
| **大运每柱细盘**（神煞/纳音/星运/藏干/十神） | ✅ 必含 | ❌ 未做 | 0% |
| **流年每柱细盘** | ✅ 必含 | ❌ 未做 | 0% |
| **人元司令** | ✅ 必含 | ❌ 未做 | 0% |
| **胎元/胎息/命卦** | ✅ 必含 | ❌ 未做 | 0% |
| **格局取法细化**（正格/从格/专旺/化格/普通） | ✅ 必含 | ❌ 未做 | 0% |
| **虚实岁** | ✅ 必含 | ❌ 未做 | 0% |
| **干支关系完整图层**（六合/三合/三会/暗合/相刑/相冲/相破/相害） | ✅ 必含 | ⚠️ 仅做半合/拱合/暗合 | ~30% |
| **设置项开关**（干支关系/人元司令/格局取法/虚实岁） | ✅ 必含 | ❌ 未做 | 0% |
| **独立 API** `GET /api/ai/xianzhi/chart/detail` | ✅ 必含 | ❌ 未做（仅挂在 chart_to_api_dict） | 10% |
| **Web 端独立页** `/chart` | ✅ 必含 | ❌ 未做 | 0% |
| **小程序端** `/pages/chart-detail` | ✅ 必含 | ❌ 未做 | 0% |
| **单测**（PRD §5.4 列 23 例） | ✅ 必含 | ❌ 未做 | 0% |

**整体完成度：约 10%**（1 个 248 行领域函数 / 16 项 PRD 要求）

---

## 2. 已交付代码质量评估（`backend/app/domain/xipan.py` 248 行）

### ✅ 优点
1. **架构契合**：纯函数、无 IO、无状态，与 `bazi_engine` / `analysis_calc` 同风格
2. **数据驱动**：`_KINSHIP_MALE/FEMALE` / `_SOCIAL` / `_TIAOHOU` 全部查表，扩展友好
3. **调候表完整**：10 天干 × 12 月支 = 120 单元全填（穷通宝鉴主流口径）
4. **避免绝对化**：末尾 `note` 字段标注"古法主流 vs 另一派，最终取用需结合大运流年"——符合 PRD §6.4 LLM 注入宽容度原则
5. **排序一致**：`_SHISHEN_ORDER` 全局复用，输出稳定
6. **docstring**：每个函数有说明

### ⚠️ 风险/改进点
1. **无单测**（核心风险）：`_build_combos` 的暗合判定用了三重嵌套生成器，逻辑最复杂却最易错（如 `HIDDEN_STEMS.get(a, ())` 默认空 tuple 是 OK，但 `frozenset((ha, hb)) in GAN_HE` 在 ha==hb 时会被 frozenset 自动去重，可能漏判定）—— 必须有 fixture
2. **gender 类型契约不明**：函数签名 `gender: str` 但依赖 `_KINSHIP_MALE if gender == "男"`。`chart.birth.gender` 实际是中文（见 `chart_builder._gender_label`），但若调用方传 int 或 enum 会静默走女命分支（gender != "男" → 女性 mapping）。**应在函数入口 `assert gender in ("男", "女")` 或显式归一化**
3. **`xipan.py` 命名**与项目"xianzhi"拼音风格一致，可接受；但 `kith_kin`（古英语"kith and kin"）对中文项目偏生僻，建议改为 `kinship`（已用作 dict key 之一，会冲突）→ 改 `build_kith_kin` 函数名为 `build_relationships` 或 `build_family_relations`
4. **`_present_ten_gods` 用 `p.shishen_gan != "日主"` 过滤**：依赖 `chart_builder._ten_god` 把日柱的 shishen_gan 设为 "日主"。如果未来重构改了 "日主" 字面量，会静默失败。建议用常量 `DAY_MASTER_LABEL = "日主"`
5. **`_build_combos` 半合/拱合逻辑遗漏**：当前仅按"申-子-辰"等 4 组查，**没有考虑相邻柱位组合的"半合半会"**（如年支申 + 时支辰，因隔着 3 柱也算"半合"——古法严不严看流派）；代码用 `present = {p.zhi for p in pillars}` 一刀切 OK，但缺少注释说明"按全部命局地支判定，不分柱距"
6. **顺序问题**：`halfCombos` 内 `sorted` 没用，依赖 `_SAN_HE_GROUPS` 字面顺序——可接受但脆弱，加 `key=` 更稳
7. **暗合输出格式**：`f"{a}{b}暗合（{label}）"` 其中 label 来自 `GAN_HE[frozenset((ha, hb))]`，是中文标签如"甲己合化土"。但如果 (a,b) 有多对藏干都能合，**只取第一个**，可能漏报。需决定：取最强 vs 全列
8. **没接大运/流年**：这是 PRD §1.4 的**核心增量**，xipan.py 只针对四柱（natal），没扩展到 DayunItem / LiunianItem

### ❌ 与 PRD §6 已知问题对照
- [ ] §6.2 dataclass 字段默认值：本次没新增 dataclass 字段，N/A
- [ ] §6.3 神煞查表：本次没改 shensha_calc.py，N/A
- [x] §6.5 跨端复用：xipan 输出 dict 键名 camelCase 风格不一致（`halfCombos` 是，但 `present_ten_gods` 不是输出层）—— `build_xipan` 输出键名 OK
- [ ] §6.6 单测覆盖：**严重缺失**，0 覆盖

---

## 3. 关键问题：未对齐 PRD 范围

deepseek 选择的功能集（宫位/亲属/社会/拱合/暗合/调候）**是我 PRD §1.4 表格的"附加分析"**，不是"细盘"的主轴。

**PRD §1.4 细盘的主轴是"大运/流年每柱细盘"**——这是参考站"专业细盘 vs 基本命盘"的核心差异（第三方介绍原文："专业细盘在基本命盘的框架下，**补充了大运与流年的梳理**"）。

当前 xipan.py **完全没涉及大运/流年**，仅做了"四柱之上的附加解读"。这导致：
- 没有"细盘"独有的差异化展示
- 没有可点击展开的大运/流年详情
- 没有满足 PRD §1.4 大运每柱必含字段（神煞/纳音/星运）

---

## 4. 返工要求（按优先级 P0→P2）

### P0 — 必须返工（验收基线 §5.1-§5.4）

| ID | 要求 | 来源 |
|---|---|---|
| F1 | **补全大运每柱细盘**：扩展 xipan 在 DayunItem 上的输出（神煞/纳音/星运/十神展开），前端能点击查看 | PRD §1.4 / §5.5 |
| F2 | **补全流年每柱细盘**：同上，针对 LiunianItem | PRD §1.4 / §5.5 |
| F3 | **补全人元司令**：按月支查当令天干（参考权威源：渊海子平/三命通会） | PRD §1.4 / §5.1 |
| F4 | **补全胎元/胎息/命卦**：BirthInfo 新增字段 | PRD §1.4 / §5.1 |
| F5 | **补全格局取法**：在 `analysis_calc` 输出 5 种之一（正格/从格/专旺/化格/普通） | PRD §1.4 / §5.1 |
| F6 | **补全虚实岁**：BirthInfo 新增字段，按生日边界切换 | PRD §1.4 / §5.1 |
| F7 | **补全干支关系图层完整数据**：六合/三合/三会/暗合/相刑/相冲/相破/相害 8 项 | PRD §1.4 / §5.2 |
| F8 | **新增单测** `tests/test_chart_detail.py`：覆盖 F3-F7 各例 + xipan.py 现有逻辑 23 例 | PRD §5.4 / §5.8 |

### P1 — 必须返工（验收基线 §5.3 + §5.5-§5.6）

| ID | 要求 | 来源 |
|---|---|---|
| F9 | **新增 API** `GET /api/ai/xianzhi/chart/detail`（Pydantic 入参校验） | PRD §5.3 |
| F10 | **新增 Web 端** `views/ChartDetail.vue` + 路由 `/chart` + 子组件 11 个 | PRD §3 / §5.5 |
| F11 | **新增小程序端** `pages/chart-detail/index.vue` + pages.json 注册 + 抽屉入口 | PRD §3 / §5.6 |

### P2 — 体验优化

| ID | 要求 | 来源 |
|---|---|---|
| F12 | **gender 类型守卫**：函数入口归一化为 "男"/"女" | §2 风险点 2 |
| F13 | **"日主" 字面量常量化** | §2 风险点 4 |
| F14 | **`_build_combos` 暗合全列 vs 取最强** 的策略注释 + 决定 | §2 风险点 7 |

---

## 5. 流程建议

deepseek 这次直接动手没对齐 PRD。建议下一轮：
1. 乐乐确认 PRD §0 五个 Q（默认我已按 web+小程序双端/折叠展开/全开放/必备/URL+档案 填写）
2. 乐乐把 PRD 发给 deepseek，要求按 PRD §3 的"文件范围"逐项实现
3. 我按 PRD §5 / §6 逐项验收

---

## 6. 当前可继续的工作

由于 xipan.py 是纯函数、无依赖，**可以单独先跑其单测**（等 deepseek 补完 F8 后）。

xipan.py 现有逻辑我也可以帮 deepseek 起草测试用例（验收官的职责），写到 `tests/test_xipan.py`：
- _present_ten_gods：固定 fixture 输入 → 期望十神集合 + 柱位
- _build_palaces：4 柱 → 4 宫位元数据
- _build_kith_kin：男命/女命 → 不同亲属映射
- _build_combos：四柱有申子辰 → 半合水；有寅午戌 全 → 三合火；无 → 空
- _build_adjustment：甲日卯月 → 庚丙丁戊

**需要乐乐决定**：让我直接补 `tests/test_xipan.py` 把现有 xipan.py 锁住，还是等 deepseek 完整返工后一起补？

---

## 7. 状态

- ✅ 完成度盘点（10%）
- ✅ 已交付代码质量评估
- ✅ P0/P1/P2 返工要求清单
- ⏳ 等待乐乐决定 F1-F14 返工节奏 + 是否让我先补 xipan 单测锁现状