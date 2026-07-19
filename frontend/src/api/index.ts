const API_BASE = import.meta.env.DEV ? "http://localhost:8123/api" : "/api"

export interface SSECallbacks {
  onMessage?: (data: string) => void
  onError?: (err: Event) => void
  onDone?: () => void
  onChartContext?: (birthTime: string, gender: string) => void
}

export interface ChatOptions {
  birth_time?: string
  gender?: string
  sect?: number
  yun_sect?: number
}

export function connectSSE(path: string, params: Record<string, string | undefined>, cb: SSECallbacks): EventSource {
  const qs = Object.keys(params)
    .filter((k) => params[k] !== undefined && params[k] !== "")
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k] as string)}`)
    .join("&")
  const url = `${API_BASE}${path}?${qs}`
  const es = new EventSource(url)
  es.onmessage = (e) => {
    if (e.data === "[DONE]") { cb.onDone?.(); es.close() }
    else cb.onMessage?.(e.data)
  }
  // 监听后端 chart_context 事件（自然语言输入时后端从工具调用提取的出生信息）
  es.addEventListener("chart_context", (e) => {
    try {
      const data = JSON.parse((e as MessageEvent).data)
      if (data?.birth_time && data?.gender) cb.onChartContext?.(data.birth_time, data.gender)
    } catch {}
  })
  // 监听后端自定义 error 事件（如 event: error）
  es.addEventListener("error", (e) => {
    const data = (e as MessageEvent).data || ""
    cb.onError?.(new ErrorEvent("error", { message: data }))
    es.close()
  })
  es.onerror = (err) => { cb.onError?.(err); es.close() }
  return es
}

export const chatWithXianzhi = (message: string, conversationId: string, cb: SSECallbacks, opts?: ChatOptions) =>
  connectSSE("/ai/xianzhi/chat", {
    message,
    conversation_id: conversationId,
    birth_time: opts?.birth_time,
    gender: opts?.gender,
    sect: opts?.sect !== undefined ? String(opts.sect) : undefined,
    yun_sect: opts?.yun_sect !== undefined ? String(opts.yun_sect) : undefined,
  }, cb)

export const chatWithRag = (message: string, sessionId: string, cb: SSECallbacks) =>
  connectSSE("/ai/xianzhi/rag", { message, session_id: sessionId }, cb)

export function downloadReport(birthTime: string, gender: string): void {
  const qs = `birth_time=${encodeURIComponent(birthTime)}&gender=${encodeURIComponent(gender)}`
  const url = `${API_BASE}/ai/xianzhi/report?${qs}`
  window.open(url, "_blank")
}

export async function generateFullReport(birthTime: string, gender: string, sections?: string[]): Promise<string> {
  const params = new URLSearchParams({ birth_time: birthTime, gender })
  if (sections && sections.length) params.set("sections", sections.join(","))
  const res = await fetch(`${API_BASE}/ai/xianzhi/full_report?${params.toString()}`)
  const data = await res.json()
  if (data.error) throw new Error(data.error)
  return data.content || ""
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

export interface ChartCase { id: string; name: string; tags: string[]; birthTime: string; gender: string; createdAt: string; updatedAt: string; bazi?: string; chartData?: ChartData }

export async function getChart(birthTime: string, gender: string, sect = 2, yunSect = 1): Promise<ChartData> {
  const params = new URLSearchParams({
    birth_time: birthTime,
    gender,
    sect: String(sect),
    yun_sect: String(yunSect),
  })
  const res = await fetch(`${API_BASE}/ai/xianzhi/chart?${params.toString()}`)
  if (!res.ok) throw new Error(`排盘失败 ${res.status}`)
  return await res.json()
}

export async function fetchChartCases(): Promise<ChartCase[]> {
  try {
    const res = await fetch(`${API_BASE}/ai/xianzhi/chart_cases`)
    if (!res.ok) throw new Error("fail")
    return await res.json()
  } catch { return [] }
}

export async function createChartCase(payload: Partial<ChartCase>): Promise<{ id?: string; error?: string }> {
  const body = {
    name: payload.name,
    birth_time: payload.birthTime,
    gender: payload.gender,
    tags: payload.tags,
    chart_data: payload.chartData,
  }
  const res = await fetch(`${API_BASE}/ai/xianzhi/chart_cases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `保存失败 ${res.status}` }))
    throw new Error(err.detail || `保存失败 ${res.status}`)
  }
  return await res.json()
}

export async function updateChartCase(id: string, payload: Partial<ChartCase>): Promise<void> {
  const res = await fetch(`${API_BASE}/ai/xianzhi/chart_cases/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: payload.name,
      tags: payload.tags,
      birth_time: payload.birthTime,
      gender: payload.gender,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `更新失败 ${res.status}` }))
    throw new Error(err.detail || `更新失败 ${res.status}`)
  }
}

export async function deleteChartCase(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/ai/xianzhi/chart_cases/${id}`, { method: "DELETE" })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `删除失败 ${res.status}` }))
    throw new Error(err.detail || `删除失败 ${res.status}`)
  }
}

export function exportChartCasesJSON(): void {
  const url = `${API_BASE}/ai/xianzhi/chart_cases/export/json`
  window.open(url, "_blank")
}

export async function importChartCasesJSON(file: File): Promise<{ inserted: number; skipped: number }> {
  const text = await file.text()
  const data = JSON.parse(text)
  const res = await fetch(`${API_BASE}/ai/xianzhi/chart_cases/import/json`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cases: data.cases || [] }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `导入失败 ${res.status}` }))
    throw new Error(err.detail || `导入失败 ${res.status}`)
  }
  return await res.json()
}

export function downloadFullReportPDF(birthTime: string, gender: string, sections?: string[]): void {
  const params = new URLSearchParams({ birth_time: birthTime, gender })
  if (sections && sections.length) params.set("sections", sections.join(","))
  const url = `${API_BASE}/ai/xianzhi/full_report_pdf?${params.toString()}`
  window.open(url, "_blank")
}

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
  const colors: Record<string, string> = { "金": "#d4af37", "木": "#4a7c3a", "水": "#3a6ea5", "火": "#c0392b", "土": "#8b6f47" }
  const result: WuxingItem[] = []
  const m = text.match(/['"]?金['"]?\s*[:=]\s*(\d+).*?['"]?木['"]?\s*[:=]\s*(\d+).*?['"]?水['"]?\s*[:=]\s*(\d+).*?['"]?火['"]?\s*[:=]\s*(\d+).*?['"]?土['"]?\s*[:=]\s*(\d+)/s)
  if (m) {
    const vals = [parseInt(m[1]), parseInt(m[2]), parseInt(m[3]), parseInt(m[4]), parseInt(m[5])]
    const names = ["金", "木", "水", "火", "土"]
    names.forEach((n, i) => result.push({ name: n, count: vals[i], color: colors[n] }))
  }
  return result
}

export interface DayunItem { year: string; ganzhi: string; startAge: number; startYear: number; endAge?: number; endYear?: number; liunian?: LiuNianItem[] }
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
    if (name && name.length < 20 && !name.includes("柱") && !name.includes("五行")) {
      result.push({ name, description: m[2].trim() })
    }
  }
  return result.slice(0, 8)
}

export interface ChatSession { id: string; title: string; lastMessage: string; lastTime: string; messageCount: number }
export async function fetchSessions(type: "xianzhi"): Promise<ChatSession[]> {
  try {
    const res = await fetch(`${API_BASE}/ai/xianzhi/sessions`)
    if (!res.ok) throw new Error("Not found")
    return res.json()
  } catch { return [] }
}

export async function deleteSession(type: "xianzhi", id: string): Promise<void> {
  if (!id) return
  try {
    await fetch(`${API_BASE}/ai/xianzhi/sessions/${id}`, { method: "DELETE" })
  } catch {}
}

export async function clearSessionMessages(type: "xianzhi", id: string): Promise<void> {
  if (!id) return
  try {
    await fetch(`${API_BASE}/ai/xianzhi/sessions/${id}/clear`, { method: "POST" })
  } catch {}
}

export async function clearRagSessionMessages(sessionId: string): Promise<void> {
  if (!sessionId) return
  try {
    await fetch(`${API_BASE}/ai/xianzhi/rag/sessions/${encodeURIComponent(sessionId)}/clear`, { method: "POST" })
  } catch {}
}

export interface SessionMessage { role: "user" | "assistant"; content: string; time?: string }

export interface RagDoc { filename: string; size: number; modified: string }
export interface RagStatus { ready: boolean; count: number }

export interface EndpointMetrics {
  method: string
  path: string
  count: number
  avg_latency_ms: number
  total_latency_ms: number
}

export interface ErrorRecord {
  timestamp: number
  method: string
  path: string
  status: number
  latency_ms: number
}

export interface MetricsData {
  total_requests: number
  avg_latency_ms: number
  error_rate: number
  status_codes: { "2xx": number; "4xx": number; "5xx": number }
  endpoints: EndpointMetrics[]
  top_endpoints: EndpointMetrics[]
  recent_errors: ErrorRecord[]
  uptime_seconds: number
}

export async function fetchMetrics(): Promise<MetricsData> {
  const res = await fetch(`${API_BASE}/ai/metrics`)
  if (!res.ok) throw new Error("获取指标失败")
  return await res.json()
}

export async function getRagStatus(): Promise<RagStatus> {
  const res = await fetch(`${API_BASE}/ai/rag/status`)
  if (!res.ok) throw new Error("获取 RAG 状态失败")
  return await res.json()
}

export async function listRagDocs(): Promise<RagDoc[]> {
  const res = await fetch(`${API_BASE}/ai/rag/docs`)
  if (!res.ok) throw new Error("获取文档列表失败")
  const data = await res.json()
  return data.files || []
}

export async function uploadRagDoc(file: File): Promise<{ filename: string; size: number }> {
  const form = new FormData()
  form.append("file", file)
  const res = await fetch(`${API_BASE}/ai/rag/docs/upload`, { method: "POST", body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `上传失败 ${res.status}` }))
    throw new Error(err.detail || `上传失败 ${res.status}`)
  }
  return await res.json()
}

export async function deleteRagDoc(filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}/ai/rag/docs/${encodeURIComponent(filename)}`, { method: "DELETE" })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `删除失败 ${res.status}` }))
    throw new Error(err.detail || `删除失败 ${res.status}`)
  }
}

export async function rebuildRagIndex(): Promise<{ ready: boolean }> {
  const res = await fetch(`${API_BASE}/ai/rag/docs/rebuild`, { method: "POST" })
  if (!res.ok) throw new Error("重建向量库失败")
  return await res.json()
}

export async function getSessionMessages(type: "xianzhi", id: string): Promise<SessionMessage[]> {
  if (!id) return []
  try {
    const res = await fetch(`${API_BASE}/ai/xianzhi/sessions/${id}/messages`)
    if (!res.ok) return []
    const data = await res.json()
    return data.map((m: any) => ({
      role: (m.role === "user" || m.role === "human") ? "user" : "assistant",
      content: typeof m.content === "string" ? m.content : "",
      time: m.time || undefined,
    }))
  } catch { return [] }
}

export interface SessionBirthInfo { time: string | null; gender: string | null }

/** 从会话历史中的排盘工具调用提取出生信息（支持农历/节日/时辰等自然语言输入场景）。 */
export async function getSessionBirthInfo(id: string): Promise<SessionBirthInfo> {
  if (!id) return { time: null, gender: null }
  try {
    const res = await fetch(`${API_BASE}/ai/xianzhi/sessions/${id}/birth-info`)
    if (!res.ok) return { time: null, gender: null }
    return await res.json()
  } catch { return { time: null, gender: null } }
}

// ========== 塔罗占卜 ==========

export type TarotSpread = "daily" | "three_card" | "relationship"

export interface TarotDrawnCard {
  name: string
  nameEn: string
  emblem: string
  arcana: string
  suit: string
  isReversed: boolean
  meaning: string
}

export interface TarotInterpretCallbacks {
  onMessage?: (chunk: string) => void
  onDone?: () => void
  onError?: (err: string) => void
}

/** 通过 WebSocket 抽牌（后端 Fisher-Yates 洗牌，不可预测） */
export function drawTarotCardsWS(
  spread: TarotSpread,
  cb: { onCards?: (cards: TarotDrawnCard[]) => void; onError?: (err: string) => void }
): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws")
  const url = `${wsBase}/ai/tarot/ws`
  const ws = new WebSocket(url)

  ws.onopen = () => {
    ws.send(JSON.stringify({ action: "draw", spread }))
  }
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data.type === "cards") cb.onCards?.(data.data || [])
      else if (data.type === "error") cb.onError?.(data.data || "抽牌失败")
    } catch {
      cb.onError?.("解析消息失败")
    }
  }
  ws.onerror = () => cb.onError?.("连接错误")
  return ws
}

/** 通过 WebSocket 获取 AI 流式解读 */
export function interpretTarotWS(
  opts: { spread: TarotSpread; question?: string; cards: TarotDrawnCard[] },
  cb: TarotInterpretCallbacks
): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws")
  const url = `${wsBase}/ai/tarot/ws`
  const ws = new WebSocket(url)

  ws.onopen = () => {
    ws.send(JSON.stringify({
      action: "interpret",
      spread: opts.spread,
      question: opts.question || "",
      cards: opts.cards,
    }))
  }
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data.type === "message") cb.onMessage?.(data.data)
      else if (data.type === "done") cb.onDone?.()
      else if (data.type === "error") cb.onError?.(data.data || "解读失败")
    } catch {
      cb.onError?.("解析消息失败")
    }
  }
  ws.onerror = () => cb.onError?.("连接错误")
  return ws
}

// ========== 管理后台：用户管理 ==========

export interface AdminUser {
  id: string
  nickname: string
  avatar: string
  createdAt: string
  lastActiveAt: string
  stats: { profiles: number; favorites: number; tarotRecords: number; sessions: number }
}

export interface AdminUserDetail {
  user: { id: string; nickname: string; avatar: string }
  profiles: any[]
  favorites: any[]
  tarotRecords: any[]
  sessions: any[]
}

export async function listAdminUsers(limit = 200, offset = 0): Promise<{ total: number; users: AdminUser[] }> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  const res = await fetch(`${API_BASE}/ai/admin/users?${params.toString()}`)
  if (!res.ok) throw new Error("获取用户列表失败")
  return await res.json()
}

export async function getAdminUser(user_id: string): Promise<AdminUserDetail> {
  const res = await fetch(`${API_BASE}/ai/admin/users/${encodeURIComponent(user_id)}`)
  if (!res.ok) throw new Error("获取用户详情失败")
  return await res.json()
}

// ========== 用户反馈 ==========

export interface FeedbackItem {
  id: string
  user_id: string | null
  user_nickname?: string | null
  content: string
  contact: string
  created_at: string
}

export async function submitFeedback(content: string, contact?: string): Promise<{ id: string }> {
  const params = new URLSearchParams({ content })
  if (contact) params.set("contact", contact)
  const token = localStorage.getItem("XZ_TOKEN")
  const headers: Record<string, string> = { "Content-Type": "application/x-www-form-urlencoded" }
  if (token) headers["Authorization"] = `Bearer ${token}`
  const res = await fetch(`${API_BASE}/ai/feedback?${params.toString()}`, {
    method: "POST",
    headers,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `提交失败 ${res.status}` }))
    throw new Error(err.detail || `提交失败 ${res.status}`)
  }
  return res.json()
}

/** 管理员获取反馈列表 */
export async function fetchFeedbacks(limit = 200): Promise<FeedbackItem[]> {
  const res = await fetch(`${API_BASE}/ai/feedback?limit=${limit}`)
  if (!res.ok) throw new Error("获取反馈列表失败")
  const data = await res.json()
  return data.items || []
}

/** 管理员删除反馈 */
export async function deleteFeedback(fid: string): Promise<void> {
  const res = await fetch(`${API_BASE}/ai/feedback/${fid}`, { method: "DELETE" })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `删除失败 ${res.status}` }))
    throw new Error(err.detail || `删除失败 ${res.status}`)
  }
}
