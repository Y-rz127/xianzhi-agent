/**
 * 共享数据模型：Web（frontend/）与小程序（uniapp/）共用的后端接口类型定义。
 *
 * R11 共享 API 层：本目录为纯 TypeScript，不依赖任何平台 API
 * （fetch / uni.request / DOM 均不可用），由各端注入自己的传输实现。
 * 字段取两端原有定义的并集，后端契约以 app/api 为准。
 */

/* ============ 排盘结构化数据 ============ */

export interface Pillar {
  name: string
  ganzhi: string
  nayin: string
  gan?: string
  zhi?: string
  ganWuxing?: string
  zhiWuxing?: string
  xunkong?: string
  hiddenStems?: string[]
  shishenGan?: string
  shishenZhi?: string[]
  changsheng?: string
  zizuo?: string
}

export interface WuxingItem { name: string; count: number; color: string }

export interface DayunItem {
  /** 大运序号，与 xipan.dayun[].index 对齐（0 为童限，chart.dayun 不含该项） */
  index?: number
  year: string
  ganzhi: string
  startAge: number
  startYear: number
  endAge?: number
  endYear?: number
  xunkong?: string
  shishenGan?: string
  gan?: string
  zhi?: string
  hiddenStems?: string[]
  shishenZhi?: string[]
  changsheng?: string
  shensha?: ShenshaItem[]
  liunian?: LiuNianItem[]
}

export interface LiuNianItem {
  year: string
  ganzhi: string
  age?: number
  dayun?: string
  dayunStartYear?: number
  dayunEndYear?: number
  xunkong?: string
  shishenGan?: string
  gan?: string
  zhi?: string
  hiddenStems?: string[]
  shishenZhi?: string[]
  changsheng?: string
  shensha?: ShenshaItem[]
}

export interface ShenshaItem { name: string; description: string; pillar?: string }

export interface ChartAnalysis {
  day_master?: string
  day_master_wuxing?: string
  strength?: string
  strength_score?: number
  useful_hint?: string
  tenGods?: Record<string, number>
  exposedStems?: string[]
  rootedStems?: string[]
  combinations?: string[]
  clashes?: string[]
  harms?: string[]
  punishments?: string[]
  threeAssemblies?: string[]
  season?: string
  adjustment?: string
  patternHint?: string
  confidence?: number
}

/* ============ 细盘（时间层级：起运→大运→流年→流月） ============ */

/** 起运信息：交运时间与节气 */
export interface XiPanQiYun {
  /** 出生后X年X月X天X时起运 */
  after: string
  /** 交运公历时刻 */
  startDate: string
  /** 交运年天干（逢X干之年交运） */
  gan: string
  /** 出生前一个节（顺排）/后一个节（逆排）名 */
  jieqi: string
  /** 距节气天数 */
  daysAfterJieqi: number
  /** 大运顺排/逆排 */
  direction: string
}

/** 细盘大运项（含藏干十神与星运） */
export interface XiPanDaYun {
  index: number
  ganzhi: string
  shishen: string
  startAge: number
  endAge: number
  startYear: number
  endYear: number
  xunkong: string
  hiddenStems: string[]
  shishenZhi: string[]
  changsheng: string
}

/** 细盘流年项（含所属大运 index 与小运） */
export interface XiPanLiuNian {
  year: number
  ganzhi: string
  age: number
  dayunIndex: number
  shishen: string
  /** 地支藏干十神（本气在前），横条展示取 [0] */
  shishenZhi?: string[]
  /** 星运：日主对该流年支的十二长生 */
  changsheng?: string
  xunkong: string
  xiaoyun: string
}

/** 细盘流月项（按节气切分，每年 12 个节） */
export interface XiPanLiuYue {
  year: number
  zhi: string
  jieqi: string
  date: string
  ganzhi: string
  shishen: string
  // 去重下发：地支十神/星运查 monthMeta[zhi]，神煞名查 liuyueShensha[ganzhi]，说明查 shenshaDict[name]
}

/** 月支 → 地支十神 / 星运（两者都是月支的纯函数，12 条一份即可） */
export interface XiPanMonthMeta {
  shishenZhi: string[]
  changsheng: string
}

/** 干支 → 命盘列字段（十神/藏干/星运/自坐/旬空/纳音，均为「干支 + 日主」的纯函数） */
export interface XiPanGanzhiMeta {
  shishen: string
  gan: string
  zhi: string
  hiddenStems: string[]
  shishenZhi: string[]
  changsheng: string
  zizuo: string
  xunkong: string
  nayin: string
}

/** 当前活动大运/流年/流月（童限期 dayunLabel 为小运、dayun 为当年小运干支） */
export interface XiPanCurrent {
  year: number
  age: number
  dayunIndex: number
  dayun: string
  dayunLabel: string
  dayunShishen: string
  liunian: string
  liunianShishen: string
  liunianXunkong: string
  liuyue: string
  liuyueShishen: string
  liuyueJieqi: string
  liuyueDate: string
}

/** 快照单列（流年/大运/四柱共 6 列） */
export interface XiPanColumn {
  name: string
  ganzhi: string
  shishen: string
  gan: string
  zhi: string
  hiddenStems: string[]
  shishenZhi: string[]
  changsheng: string
  zizuo: string
  xunkong: string
  nayin: string
}

/** 当前大运+流年叠加四柱的六列快照 */
export interface XiPanSnapshot {
  columns: XiPanColumn[]
  label: string
}

/** 月令五行旺相休囚 */
export interface XiPanWuxingState { name: string; state: string }

/** 人元司令分野 */
export interface XiPanSiLing { stem: string; detail: string }

/** 干支关系一组：岁运（大运·流年·流月）或原局四柱 */
export interface XiPanRelationGroup {
  /** 岁运栏为「壬申 · 丙午 · 丙申」，原局栏为四柱干支 */
  label: string
  /** 天干栏：只列五合与四冲（甲庚/乙辛/丙壬/丁癸），如「丁壬合木」「丙壬冲」 */
  gan: string[]
  /** 地支栏：三合/半合/拱局/会方/六合/六冲/六害/六破/三刑/自刑 */
  zhi: string[]
  /** 整柱栏：伏吟/反吟（岁运）或盖头/截脚（原局） */
  zhu: string[]
}

/** 岁运分析与原局分析 */
export interface XiPanRelations {
  suiyun: XiPanRelationGroup
  yuanju: XiPanRelationGroup
}

export interface XiPanData {
  qiyun: XiPanQiYun
  current: XiPanCurrent
  dayun: XiPanDaYun[]
  liunian: XiPanLiuNian[]
  liuyue: XiPanLiuYue[]
  /** 流月干支 → 神煞名列表（月干支 60 个一循环，按干支去重下发） */
  liuyueShensha?: Record<string, string[]>
  /** 流年干支 → 神煞名列表（覆盖全部流年，切到任何一步大运的十年都取得到） */
  liunianShensha?: Record<string, string[]>
  /**
   * 小运干支 → 神煞名列表（与 liunianShensha 同一「运柱神煞」口径）。
   * 童限期细盘表把「大运」列换成小运显示，那一列的神煞取这里。
   */
  xiaoyunShensha?: Record<string, string[]>
  /** 60 干支 → 命盘列字段，供前端按点选的大运/流年重拼命盘大表 */
  ganzhiMeta?: Record<string, XiPanGanzhiMeta>
  /** 神煞名 → 说明，配合 liuyueShensha 解析流月神煞 */
  shenshaDict?: Record<string, string>
  /** 月支 → 地支十神/星运，配合 liuyue[].zhi 解析 */
  monthMeta?: Record<string, XiPanMonthMeta>
  snapshot: XiPanSnapshot
  relations?: XiPanRelations
  wuxingState: XiPanWuxingState[]
  siling: XiPanSiLing
  note?: string
}

export interface ChartData {
  birth?: Record<string, any>
  pillars: Pillar[]
  wuxing: WuxingItem[]
  dayun: DayunItem[]
  liunian: LiuNianItem[]
  shensha: ShenshaItem[]
  analysis?: ChartAnalysis
  startYun?: Record<string, any>
  warnings?: string[]
  chartText?: string
  analysisText?: string
  dayunText?: string
  liunianText?: string
  mingGong?: string
  shenGong?: string
  taiYuan?: string
  xipan?: XiPanData
}

export interface BaziCandidate { birth_time: string; ganzhi: string; shi_chen: string }

/* ============ 命理 K 线（确定性运势评分 → 年蜡烛） ============ */

/** 取象维度；key 与后端 `fortune_score.DIMENSIONS`、既有领域 key 对齐 */
export type KlineDimension = 'comprehensive' | 'career' | 'wealth' | 'love' | 'health' | 'study'

export interface KlineDimensionOption {
  key: KlineDimension
  label: string
  note: string
}

/** 一根年蜡烛。open 承接上年 close，故相邻蜡烛首尾相接 */
export interface KlineCandle {
  year: number
  /** 虚岁 */
  age: number
  ganzhi: string
  /** 所在大运干支 */
  dayun: string
  /** open/close/high/low 同域：后端 SCORE_MIN–SCORE_MAX，即 0–100 分。
      前端画布坐标域必须覆盖这一整段，取窄了高分年份的影线会被裁平 */
  open: number
  close: number
  high: number
  low: number
  volume: number
  /** 该年 12 个节气月分数；默认不返回，include_months=1 才有 */
  monthScores?: number[]
  /** 命中的干支关系（合/冲/刑/害/破、伏吟、反吟等） */
  relations: string[]
  relationAdj: number
  /** 关系带来的振幅放大；冲主变动、与喜忌无关 */
  volatility: number
  isDayunStart: boolean
  /** close >= open，前端按国内习惯涨红跌绿着色 */
  isUp: boolean
}

/** 十年一段的大运带，供前端画宏观背景与均线 */
export interface KlineDayunBand {
  index: number
  ganzhi: string
  startYear: number
  endYear: number
  startAge: number
  endAge: number
  shishenGan: string
}

export interface KlineFavor {
  dayMaster: string
  dayMasterWuxing: string
  strength: string
  specialPattern: string
  favor: Record<string, number>
  mostFavored: string
  mostOpposed: string
  /** 病神代号（如 resource_dominant）；无病为空串。喜忌为何这样定，看这里 */
  ailment: string
  /** 病神的一句话依据，前端直接显示、不自行解释命理口径 */
  ailmentNote: string
}

export interface KlineMeta {
  startYear: number | null
  endYear: number | null
  yearCount: number
  maxAge: number
  /** 请求时声明的覆盖步数（0=没启用，按 maxAge 截断）。用于核对图与批注是不是同一段 */
  maxDayun: number
  dimension: KlineDimension
  dimensionLabel: string
  /** 该维度的一句话取象说明，前端直接显示、不自行解释命理口径 */
  dimensionNote: string
  /** 该维度的十神侧重（五行 → 系数，均值归一为 1）；综合维度为空表 */
  dimensionEmphasis: Record<string, number>
  availableDimensions: KlineDimensionOption[]
  kScore: number
  weightDayun: number
  weightLiunian: number
  weightLiuyue: number
  note: string
}

export interface KlineData {
  favor: KlineFavor
  candles: KlineCandle[]
  dayunBands: KlineDayunBand[]
  meta: KlineMeta
}

/** 批注粒度：overview=当前大运与全期极值（进页面即取）；year=指定流年（点了才取） */
export type KlineAnnotationScope = 'overview' | 'year'

export interface KlineAnnotation {
  /** 生成成功且通过事实校验。false 时 text 必为空串 */
  ok: boolean
  /** 批注正文；校验不过时为 '' —— 前端应显示提示而不是空行 */
  text: string
  /** 是否通过 check_facts 事实校验 */
  factsOk: boolean
  /** 未通过时的具体问题 */
  issues: string[]
  scope: KlineAnnotationScope
  year?: number | null
  /** 「当下」锚定年：overview 讲的是这一年的当前大运 */
  anchorYear?: number | null
  /** 该批注涉及的年份（用于图上高亮） */
  years?: number[]
  dimension: KlineDimension
  cached: boolean
}

/* ---- 合盘共振线 ---- */

/** 双盘日主五行关系：相生互补 / 同类 / 相克 */
export type KlineResonanceKind = '相生' | '同类' | '相克' | ''

/** 共振强度档位（由后端 verdict_of 给出，前端只负责上色） */
export type KlineResonanceVerdict = '强共振' | '偏顺' | '平稳' | '偏逆' | '背离'

/** 流年干支对双方喜忌的一致度 */
export type KlineResonanceAlign = '双利' | '双损' | '一利一损' | '无明显作用'

export interface KlineResonanceBase {
  relationKind: KlineResonanceKind
  complement: {
    aNeeds: string
    bCovers: boolean
    bNeeds: string
    aCovers: boolean
  }
  dayZhi: { a: string; b: string; relation: string }
  /** 各项原始点（折合分之前），便于解释基线为何是这个分 */
  points: Record<string, number>
  /** 基线分 0-100：不随年份变的那部分 */
  score: number
}

export interface KlineResonanceYear {
  year: number
  ganzhi: string
  dayun: string
  /** 甲方该年收盘分 */
  scoreA: number
  scoreB: number
  isUpA: boolean
  isUpB: boolean
  /** 双方同比走向是否同号 */
  sameDirection: boolean
  moveGap: number
  align: { deltaA: number; deltaB: number; label: KlineResonanceAlign }
  palace: { a: string; b: string }
  /** 四项逐年修正的分值明细（trend/align/sync/palace），sum + 基线 = resonance */
  terms: Record<string, number>
  resonance: number
  verdict: KlineResonanceVerdict
}

export interface KlineResonanceMeta {
  startYear: number | null
  endYear: number | null
  yearCount: number
  maxAge: number
  dimension: KlineDimension
  dimensionLabel?: string
  meanScore: number | null
  peakYear: number | null
  troughYear: number | null
  weights: Record<string, number>
  /** 口径说明：权重是待校准先验，只应读作相对次序 */
  note: string
  availableDimensions?: KlineDimensionOption[]
}

export interface KlineResonance {
  base: KlineResonanceBase
  years: KlineResonanceYear[]
  meta: KlineResonanceMeta
  /** 两盘各自的喜忌摘要（后端顺带返回，省两次 /kline） */
  favorA: KlineFavor
  favorB: KlineFavor
  cached: boolean
}

/* ---- 反馈闭环 ---- */

export interface KlineFeedbackPayload {
  birthTime: string
  gender: string
  dimension: KlineDimension
  scope: KlineAnnotationScope
  year?: number
  /** 生成批注时的当前年（批注含「当前大运」类措辞，须留锚点） */
  anchorYear?: number
  /** 1-5 星认可度 */
  rating: number
  /** 与实际是否吻合；不确定留空 */
  accurate?: boolean | null
  comment?: string
  snapshot?: Record<string, unknown>
}

export interface KlineFeedbackResult {
  ok: boolean
  id: string
}

export interface KlineFeedbackStats {
  total: number
  avgRating: number | null
  accurateYes: number
  accurateNo: number
  /** 明确表过态的样本数；accurateRate 只对它计算 */
  decided: number
  accurateRate: number | null
  byDimension: { dimension: string; count: number; avgRating: number | null }[]
  byScope: { scope: string; count: number }[]
}

/* ---- 事件标注与回测（校准闭环的真相面） ---- */

/** 事件极性：1=吉 / 0=平 / -1=凶 */
export type KlinePolarity = 1 | 0 | -1

/** 事件领域。与评分维度对齐（general 用综合维度打分） */
export type KlineEventDomain = 'general' | 'career' | 'wealth' | 'love' | 'health' | 'study'

/** 回测的预测器：close=年末分（与页面同源，默认）；mean=12 月均值（更稳，作对照） */
export type KlinePredictor = 'close' | 'mean'

export interface KlineEventPayload {
  birthTime: string
  gender: string
  sect?: number
  yunSect?: number
  longitude?: number
  /** 命理年（立春换岁）。与 eventDate 至少给一个；都给则后端互相校验 */
  ganzhiYear?: number
  /** 原始公历日期 YYYY-MM-DD，用于推导命理年（1-2 月的事件必须走它） */
  eventDate?: string
  polarity: KlinePolarity
  domain?: KlineEventDomain
  /** 来源：传记 / 自述 / 案例库 / 人工 */
  source?: string
  note?: string
  caseId?: string
}

export interface KlineEventResult {
  ok: boolean
  id: string
  /** 后端确认的命理年（可能是由 eventDate 推出的，回填用它而不是本地推算） */
  ganzhiYear: number
}

export interface KlineEventItem {
  id: string
  birth_time: string
  gender: string
  sect: number
  yun_sect: number
  longitude: number | null
  ganzhiYear: number
  /** 原始公历日期；只记到年的事件为空串 */
  eventDate: string
  polarity: KlinePolarity
  domain: KlineEventDomain
  source: string
  note: string
  caseId: string
  createdAt: string | null
}

export interface KlineEventStats {
  total: number
  charts: number
  yearCount: number
  yearFrom: number | null
  yearTo: number | null
  byPolarity: { polarity: number; count: number }[]
  byDomain: { domain: string; count: number }[]
  byChart: {
    birthTime: string
    gender: string
    count: number
    yearFrom: number | null
    yearTo: number | null
  }[]
}

/**
 * 回测指标块。**必须与 randomBaseline 一并读**：
 * 三分类随机猜也有约 1/3；只有 ci95 下界高于基线才算有区分度。
 */
export interface KlineBacktestSummary {
  samples: number
  /** 实际有吉凶的样本数（排除实际为平） */
  decided: number
  hits: number
  hitRate: number | null
  /** 严格口径：只算实际有吉凶的样本，预测为平一律算错 */
  hitRateStrict: number | null
  randomBaseline: number | null
  randomBaselineStrict: number | null
  /** 恒猜最多一类的命中率，最朴素的那条杠 */
  majorityBaseline: number | null
  lift: number | null
  liftStrict: number | null
  ci95: [number, number] | null
  /** 仅总计块有：样本是否够 */
  ok?: boolean
  /** 仅总计块有：95% 区间下界是否高于随机基线 */
  significant?: boolean
}

export interface KlineBacktestMiss {
  chart: string
  year: number
  ganzhi: string
  pred: string
  truth: string
  score: number
  domain: string
  note: string
}

export interface KlineBacktest {
  dimension: string
  predictor: KlinePredictor
  minSamples: number
  charts: number
  yearFrom: number | null
  yearTo: number | null
  /** 回测窗口按多少虚岁固定切（与 yearFrom/yearTo 不是一回事） */
  ageSpan: number
  /** 各盘/各对预测区间的并集开始年；空库时为 null */
  spanFrom: number | null
  spanTo: number | null
  events: { total: number; used: number; unmatched: number; invalid: number; duplicate: number }
  unmatchedYears: { chart: string; ganzhiYear: number; note: string }[]
  summary: KlineBacktestSummary
  byDomain: (KlineBacktestSummary & { domain: string })[]
  byDimension: (KlineBacktestSummary & { dimension: string })[]
  byChart: (KlineBacktestSummary & { chart: string })[]
  /** 错判样例（惊讶度由高到低），供人工复盘 */
  misses: KlineBacktestMiss[]
  warnings: string[]
  note: string
}

/* ---- 合盘关系事件与合盘回测（共振权重的唯一校准数据源） ----
 *
 * 为什么与单盘事件分开：单盘事件校准的是「这个人这年过得好不好」，
 * 共振权重只能由「这两人这年顺不顺」校准。两者主键不同（单盘=盘×年×领域；
 * 关系事件没有领域切片 —— 同一年两人可以一个升职一个生病，但"我们俩这一年"
 * 只有一个答案），硬合成一张表会让"哪些列该为空"变成隐性契约。
 */

/** 关系类型：只是"这分数该怎么读"的解释框架与复盘切片维度，**不参与打分** */
export type KlineRelation = '夫妻' | '恋人' | '亲子' | '同事' | '朋友' | '合作' | '其他'

export interface KlinePairEventPayload {
  birthTimeA: string
  genderA: string
  birthTimeB: string
  genderB: string
  sect?: number
  yunSect?: number
  longitudeA?: number
  longitudeB?: number
  /** 命理年（立春换岁）。与 eventDate 至少给一个；都给则后端互相校验 */
  ganzhiYear?: number
  /** 原始公历日期 YYYY-MM-DD，用于推导命理年（1-2 月的事件必须走它） */
  eventDate?: string
  /** **关系本身**的吉凶（1=顺 / 0=平 / -1=逆），不是某一方的个人运势 */
  polarity: KlinePolarity
  relation?: KlineRelation | ''
  source?: string
  note?: string
}

/** 与单盘事件同一形状：ok + id + 后端确认的命理年 */
export type KlinePairEventResult = KlineEventResult

export interface KlinePairEventItem {
  id: string
  birthTimeA: string
  genderA: string
  birthTimeB: string
  genderB: string
  sect: number
  yunSect: number
  longitudeA: number | null
  longitudeB: number | null
  ganzhiYear: number
  /** 原始公历日期；只记到年的事件为空串 */
  eventDate: string
  polarity: KlinePolarity
  /** 空串 = 未标注关系类型 */
  relation: string
  source: string
  note: string
  createdAt: string | null
}

export interface KlinePairEventStats {
  total: number
  /** 涉及多少对人 */
  pairs: number
  yearCount: number
  yearFrom: number | null
  yearTo: number | null
  byPolarity: { polarity: number; count: number }[]
  /** 空 relation 在服务端已折叠成「未标注」 */
  byRelation: { relation: string; count: number }[]
  byPair: {
    birthTimeA: string
    genderA: string
    birthTimeB: string
    genderB: string
    count: number
    yearFrom: number | null
    yearTo: number | null
  }[]
}

/**
 * 逐项诊断：每个 term 在"实际吉"的年份是不是真的更高。
 *
 * 这是**反推权重的直接依据**，比总命中率有用得多：总命中率只能说"合起来不准"，
 * 逐项均值差能指出是哪一项在帮倒忙。`delta <= 0` 就是该项（或其符号）与现实相反。
 */
export interface KlineTermDiagnostic {
  term: string
  meanUp: number | null
  meanDown: number | null
  /** meanUp - meanDown；样本不足时为 null */
  delta: number | null
  /** delta > 0 即方向正确；样本不足时为 null */
  signOk: boolean | null
  samplesUp: number
  samplesDown: number
}

export interface KlinePairBacktest {
  dimension: string
  /** 合盘只有一个预测源（共振分），恒为 resonance */
  predictor: string
  minSamples: number
  pairs: number
  yearFrom: number | null
  yearTo: number | null
  /** 回测窗口按多少虚岁固定切（与 yearFrom/yearTo 不是一回事） */
  ageSpan: number
  /** 各对预测区间的并集开始年；空库时为 null */
  spanFrom: number | null
  spanTo: number | null
  events: { total: number; used: number; unmatched: number; invalid: number; duplicate: number }
  unmatchedYears: { pair: string; ganzhiYear: number; note: string }[]
  summary: KlineBacktestSummary
  byRelation: (KlineBacktestSummary & { relation: string })[]
  byPair: (KlineBacktestSummary & { pair: string })[]
  termDiagnostics: KlineTermDiagnostic[]
  misses: {
    pair: string
    year: number
    ganzhi: string
    pred: string
    truth: string
    score: number
    relation: string
    note: string
  }[]
  warnings: string[]
  note: string
}

/* ============ 命例 / 会话 ============ */
export interface ChartCase {
  id: string
  name: string
  tags: string[]
  birthTime: string
  gender: string
  createdAt: string
  updatedAt: string
  bazi?: string
  chartData?: ChartData
  bio?: string
  analysis?: string
  keypoints?: string
}

export interface ChatSession {
  id: string
  title: string
  lastMessage: string
  lastTime: string
  messageCount: number
}

export interface SessionMessage { role: 'user' | 'assistant'; content: string; time?: string }

export interface SessionBirthInfo { time: string | null; gender: string | null }

/* ============ 账号 / 档案 / 收藏 / 塔罗 / 反馈 ============ */

export interface XzUser { id: string; nickname: string; avatar: string }

export interface BaziProfile {
  id: string
  name: string
  relation: string
  birthTime: string
  gender: string
  sect: number
  yunSect: number
  chartData?: ChartData
  createdAt: string
}

export interface FavoriteCase {
  caseId: string
  name: string
  tags: string[]
  birthTime: string
  gender: string
  chartData?: ChartData
  createdAt: string
}

/** 塔罗牌张（与抽牌页 DrawnCard 对齐；后端透传可能携带额外字段） */
export interface TarotCard {
  name?: string
  nameEn?: string
  emblem?: string
  [key: string]: unknown
}

export interface AnswerFeedbackPayload {
  conversation_id: string
  question?: string
  answer: string
  rating: 'up' | 'down'
  reason?: string
  chart_snapshot?: Record<string, unknown>
}

export interface HehunParams {
  birthTimeA: string
  genderA: string
  birthTimeB: string
  genderB: string
  /** 日柱流派：1=早子时（子时换日），2=晚子时（默认） */
  sect?: number
  /** 出生地经度（°E），用于真太阳时校正 */
  longitudeA?: number
  longitudeB?: number
}

/* ============ 聊天参数 ============ */

export interface ChatOptions {
  birth_time?: string
  gender?: string
  birth_place?: string
  sect?: number
  yun_sect?: number
}
