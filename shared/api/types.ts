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

export interface TarotRecord {
  id: string
  spread: string
  question: string
  cards: TarotCard[]
  interpretation: string
  createdAt: string
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
