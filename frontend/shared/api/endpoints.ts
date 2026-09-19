/**
 * 后端接口端点与请求参数构造（纯逻辑，不含任何传输实现）。
 *
 * R11 共享 API 层：后端路由前缀 /api/ai，路径集中在此维护，
 * 避免 Web/小程序两端各自硬编码导致漂移。
 */
import type { BaziProfile, ChartCase, HehunParams } from './types'

export const EP = {
  CHAT_SYNC: '/ai/xianzhi/chat/sync',
  CHAT_STREAM: '/ai/xianzhi/chat',
  CHART: '/ai/xianzhi/chart',
  /** 按点选的大运/流年/流月现算「岁运分析 / 原局分析」六栏 */
  RELATIONS: '/ai/xianzhi/relations',
  /** 命理 K 线：确定性运势评分 → 年蜡烛 + 大运带（一次请求一个维度） */
  KLINE: '/ai/xianzhi/kline',
  KLINE_ANNOTATION: '/ai/xianzhi/kline/annotation',
  KLINE_RESONANCE: '/ai/xianzhi/kline/resonance',
  KLINE_FEEDBACK: '/ai/xianzhi/kline/feedback',
  KLINE_FEEDBACK_STATS: '/ai/xianzhi/kline/feedback/stats',
  /** 事件标注（回测的 ground truth）：/events 增删查，/events/stats 总览 */
  KLINE_EVENTS: '/ai/xianzhi/kline/events',
  KLINE_EVENT_STATS: '/ai/xianzhi/kline/events/stats',
  /** 回测：命中率 / 随机基线 / lift / 置信区间 */
  KLINE_BACKTEST: '/ai/xianzhi/kline/backtest',
  /** 合盘关系事件（共振权重的 ground truth）：一对人·某年顺不顺 */
  KLINE_PAIR_EVENTS: '/ai/xianzhi/kline/pair-events',
  KLINE_PAIR_EVENT_STATS: '/ai/xianzhi/kline/pair-events/stats',
  /** 合盘回测：命中率 + 逐项 term 诊断（反推权重的输入） */
  KLINE_PAIR_BACKTEST: '/ai/xianzhi/kline/pair-backtest',
  HEHUN: '/ai/xianzhi/hehun',
  FULL_REPORT: '/ai/xianzhi/full_report',
  REPORT_PDF: '/ai/xianzhi/report',
  FULL_REPORT_PDF: '/ai/xianzhi/full_report_pdf',
  INFER_DATES: '/ai/xianzhi/bazi/infer-dates',
  CACHE_STATS: '/ai/xianzhi/cache_stats',
  HEALTH: '/ai/health',
  CASES: '/ai/xianzhi/cases',
  SESSIONS: '/ai/xianzhi/sessions',
  SESSIONS_MINE: '/ai/xianzhi/sessions/mine',
  PROFILES: '/ai/profiles',
  FAVORITES: '/ai/favorites',
  AI_INTERPRETATION_RECORDS: '/ai/ai_interpretation_records',
  FEEDBACK: '/ai/feedback',
  FEEDBACK_ANSWER: '/ai/feedback/answer',
  ME: '/ai/me',
  AUTH_REGISTER: '/ai/auth/register',
  AUTH_LOGIN: '/ai/auth/login',
  AUTH_WX_LOGIN: '/ai/auth/wx-login',
  AUTH_ME: '/ai/auth/me',
} as const

/** 把参数对象编码为 query string（跳过 undefined/null/空串），不含前导 '?'。 */
export function buildQueryString(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.keys(params)
    .filter((k) => params[k] !== undefined && params[k] !== null && params[k] !== '')
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(String(params[k]))}`)
  return entries.join('&')
}

/** 排盘接口 query 参数 */
export function chartQuery(birthTime: string, gender: string, sect = 2, yunSect = 1, longitude?: number): string {
  return buildQueryString({
    birth_time: birthTime,
    gender,
    sect,
    yun_sect: yunSect,
    ...(longitude ? { longitude } : {}),
  })
}

/** 合婚接口 query 参数 */
export function hehunQuery(a: HehunParams): string {
  return buildQueryString({
    birth_time_a: a.birthTimeA,
    gender_a: a.genderA,
    birth_time_b: a.birthTimeB,
    gender_b: a.genderB,
    sect: a.sect ?? 2,
    longitude_a: a.longitudeA,
    longitude_b: a.longitudeB,
  })
}

/** 命例保存/更新请求体（camelCase 前端模型 → snake_case 后端契约） */
export function chartCaseBody(payload: Partial<ChartCase>, extra?: { bio?: string; analysis?: string; keypoints?: string }): Record<string, any> {
  const body: Record<string, any> = {
    name: payload.name,
    birth_time: payload.birthTime,
    gender: payload.gender,
    tags: payload.tags,
    chart_data: payload.chartData,
  }
  if (extra?.bio) body.bio = extra.bio
  if (extra?.analysis) body.analysis = extra.analysis
  if (extra?.keypoints) body.keypoints = extra.keypoints
  return body
}

/** 八字档案请求体（创建/更新共用） */
export function profileBody(p: Partial<BaziProfile>): Record<string, any> {
  return {
    name: p.name,
    relation: p.relation,
    birth_time: p.birthTime,
    gender: p.gender,
    sect: p.sect ?? 2,
    yun_sect: p.yunSect ?? 1,
    chart_data: p.chartData,
  }
}
