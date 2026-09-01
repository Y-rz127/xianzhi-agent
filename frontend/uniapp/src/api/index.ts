/**
 * API 请求层 - 基于 uni.request，对齐后端 FastAPI 接口
 * 后端路由前缀: /api/ai
 * 基址来自 config.ts，运行时可调用 setConfig({ apiBase }) 覆盖（小程序切局域网 IP 用）
 */
import { getConfig } from '@/config'
import { getToken } from '@/utils/storage'

// R11 共享 API 层：数据模型/文本解析器/端点常量与 Web 端共用，统一在仓库根 shared/api 维护
export type {
  AnswerFeedbackPayload, BaziProfile, ChartAnalysis, ChartCase, ChartData,
  ChatSession, DayunItem, FavoriteCase, HehunParams, LiuNianItem, Pillar,
  SessionMessage, ShenshaItem, TarotRecord, WuxingItem, XzUser,
} from '@shared/api'
export type { SessionBirthInfo as BirthInfo } from '@shared/api'
export { parseDayun, parsePillars, parseShensha, parseWuxing } from '@shared/api'
import type {
  AnswerFeedbackPayload, BaziProfile, ChartCase, ChartData, ChatSession,
  FavoriteCase, HehunParams, SessionMessage, TarotCard, TarotRecord, XzUser,
} from '@shared/api'
import type { SessionBirthInfo } from '@shared/api'
import { EP, profileBody } from '@shared/api'

function getApiBase(): string {
  return getConfig().apiBase
}

export const API_BASE = getConfig().apiBase

// 配置变更后重新读取基址（downloadPdf 等场景使用）
export function refreshApiBase() {
  return getConfig().apiBase
}

/** 统一请求封装 */
function request<T = any>(options: UniApp.RequestOptions): Promise<T> {
  return new Promise((resolve, reject) => {
    const token = getToken()
    const header = { ...(options.header || {}) }
    if (token) header['Authorization'] = 'Bearer ' + token
    uni.request({
      ...options,
      header,
      url: getApiBase() + options.url,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data as T)
        } else {
          // any 理由：后端错误响应结构未知，仅安全提取 detail 字段
          const detail =
            typeof res.data === 'object' && res.data !== null && 'detail' in res.data
              ? (res.data as any).detail
              : `请求失败 ${res.statusCode}`
          reject(new Error(String(detail)))
        }
      },
      fail: (err) => reject(new Error(err.errMsg || '网络错误')),
    })
  })
}

/** 给 URL 追加用户 token（部分接口从 query 读取 token） */
function withToken(url: string): string {
  const token = getToken()
  if (!token) return url
  return url + (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token)
}

function get<T = any>(url: string, params?: Record<string, any>): Promise<T> {
  let qs = ''
  const merged: Record<string, any> = { ...(params || {}) }
  const token = getToken()
  if (token) merged['token'] = token
  if (Object.keys(merged).length) {
    const entries = Object.keys(merged)
      .filter((k) => merged[k] !== undefined && merged[k] !== null && merged[k] !== '')
      .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(String(merged[k]))}`)
    if (entries.length) qs = '?' + entries.join('&')
  }
  return request<T>({ url: url + qs, method: 'GET' })
}

// any 理由：通用传输层，响应/请求体类型由调用方泛型 T 约束，此处无法静态推导
function post<T = any>(url: string, data?: any): Promise<T> {
  return request<T>({ url: withToken(url), method: 'POST', data, header: { 'Content-Type': 'application/json' } })
}

export const transcribeAudio = (audio: string, format = 'mp3') =>
  post<{ text: string; model: string }>('/ai/asr/transcribe', { audio, format })

export interface LiuYaoResult { method: string; createdAt: string; lines: Array<{ index: number; value: number; yang: boolean; moving: boolean }>; movingLines: number[]; summary: string; original: { name: string; upper: { name: string; symbol: string }; lower: { name: string; symbol: string } }; changed: { name: string; upper: { name: string; symbol: string }; lower: { name: string; symbol: string } } | null }
export const castLiuYao = (method: 'coins' | 'numbers' | 'time', numbers?: number[]) => post<LiuYaoResult>('/ai/liuyao/cast', { method, numbers })
export const interpretLiuYao = (question: string, result: LiuYaoResult) => post<{ interpretation: string }>('/ai/liuyao/interpret', { question, result })

/* ============ 每日黄历（只读，无需登录） ============ */

export interface HuangLiHour { zhi: string; range: string; tian_shen: string; luck: string; yi: string[]; ji: string[]; chong: string }
export interface HuangLiDay {
  date: string; solar: string
  lunar: { year_gz: string; month_gz: string; day_gz: string; text: string }
  festivals: string[]; jieqi: string; yi: string[]; ji: string[]
  chong: { desc: string; sha: string }
  pengzu: { gan: string; zhi: string }
  taishen: string; nayin: string
  jishen: string[]; xiongsha: string[]
  positions: { cai: string; xi: string; fu: string; yang_gui: string; yin_gui: string; five_ghost: string; sheng_men: string; si_men: string }
  tian_shen: { name: string; type: string; luck: string }
  zhixing: string; nine_star: string; xiu: { name: string; luck: string }
  hours: HuangLiHour[]
}
export interface HuangLiRangeDay {
  date: string; weekday: string; lunar_day: string
  festivals: string[]; jieqi: string; yi_top5: string[]; ji_top3: string[]; tianshe: boolean
}
export interface HuangLiZejiDay { date: string; day_gz: string; chong: string; jishen: string[]; tian_shen: string; stars: number; note: string }

export const getHuangLiDay = (date?: string) => get<HuangLiDay>('/ai/huangli/day', date ? { date } : undefined)
export const getHuangLiRange = (start: string, end: string) =>
  get<{ days: HuangLiRangeDay[] }>('/ai/huangli/range', { start, end }).then((r) => r.days)
export const getHuangLiZeji = (yi: string, start: string, end: string, avoidChong = '') =>
  get<{ yi: string; days: HuangLiZejiDay[] }>('/ai/huangli/zeji', {
    yi, start, end, avoid_chong: avoidChong || undefined,
  }).then((r) => r.days)
export const getHuangLiItems = () => get<{ items: string[] }>('/ai/huangli/items').then((r) => r.items)

/* ============ 紫微斗数（排盘 + 点宫详情 + AI 简批，只读排盘无需登录） ============ */

export interface ZiWeiStar { name: string; type: string; brightness: string; mutagen: string }
export interface ZiWeiDecadal { range: number[]; heavenly_stem: string; earthly_branch: string }
export interface ZiWeiPalace {
  index: number; name: string; heavenly_stem: string; earthly_branch: string; is_body: boolean
  major_stars: ZiWeiStar[]; minor_stars: ZiWeiStar[]; adjective_stars: ZiWeiStar[]
  changsheng12: string; boshi12: string; jiangqian12: string; suiqian12: string
  decadal: ZiWeiDecadal | null; ages: number[]
}
export interface ZiWeiChart {
  gender: string; solar_date: string; lunar_date: string
  time_index: number; time_name: string; time_range: string
  sign: string; zodiac: string
  earthly_branch_of_soul: string; earthly_branch_of_body: string
  soul_star: string; body_star: string; five_elements_class: string
  four_pillars: { yearly: string; monthly: string; daily: string; hourly: string }
  palaces: ZiWeiPalace[]
}
export interface ZiWeiCastParams {
  date: string; time_index: number; gender: string; calendar?: 'solar' | 'lunar'; leap?: boolean
}

export const getZiWeiChart = (p: ZiWeiCastParams) =>
  get<ZiWeiChart>('/ai/ziwei/chart', {
    date: p.date, time_index: p.time_index, gender: p.gender,
    calendar: p.calendar || 'solar', leap: p.leap || undefined,
  })
export const interpretZiWei = (p: ZiWeiCastParams & { focus?: string }) =>
  post<{ text: string }>('/ai/ziwei/interpret', {
    date: p.date, time_index: p.time_index, gender: p.gender,
    calendar: p.calendar || 'solar', leap: p.leap || false, focus: p.focus || '',
  }).then((r) => r.text)

function put<T = any>(url: string, data?: any): Promise<T> {
  return request<T>({ url: withToken(url), method: 'PUT', data, header: { 'Content-Type': 'application/json' } })
}

function del<T = any>(url: string): Promise<T> {
  return request<T>({ url: withToken(url), method: 'DELETE' })
}

/* ============ 同步聊天（小程序兜底，无流式） ============ */

export interface ChatResult { result?: string; error?: string }

export const chatWithXianzhiSync = (
  message: string,
  conversationId = 'default',
  opts?: { birth_time?: string; gender?: string; sect?: number; yun_sect?: number }
) =>
  get<ChatResult>('/ai/xianzhi/chat/sync', {
    message,
    conversation_id: conversationId,
    birth_time: opts?.birth_time,
    gender: opts?.gender,
    sect: opts?.sect,
    yun_sect: opts?.yun_sect,
  })

/* ============ 命理工具 ============ */

export interface HehunResult { result?: string }

export const hehun = (a: HehunParams) =>
  get<HehunResult>(EP.HEHUN, {
    birth_time_a: a.birthTimeA,
    gender_a: a.genderA,
    birth_time_b: a.birthTimeB,
    gender_b: a.genderB,
    sect: a.sect ?? 2,
    longitude_a: a.longitudeA,
    longitude_b: a.longitudeB,
  })

export const getCacheStats = () => get('/ai/xianzhi/cache_stats')

export const getHealth = () => get<{ status: string; rag_ready: boolean }>('/ai/health')

/* ============ 直排盘结构化数据（类型见 shared/api/types） ============ */

export const getChart = (birthTime: string, gender: string, sect = 2, yunSect = 1, longitude?: number) =>
  get<ChartData>(EP.CHART, {
    birth_time: birthTime,
    gender,
    sect,
    yun_sect: yunSect,
    ...(longitude ? { longitude } : {}),
  })

/* ============ 命理报告 ============ */

export interface FullReportResult { content?: string; error?: string }

export const generateFullReport = (birthTime: string, gender: string, sections?: string[]) =>
  get<FullReportResult>('/ai/xianzhi/full_report', {
    birth_time: birthTime,
    gender,
    sections: sections?.length ? sections.join(',') : undefined,
  })

/**
 * 下载 PDF 报告
 * 小程序: uni.downloadFile + uni.openDocument
 * H5: 直接打开 URL
 */
export function downloadPdf(path: string, params: Record<string, string>): void {
  const qs = Object.keys(params)
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
    .join('&')
  const url = `${getConfig().apiBase}${path}?${qs}`

  // #ifdef H5
  window.open(url, '_blank')
  // #endif

  // #ifndef H5
  uni.downloadFile({
    url,
    success: (res) => {
      if (res.statusCode === 200) {
        uni.openDocument({
          filePath: res.tempFilePath,
          showMenu: true,
          fail: () => uni.showToast({ title: '打开失败', icon: 'none' }),
        })
      }
    },
    fail: () => uni.showToast({ title: '下载失败', icon: 'none' }),
  })
  // #endif
}

export const downloadReport = (birthTime: string, gender: string) =>
  downloadPdf('/ai/xianzhi/report', { birth_time: birthTime, gender })

export const downloadFullReportPdf = (birthTime: string, gender: string, sections?: string[]) =>
  downloadPdf('/ai/xianzhi/full_report_pdf', {
    birth_time: birthTime,
    gender,
    ...(sections?.length ? { sections: sections.join(',') } : {}),
  })

/* ============ 命例管理（类型见 shared/api/types） ============ */

export const fetchChartCases = () => get<ChartCase[]>(EP.CASES)

export const createChartCase = (payload: Partial<ChartCase>) =>
  post<{ id?: string; error?: string }>(EP.CASES, {
    name: payload.name,
    birth_time: payload.birthTime,
    gender: payload.gender,
    tags: payload.tags,
    chart_data: payload.chartData,
  })

export const updateChartCase = (id: string, payload: Partial<ChartCase>) =>
  put(`${EP.CASES}/${id}`, {
    name: payload.name,
    tags: payload.tags,
    birth_time: payload.birthTime,
    gender: payload.gender,
  })

export const deleteChartCase = (id: string) => del(`${EP.CASES}/${id}`)

/* ============ 会话管理 ============ */

export const fetchSessions = (type: 'xianzhi') => {
  const endpoint = 'xianzhi'
  const prefix = 'mp-xianzhi'
  return get<ChatSession[]>(`/ai/${endpoint}/sessions`, { prefix })
}

export const deleteSession = (type: 'xianzhi', id: string) => {
  return del(`/ai/xianzhi/sessions/${id}`)
}

export const getSessionMessages = async (type: 'xianzhi', id: string): Promise<SessionMessage[]> => {
  if (!id) return []
  interface RawMessage { role?: string; content?: unknown; time?: string }
  const data = await get<RawMessage[]>(`/ai/xianzhi/sessions/${id}/messages`)
  // 后端 get_messages 已统一返回 'user'/'assistant'，并已过滤 tool/system/next_step_prompt
  // 前端只需直接透传，避免二次映射导致 user 被错分成 assistant
  return (data || []).map((m: RawMessage) => ({
    role: (m.role === 'user' || m.role === 'assistant') ? m.role : 'assistant',
    content: typeof m.content === 'string' ? m.content : '',
    time: m.time || undefined,
  }))
}

/** 从会话历史中的排盘工具调用提取出生信息（支持农历/节日/时辰等自然语言输入场景）。 */
export const getSessionBirthInfo = async (id: string): Promise<SessionBirthInfo> => {
  if (!id) return { time: null, gender: null }
  try {
    return await get<SessionBirthInfo>(`/ai/xianzhi/sessions/${id}/birth-info`)
  } catch {
    return { time: null, gender: null }
  }
}

/* ============ 文本解析工具：已上收至 shared/api/parsers（顶部重导出） ============ */

/* ============ 账号登录（类型见 shared/api/types） ============ */

export const register = (nickname: string, password: string) =>
  post<{ token: string; user: XzUser }>(EP.AUTH_REGISTER, { nickname, password })

export const login = (nickname: string, password: string) =>
  post<{ token: string; user: XzUser }>(EP.AUTH_LOGIN, { nickname, password })

export const wxLogin = (code: string) =>
  post<{ token: string; user: XzUser }>(EP.AUTH_WX_LOGIN, { code })

export const fetchMe = () => get<{ user: XzUser }>(EP.AUTH_ME)

export const updateMe = (body: { nickname?: string; avatar?: string; password?: string }) =>
  put<{ user: XzUser }>(EP.AUTH_ME, body)

/* ============ 八字档案（按用户隔离） ============ */

export const fetchProfiles = () => get<BaziProfile[]>(EP.PROFILES)

export const createProfile = (p: Partial<BaziProfile>) =>
  post<{ id: string }>(EP.PROFILES, profileBody(p))

export const updateProfile = (id: string, p: Partial<BaziProfile>) =>
  put(`${EP.PROFILES}/${id}`, profileBody(p))

export const deleteProfile = (id: string) => del(`${EP.PROFILES}/${id}`)

/* ============ 命例收藏（按用户隔离） ============ */

export const fetchFavorites = () => get<FavoriteCase[]>(EP.FAVORITES)
export const addFavorite = (caseId: string) => post(EP.FAVORITES, { case_id: caseId })
export const removeFavorite = (caseId: string) => del(`${EP.FAVORITES}/${caseId}`)
export const favoriteStatus = (caseId: string) =>
  get<{ favorited: boolean }>(`${EP.FAVORITES}/${caseId}/status`)

/* ============ 塔罗记录（按用户隔离） ============ */

export const fetchTarotRecords = () => get<TarotRecord[]>(EP.TAROT_RECORDS)
export const createTarotRecord = (r: { spread: string; question?: string; cards: TarotCard[]; interpretation: string }) =>
  post<{ id: string }>(EP.TAROT_RECORDS, r)
export const deleteTarotRecord = (id: string) => del(`${EP.TAROT_RECORDS}/${id}`)

/* ============ 我的聚合 + 我的对话 ============ */

export const fetchMyOverview = () =>
  get<{ user: XzUser; stats: { profiles: number; favorites: number; tarotRecords: number; sessions: number } }>(EP.ME)
export const fetchMySessions = () => get<ChatSession[]>(EP.SESSIONS_MINE)

/* ============ 问题反馈 ============ */

export const submitFeedback = (content: string, contact?: string) =>
  post(EP.FEEDBACK, { content, contact })

/* ============ 回答反馈（点赞/点踩） ============ */

export const submitAnswerFeedback = (payload: AnswerFeedbackPayload) =>
  post<{ id: string }>(EP.FEEDBACK_ANSWER, payload)
