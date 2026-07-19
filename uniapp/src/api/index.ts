/**
 * API 请求层 - 基于 uni.request，对齐后端 FastAPI 接口
 * 后端路由前缀: /api/ai
 * 基址来自 config.ts，运行时可调用 setConfig({ apiBase }) 覆盖（小程序切局域网 IP 用）
 */
import { getConfig } from '@/config'
import { getToken } from '@/utils/storage'

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

function post<T = any>(url: string, data?: any): Promise<T> {
  return request<T>({ url: withToken(url), method: 'POST', data, header: { 'Content-Type': 'application/json' } })
}

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

export const chatWithRagSync = (message: string, sessionId = 'default') =>
  get<ChatResult>('/ai/xianzhi/rag/sync', { message, session_id: sessionId })

/* ============ 命理工具 ============ */

export interface HehunResult { result?: string }

export const hehun = (a: { birthTimeA: string; genderA: string; birthTimeB: string; genderB: string }) =>
  get<HehunResult>('/ai/xianzhi/hehun', {
    birth_time_a: a.birthTimeA,
    gender_a: a.genderA,
    birth_time_b: a.birthTimeB,
    gender_b: a.genderB,
  })

export const getCacheStats = () => get('/ai/xianzhi/cache_stats')

export const getHealth = () => get<{ status: string; rag_ready: boolean }>('/ai/health')

/* ============ 直排盘结构化数据 ============ */

export interface ChartData {
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

export const getChart = (birthTime: string, gender: string, sect = 2, yunSect = 1) =>
  get<ChartData>('/ai/xianzhi/chart', {
    birth_time: birthTime,
    gender,
    sect,
    yun_sect: yunSect,
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

/* ============ 命例管理 ============ */

export interface ChartCase {
  id: string
  name: string
  tags: string[]
  birthTime: string
  gender: string
  createdAt: string
  updatedAt: string
  bazi?: string
  chartData?: any
}

export const fetchChartCases = () => get<ChartCase[]>('/ai/xianzhi/chart_cases')

export const createChartCase = (payload: Partial<ChartCase>) =>
  post<{ id?: string; error?: string }>('/ai/xianzhi/chart_cases', {
    name: payload.name,
    birth_time: payload.birthTime,
    gender: payload.gender,
    tags: payload.tags,
    chart_data: payload.chartData,
  })

export const updateChartCase = (id: string, payload: Partial<ChartCase>) =>
  put(`/ai/xianzhi/chart_cases/${id}`, {
    name: payload.name,
    tags: payload.tags,
    birth_time: payload.birthTime,
    gender: payload.gender,
  })

export const deleteChartCase = (id: string) => del(`/ai/xianzhi/chart_cases/${id}`)

/* ============ 会话管理 ============ */

export interface ChatSession {
  id: string
  title: string
  lastMessage: string
  lastTime: string
  messageCount: number
}

export const fetchSessions = (type: 'xianzhi') => {
  const endpoint = 'xianzhi'
  const prefix = 'mp-xianzhi'
  return get<ChatSession[]>(`/ai/${endpoint}/sessions`, { prefix })
}

export const deleteSession = (type: 'xianzhi', id: string) => {
  return del(`/ai/xianzhi/sessions/${id}`)
}

/** 清空指定会话的消息记录，但保留会话本身（不新建会话） */
export const clearSessionMessages = (type: 'xianzhi', id: string) => {
  return post(`/ai/xianzhi/sessions/${id}/clear`, {})
}

export const clearRagSessionMessages = (sessionId: string) => {
  return post(`/ai/xianzhi/rag/sessions/${encodeURIComponent(sessionId)}/clear`, {})
}
export interface SessionMessage {
  role: 'user' | 'assistant'
  content: string
  time?: string
}

export const getSessionMessages = async (type: 'xianzhi', id: string): Promise<SessionMessage[]> => {
  if (!id) return []
  const data = await get<any[]>(`/ai/xianzhi/sessions/${id}/messages`)
  // 后端 get_messages 已统一返回 'user'/'assistant'，并已过滤 tool/system/next_step_prompt
  // 前端只需直接透传，避免二次映射导致 user 被错分成 assistant
  return (data || []).map((m: any) => ({
    role: (m.role === 'user' || m.role === 'assistant') ? m.role : 'assistant',
    content: typeof m.content === 'string' ? m.content : '',
    time: m.time || undefined,
  }))
}

export interface BirthInfo { time: string | null; gender: string | null }

/** 从会话历史中的排盘工具调用提取出生信息（支持农历/节日/时辰等自然语言输入场景）。 */
export const getSessionBirthInfo = async (id: string): Promise<BirthInfo> => {
  if (!id) return { time: null, gender: null }
  try {
    return await get<BirthInfo>(`/ai/xianzhi/sessions/${id}/birth-info`)
  } catch {
    return { time: null, gender: null }
  }
}

/* ============ 文本解析工具（与 Web 端 frontend/src/api 一致） ============ */

export interface Pillar { name: string; ganzhi: string; nayin: string }
export function parsePillars(text: string): Pillar[] {
  if (!text) return []
  const result: Pillar[] = []
  const re = /(年柱|月柱|日柱|时柱)[:\s]*([^\s(]+)\s*\(([^)]+)\)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    result.push({ name: m[1], ganzhi: m[2].trim(), nayin: m[3].trim() })
  }
  return result
}

export interface WuxingItem { name: string; count: number; color: string }
export function parseWuxing(text: string): WuxingItem[] {
  if (!text) return []
  const colors: Record<string, string> = {
    金: '#d4af37', 木: '#4a7c3a', 水: '#3a6ea5', 火: '#c0392b', 土: '#8b6f47',
  }
  const result: WuxingItem[] = []
  const m = text.match(/['"]?金['"]?\s*[:=]\s*(\d+).*?['"]?木['"]?\s*[:=]\s*(\d+).*?['"]?水['"]?\s*[:=]\s*(\d+).*?['"]?火['"]?\s*[:=]\s*(\d+).*?['"]?土['"]?\s*[:=]\s*(\d+)/s)
  if (m) {
    const vals = [parseInt(m[1]), parseInt(m[2]), parseInt(m[3]), parseInt(m[4]), parseInt(m[5])]
    const names = ['金', '木', '水', '火', '土']
    names.forEach((n, i) => result.push({ name: n, count: vals[i], color: colors[n] }))
  }
  return result
}

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
  season?: string
  adjustment?: string
  patternHint?: string
  confidence?: number
}

export interface DayunItem { year: string; ganzhi: string; startAge: number; startYear: number; endAge?: number; endYear?: number }
export interface LiuNianItem { year: string; ganzhi: string; age?: number; dayun?: string; dayunStartYear?: number; dayunEndYear?: number; xunkong?: string }
export function parseDayun(text: string): DayunItem[] {
  if (!text) return []
  const result: DayunItem[] = []
  const re = /(\d+)[\s-~至~到](\d+)岁?\s*([^\s]+)\s*(\d+)-(\d+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    result.push({ year: m[3], ganzhi: m[3], startAge: parseInt(m[1]), startYear: parseInt(m[4]) })
  }
  return result
}

export interface ShenshaItem { name: string; description: string }
export function parseShensha(text: string): ShenshaItem[] {
  if (!text) return []
  const result: ShenshaItem[] = []
  const re = /([^\n:：]+)[：:]\s*([^\n]+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    const name = m[1].trim()
    if (name && name.length < 20 && !name.includes('柱') && !name.includes('五行')) {
      result.push({ name, description: m[2].trim() })
    }
  }
  return result.slice(0, 8)
}

/* ============ 账号登录 ============ */

export interface XzUser { id: string; nickname: string; avatar: string }

export const register = (nickname: string, password: string) =>
  post<{ token: string; user: XzUser }>('/ai/auth/register', { nickname, password })

export const login = (nickname: string, password: string) =>
  post<{ token: string; user: XzUser }>('/ai/auth/login', { nickname, password })

export const wxLogin = (code: string) =>
  post<{ token: string; user: XzUser }>('/ai/auth/wx-login', { code })

export const fetchMe = () => get<{ user: XzUser }>('/ai/auth/me')

export const updateMe = (body: { nickname?: string; avatar?: string; password?: string }) =>
  put<{ user: XzUser }>('/ai/auth/me', body)

/* ============ 八字档案（按用户隔离） ============ */

export interface BaziProfile {
  id: string
  name: string
  relation: string
  birthTime: string
  gender: string
  sect: number
  yunSect: number
  chartData?: any
  createdAt: string
}

export const fetchProfiles = () => get<BaziProfile[]>('/ai/profiles')

export const createProfile = (p: Partial<BaziProfile>) =>
  post<{ id: string }>('/ai/profiles', {
    name: p.name,
    relation: p.relation,
    birth_time: p.birthTime,
    gender: p.gender,
    sect: p.sect ?? 2,
    yun_sect: p.yunSect ?? 1,
    chart_data: p.chartData,
  })

export const updateProfile = (id: string, p: Partial<BaziProfile>) =>
  put(`/ai/profiles/${id}`, {
    name: p.name,
    relation: p.relation,
    birth_time: p.birthTime,
    gender: p.gender,
    sect: p.sect ?? 2,
    yun_sect: p.yunSect ?? 1,
    chart_data: p.chartData,
  })

export const deleteProfile = (id: string) => del(`/ai/profiles/${id}`)

/* ============ 命例收藏（按用户隔离） ============ */

export interface FavoriteCase {
  caseId: string
  name: string
  tags: string[]
  birthTime: string
  gender: string
  chartData?: any
  createdAt: string
}

export const fetchFavorites = () => get<FavoriteCase[]>('/ai/favorites')
export const addFavorite = (caseId: string) => post('/ai/favorites', { case_id: caseId })
export const removeFavorite = (caseId: string) => del(`/ai/favorites/${caseId}`)
export const favoriteStatus = (caseId: string) =>
  get<{ favorited: boolean }>(`/ai/favorites/${caseId}/status`)

/* ============ 塔罗记录（按用户隔离） ============ */

export interface TarotRecord {
  id: string
  spread: string
  question: string
  cards: any[]
  interpretation: string
  createdAt: string
}

export const fetchTarotRecords = () => get<TarotRecord[]>('/ai/tarot_records')
export const createTarotRecord = (r: { spread: string; question?: string; cards: any[]; interpretation: string }) =>
  post<{ id: string }>('/ai/tarot_records', r)
export const deleteTarotRecord = (id: string) => del(`/ai/tarot_records/${id}`)

/* ============ 我的聚合 + 我的对话 ============ */

export const fetchMyOverview = () => get<{ user: XzUser; stats: any }>('/ai/me')
export const fetchMySessions = () => get<ChatSession[]>('/ai/xianzhi/sessions/mine')

/* ============ 问题反馈 ============ */

export const submitFeedback = (content: string, contact?: string) =>
  post('/ai/feedback', { content, contact })
