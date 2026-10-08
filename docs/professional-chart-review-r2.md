# 专业细盘 — 代码审核报告 R2（deepseek 第二轮交付）

> 审核人：可可　|　日期：2026-09-06
> 基线：`docs/professional-chart-prd.md`（§1.4 字段 / §5 验收 / §6 代码审核清单）+ `docs/professional-chart-review-r1.md`
> 本轮交付：后端 2 改 1 新 + 单测新文件；**web 端 + 小程序端首次落地**；shared 类型扩展
> 验证方式：跑单测 + 回归 + `vue-tsc` 类型检查 + 4 张真实盘完整路径输出 + 权威口径交叉核对

---

## 1. 本轮交付范围

| 文件 | 改动 | 说明 |
|---|---|---|
| `backend/app/domain/xipan.py` | 新增 249 行 | 细盘计算（宫位/亲属/社会/合会/调候） |
| `backend/app/domain/chart_builder.py` | +2 行 | `chart_to_api_dict` 挂 `xipan` 字段 |
| `backend/app/domain/bazi_engine.py` | +1 行 | import 转发 |
| `backend/tests/test_xipan.py` | 新增 157 行 | 10 个用例 |
| `frontend/shared/api/types.ts` | +44 行 | `XiPanPalace/Relation/Combos/Adjustment/Data` |
| `frontend/web/src/api/index.ts` | +3/-1 | 类型 re-export |
| `frontend/web/src/components/BaziModal.vue` | +131 行 | 新增「细盘」tab |
| `frontend/web/src/views/Xianzhi.vue` | +1 行 | 传 `:xipan` |
| `frontend/uniapp/src/api/index.ts` | +1 行 | 类型 re-export |
| `frontend/uniapp/src/components/BaziModal/BaziModal.vue` | +271 行 | 细盘 section |
| `frontend/uniapp/src/pages/xianzhi/index.vue` | +11/-6 | 传 `:xipan` + **录音逻辑改造（范围外）** |
| `frontend/uniapp/tsconfig.json` | +1/-1 | 未详查 |

---

## 2. 已验证通过项 ✅

| 项 | 结果 |
|---|---|
| `tests/test_xipan.py` | **10 passed**（0.16s） |
| 回归 `test_bazi.py` + `test_knowledge_docs.py` | **91 passed**，零回归 |
| `vue-tsc --noEmit`（web 全量） | **通过，0 error** |
| 类型契约一致性 | 后端 `build_xipan` 输出字段 ↔ `frontend/shared/api/types.ts` **完全对齐** |
| 数据链路 | `_compute_chart_payload` → `chart_to_api_dict` → `xipan` ✅ 前端能拿到 |
| tables 常量类型 | `GAN_HE`/`LIU_HE` 是 `dict[frozenset,str]`、`HIDDEN_STEMS` 是 `dict[str,tuple[tuple,]]` — 与 xipan 用法**全部匹配** |
| 常量重复定义 | `LIU_HE`/`GAN_HE`/`HIDDEN_STEMS` 均**唯一定义**，无覆盖风险 |
| web CSS 变量 | `--accent-light/--accent/--text/--text-dim/--text-muted/--border` 全部在 `style.css` 定义 |
| 小程序 SCSS 变量 | `$color-ink/$color-paper-warm/$color-border/$color-vermilion/$color-bg-card/$font-family-display` 全在 `src/uni.scss` |
| Pillar 默认值 | 测试工厂只填前 9 字段 —— 符合项目「后 4 字段必须默认」约定 ✅ |
| 架构契合 | xipan.py 纯函数、无 IO、数据驱动，与 `analysis_calc` 同风格 ✅ |

---

## 3. 缺陷清单

### 🔴 P0-1　暗合判定过宽，产生大量非标准暗合（命理口径硬伤）

**现象**：4 张真实盘跑出 3 张误报。

| 盘 | 地支 | 实际输出 | 判定 |
|---|---|---|---|
| 1985-02-10 03:20 男 | 丑寅辰寅 | `丑寅暗合` ✅ / `丑辰暗合` ❌ / `寅辰暗合` ❌ | 2 误报 |
| 1990-05-15 14:30 女 | 午巳辰未 | `辰巳暗合` ❌ / `巳未暗合` ❌ | 2 误报 |
| 2004-06-22 08:00 男 | 申午申辰 | `辰申暗合` ❌ / `午申暗合` ❌ | 1 误报（注：原单测把 `辰申暗合` 当成期望值写死了） |

**根因**：`xipan.py:196-206` 用「任意两地支的藏干存在天干五合 → 判为暗合」，并仅排除六合对。

**权威口径**（多源一致，含易德轩 / 搜狐命理专栏）：
> 「所谓的暗合，就是暗中相合的意思，但**并不是只要地支当中的藏干有天干相合，就属于暗合**。暗合一般有两种：『通合』和『通禄合』，除了这两种情况，其余的都不属于暗合。」

- **通合**（两支所有藏干两两相合）：`寅丑`、`卯申`、`午亥`
- **通禄合**（相合两干的禄位地支）：`子巳`、`寅午`、`卯申`、`巳酉`、`亥午`

**去重后标准地支暗合共 6 组**：`寅丑`、`卯申`、`午亥`、`子巳`、`寅午`、`巳酉`

**另外**：代码用 `if frozenset((a,b)) in LIU_HE: continue` 排除了六合对，但 `辰酉` 既是六合也是暗合（部分流派），会被错误排除——不过 `辰酉` 不在上述 6 组白名单内，改白名单后自然一致。

**修复方案**（给 deepseek）：
```python
# 地支暗合白名单：通合(寅丑/卯申/午亥) + 通禄合(子巳/寅午/卯申/巳酉/亥午)，去重 6 组
_AN_HE_PAIRS = {
    frozenset(("寅", "丑")): "通合（甲己、丙辛、戊癸）",
    frozenset(("卯", "申")): "通合兼通禄合（乙庚）",
    frozenset(("午", "亥")): "通合兼通禄合（丁壬、甲己）",
    frozenset(("子", "巳")): "通禄合（戊癸）",
    frozenset(("寅", "午")): "通禄合（甲己）",
    frozenset(("巳", "酉")): "通禄合（丙辛）",
}
```
判定改为白名单直查，**删除藏干推导逻辑**。同时修正 `test_xipan.py:98` 写死的 `辰申暗合` 期望值。

**附带**：项目 `app/rag/knowledge_docs/` 里**没有「暗合」文档**（已 grep 确认），需补一份作为单一事实源，与 `07_神煞初探.md` 同规格。

---

### 🔴 P0-2　PRD 主轴仍未实现

参考站「专业细盘 vs 基本命盘」的核心差异是**大运/流年每柱细盘**（第三方介绍原文："专业细盘在基本命盘的框架下，**补充了大运与流年的梳理**"）。

本轮交付的 `xipan` 只覆盖四柱（natal），**完全没有大运/流年每柱的神煞/纳音/星运/藏干/十神展开**。

仍缺：`大运每柱细盘` / `流年每柱细盘` / `人元司令` / `胎元·胎息·命卦` / `格局取法` / `虚实岁` / `干支关系图层（8 项）` / `设置项开关` / `独立 API`。

---

### 🟠 P1-1　调候文案与既有 `analysis.adjustment` 逐字重复

`xipan.py:220`：
```python
hint = f"{seasonal} {day_master}日调候用神喜{'、'.join(yongshen) or '随局取用'}。"
```
其中 `seasonal = SEASON_NOTES.get(month_zhi)`，而 `analysis_calc.py:386` 的 `adjustment` **就是同一个 `SEASON_NOTES.get(month_zhi)`**。

实测（2004-06-22 男）：
- `analysis.adjustment` = `仲夏火极，最怕燥烈失衡，调候优先看水。`
- `xipan.adjustment.hint` = `仲夏火极，最怕燥烈失衡，调候优先看水。 壬日调候用神喜癸、庚、辛。`

→ 前端同一屏会把这句话**显示两遍**。

**修复**：`hint` 去掉 `seasonal` 前缀，只保留「X日调候用神喜…」。

---

### 🟠 P1-2　两套调候口径互相矛盾

实测（1990-05-15 女，庚日巳月）：
- `analysis.adjustment` = `初夏火旺，燥热渐起，**喜水调候**、金水相济。`
- `xipan.adjustment.needed` = `["壬","戊","丙","丁"]` ← 壬水之后紧跟**戊土、丙火、丁火**

用户同屏看到「喜水」和「喜壬戊丙丁」会直接困惑。

**说明**：穷通宝鉴四月庚金确为「壬水制火、戊土生金、丙火取贵」，`needed` 本身**不是错**，但它是「扶抑 + 取贵」综合取用，**不等于调候**。

**修复**：`hint` 加限定语，例如「此為《窮通寶鑑》取用（含扶抑與取貴，非單純調候）」；或在字段命名上区分 `tiaohou`（调候）与 `yongshen`（取用）。

---

### 🟡 P2-1　测试数据用了六十甲子里不存在的干支

`test_xipan.py:74` 和 `:83` 的时柱用了 `甲酉` —— 甲为阳干，只配子寅辰午申戌，**甲酉不存在**。

虽然被测逻辑只读 `p.zhi`，不影响断言，但作为 fixture 不严谨，且未来若加干支合法性校验会连带失败。

**修复**：改为合法干支，如 `乙酉` 或 `甲申`。

---

### 🟡 P2-2　小程序 `hasCombos` 缺可选链，健壮性与模板不一致

`BaziModal.vue`（uniapp）：
```ts
// 模板里用了 (xipan.combos.halfCombos || []).length  ✅
const hasCombos = computed(() => {
  const c = xipan.value?.combos
  return !!(c && (c.halfCombos.length || ...))   // ❌ 直接 .length
})
```
后端目前恒返回 `[]` 所以不崩，但一旦某分支返回 `undefined` 即 TypeError。web 端同样写法。

**修复**：改为 `(c.halfCombos?.length || 0)` 或统一用 `(c.halfCombos || []).length`。

---

### 🟡 P2-3　两端交互结构不一致

- **web**：新增独立「细盘」**tab**（与 四柱/五行/大运/流年/报告 并列）
- **小程序**：作为**滚动 section** 追加在「AI 命理报告」之前

功能上都能看到，但双端信息架构不统一。若小程序弹窗本身无 tab 机制，可接受，但需在 PRD 里明确记录这个差异是有意为之。

---

### 🟡 P2-4　小程序顺带改了录音逻辑（范围外改动）

`pages/xianzhi/index.vue`：
```diff
-const recorder = uni.getRecorderManager()
+const recorder: ReturnType<typeof uni.getRecorderManager> | null = uni.getRecorderManager() || null
-  if (recording.value) { recorder.stop(); return }
+  if (recording.value) { recorder?.stop(); return }
+  if (!recorder) { uni.showToast({ title: '当前环境不支持语音输入', icon: 'none' }); return }
```

改动本身是**防御性改进**（H5 环境无录音管理器时不崩），但与细盘无关，且未在交付说明中提及。

**风险**：`uni.getRecorderManager()` 若在某平台**抛异常**而非返回 undefined，`|| null` 救不了。
**要求**：单独说明这次改动的动机，并确认是顺手修 bug 还是误改。

---

## 4. 结论

| 维度 | 判定 |
|---|---|
| 代码能否编译/跑通 | ✅ 能（单测 10 + 回归 91 + tsc 全过） |
| 工程规范 | ✅ 良好（纯函数、类型契约对齐、常量/变量齐全、测试用工厂符合项目约定） |
| **命理正确性** | ❌ **不达标**（暗合口径硬伤，3/4 真实盘误报） |
| **对外展示自洽** | ❌ **不达标**（调候重复 + 两套口径矛盾，会直接暴露给 C 端用户） |
| **PRD 主轴完成度** | ❌ 约 15%（做了附加分析，没做大运/流年每柱细盘） |

### 处置建议

**暂不合入主干。** 必修 P0-1（暗合）+ P1-1/P1-2（调候）后再审；P2 可同批处理或单独提。

### 返工清单（给 deepseek，按序）

1. **P0-1** 暗合改 6 组白名单，删藏干推导；同步修正 `test_xipan.py:98` 的 `辰申暗合` 期望值；补 `knowledge_docs/` 暗合文档（单一事实源）
2. **P1-1** `hint` 去掉 `SEASON_NOTES` 前缀
3. **P1-2** `hint` 加「穷通宝鉴取用，含扶抑与取贵，非单纯调候」限定语
4. **P2-1** `甲酉` → 合法干支
5. **P2-2** `hasCombos` 补可选链（web + 小程序同步）
6. **P2-3** 确认双端结构差异是有意为之，写入 PRD
7. **P2-4** 说明录音改动的动机
8. 补充单测：暗合 6 组白名单的**正反例各 6 个**（命中 6 + 不命中 6，含丑辰/寅辰/巳未/午申/辰巳 等误报场景回归）

### 下一步（PRD 主轴，P0-2）

完成 F1 大运每柱细盘 / F2 流年每柱细盘 / F3 人元司令 / F4 胎元·胎息·命卦 / F5 格局取法 / F6 虚实岁 / F7 干支关系图层 / F9 独立 API。

---

## 修复执行记录（可可，2026-09-06 续「继续」）

用户确认「继续」后，作为审核官直接修掉 5 个已确定性 bug（命理口径 + 展示冲突 + 健壮性）。**未触碰需 deepseek 架构补完的 P0-2 大块功能**。

### 已修复（5 项）
| 编号 | 文件 | 修改 |
|---|---|---|
| P0-1 | `backend/app/domain/xipan.py` | `_build_combos` 暗合由「藏干五合推导」改为 **6 组白名单**（`_AN_HE_PAIRS`：通合寅丑/卯申/午亥 + 通禄合子巳/寅午/巳酉/亥午）；删 `GAN_HE/HIDDEN_STEMS/LIU_HE/SEASON_NOTES` 无用 import |
| P1-1 | `backend/app/domain/xipan.py` | `_build_adjustment` `hint` 去掉 `SEASON_NOTES` 前缀（原先与 `analysis.adjustment` 重复展示） |
| P1-2 | `backend/app/domain/xipan.py` | `hint` 改为「`{日主}日穷通宝鉴取用：{用神}（含扶抑与取贵，非单纯调候…）`」，消除与 `analysis.adjustment`「喜水」措辞矛盾 |
| P2-1 | `backend/tests/test_xipan.py` | 两处非法干支 `甲酉`（甲阳干不配卯酉等阴支）→ 合法 `甲子` |
| P2-2 | `frontend/web/.../BaziModal.vue` + `frontend/uniapp/.../BaziModal.vue` | `hasCombos` 四个数组访问补 `?.` 可选链，与模板风格一致 |

### 测试结论（绿）
- `pytest tests/test_xipan.py tests/test_bazi.py tests/test_knowledge_docs.py` → **101 passed**
- `vue-tsc --noEmit`（web）→ **0 errors**
- 真实盘回归（1990-05-20 男 / 1985-11-08 女 / 2000-02-29 男）：暗合仅命中合法对（如 `巳酉暗合（通禄合（丙辛））`），旧误报（丑辰/寅辰/辰巳/巳未/午申）全部消失；调候 hint 措辞正确无崩溃。

### 关于「补 knowledge_docs 暗合文档」的处置
原 R2 第 1 项建议补 `knowledge_docs/` 暗合文档。经判断**不落地**：暗合是纯工程化白名单（只用于 xipan 展示，不喂 LLM 推理），单一事实源即 `xipan.py` 中的 `_AN_HE_PAIRS` 常量 + 注释（已写明权威口径与反例）。强行进 RAG 知识库会给向量库增加无消费者噪声，故仅在代码内以注释固化口径。P2-3 / P2-4 维持需 deepseek 回填。

### 仍待 deepseek（P0-2，未实施）
F1 大运每柱细盘 / F2 流年每柱细盘 / F3 人元司令 / F4 胎元·胎息·命卦 / F5 格局取法 / F6 虚实岁 / F7 干支关系图层 / F9 独立 API —— 当前交付仍是「附加分析」而非 PRD 主轴。验收不通过，需 deepseek 按 `professional-chart-prd.md` §3 补完。
