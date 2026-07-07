/**
 * API 请求层 - 基于 uni.request，对齐后端 FastAPI 接口
 * 后端路由前缀: /api/ai
 * 基址来自 config.ts，运行时可调用 setConfig({ apiBase }) 覆盖（小程序切局域网 IP 用）
 */
import { getConfig } from '@/config'

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
    uni.request({
      ...options,
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

function get<T = any>(url: string, params?: Record<string, any>): Promise<T> {
  let qs = ''
  if (params) {
    const entries = Object.keys(params)
      .filter((k) => params[k] !== undefined && params[k] !== null && params[k] !== '')
      .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(String(params[k]))}`)
    if (entries.length) qs = '?' + entries.join('&')
  }
  return request<T>({ url: url + qs, method: 'GET' })
}

function post<T = any>(url: string, data?: any): Promise<T> {
  return request<T>({ url, method: 'POST', data, header: { 'Content-Type': 'application/json' } })
}

function put<T = any>(url: string, data?: any): Promise<T> {
  return request<T>({ url, method: 'PUT', data, header: { 'Content-Type': 'application/json' } })
}

function del<T = any>(url: string): Promise<T> {
  return request<T>({ url, method: 'DELETE' })
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

export const fetchSessions = (type: 'xianzhi' | 'love') => {
  const endpoint = type === 'xianzhi' ? 'xianzhi' : 'love_app'
  return get<ChatSession[]>(`/ai/${endpoint}/sessions`)
}

export const deleteSession = (type: 'xianzhi' | 'love', id: string) => {
  const endpoint = type === 'xianzhi' ? 'xianzhi' : 'love_app'
  return del(`/ai/${endpoint}/sessions/${id}`)
}

export interface SessionMessage {
  role: 'user' | 'assistant'
  content: string
  time?: string
}

export const getSessionMessages = async (type: 'xianzhi' | 'love', id: string): Promise<SessionMessage[]> => {
  if (!id) return []
  const endpoint = type === 'xianzhi' ? 'xianzhi' : 'love_app'
  const data = await get<any[]>(`/ai/${endpoint}/sessions/${id}/messages`)
  return (data || []).map((m: any) => ({
    role: m.role === 'user' ? 'user' : 'assistant',
    content: typeof m.content === 'string' ? m.content : '',
    time: m.time || undefined,
  }))
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
