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
  TAROT_RECORDS: '/ai/tarot_records',
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
