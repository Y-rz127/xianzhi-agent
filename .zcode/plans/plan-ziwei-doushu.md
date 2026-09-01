## 紫微斗数排盘子应用 — 确认版实施方案

> 确认记录（2026-09-01）：技术路线=Python 自研 + iztro 黄金快照；MVP 范围=仅 P0（排盘+点宫详情+AI 简批，今日运势/黄历联动留 P1）；四化表=三合通用表；accent 色默认 #5B6FC8 可在视觉验收时调整。

方案经实际验证（2026-09-01）：iztro 2.6.0（MIT，GitHub SylarLong/iztro）已在本机跑通排盘探针，输出结构、闰月、每日运势、晚子时行为均已实测；py-iztro（PyPI 0.1.5）实装检查后否决（详见路线对比）。项目现状确认：全仓无任何紫微/星曜代码，lunar-python 1.4.8 仅用于历法，新子应用不与其冲突；集成点全部沿用黄历/六爻既有约定，零新增运行时依赖、不碰数据库、不碰 RAG、无迁移。

---

### 一、调研结论摘要

**开源阵营**：iztro 是紫微斗数排盘事实上的标准开源引擎（MIT、npm 2.6.0、多语言、持续维护），功能覆盖十二宫、十四主星、辅曜杂曜、庙旺亮度、四化、大限/小限/流年/流月/流日/流时、horoscope 每日运势。Python 侧的 py-iztro 只是用 pythonmonkey（嵌入式 SpiderMonkey 原生扩展）包了一层 iztro JS，非真正移植。另有 mingli-master（排盘→可视化 HTML→LLM 解读）与 Numerology（确定性排盘 + AI 解读 + 知识库校订抑幻觉）两个参考项目，理念与本项目一致。

**商业竞品**（文墨天机、风箱说紫微、元亨利贞、飞碟紫微助手等）共性功能：阳历/农历输入切换 + 闰月、时辰选择、4×4 宫格命盘、点宫看详情、三方四正、大限流年推演、真太阳时校正（专业版）。付费点集中在详批、流年报告、合盘。竞品普遍"工具强、解读弱、视觉旧"——本项目的差异化空间在 **AI 解读、黄历联动、新中式暗夜星空视觉**。

**流派结论**：安星法各派一致（同一生辰排出的星曜分布相同），分歧集中在四化表（三合通用表 / 钦天四化 / 中州派细微差异）。本方案 MVP 采用三合通用四化表（即 iztro 默认），四化表设计为可替换常量，后续可扩展。闰月采用"上半月算本月、下半月算下月"（中州规则，与 iztro 一致，以 fixtures 钉死）；晚子时（23:00–24:00）归次日（iztro 实测与次日早子时结果一致，即主流约定）。

---

### 二、技术路线（已选定，附否决理由）

| 路线 | 结论 | 理由 |
|---|---|---|
| **A. Python 领域层自研排盘引擎，iztro 仅作黄金数据 oracle** | ✅ 选定 | 完全对齐黄历/八字既有架构（纯函数 + 黄金快照测试）；零新增运行时依赖；可被 Agent 工具消费；流派/规则全自主可控。iztro 为 MIT，且星曜排布属传统公共规则，用它批量生成参考数据无版权问题 |
| B. 引入 py-iztro | ❌ 否决 | 依赖 pythonmonkey 重型原生扩展（Windows wheel 兼容风险）、无 license、版本 0.1.5 功能不全、单人维护 |
| C. 前端 uniapp 直接跑 iztro（JS） | ❌ 否决 | 计算逻辑不进领域层，违反项目约定；无 pytest 黄金快照钉流派；Agent 无法调用排盘；包体增大 |

自研引擎的正确性保障：**一次性 Node 脚本调 iztro 批量生成 40+ 组生辰的完整排盘结果，存入 `tests/fixtures/ziwei_oracle/`，pytest 逐组断言**。引擎写错即红，流派调整时 fixtures 与代码同步评审。

---

### 三、产品设计（MVP）

页面流：`生辰输入表单 → 命盘展示 → 点宫详情 → AI 简批`，单页分阶段（phase 机，仿 liuyao/index.vue）。

**P0（MVP）**
1. 输入表单：阳历/农历切换、日期选择（1900–2099）、时辰选择（12 时辰 + 显示对应时段）、性别、农历闰月开关（农历模式）；文案带"传统民俗文化参考"免责口径。
2. 命盘展示：经典 4×4 宫格（外圈 12 宫 + 中央信息区显示农历/四柱/五行局/命宫身宫），每宫显示宫名、宫干支、主星（带庙旺亮度小字标注）、吉凶曜、四化角标（禄=金、权=朱、科=青、忌=墨）、大限年龄段、身宫标记。
3. 点宫详情：弹层展示该宫主星/辅曜/杂曜完整列表（含亮度、四化）、长生十二神、博士十二神、将前/岁前诸星、三方四正提示。
4. AI 简批：基于命盘生成一段整体简批 + 命宫/财帛/官禄三宫要点（走既有 LLM，prompt 约束"依据命盘数据、不虚构星曜、民俗参考口径"）。

**P1（MVP 后紧跟）**
5. 今日运势：horoscope 流日——今日流日宫位 + 流日四化 + 一句提示，与黄历页做入口互链（创新点：紫微 × 黄历双历联动）。
6. 大限/流年面板：当前大限宫位高亮、流年四化。

**P2（远期）**：合盘、真太阳时校正、飞星/自化详析、分享卡片、命例收藏（复用现有 favorites 体系）。

**视觉**：新增 `$nx-accent-ziwei: #5B6FC8`（黛蓝紫，"紫气东来"意象，与塔罗紫 #9A6FD4、合婚棕 #C08A5E 区隔）；页面沿用暗夜星空 + 流星装饰；命盘卡片用 `$nx-card/$nx-border`，四化角标用主题语义色。

---

### 四、实施步骤

1. **Oracle 数据生成（一次性开发工具）** `scripts/gen_ziwei_oracle.js`：
   - Node 脚本（不入生产包，README 注明用途），调用 iztro `astro.bySolar/byLunar` + `horoscope()`
   - 样本覆盖：五行局全覆盖、男女、十二时辰、闰月（2023 闰二月 15/16 日各一组验证上下半月规则）、晚子时（23:30）、早年晚年（1901/2099）；≥40 组
   - 输出 `tests/fixtures/ziwei_oracle/case_XX.json`：十二宫干支/主星(名+亮度+四化)/吉凶曜/杂曜四组/大限区间/身宫位置/五行局

2. **领域层** `app/domain/ziwei/`（包结构，文件会多，不塞单文件）：
   - `models.py`：dataclass `Star(name, type, scope, brightness, mutagen)`、`Palace(...)`、`Chart(...)`、`to_dict()`
   - `tables.py`：紫微安星表（日数×五行局）、天府系对称表、亮度表（14 主星×12 宫）、四化表（十天干，可替换常量）、天魁天钺/禄存擎羊陀罗（年干）、火铃（年支组+时辰）、昌曲/辅弼（时辰/月）、空劫（时辰）、天马/红鸾/天喜/天姚/咸池等（年支）、长生起宫（五行局+阴阳）、博士/将前/岁前十二神表。表结构对齐 iztro 源码逐项誊录，每张表注释出处
   - `engine.py`：
     - `cast_chart(*, solar_date=None, lunar_date=None, leap=False, time_index, gender) -> Chart`：内部用 lunar-python 做阴阳历互转（`Solar.fromYmd().getLunar()`，项目已锁 1.4.8）；安命宫/身宫 → 定五行局 → 安主星 → 安辅曜杂曜 → 起四化 → 排大限小限；非法参数抛 `ValueError`
     - `horoscope(chart, target_date) -> dict`：流日/流月宫位与流四化（P1 用，MVP 先留接口）
   - 流派决策以模块头注释写明（三合通用四化表、闰月规则、晚子归次日），与黄历 `_DAY_GOD_POS` 注释风格一致

3. **测试** `tests/test_ziwei.py`（先于/同步于引擎，仿 test_huangli.py）：
   - 全部 oracle fixtures 逐组断言（主星分布、四化、亮度、大限区间、身宫、五行局）
   - 边界：闰月 15/16 日分界、晚子时 23:30 == 次日早子、time_index 0–12 全覆盖、1900/2099 边界
   - `pytest.raises(ValueError, match=...)`：非法性别、超范围日期、农历日期不存在（如农历 2 月 30 日）

4. **子应用** `app/sub_app/ziwei/`（仿 huangli 三件套）：
   - `__init__.py` 一行 docstring；`ziwei_app.py` 组装层（参数解析 → engine → JSON dict）；`routes.py`：`APIRouter(prefix="/ziwei", tags=["ZiWei"])`
     - `GET /api/ai/ziwei/chart?date=&time_index=&gender=&calendar=solar|lunar&leap=false` → 完整命盘 dict（snake_case）
     - `POST /api/ai/ziwei/interpret` body `{date, time_index, gender, calendar, leap, focus?}` → `{text}`；后端重排盘（不信任前端传盘）、拼结构化命盘摘要入 prompt、走既有 LLM 配置；LLM 失败 502（仿 liuyao/interpret）
     - `GET /api/ai/ziwei/horoscope?...&target=`（P1 再开）
   - 错误处理：`ValueError→400`、其他 `500+client_error(e)` + `log.exception`；无鉴权、不进 AppContext
   - `app/api/routes.py` 加 import + include_router 两行

5. **Agent 工具** `app/tools/ziwei.py`：`ziwei_chart(date, time_desc, gender)` 同步 `@tool` 返回 str 文本摘要（命宫主星、五行局、四化、身宫，约 200 字），导出 `ziwei_tools`，`main.py` local_tools 拼接处加一项。让仙芝对话能直接排盘并衔接解读。

6. **前端 uniapp**：
   - `uniapp/src/api/index.ts`：`ZiWeiChart/ZiWeiPalace/ZiWeiStar` 等 TS interface + `getZiWeiChart()`、`interpretZiWei()`（照抄黄历区写法）
   - `uniapp/src/pages/ziwei/index.vue`（仿 liuyao/index.vue 三段式）：根 `.page :class="themeClass"` + 暗夜 meteor + 自绘返回 + hero（标题「紫微斗数」+ 副文案免责口径）+ scroll-view；phase: `form → chart → (detail 弹层 / interpret 面板)`
   - 命盘渲染：4×4 `grid` 布局（**必须 `grid-template: repeat(4, 1fr)`，禁用 flex calc%，项目已有取整换行教训**），中央 2×2 信息区；宫格内字号分级（宫名>主星>辅曜>亮度小字）；四化角标绝对定位宫格四角
   - `pages.json` 注册 `{ "path": "pages/ziwei/index", "style": { "navigationStyle": "custom", "navigationBarTitleText": "紫微斗数" } }`
   - 首页抽屉快捷功能区加第五个 `drawer-quick-btn` + `goZiWei()`（`uni.navigateTo`）
   - `uni.scss` 加 `$nx-accent-ziwei`；样式只用 `$nx-*`/`$color-*` token，禁止对变量做 `rgba()/darken()` 运算；页面根节点主题类绑定勿漏（设置页前车之鉴）

7. **README + 冒烟**：README 补「紫微斗数」一节；冒烟步骤 = 起服务（`.venv\Scripts\python.exe main.py`）→ curl chart/interpret → 微信开发者工具打开 `uniapp/dist/build/mp-weixin` 走一遍表单→排盘→点宫→简批，白天/暗夜双主题各验一次。

---

### 五、验证与验收门禁

- `pytest -q`（新增 test_ziwei.py 全绿，含 ≥40 组 oracle 快照）
- `pytest -q --cov=app --cov-report=term-missing --cov-fail-under=60`（CI 门禁）
- `ruff check .`
- `cd uniapp && npm run build:mp-weixin`（type-check 在 HEAD 即坏，不作为门禁，沿用既有做法）
- 真机/开发者工具冒烟：排盘结果与 oracle fixtures 肉眼抽查 3 组 + 双主题视觉

---

### 六、待确认决策点

1. **技术路线**：是否认可「Python 自研 + iztro 生成黄金快照」？（若倾向更快上线，可退而选前端 iztro 直出，但牺牲可测性与 Agent 化）
2. **MVP 范围**：P0（排盘+点宫+AI简批）是否足够，还是 P0+P1（含今日运势/黄历联动）一次做完？
3. **四化表**：默认三合通用表（iztro 同款），如需指定中州派或钦天表请说明。
4. **accent 色**：默认 `#5B6FC8` 黛蓝紫，可在视觉验收时调整。

不碰数据库、不碰 RAG 索引、无迁移、不动 shared/。工作量预计 4–6 个工作日（编码 + 审查 + 验证）。
