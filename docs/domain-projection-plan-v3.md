# 让先知「按领域看全盘、一步步推演」——领域投影 + 岁运关系 + 分析规程（v3 定稿）

> v3 = v2（`domain-projection-plan-v2.md`）经落地前代码复核 + 一次正式评审后的修订定稿。
> v3 覆盖 v2，本文自包含，无需对照 v1/v2。

## 〇、版本修订记录

### v3 相对 v2（本版新增，均来自代码复核与评审）

| # | 决策 | 内容 | 依据 |
| --- | --- | --- | --- |
| A | **补 `appearance` 进映射表** | `WORKERS` 与 `DOMAIN_LABELS` 实为 **19 个** domain（v2 写 18 有误）。v2 映射表 14 有简报 + 4 空 = 18，**漏了 appearance**，其极易受此影响（最依赖五行形相/十神泄秀取象）。补一行 | 代码复核 |
| B | **补童限期** | 未交大运者 `DayunItem.index=0`、`ganzhi="童限"`（非干支）。`resolve_target_dayuns("当前")` 命中童限时 `_gan_rel/_zhi_pair_rel` 的 len==2 校验静默跳过 → 岁运关系全空。处理：童限以当年**小运**干支作岁柱参与判定（复用 `xipan._current` 的 `tongxian` 逻辑），格式输出置位 | 用户拍板「可提」 |
| C | **compact_facts 注入 gate 去 worker 依赖** | v2 Step 9 "仅当 `needs_chart and not worker.skip_facts`"，但 `compact_facts(chart, intent)` 无 worker 参数。实际 gate = `intent.needs_chart` 且该 domain 映射非空（theory/chitchat/naming/auspicious 天然空串短路）。同时**对齐 build_messages 与 build_repair_messages 的 skip_facts 语义差**（前者 `and not needs_chart`、后者仅 `skip_facts`） | 评审裁决 |
| D | **hits_yongshen 不进 Reviewer 维度 11** | hits_yongshen 是 `useful_hint` 文本的粗分类（调候/扶抑用神不唯一，本身可能错）。维度 11 只核**干支关系类**（天克地冲/岁运并临/伏吟反吟/合冲刑害/touched_pillars）；hits_yongshen 仅作参考字段，不参与硬校验，防新增误杀源 | 评审裁决 |
| E | **神煞防漂移锚点改 `shensha_calc`** | v2 写「与 `_SHENSHA_NAMES` 逐字一致」是错的锚点——那是 Reviewer 匹配名单，含非排盘产出名（空亡/三奇贵人）。应改为与 `shensha_calc._compute_shensha` **实际产出**的 name 集合核对 | 评审裁决 |
| F | **`bazi_liunian` cache key 含 start_year** | 现键 `"liunian:{years}:{current_year}"` 不含起始年，新增 `start_year` 后问过去某年会读错缓存 | 评审裁决 |
| G | 年龄口径**不处理** | 用户是先看命盘再指认大运，`resolve_target_dayuns` 直接用 `DayunItem.start_age/end_age`（虚岁区间）交集即可，不做虚岁/周岁换算 | 用户拍板 |

### v2 相对 v1（保留历史）

| # | 决策 | 内容 |
| --- | --- | --- |
| 1 | 大运统一 12 步 | 初始挂盘 10→12、db 10→12、工具 bazi_dayun 默认 8→12；cases.py 命例库保持 8（刻意小盘） |
| 2 | 年龄区间跨步 | 「30-40」与区间有交集的大运全部命中（0-2 个），`resolve_target_dayuns` 返回列表 |
| 3 | 补流月 | 目标流年附 12 节气月干支+十神一行（仅用户明确问到的年份、≤2 年）；不做流月×原局关系 |
| 4 | frozen intent 零替换 | 大运→年份换算走纯函数 `effective_target_years()`，intent 在 classify 后永不变更 |
| 5 | Reviewer 同源 | `build_sui_section(chart, intent)` 一个函数，generate 与 check/repair 共用，字节级一致 |
| 6 | 长度预算 | 岁运关系 ≤300（单年）/≤600（大运）字；fact_block 流年行 ≤12 行；流月 ≤2 行 |
| 7 | 砍私有重导出 | `yun_relations` 直接 `from app.domain.xipan import ...`；bazi_engine 门面只重导出新模块公共符号 |
| 8 | 正则层不校岁运 | `_regex_review`/`check_facts` 均不加岁运/流月干支校验，仅 LLM 维度 11 |
| 9 | 事实修正 | WORKERS 数、`DayunItem.index` 基数实现时核对 |

---

## 一、现状诊断（已读代码，非猜测）

命盘挂载后走 `XianzhiWorkflow` 的 LangGraph（`xianzhi_langgraph.py`，State 为 TypedDict，节点只写 state delta）：
`classify → chart(扩盘) → retrieve(RAG) → generate → check → repair`

| 能力 | 位置 | 现状 |
| --- | --- | --- |
| 领域路由 | `agent/prompts.py` `domain_sysprompt` | LLM 拆出 domain + queries + needs_chart（JSON 里**无** target_years，年份纯正则提取） |
| 领域 Worker | `agent/workflow/workflow_workers.py` `WORKERS` | **19 个**领域（career/wealth/love/marriage/health/study/social/family/liunian/theory/chitchat/personality/migration/naming/auspicious/match/children/**appearance**/general） |
| 领域 RAG | `rag/retrieval.py` `DOMAIN_RULE_QUERIES` | 按 domain 拼检索词 |
| 命盘事实 | `workflow_messages.py::fact_block` | 四柱详述、神煞按柱、强弱、格局、用神、十神结构、干支关系、调候、大运、流年 |
| 双重校验 | `workflow_workers.py::ReviewerWorker` | 正则 `_regex_review` + LLM `_llm_review`（现有 10 维，维度 9=表述宽容度） |

**真正的缺口：**

1. **命盘投影是「平铺的、领域无关的」**。`fact_block` 对所有领域输出同一份长事实。问事业也得自己找官杀/印星在哪 → 感觉「只给了固定命盘事实」。
2. **没有显式「分析规程」注入**。`24_标准分析流程.md`、`13_大运流年咨询规则卡.md` 只是普通 RAG chunk，靠检索命中才有；`worker.expertise_prompt` 给的是断法要点而非分析顺序。
3. **大运/流年与原局的关系完全没预计算**。`DayunItem`/`LiunianItem` 只带自身干支/十神/藏干/星运/神煞；`xipan._build_relations` 只算当前时刻快照。问「2027 年怎样」，模型手上没有「丁未冲年支丑、引动婚姻宫」这类事实，只能自己推——违背「确定性优先，LLM 不得自算干支」原则，且 Reviewer 检不出来。
4. **流月不在对话路径**。xipan 的 `_build_liuyue_list`（节气月干支+十神）只有细盘/前端用，LLM 说到「某月如何」时无干支依据。
5. **intent 只提取具体年份**（`(?:19|20)\d{2}` + 今年/明年），无法锁定「某一步大运」；`extend_chart_if_needed` 只认 `target_years`。

**大运步数口径漂移（v2 一并统一）**：

| 调用点 | 现值 | v3 |
| --- | --- | --- |
| 初始挂盘 `workflow_support.py::build_chart_context` | 10 | **12** |
| 扩盘 `workflow_retrieval.py::extend_chart_if_needed` | 12 | 12 |
| `api/xianzhi.py` | 12 | 12 |
| `db/user_records.py` | 10 | **12** |
| 工具 `bazi_dayun` 默认 count | 8 | **12** |
| `api/cases.py`（命例库） | 8 | 8（不动，刻意小盘） |

---

## 二、方案总览

```
用户提问
  └ XianzhiWorkflow.answer
      ├ LLM 拆解 → QuestionIntent{domain, queries, needs_chart, target_years, target_dayun}  ← 新增 target_dayun
      ├ LangGraph: classify → chart(扩盘) → retrieve → generate → check → repair
      │    （六节点结构与连线不变；chart_node 内的 extend_chart_if_needed 变为大运感知）
      │
      │    intent 在 classify 后【永不变更】（frozen）。所有「大运→年份」换算走同一纯函数：
      │      effective_target_years(chart, target_years, target_dayun) -> list[int]
      │    四个调用点：extend_chart_if_needed / fact_block / build_sui_section / build_domain_brief
      │
      ├ generate 组装的 user prompt 新增两段：
      │      【本领域盘面要素】 ← 新增 domain_brief.py（领域投影）
      │      【岁运关系】       ← build_sui_section()（workflow_messages.py，内调 yun_relations.py + 流月行）
      │    system 追加：
      │      【XX分析规程】     ← prompts.py 新增（内部推演顺序，不输出）
      └ Reviewer：check/repair 节点调 build_sui_section() 得到同一字符串，以 sui_text 传入
```

**分层原则（守住现有架构契约）：**

- `yun_relations.py` / `domain_brief.py` 是**纯计算层**（domain 层，不 import agent 层类型）：只做要素筛选、归位、关系判定，**不产生任何断语**。结论仍由 LLM 依据要素 + RAG 得出。
- `build_sui_section(chart, intent)` 放 **agent 层**（workflow_messages.py），负责把 domain 层输出按 intent 组装成注入文本；generate 与 Reviewer 共用，天然同源。
- 不新增/不改名 `knowledge_docs/` 下任何文件（`tests/test_knowledge_docs.py` 硬编码期望值）。
- 合婚（match）：只做**本方盘**投影与岁运关系，对方盘维持 fact_block 平铺。

---

## 三、分步实施

### Step 1 · 新增 `backend/app/domain/yun_relations.py`

岁运关系计算。**复用 `xipan.py` 已有判定函数**（口径与细盘「岁运」栏一致，避免两套实现漂移），直接同包导入私有函数（**不经 bazi_engine 门面**）：
`_gan_rel` / `_zhi_pair_rel` / `_zhi_xing` / `_zhi_group_rel` / `_pillar_rel` / `_own_pillar_rel` / `_dedup` / `_ke`。

```python
@dataclass(frozen=True)
class SuiRelations:
    label: str                 # "2027丁未" 或大运 "第3步辛未"
    ganzhi: str
    shishen_gan: str           # 干对日主十神
    shishen_zhi: list[str]
    gan_rel: list[str]         # 天干：合/相克（对原局四柱 + 其余岁柱）
    zhi_rel: list[str]         # 地支：六合/六冲/六害/六破/三刑/三合半合拱/会方
    zhu_rel: list[str]         # 伏吟/反吟（整柱对整柱）
    touched_pillars: list[str] # 原局中被合/冲/刑/害到的柱 → "年柱(祖上父母宫)"
    sui_yun_bing_lin: bool     # 岁运并临（流年干支 == 所在大运干支）
    tian_ke_di_chong: bool     # 天克地冲（流年 vs 大运）
    hits_yongshen: str         # 该岁运五行命中喜/忌/闲（解析 useful_hint 粗分类，仅参考，不进维度11）
    is_tongxian: bool = False  # 是否童限期（未交大运，以当年小运作岁柱）

def cross_relations(a_gz: str, b_gz: str) -> list[str]      # 两岁柱：天克地冲/伏吟/反吟/干合/支合冲
def relations_for(chart, *, dayun_ganzhi="", liunian_ganzhi="") -> SuiRelations
def dayun_relations(chart, limit: int | None = None) -> list[SuiRelations]     # 每步大运 × 原局
def liunian_relations(chart, years: Sequence[int]) -> list[SuiRelations]       # 目标年 × (所在大运 + 原局)
def resolve_target_dayuns(chart, spec: str) -> list[DayunItem]                 # 0-2 个（见下）
def effective_target_years(chart, target_years: Sequence[int], target_dayun: str) -> list[int]
def liuyue_line(chart, year: int) -> str           # 该年 12 节气月一行（复用 xipan._build_liuyue_list）
def format_sui_relations(items: Sequence[SuiRelations]) -> str                 # 紧凑注入文本（每年一行）
```

**`resolve_target_dayuns` 的 spec 语义：**

| spec | 解析 | 返回 |
| --- | --- | --- |
| `当前` | today.year 落在 `[start_year, end_year]` 的步 | 0-1 个 |
| `下一步` | 当前步之后的一步（按 chart.dayun 列表顺序） | 0-1 个 |
| 序号 `3` / `三` | 用户口语「第 3 步」 | 0-1 个 |
| 年龄区间 `30-40` | **与 [30,40] 有交集的步全部命中**（`start_age <= 40 and end_age >= 30`） | 0-2 个 |
| 干支 `丙午` | `chart.dayun` 中 ganzhi 匹配 | 0-1 个 |
| 空 / 乱填 | 不猜 | `[]` |

**注意（实现时核对）**：`DayunItem.index` 直接透传 lunar `getIndex()`——lunar 惯例 0=起运前、1=第一步大运。动工前先用真实盘打印 `[(d.index, d.ganzhi, d.start_year) for d in chart.dayun]` 核对基数；序号语义以「用户口语第一步 = 第一步大运」为准。

**童限期（v3 新增，见修订记录 B）**：「当前/下一步」命中 `index=0`（`ganzhi="童限"`，非干支）的步时，该步不能直接进 `_gan_rel/_zhi_pair_rel`（len==2 静默跳过）。处理：
- 从 `chart` 的流年小运字段取当年小运干支（`LiunianItem` 若带小运则用；否则复用 `xipan._current` 的 `tongxian` + `xiaoyun.get(liunian_year)` 逻辑）作岁柱；
- 返回的 `SuiRelations` 置 `is_tongxian=True`，`ganzhi` 填小运干支；
- `format_sui_relations` 对童限期输出「童限期（未交大运，以 X 年小运 Y 论）」占位。

`effective_target_years` 实现：

```python
def effective_target_years(chart, target_years, target_dayun):
    years = set(target_years)
    for d in resolve_target_dayuns(chart, target_dayun):
        years.update(range(d.start_year, d.end_year + 1))
    return sorted(years)
```

`liuyue_line` 复用 `xipan._build_liuyue_list(year, year, day_master, pillars, gender_int)`，取该年 12 项，输出一行：
`流月 2027: 寅月壬寅(偏印,2/4起) 卯月癸卯(劫财,3/6起) …`（12 项，含节气公历起始日，方便 LLM 对应「阳历几月」）。

`touched_pillars` 是本轮最关键的产物：把「某年冲日支」直接翻译成「婚姻宫动」，LLM 不必自己做宫位映射。

### Step 2 · 新增 `backend/app/domain/domain_brief.py`

领域命盘投影层：领域 → 关注要素映射表 + 渲染函数。

```python
def build_domain_brief(chart, domain: str, *, target_years=(), target_dayun="") -> str
```

映射表（**19 个 domain 全覆盖**；实现时**神煞名必须与 `shensha_calc._compute_shensha` 实际产出的 name 集合逐字一致**（v3 修订 E，锚点非 `_SHENSHA_NAMES`），否则筛不出；性别从 `chart.birth.gender` 取，**无需加参数**）：

| domain | 关注十神 | 性别覆盖 | 关注宫位 | 关注神煞 |
| --- | --- | --- | --- | --- |
| career | 正官 七杀 正印 偏印 食神 伤官 | — | 月柱(事业宫) 日支 | 将星 国印贵人 天乙贵人 文昌贵人 学堂 正学堂 词馆 正词馆 金神 魁罡 |
| wealth | 正财 偏财 食神 伤官 比肩 劫财 | — | 月柱 日支 时柱 | 金舆 天厨贵人 禄神 拱禄 十恶大败 劫煞 亡神 |
| love | 正财 偏财 正官 七杀 比肩 劫财 | 男→财 女→官杀 | 日柱(配偶宫) | 桃花 红艳煞 红鸾 天喜 孤辰 寡宿 阴差阳错 孤鸾煞 |
| marriage | 同 love + 食神 伤官 | 同上 | 日柱 月柱 | 同 love + 童子煞 |
| health | 日主强弱/五行失衡为主线 | — | 全四柱 | 羊刃 飞刃 血刃 病符 天医 流霞 劫煞 灾煞 天罗 地网 |
| study | 正印 偏印 食神 伤官 正官 七杀 | — | 年柱 月柱 时柱 | 文昌贵人 学堂 正学堂 词馆 正词馆 华盖 德秀贵人 六秀日 十灵日 |
| social | 比肩 劫财 正官 七杀 | — | 月柱(兄弟/朋友宫) | 天乙贵人 天德贵人 月德贵人 太极贵人 勾绞煞 元辰 |
| family | 全部十神（按宫位归星） | — | 年柱(祖上父母宫) 月柱(父母兄弟宫) 日支 时柱(子女宫) | 天乙贵人 丧门 吊客 披麻 孤辰 寡宿 |
| personality | 十神计数前 3 + 透干者 | — | 日柱 | 魁罡 华盖 十灵日 八专日 九丑日 六秀日 德秀贵人 天赦日 四废日 |
| migration | 比肩 劫财 正官 七杀 正印 偏印 | — | 日支 月柱 | 驿马 天乙贵人 天罗 地网 |
| children | 正官 七杀 食神 伤官 | 男→官杀 女→食伤 | 时柱(子女宫) | 天乙贵人 华盖 孤辰 寡宿 |
| liunian | 目标大运/流年干支对日主取的十神 | — | 四柱全 | 驿马 桃花 红鸾 天喜 羊刃 |
| match | 配偶星 + 日支（**仅本方盘**，对方盘随 fact_block） | 男→财 女→官杀 | 日柱 | 桃花 红艳煞 红鸾 天喜 孤辰 寡宿 |
| **appearance** | 食神 伤官 正印 偏印 劫财 比肩 | — | 日柱 时柱 | 桃花 红艳煞 天乙贵人 六秀日 九丑日 八专日 魁罡 阳刃 |
| general | 十神计数前 3 + 日主/格局/用神 | — | 四柱 | 吉神优先：天乙 天德 月德 文昌 学堂 禄神 |
| naming / auspicious / theory / chitchat | 不生成简报（返回空串，零开销） | | | |

> **appearance 说明（v3 修订 A）**：身材样貌最依赖「五行形相 + 十神泄秀 + 神煞加分」取象，正是因为缺任一都会让取象悬空，故必须进简报。神煞取形貌相关强项（桃花/红艳煞/天乙贵人/六秀/九丑/八专/魁罡/阳刃），与 `appearance` worker 的 expertise_prompt 提的加分项对齐。

输出形如（≤700 字，超长截断）：

```
【本领域盘面要素 · 事业工作】
一、骨架：日主 甲木（偏旺，score 3.1）；用神提示 喜火土忌金水；月令 巳（调候：…）
二、事业相关十神落点
  正官：月柱天干「庚」（透出，得令）｜日支藏干「辛」
  七杀：无
  正印：时柱藏干「壬」（未透，力弱）
  食神/伤官：年柱、日柱地支藏干
三、相关宫位
  月柱（事业宫/父母宫）：庚午 主星正官 ｜ 地支午（藏 丁己）｜ 原局关系：午未…
  日支（配偶宫/自身宫）：…
四、相关神煞
  将星：日柱 ｜ 国印贵人：月柱 ｜ 天乙贵人：年柱
五、当前岁运
  大运 辛未（正印）2028-2037：与原局 午未六合日支(自身宫)、丑未冲年柱(祖上父母宫)
  （区间场景列 2 步；目标流年详情见【岁运关系】段，不在此重复）
```

实现要点：

- 十神落点：遍历 `p.shishen_gan`（主星）与 `p.shishen_zhi`（副星，索引对齐 `p.hidden_stems` 判本气/中气/余气），标「透出/未透」用 `analysis.exposed_stems`、标「有根」用 `analysis.rooted_stems`。
- 旺衰粗标注：参考 `wuxing.counts` 与 `p.changsheng` 给「得令/得地/力弱」的**事实性标签**，不下断语。
- 宫位别名按领域渲染（love 场景日支=配偶宫、health 场景日支=自身宫），映射表「关注宫位」列即渲染依据。
- 空串短路：`naming/auspicious/theory/chitchat` 直接 `return ""`。

### Step 3 · 重导出（`backend/app/domain/bazi_engine.py`）

兼容门面只补**公共符号**重导出（外部消费者习惯从门面导入）：
`SuiRelations` / `relations_for` / `dayun_relations` / `liunian_relations` / `resolve_target_dayuns` / `effective_target_years` / `liuyue_line` / `format_sui_relations` / `build_domain_brief`。
**xipan 私有函数不进门面**——`yun_relations` 直接 `from app.domain.xipan import _gan_rel, ...`（同包，Python 无真私有）。

### Step 4 · 提示词（`backend/app/agent/prompts.py`）

新增两个常量（并加进 `__all__`）：

```python
# 领域 → 分析聚焦点（一句话，只补规程第 2/3 步的领域侧重）
DOMAIN_STEP_FOCUS: dict[str, str] = {"career": "官杀(职位/权柄/压力)、印星(平台/靠山)、食伤(技能/表达) 三者的落点与流通", "appearance": "五行形相与十神泄秀为体、神煞为加分，先判身之强弱再论美", ...}

# 分析规程：内部推演顺序，禁止向用户输出步骤名
DOMAIN_PROCEDURE_TEMPLATE = """【{领域}分析规程 · 内部推演顺序】
按以下顺序在心里推演，每步只在有盘面依据时才下结论；最终回答只给结论与依据，不要输出本规程的步骤名或"第一步/第二步"这类字样。
1. 定骨架：日主与强弱档位、用神喜忌五行、月令调候（一律以【系统排盘事实】为准，不得自算）。
2. 定主星：从【本领域盘面要素】里取本领域相关的星，看它透干还是藏支、落在哪一柱、有无根气、星运如何。
3. 看流通制化：这些星彼此以及与原局其他十神之间的生克合冲（官印相生 / 财生官 / 食伤生财 / 食伤制杀 / 比劫夺财 / 伤官见官 / 官杀混杂 等）。只依据盘面要素判断，盘面没有的组合不得臆造。
4. 定倾向：结合格局清浊与用神得力程度给方向性判断，用"偏/倾向/看情况"措辞，不用绝对化断言，也不为求稳而通篇模糊。
5. 查岁运：先看当前大运对本领域是助是抑，再看用户所指年份的流年如何引动本领域相关的星与宫位。凡提年份必须带上该年流年干支与所在大运。
6. 落建议：最后给一条可执行的现实建议。
本领域侧重：{聚焦点}
"""
```

同步修改 `domain_sysprompt`：JSON 输出新增 `"target_dayun"` 字段，取值说明
`'当前' | '下一步' | 序号如'3' | 年龄区间如'30-40' | 干支如'丙午' | ''（未指定）`。

`REVIEWER_SYSTEM` 追加**维度 11「岁运关系一致性」**：回答若描述某年/某步大运与大运/原局构成某关系（天克地冲、岁运并临、伏吟、反吟、合冲刑害、宫位引动），须与【岁运关系】段一致；矛盾记问题；回答未描述关系则不记问题（宁可不误杀）。**hits_yongshen 是粗分类、不参与本维度校验（v3 修订 D）；流月干支本次不列入校验**（冒烟观察误报率后另议）。不动维度 9 白名单。

### Step 5 · 意图模型（`agent/workflow/workflow_models.py`）

`QuestionIntent` 增加 `target_dayun: str = ""`（frozen dataclass，带默认值追加在尾部，不破坏现有构造调用）。**不加 `target_dayun_years` 字段**——大运→年份的换算由 `effective_target_years` 在使用点派生（Step 8/9），intent 在 classify 后永不变更。

### Step 6 · 拆解解析（`agent/workflow/xianzhi_workflow.py::_decompose_query`）

读取 `data.get("target_dayun")`，`str().strip()`，写入 `QuestionIntent`；日志补 `target_dayun=`。其余逻辑（含年份正则提取）不动。

### Step 7 · 关键词兜底（`agent/workflow/workflow_support.py::classify_question`）

新增识别（LLM 拆解失败时才用）：

- `第[一二三四五六七八九十\d]+步大运` → 归一为序号串（`"3"`/`"三"` → `"3"`）
- `(\d{1,2})\s*[-~到至]\s*(\d{1,2})\s*岁` → 年龄区间串
- `大运` 附近出现的干支对（`GANZHI_RE`，已存在于本文件）→ 干支串

无命中留空串，**不猜**。同时本文件 `build_chart_context` 的 `dayun_count` 10 → **12**（大运统一）。

### Step 8 · 扩盘（`agent/workflow/workflow_retrieval.py::extend_chart_if_needed`）

**签名与调用方式不变**（`chart_node` 零改动），内部改为大运感知：

```python
def extend_chart_if_needed(ctx, intent) -> WorkflowChartContext:
    years = effective_target_years(ctx.chart, intent.target_years, intent.target_dayun)
    if not years:
        return ctx
    known_years = {item.year for item in ctx.chart.liunian}
    if all(y in known_years for y in years):
        return ctx
    start = min(min(years), _dt.date.today().year)
    end = max(max(years), _dt.date.today().year)
    chart = build_bazi_chart(..., dayun_count=12, liunian_start_year=start,
                             liunian_years=max(1, end - start + 1))
    return WorkflowChartContext(...)
```

用户问大运而不带年份时 `effective_target_years` 非空 → 不再被 `if not intent.target_years` 短路（原缺口的根因）。**大运与流年用同一份 chart**：扩盘后 `chart.dayun` 仍是 12 步、`chart.liunian` 覆盖目标区间，`fact_block`/`build_sui_section` 从 state 里的同一 ctx 取数。

### Step 9 · 消息装配（`agent/workflow/workflow_messages.py`）—— 主改动

1. `fact_block`：流年选择改为
   ```python
   years = effective_target_years(chart, intent.target_years, intent.target_dayun)[:12]
   if years:
       liunian_items = [item for item in chart.liunian if item.year in set(years)]
   else:
       # 现状 fallback：当前年+3 年，空则前 4 条（不变）
   ```
   （`[:12]` 为流年行硬上限；大运场景天然 10-11 行，极端宽区间截断。）
2. 新增 `build_sui_section(chart: BaziChart, intent: QuestionIntent) -> str`（**agent 层**，generate 与 Reviewer 的唯一同源函数）：
   ```python
   def build_sui_section(chart, intent) -> str:
       dayuns = resolve_target_dayuns(chart, intent.target_dayun)
       items = [relations_for(chart, dayun_ganzhi=d.ganzhi) for d in dayuns]
       years = effective_target_years(chart, intent.target_years, intent.target_dayun)
       items += liunian_relations(chart, years)
       parts = [format_sui_relations(items)]
       asked = [y for y in intent.target_years if y in {i.year for i in chart.liunian}][:2]
       parts += [liuyue_line(chart, y) for y in asked]
       return "\n".join(p for p in parts if p)
   ```
   `format_sui_relations` 压缩规则：**每个岁柱一行**（大运行带起止年，流年行带年份干支十神 + 关系短语 + hits_yongshen；童限期加「未交大运，以 X 年小运 Y 论」占位），确保大运场景 ≤600 字、单年场景 ≤300 字；超限从非目标年侧截断。
3. `compact_facts`：不改签名；在 `fact_block`（+合婚对方盘）之后追加
   ```
   【本领域盘面要素】\n{build_domain_brief(chart, intent.domain, target_years=..., target_dayun=...)}
   【岁运关系】\n{build_sui_section(chart, intent)}
   ```
   **注入 gate（v3 修订 C，去 worker 依赖）**：仅当 `intent.needs_chart` 且该 domain 简报非空时注入。`compact_facts(chart, intent)` 无 worker 参数，故**不用** `worker.skip_facts`；`theory/chitchat/naming/auspicious` 四个 domain 的 `build_domain_brief` 返回空串、且其 `needs_chart` 也多为 False，天然短路。同时 build_messages 与 build_repair_messages 的 skip_facts 判定需对齐（见第 4、5 点）。
4. `build_messages`：`system` 追加 `DOMAIN_PROCEDURE_TEMPLATE.format(领域=worker.label, 聚焦点=DOMAIN_STEP_FOCUS.get(domain, ""))`（**仅注入简报时加**，即与第 3 点同 gate；否则闲聊也塞规程）；`human` 顺序保持「用户问题 → 识别意图 → 历史摘要 → 系统排盘事实 → 本领域盘面要素 → 岁运关系 → 合婚基础/历史断事 → 命理规则检索 → 输出要求」。
5. `build_repair_messages`：与 build_messages **同 gate**（v3 修订 C：修复路径现用 `worker.skip_facts`、缺 `needs_chart` 判定，需改成与 build_messages 一致的 `worker.skip_facts and not needs_chart`），并同样带上「本领域盘面要素 + 岁运关系 + 分析规程」（**容易漏的一处**，进单测）。
6. `【输出要求】` 保留现有「提到具体年份必须核对流年干支与所在大运」，补一句「岁运关系一律引用【岁运关系】段，不得自行编排天克地冲/岁运并临；流月干支以该段流月行为准」。

### Step 10 · Reviewer（`agent/workflow/workflow_workers.py` + `xianzhi_langgraph.py`）

- `ReviewerWorker.review()` 与 `_llm_review()` 增加可选参数 `sui_text: str = ""`；`_llm_review` 的 `human_content` 在【系统排盘事实】后追加 `【岁运关系】\n{sui_text}`（非空才加）。
- `xianzhi_langgraph.py` 的 `check_node` 与 `repair_node`（LLM 深审分支）各加一行：
  `sui_text=build_sui_section(state["chart_context"].chart, state["intent"])`——与 generate 走同一函数，字节级一致。
- 维度 11 按 Step 4 定义，**hits_yongshen 与流月干支不参与校验**（防误杀）。
- **正则层（`_regex_review` / `check_facts`）本次不加任何岁运/流月校验**（写死，防止实现时顺手加出误杀；`check_facts` 现有 NOTE 已特意把大运/流年排除在锚点外）。

### Step 11 · 工具路径（`backend/app/tools/bazi.py`）

未挂盘 ReAct 路径口径对齐：

- `bazi_analysis(..., question=...)`（**question 参数已存在**）→ 用 `detect_domain(question)` 反查 domain，追加领域简报。
- `bazi_dayun(...)` → 默认 `count` 8 → **12**；每步大运后附「与原局关系」一行（`dayun_relations`）。
- `bazi_liunian(...)` → 新增 `start_year: int | None = None`（现只能从当前年起算，问过去某年不支持），并附岁运关系。**cache key 改为 `"liunian:{start_year}:{years}:{current_year}"`——必须含 start_year（v3 修订 F），否则问过去某年读错缓存**；`bazi_dayun` 追加关系行后注意同步更新其格式缓存的应用逻辑（首版无旧缓存则可忽略）。
- `bazi_full(...)` → 新增 `domain: str = ""` 参数，给了就附领域简报。
- 更新各工具 docstring（工具描述即 LLM 的选择依据，必须写清新增参数）。

### Step 12 · 单测

新增：

- `backend/tests/test_yun_relations.py`：
  - 天克地冲/岁运并临/伏吟反吟判定；`touched_pillars` 宫位归位；
  - `resolve_target_dayuns`：当前/下一步/`3`/`30-40`（**断言跨两步返回 2 个**）/`丙午`/乱填（返回 `[]`）；
  - **童限期（v3 修订 B）**：未交大运盘上「当前」返回童限项、`is_tongxian=True`、ganzhi 为当年小运、`format_sui_relations` 含「未交大运」占位；
  - `effective_target_years`：纯年份 / 纯大运 / 年份∪大运 三种合并；
  - `liuyue_line(2027)`：12 项、月干支五虎遁核对、节气日期非空。
- `backend/tests/test_domain_brief.py`：career 简报含正官/印星/月柱宫/将星；女命 love 用官杀、男命用财星；**appearance 简报含五行形相相关字段**（v3 修订 A）；`theory/chitchat/auspicious` 返回空串；**神煞名与 `shensha_calc._compute_shensha` 实际产出集合交叉校验**（v3 修订 E：锚点非 `_SHENSHA_NAMES`）。
- 更新 `backend/tests/test_xianzhi_workflow.py`：
  - `intent.target_dayun` 解析（LLM 路径 + classify_question 兜底）；
  - `build_messages` 在 `needs_chart=True` 时含三段新内容、`chitchat` 时不含；
  - `extend_chart_if_needed`：问大运**不带年份**时也扩盘（v1 缺口的回归用例）；`fact_block` 大运场景选覆盖流年且 ≤12 行；
  - `build_repair_messages` 含三段新内容，且其 skip 判定与 build_messages 一致（v3 修订 C）；
  - appearance domain 走有简报路径。
- 大运 12 步统一后：`grep -rn "dayun_count\|count=8\|count=10" backend/tests`，有步数断言同步更新（实施时确认，勿凭记忆）。

---

## 四、验收方式

1. **语法**：managed 3.13 对全部改动文件做 `ast.parse`。
2. **纯函数验证**：`yun_relations` / `domain_brief` 不依赖 lunar-python 的部分直接 `exec` 抽函数跑断言；涉及 `build_bazi_chart` 的用例需 3.12 venv。
3. **完整单测**：新建 3.12 venv + `pip install -r requirements.lock` 后
   `pytest tests/test_yun_relations.py tests/test_domain_brief.py tests/test_xianzhi_workflow.py tests/test_bazi.py`。
4. **端到端冒烟**（最重要，用一张真实盘）：
   - 「我事业怎么样」→ 日志确认 human 含【本领域盘面要素 · 事业工作】+【分析规程】；回答里官杀/印星表述与简报一致；
   - 「我身材怎么样」→ 【本领域盘面要素 · 身材样貌】注入、回答聚焦五行形相/泄秀（v3 修订 A 的冒烟）；
   - 「2027 年怎么样」→ 【岁运关系】含该年与所在大运、与原局的关系 + **流月一行**；回答不得出现简报里没有的关系词；
   - 「我 30 到 40 岁那步大运怎么样」→ `target_dayun` 解析、**两步大运都进简报岁运段**、流年扩到覆盖区间、回答聚焦该两步；
   - 「第 11 步大运怎么样」→ 初始盘（统一 12 步后）能命中，扩盘正常；
   - 未交大运年轻命例「我现在怎么样」→ 命盘岁运段为童限期占位、无干戈空关系（v3 修订 B 的冒烟）；
   - 「你好」/「什么是伤官」→ **未**注入任何新段（零开销回归）。

## 五、风险与回滚

| 风险 | 处置 |
| --- | --- |
| prompt 变长导致时延/成本上升 | 仅 `needs_chart` 场景注入；简报 ≤700 字、岁运关系 ≤600/300 字、流年行 ≤12、流月 ≤2 行，**总增量 ≤ ~1600 字**；`naming/auspicious/theory/chitchat` 零注入 |
| 领域映射表与 expertise_prompt 内容重复 | 分工明确：expertise_prompt=知识要点，规程=分析顺序；规程只写顺序 + 一句领域侧重，不抄断法 |
| 新注入内容被 Reviewer 误判「脱离排盘事实」 | 简报要素全部来自 `chart` 与复用函数，天然一致；不动维度 9 白名单；正则层不校岁运 |
| `build_repair_messages` 漏改导致修复后退化 | Step 9 第 5 点单列（含 skip 判定与 build_messages 对齐），进单测 |
| **appearance 漏映射导致身材样貌退回平铺** | Step 2 映射表已补 appearance 行，进入 Step 12 单测 + 冒烟 |
| **童限期岁运关系全空** | Step 1 以当年小运作岁柱 + 置位占位，进单测 + 冒烟 |
| **hits_yongshen 粗分类误伤** | 维度 11 不含 hits_yongshen（仅干支关系类），防新增误杀源 |
| 神煞名与产出集合不一致筛空 | 单测以 `shensha_calc._compute_shensha` 实际产出做交叉校验（锚点修正） |
| 流月干支 LLM 说错但检不出 | 本次不校验（防误杀），冒烟统计误报率后决定是否进维度 11 |
| 大运 12 步统一后旧库/旧会话 10 步盘 | 只影响新挂盘；旧数据读出仍 10 步，功能不受影响（resolve 找不到第 11-12 步时静默降级为平铺事实） |

回滚：全部改动集中在 2 个新文件 + 12 个既有文件；`QuestionIntent` 新字段有默认值、`build_domain_brief` 未映射领域返回空串，**关掉注入只需让 `compact_facts` 不拼两段新内容**（其余改动无副作用）；大运步数统一可单独回退（三处常量）。

## 六、本次不做（避免范围失控）

- 不做 Agentic 多轮工具循环（已选预计算路线）。
- 不把推演过程对用户可见，保持「不输出 ReAct 过程」硬约束。
- 不在算法层写合化、调候、大运破格的自动判定（既有原则：交 LLM 推理层）。
- **流月×原局关系、流日**不进对话路径（流月只注干支事实行；关系维度下轮按冒烟数据决定）。
- 不改 `knowledge_docs/` 任何文件名与内容（CI 硬编码）。
- 不新增前端字段（纯后端；小程序展示「领域简述」另开任务）。
- 合婚对方盘不做投影/岁运关系（只本方盘）。
- **年龄虚岁/周岁不换算**（用户先看盘指认，`resolve_target_dayuns` 直接按虚岁区间交集）。

## 七、涉及文件清单

**新增**

- `backend/app/domain/yun_relations.py`
- `backend/app/domain/domain_brief.py`
- `backend/tests/test_yun_relations.py`
- `backend/tests/test_domain_brief.py`

**修改**

- `backend/app/domain/bazi_engine.py`（公共符号重导出）
- `backend/app/agent/prompts.py`（`DOMAIN_STEP_FOCUS` 含 appearance / `DOMAIN_PROCEDURE_TEMPLATE` / `domain_sysprompt` / `REVIEWER_SYSTEM` 维度 11）
- `backend/app/agent/workflow/workflow_models.py`（`QuestionIntent.target_dayun`）
- `backend/app/agent/workflow/xianzhi_workflow.py`（`_decompose_query`）
- `backend/app/agent/workflow/workflow_support.py`（`classify_question` 兜底 + `build_chart_context` 大运 12）
- `backend/app/agent/workflow/workflow_retrieval.py`（`extend_chart_if_needed` 大运感知）
- `backend/app/agent/workflow/workflow_messages.py`（主改动：fact_block 流年选择 / compact_facts 注入 gate / build_sui_section / build_repair_messages 对齐）
- `backend/app/agent/workflow/workflow_workers.py`（Reviewer `sui_text` 参数 + 维度 11 范围）
- `backend/app/agent/xianzhi_langgraph.py`（check_node / repair_node 传 `sui_text`）
- `backend/app/tools/bazi.py`（4 工具增强 + `bazi_dayun` 默认 12 + `bazi_liunian` cache key）
- `backend/app/db/user_records.py`（大运 10 → 12）
- `backend/tests/test_xianzhi_workflow.py`（补断言）