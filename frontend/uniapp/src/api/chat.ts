/**
 * WebSocket 聊天层 - 基于 uni.connectSocket
 *
 * 用 WebSocket 替代小程序不支持的 SSE(EventSource)。
 * 生产环境必须使用 wss:// (小程序强制)。
 *
 * 后端 WS 接口:
 *   - /ai/xianzhi/ws      先知智能体（命理问答与排盘统一入口）
 *   - /api/ai/tarot/ws       塔罗占卜
 *
 * 协议:
 *   发送: JSON 对象（各接口字段略有差异）
 *   接收: { type: 'message'|'done'|'error', data: string }
 *
 * ════════════════════════════════════════════════════════
 * 真机调试踩坑记录（血泪教训，2026-07-20）：
 *   坑1: connectSocket success 回调内 task 为 undefined
 *        → 不能在 success 里调用 task.send
 *
 *   坑2: task.onOpen 在真机上根本不触发
 *        → 不能依赖 onOpen 触发发送
 *
 *   坑3: task 对象是空对象 {}，无任何方法
 *        → send/onOpen/onMessage 全部不存在
 *
 *   ✅ 最终方案：使用 wx 全局 WebSocket API
 *      wx.onSocketOpen / wx.onSocketMessage / wx.sendSocketMessage
 *      这些全局 API 不依赖 task 对象，真机上稳定可用
 * ════════════════════════════════════════════════════════
 */
import { resolveWsBase, getConfig } from '@/config'

export interface ChatWSCallbacks {
  onMessage: (data: string) => void
  onDone: () => void
  onError: (err: string) => void
  onChartContext?: (birthTime: string, gender: string, birthPlace?: string) => void
  /** 阶段进度（"正在检索命理知识…"）：长静默期给用户反馈，别让人以为卡死 */
  onProgress?: (text: string) => void
  /**
   * done/error 之前连接就断了（后端长静默期里切页面、被系统回收、网关掐断等）。
   * 页面应清掉"推演中"状态并去会话记录里把已生成好的回答取回来。
   */
  onDisconnect?: (reason: string) => void
  onCards?: (cards: any[]) => void
}

function wsPath(path: string): string {
  // #ifdef H5
  if (getConfig().apiBase.startsWith('/api')) return `/ws${path}`
  return path
  // #endif
  // #ifndef H5
  return path
  // #endif
}

function extractErrMsg(err: any, fallback: string): string {
  if (!err) return fallback
  if (typeof err === 'string') return err
  const msg = err.errMsg || err.message || err.msg || ''
  if (msg.includes('url not in domain list')) return 'WS域名未配置，请勾选"不校验合法域名"'
  if (msg.includes('timeout')) return '连接超时，请检查网络'
  if (msg.includes('fail socket') || msg.includes('fail to connect')) return '连接失败，请检查网络后重试'
  if (msg.includes('fail')) return '连接失败，请稍后重试'
  if (msg.includes('closed') || msg.includes('断开')) return '连接已断开，正在重试…'
  return fallback
}

/**
 * 连接握手超时（ms）：正常 1s 内连上，给弱网首连留足余量。
 *
 * ⚠️ 不要退回"X 毫秒后先盲发一次"的兜底（2026-09-19 线上现场）：
 * 未连通的 socket 上 `sendSocketMessage` 必定失败，而 fail 回调会把整轮请求判死
 * （弹「发送失败」+ sent 已置位 ⇒ onSocketOpen 到达后也不再重试）—— 用户消息就这么丢了。
 * 那段兜底来自文件头「坑2：真机 task.onOpen 不触发」，但改用 wx 全局 API 之后
 * `wx.onSocketOpen` 是可靠的，盲发只剩副作用。
 * 真机若再现 onOpen 不触发，现在的症状是「连接超时」（可见、可重试），不再伪装成发送失败。
 */
const WS_CONNECT_TIMEOUT_MS = 10000

/**
 * 装配握手超时兜底，返回取消函数（onOpen / onError / onClose 都必须调用）。
 * 到点仍未 settle 就按"连不上"报错，而不是在未连通的 socket 上盲发。
 */
function armConnectTimeout(
  isMine: () => boolean,
  isSettled: () => boolean,
  onTimeout: () => void
): () => void {
  const timer = setTimeout(() => {
    if (!isMine() || isSettled()) return
    onTimeout()
  }, WS_CONNECT_TIMEOUT_MS)
  return () => clearTimeout(timer)
}

let currentChatActive = false
let currentTarotActive = false
let wsConnId = 0

export function closeAllWS() {
  try { wx.closeSocket() } catch { }
  currentChatActive = false
  currentTarotActive = false
  currentStreamActive = false
}

/**
 * 通用 WS 连接 — 使用 wx 全局 API（真机兼容）
 */
function connectChatWS(path: string, payload: Record<string, any>, cb: ChatWSCallbacks): UniApp.SocketTask | null {
  try { wx.closeSocket() } catch { }
  currentChatActive = false
  const myId = ++wsConnId

  const url = resolveWsBase() + wsPath(path)

  let receivedMessage = false
  let doneOrError = false
  let sent = false
  // 是否已连上（只有 onSocketOpen 置 true）：未连通的 socket 发不出消息，见 doSend 注释
  let opened = false
  // 握手超时兜底的取消函数（onOpen / onError / onClose 都要调）
  let cancelConnectTimeout: () => void = () => {}

  function isMine() { return wsConnId === myId }

  function doSend() {
    // 只在真正连上后发送：未连通时 sendSocketMessage 必定失败，失败回调会把整轮判死
    // （弹「发送失败」且 sent 已置位 ⇒ onSocketOpen 到达后也不再重试）—— 消息就丢了。
    if (sent || doneOrError || !opened) return
    sent = true
    wx.sendSocketMessage({
      data: JSON.stringify(payload),
      fail: (err: any) => {
        console.error('[WS] send fail id=', myId, err)
        if (!doneOrError && isMine()) { doneOrError = true; cb.onError(extractErrMsg(err, '发送失败')) }
      },
    })
  }

  wx.onSocketOpen(() => {
    if (!isMine()) return
    cancelConnectTimeout()
    opened = true
    currentChatActive = true
    doSend()
  })

  wx.onSocketMessage((res: any) => {
    if (!isMine() || !currentChatActive) return
    receivedMessage = true
    try {
      const data = JSON.parse(res.data as string)
      if (data.type === 'message') cb.onMessage(data.data)
      else if (data.type === 'cards') cb.onCards?.(data.data)
      else if (data.type === 'chart_context') cb.onChartContext?.(data.data?.birth_time, data.data?.gender, data.data?.birth_place)
      else if (data.type === 'progress') cb.onProgress?.(String(data.data || ''))
      else if (data.type === 'ping') { /* 服务端保活，忽略 */ }
      else if (data.type === 'done') { doneOrError = true; cb.onDone(); currentChatActive = false }
      else if (data.type === 'error') { doneOrError = true; cb.onError(data.data || '服务错误'); currentChatActive = false }
    } catch (e: any) {
      console.error('[WS] parse fail id=', myId, e)
      if (!doneOrError) { doneOrError = true; cb.onError('解析失败') }
    }
  })

  wx.onSocketError((err: any) => {
    console.error('[WS] onSocketError id=', myId, 'isMine=', isMine(), 'receivedMsg=', receivedMessage, 'err=', err)
    if (!isMine()) return
    cancelConnectTimeout()
    if (!receivedMessage && !doneOrError) { doneOrError = true; cb.onError(extractErrMsg(err, '连接错误')) }
    currentChatActive = false
  })

  wx.onSocketClose(() => {
    if (!isMine()) return
    cancelConnectTimeout()
    currentChatActive = false
    // 还没收到 done/error 就关了：后端可能仍在生成（本轮实测可长达 2 分钟），
    // 通知页面去取回已落库的回答，而不是让"推演中…"永远转下去
    if (!doneOrError) {
      doneOrError = true
      cb.onDisconnect?.('连接已断开')
    }
  })

  // uni.connectSocket 发起连接（走 uni-app 域名绕过），wx 全局回调收消息（真机稳定）
  uni.connectSocket({ url, complete: () => { } })

  // 握手超时兜底：连不上要如实报超时（原"500ms 后盲发一次"已删，理由见 armConnectTimeout）
  cancelConnectTimeout = armConnectTimeout(isMine, () => opened || doneOrError, () => {
    doneOrError = true
    cb.onError('连接超时，请检查网络后重试')
  })

  return null as any
}

export interface XianzhiChatOptions extends ChatWSCallbacks {
  conversationId: string
  birthTime?: string
  gender?: string
  birthPlace?: string
  sect?: number
  yunSect?: number
  token?: string
}

export function chatWithXianzhiWS(message: string, opts: XianzhiChatOptions) {
  return connectChatWS(
    '/api/ai/xianzhi/ws',
    { message, conversation_id: opts.conversationId, birth_time: opts.birthTime, gender: opts.gender, birth_place: opts.birthPlace, sect: opts.sect ?? 2, yun_sect: opts.yunSect ?? 1, token: opts.token || '' },
    opts
  )
}

export interface TarotDrawCallbacks { onCards: (cards: any[]) => void; onError: (err: string) => void }
export interface TarotInterpretCallbacks { onMessage: (chunk: string) => void; onDone: () => void; onError: (err: string) => void }

/** 塔罗抽牌 */
export function drawTarotCards(spread: 'daily' | 'three_card' | 'relationship' | 'decision' | 'celtic_cross', cb: TarotDrawCallbacks) {
  try { wx.closeSocket() } catch { }
  currentTarotActive = false
  const myId = ++wsConnId
  const url = resolveWsBase() + wsPath('/api/ai/tarot/ws')

  let receivedMessage = false, doneOrError = false, sent = false, opened = false
  let cancelConnectTimeout: () => void = () => {}
  function isMine() { return wsConnId === myId }

  function doSend() {
    // 未连通的 socket 发不出消息，且失败回调会把整轮判死（详见 armConnectTimeout 注释）
    if (sent || doneOrError || !opened) return
    sent = true
    wx.sendSocketMessage({
      data: JSON.stringify({ action: 'draw', spread }),
      fail: (err: any) => { if (!doneOrError && isMine()) { doneOrError = true; cb.onError(extractErrMsg(err, '发送失败')) } },
    })
  }

  wx.onSocketOpen(() => { if (!isMine()) return; cancelConnectTimeout(); opened = true; currentTarotActive = true; doSend() })

  wx.onSocketMessage((res: any) => {
    if (!isMine() || !currentTarotActive) return
    receivedMessage = true
    try {
      const d = JSON.parse(res.data as string)
      if (d.type === 'cards') cb.onCards(d.data || [])
      else if (d.type === 'error') { doneOrError = true; cb.onError(d.data || '抽牌失败'); currentTarotActive = false }
    } catch { if (!doneOrError) { doneOrError = true; cb.onError('解析失败') } }
  })

  wx.onSocketError((err: any) => {
    if (!isMine()) return
    cancelConnectTimeout()
    if (!receivedMessage && !doneOrError) { doneOrError = true; cb.onError(extractErrMsg(err, '连接错误')) }
    currentTarotActive = false
  })
  wx.onSocketClose(() => { if (!isMine()) return; cancelConnectTimeout(); currentTarotActive = false })

  uni.connectSocket({ url, complete: () => { } })
  cancelConnectTimeout = armConnectTimeout(isMine, () => opened || doneOrError, () => {
    doneOrError = true
    cb.onError('连接超时，请检查网络后重试')
  })

  return null as any
}

/** 塔罗解读 */
export function interpretTarotWS(opts: { spread: 'daily' | 'three_card' | 'relationship' | 'decision' | 'celtic_cross'; question?: string; cards: any[] }, cb: TarotInterpretCallbacks) {
  try { wx.closeSocket() } catch { }
  currentTarotActive = false
  const myId = ++wsConnId
  const url = resolveWsBase() + wsPath('/api/ai/tarot/ws')

  let receivedMessage = false, doneOrError = false, sent = false, opened = false
  let cancelConnectTimeout: () => void = () => {}
  function isMine() { return wsConnId === myId }

  function doSend() {
    // 未连通的 socket 发不出消息，且失败回调会把整轮判死（详见 armConnectTimeout 注释）
    if (sent || doneOrError || !opened) return
    sent = true
    wx.sendSocketMessage({
      data: JSON.stringify({ action: 'interpret', spread: opts.spread, question: opts.question || '', cards: opts.cards }),
      fail: (err: any) => { if (!doneOrError && isMine()) { doneOrError = true; cb.onError(extractErrMsg(err, '发送失败')) } },
    })
  }

  wx.onSocketOpen(() => { if (!isMine()) return; cancelConnectTimeout(); opened = true; currentTarotActive = true; doSend() })

  wx.onSocketMessage((res: any) => {
    if (!isMine() || !currentTarotActive) return
    receivedMessage = true
    try {
      const d = JSON.parse(res.data as string)
      if (d.type === 'message') {
        let msgData = d.data
        if (typeof msgData !== 'string') {
          msgData = typeof msgData === 'object' ? JSON.stringify(msgData) : String(msgData || '')
        }
        cb.onMessage(msgData)
      }
      else if (d.type === 'done') { doneOrError = true; cb.onDone(); currentTarotActive = false }
      else if (d.type === 'error') { doneOrError = true; cb.onError(d.data || '解读失败'); currentTarotActive = false }
    } catch { if (!doneOrError) { doneOrError = true; cb.onError('解析失败') } }
  })

  wx.onSocketError((err: any) => {
    if (!isMine()) return
    cancelConnectTimeout()
    if (!receivedMessage && !doneOrError) { doneOrError = true; cb.onError(extractErrMsg(err, '连接错误')) }
    currentTarotActive = false
  })
  wx.onSocketClose(() => { if (!isMine()) return; cancelConnectTimeout(); currentTarotActive = false })

  uni.connectSocket({ url, complete: () => { } })
  cancelConnectTimeout = armConnectTimeout(isMine, () => opened || doneOrError, () => {
    doneOrError = true
    cb.onError('连接超时，请检查网络后重试')
  })

  return null as any
}

/* ═══════════════════════════════════════════════════════
 * 六爻 / 紫微 / 合婚 流式解读 — 复用 wx 全局 WS API
 * ═══════════════════════════════════════════════════════ */

export interface StreamCallbacks {
  onMessage: (chunk: string) => void
  onDone: () => void
  onError: (err: string) => void
}

let currentStreamActive = false

function startStreamWS(path: string, payload: Record<string, any>, cb: StreamCallbacks) {
  try { wx.closeSocket() } catch { }
  currentStreamActive = false
  const myId = ++wsConnId
  const url = resolveWsBase() + wsPath(path)

  let receivedMessage = false, doneOrError = false, sent = false, opened = false
  let cancelConnectTimeout: () => void = () => {}
  function isMine() { return wsConnId === myId }

  function doSend() {
    // 未连通的 socket 发不出消息，且失败回调会把整轮判死（详见 armConnectTimeout 注释）
    if (sent || doneOrError || !opened) return
    sent = true
    wx.sendSocketMessage({
      data: JSON.stringify(payload),
      fail: (err: any) => { if (!doneOrError && isMine()) { doneOrError = true; cb.onError(extractErrMsg(err, '发送失败')) } },
    })
  }

  wx.onSocketOpen(() => { if (!isMine()) return; cancelConnectTimeout(); opened = true; currentStreamActive = true; doSend() })

  wx.onSocketMessage((res: any) => {
    if (!isMine() || !currentStreamActive) return
    receivedMessage = true
    try {
      const d = JSON.parse(res.data as string)
      if (d.type === 'message') {
        let msgData = d.data
        if (typeof msgData !== 'string') {
          msgData = typeof msgData === 'object' ? JSON.stringify(msgData) : String(msgData || '')
        }
        cb.onMessage(msgData)
      } else if (d.type === 'done') {
        doneOrError = true; cb.onDone(); currentStreamActive = false
      } else if (d.type === 'error') {
        doneOrError = true; cb.onError(d.detail || d.data || '解读失败'); currentStreamActive = false
      }
    } catch { if (!doneOrError) { doneOrError = true; cb.onError('解析失败') } }
  })

  wx.onSocketError((err: any) => {
    if (!isMine()) return
    cancelConnectTimeout()
    if (!receivedMessage && !doneOrError) { doneOrError = true; cb.onError(extractErrMsg(err, '连接错误')) }
    currentStreamActive = false
  })
  wx.onSocketClose(() => { if (!isMine()) return; cancelConnectTimeout(); currentStreamActive = false })

  uni.connectSocket({ url, complete: () => { } })
  cancelConnectTimeout = armConnectTimeout(isMine, () => opened || doneOrError, () => {
    doneOrError = true
    cb.onError('连接超时，请检查网络后重试')
  })
}

/** 六爻流式解读 */
export function interpretLiuYaoStreamWS(question: string, result: any, cb: StreamCallbacks) {
  startStreamWS('/api/ai/liuyao/ws', { question, result }, cb)
}

/** 紫微斗数流式解读 */
export function interpretZiWeiStreamWS(params: Record<string, any>, cb: StreamCallbacks) {
  startStreamWS('/api/ai/ziwei/ws', params, cb)
}

/** 合婚流式分析 */
export function hehunStreamWS(params: Record<string, any>, cb: StreamCallbacks) {
  startStreamWS('/api/ai/xianzhi/hehun/ws', params, cb)
}