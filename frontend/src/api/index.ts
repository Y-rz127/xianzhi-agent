// R11 共享 API 层：数据模型/文本解析器/端点常量与小程序端共用，统一在仓库根 shared/api 维护
export type {
  AnswerFeedbackPayload, BaziCandidate, ChartAnalysis, ChartCase, ChartData,
  ChatOptions, ChatSession, DayunItem, LiuNianItem, Pillar, SessionBirthInfo,
  SessionMessage, ShenshaItem, WuxingItem,
} from "@shared/api"
export { EP, parseDayun, parsePillars, parseShensha, parseWuxing } from "@shared/api"
import type { AnswerFeedbackPayload, BaziCandidate, BaziProfile, ChartCase, ChartData, ChatOptions, ChatSession, FavoriteCase, SessionBirthInfo, SessionMessage, TarotRecord } from "@shared/api"
import { EP } from "@shared/api"

const API_BASE = import.meta.env.VITE_API_BASE
  || (import.meta.env.DEV ? "http://localhost:8123/api" : "/api")
// 管理端 API Key：优先读 VITE_API_KEY（.env.local，已 gitignore，需与后端 API_KEYS 对齐）。
// 注意：前端可见的 Key 只能防君子不能防小人；转公开站点时应改为后端代理转发，见 docs/architecture_review.md。
// 兜底值仅供本地开发（后端 API_KEYS 为空时鉴权关闭，不影响使用）。
const API_KEY = import.meta.env.VITE_API_KEY || "xianzhi-yrz-admin"

function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers)
  headers.set("X-API-Key", API_KEY)
  return fetch(input, { ...init, headers })
}

export { apiFetch }

function withApiKey(url: string): string {
  const sep = url.includes("?") ? "&" : "?"
  return `${url}${sep}api_key=${encodeURIComponent(API_KEY)}`
}

export interface SSECallbacks {
  onMessage?: (data: string) => void
  onError?: (err: Event) => void
  onDone?: () => void
  onChartContext?: (birthTime: string, gender: string, birthPlace?: string) => void
}

export function connectSSE(path: string, params: Record<string, string | undefined>, cb: SSECallbacks): EventSource {
  const qs = Object.keys(params)
    .filter((k) => params[k] !== undefined && params[k] !== "")
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k] as string)}`)
    .join("&")
  const url = withApiKey(`${API_BASE}${path}?${qs}`)
  const es = new EventSource(url)
  es.onmessage = (e) => {
    if (e.data === "[DONE]") { cb.onDone?.(); es.close() }
    else cb.onMessage?.(e.data)
  }
  // 监听后端 chart_context 事件（自然语言输入时后端从工具调用提取的出生信息）
  es.addEventListener("chart_context", (e) => {
    try {
      const data = JSON.parse((e as MessageEvent).data)
      if (data?.birth_time && data?.gender) cb.onChartContext?.(data.birth_time, data.gender, data.birth_place)
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
    birth_place: opts?.birth_place,
    sect: opts?.sect !== undefined ? String(opts.sect) : undefined,
    yun_sect: opts?.yun_sect !== undefined ? String(opts.yun_sect) : undefined,
  }, cb)

export function downloadReport(birthTime: string, gender: string): void {
  const qs = `birth_time=${encodeURIComponent(birthTime)}&gender=${encodeURIComponent(gender)}`
  const url = `${API_BASE}/ai/xianzhi/report?${qs}`
  window.open(url, "_blank")
}

export async function generateFullReport(birthTime: string, gender: string, sections?: string[]): Promise<string> {
  const params = new URLSearchParams({ birth_time: birthTime, gender })
  if (sections && sections.length) params.set("sections", sections.join(","))
  const res = await apiFetch(`${API_BASE}/ai/xianzhi/full_report?${params.toString()}`)
  const data = await res.json()
  if (data.error) throw new Error(data.error)
  return data.content || ""
}

export async function getChart(birthTime: string, gender: string, sect = 2, yunSect = 1, longitude?: number): Promise<ChartData> {
  const params = new URLSearchParams({
    birth_time: birthTime,
    gender,
    sect: String(sect),
    yun_sect: String(yunSect),
  })
  if (longitude !== undefined && longitude !== 0) params.set("longitude", String(longitude))
  const res = await apiFetch(`${API_BASE}${EP.CHART}?${params.toString()}`)
  if (!res.ok) throw new Error(`排盘失败 ${res.status}`)
  return await res.json()
}

export async function inferBaziDates(payload: { pillars: string; gender: string; top_n?: number }): Promise<{ candidates: BaziCandidate[] }> {
  const res = await apiFetch(`${API_BASE}${EP.INFER_DATES}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pillars: payload.pillars, gender: payload.gender, top_n: payload.top_n || 3 }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `反推失败 ${res.status}` }))
    throw new Error(err.detail || `反推失败 ${res.status}`)
  }
  return await res.json()
}

export async function fetchChartCases(): Promise<ChartCase[]> {
  try {
    const res = await apiFetch(`${API_BASE}/ai/xianzhi/cases`)
    if (!res.ok) throw new Error("fail")
    return await res.json()
  } catch { return [] }
}

export async function createChartCase(payload: Partial<ChartCase> & Record<string, any>): Promise<{ id?: string; error?: string }> {
  const body: Record<string, any> = {
    name: payload.name,
    birth_time: payload.birthTime,
    gender: payload.gender,
    tags: payload.tags,
    chart_data: payload.chartData,
  }
  if (payload.bio) body.bio = payload.bio
  if (payload.analysis) body.analysis = payload.analysis
  if (payload.keypoints) body.keypoints = payload.keypoints
  const res = await apiFetch(`${API_BASE}/ai/xianzhi/cases`, {
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

export async function updateChartCase(id: string, payload: Partial<ChartCase> & Record<string, any>): Promise<void> {
  const body: Record<string, any> = {
    name: payload.name,
    tags: payload.tags,
    birth_time: payload.birthTime,
    gender: payload.gender,
  }
  if (payload.bio !== undefined) body.bio = payload.bio
  if (payload.analysis !== undefined) body.analysis = payload.analysis
  if (payload.keypoints !== undefined) body.keypoints = payload.keypoints
  const res = await apiFetch(`${API_BASE}/ai/xianzhi/cases/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `更新失败 ${res.status}` }))
    throw new Error(err.detail || `更新失败 ${res.status}`)
  }
}

export async function deleteChartCase(id: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/ai/xianzhi/cases/${id}`, { method: "DELETE" })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `删除失败 ${res.status}` }))
    throw new Error(err.detail || `删除失败 ${res.status}`)
  }
}

export function exportChartCasesJSON(): void {
  const url = `${API_BASE}/ai/xianzhi/cases/export/json`
  window.open(url, "_blank")
}

export async function importChartCasesJSON(file: File): Promise<{ inserted: number; skipped: number }> {
  const text = await file.text()
  const data = JSON.parse(text)
  const res = await apiFetch(`${API_BASE}/ai/xianzhi/cases/import/json`, {
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

export async function fetchSessions(type: "xianzhi"): Promise<ChatSession[]> {
  try {
    const res = await apiFetch(`${API_BASE}${EP.SESSIONS}`)
    if (!res.ok) throw new Error("Not found")
    return res.json()
  } catch { return [] }
}

export async function deleteSession(type: "xianzhi", id: string): Promise<void> {
  if (!id) return
  try {
    await apiFetch(`${API_BASE}${EP.SESSIONS}/${id}`, { method: "DELETE" })
  } catch {}
}

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
  const res = await apiFetch(`${API_BASE}/ai/metrics`)
  if (!res.ok) throw new Error("获取指标失败")
  return await res.json()
}

export async function getRagStatus(): Promise<RagStatus> {
  const res = await apiFetch(`${API_BASE}/ai/rag/status`)
  if (!res.ok) throw new Error("获取 RAG 状态失败")
  return await res.json()
}

export async function listRagDocs(): Promise<RagDoc[]> {
  const res = await apiFetch(`${API_BASE}/ai/rag/docs`)
  if (!res.ok) throw new Error("获取文档列表失败")
  const data = await res.json()
  return data.files || []
}

export async function uploadRagDoc(file: File): Promise<{ filename: string; size: number }> {
  const form = new FormData()
  form.append("file", file)
  const res = await apiFetch(`${API_BASE}/ai/rag/docs/upload`, { method: "POST", body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `上传失败 ${res.status}` }))
    throw new Error(err.detail || `上传失败 ${res.status}`)
  }
  return await res.json()
}

export async function deleteRagDoc(filename: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/ai/rag/docs/${encodeURIComponent(filename)}`, { method: "DELETE" })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `删除失败 ${res.status}` }))
    throw new Error(err.detail || `删除失败 ${res.status}`)
  }
}

export async function rebuildRagIndex(): Promise<{ ready: boolean }> {
  const res = await apiFetch(`${API_BASE}/ai/rag/docs/rebuild`, { method: "POST" })
  if (!res.ok) throw new Error("重建向量库失败")
  return await res.json()
}

export async function getSessionMessages(type: "xianzhi", id: string): Promise<SessionMessage[]> {
  if (!id) return []
  try {
    const res = await apiFetch(`${API_BASE}/ai/xianzhi/sessions/${id}/messages`)
    if (!res.ok) return []
    const data = await res.json()
    return data.map((m: { role?: string; content?: unknown; time?: string }) => ({
      role: (m.role === "user" || m.role === "human") ? "user" : "assistant",
      content: typeof m.content === "string" ? m.content : "",
      time: m.time || undefined,
    }))
  } catch { return [] }
}

/** 从会话历史中的排盘工具调用提取出生信息（支持农历/节日/时辰等自然语言输入场景）。 */
export async function getSessionBirthInfo(id: string): Promise<SessionBirthInfo> {
  if (!id) return { time: null, gender: null }
  try {
    const res = await apiFetch(`${API_BASE}/ai/xianzhi/sessions/${id}/birth-info`)
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
  const url = withApiKey(`${wsBase}/ai/tarot/ws`)
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
  const url = withApiKey(`${wsBase}/ai/tarot/ws`)
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
  profiles: BaziProfile[]
  favorites: FavoriteCase[]
  tarotRecords: TarotRecord[]
  sessions: ChatSession[]
}

export async function listAdminUsers(limit = 200, offset = 0): Promise<{ total: number; users: AdminUser[] }> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  const res = await apiFetch(`${API_BASE}/ai/admin/users?${params.toString()}`)
  if (!res.ok) throw new Error("获取用户列表失败")
  return await res.json()
}

export async function getAdminUser(user_id: string): Promise<AdminUserDetail> {
  const res = await apiFetch(`${API_BASE}/ai/admin/users/${encodeURIComponent(user_id)}`)
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

export interface AnswerFeedbackItem {
  id: string
  user_id: string | null
  user_nickname?: string | null
  conversation_id: string
  question: string
  answer: string
  rating: "up" | "down"
  reason: string
  chart_snapshot?: Record<string, unknown>
  created_at: string
  reviewed: boolean
  reviewed_by: string
}

export async function submitFeedback(content: string, contact?: string): Promise<{ id: string }> {
  const token = localStorage.getItem("XZ_TOKEN")
  const params = new URLSearchParams()
  if (token) params.set("token", token)
  const res = await apiFetch(`${API_BASE}/ai/feedback?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, contact: contact || "" }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `提交失败 ${res.status}` }))
    throw new Error(err.detail || `提交失败 ${res.status}`)
  }
  return res.json()
}

export async function submitAnswerFeedback(payload: AnswerFeedbackPayload): Promise<{ id: string }> {
  const token = localStorage.getItem("XZ_TOKEN")
  const params = new URLSearchParams()
  if (token) params.set("token", token)
  const res = await apiFetch(`${API_BASE}/ai/feedback/answer?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `提交失败 ${res.status}` }))
    throw new Error(err.detail || `提交失败 ${res.status}`)
  }
  return res.json()
}

export async function fetchAnswerFeedbacks(limit = 200, rating?: "up" | "down"): Promise<AnswerFeedbackItem[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (rating) params.set("rating", rating)
  const res = await apiFetch(`${API_BASE}/ai/feedback/answers?${params.toString()}`)
  if (!res.ok) throw new Error("获取回答反馈失败")
  const data = await res.json()
  return data.items || []
}

export function answerFeedbackSftExportUrl(rating: "up" | "down" = "up", limit = 1000): string {
  const params = new URLSearchParams({ rating, limit: String(limit) })
  return withApiKey(`${API_BASE}/ai/feedback/answers/export/sft?${params.toString()}`)
}

export function answerFeedbackDpoExportUrl(limit = 500): string {
  const params = new URLSearchParams({ limit: String(limit) })
  return withApiKey(`${API_BASE}/ai/feedback/answers/export/dpo?${params.toString()}`)
}

export async function reviewAnswerFeedback(fid: string): Promise<{ ok: boolean }> {
  const res = await apiFetch(`${API_BASE}/ai/feedback/answers/${fid}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewer: "admin" }),
  })
  if (!res.ok) throw new Error("审核失败")
  return res.json()
}

export async function promoteAnswerToCase(fid: string): Promise<{ case_id: string; file_path: string }> {
  const res = await apiFetch(`${API_BASE}/ai/feedback/answers/${fid}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewer: "admin" }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "转案例失败" }))
    throw new Error(err.detail || "转案例失败")
  }
  return res.json()
}

/** 管理员获取反馈列表 */
export async function fetchFeedbacks(limit = 200): Promise<FeedbackItem[]> {
  const res = await apiFetch(`${API_BASE}/ai/feedback?limit=${limit}`)
  if (!res.ok) throw new Error("获取反馈列表失败")
  const data = await res.json()
  return data.items || []
}

/** 管理员删除反馈 */
export async function deleteFeedback(fid: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/ai/feedback/${fid}`, { method: "DELETE" })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `删除失败 ${res.status}` }))
    throw new Error(err.detail || `删除失败 ${res.status}`)
  }
}
// ========== 管理后台：管理员账号 ==========

export interface AdminAccount {
  id: string
  username: string
  nickname: string | null
  enabled: boolean
  is_super: boolean
  created_at: string
}

/** 获取管理员账号列表 */
export async function listAdminAccounts(): Promise<AdminAccount[]> {
  const res = await apiFetch(`${API_BASE}/ai/admin/accounts`)
  if (!res.ok) throw new Error("获取管理员账号列表失败")
  const data = await res.json()
  return data.accounts || []
}

/** 创建管理员账号 */
export async function createAdminAccount(data: { username: string; password: string; nickname?: string }): Promise<AdminAccount> {
  const res = await apiFetch(`${API_BASE}/ai/admin/accounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || "创建账号失败")
  }
  return await res.json()
}

/** 更新管理员账号 */
export async function updateAdminAccount(account_id: string, data: { nickname?: string; password?: string; enabled?: boolean }): Promise<AdminAccount> {
  const res = await apiFetch(`${API_BASE}/ai/admin/accounts/${encodeURIComponent(account_id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || "更新账号失败")
  }
  return await res.json()
}

/** 删除管理员账号 */
export async function deleteAdminAccount(account_id: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/ai/admin/accounts/${encodeURIComponent(account_id)}`, {
    method: "DELETE",
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || "删除账号失败")
  }
}

/** 管理员登录 */
export async function adminLogin(username: string, password: string): Promise<{ id: string; username: string; nickname: string }> {
  const res = await fetch(`${API_BASE}/ai/admin/accounts/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || "登录失败")
  }
  return await res.json()
}