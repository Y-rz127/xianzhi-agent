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
