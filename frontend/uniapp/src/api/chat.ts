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
import { getToken } from '@/utils/storage'

/** 付费解读 WS 通过 query 携带 token（浏览器/小程序 WS 不能自定义 Authorization 头）。 */
function withTokenUrl(path: string): string {
  const token = getToken()
  if (!token) return path
  return path + (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token)
}

/**
 * 先知对话：一轮的推送回调。
 * 帧已经被 SDK 按 request_id 路由好了，回调里不必再判断"这是不是本轮"。
 */
export interface XianzhiTurnHandlers {
  onMessage: (data: string) => void
  onDone: () => void
  onError: (err: string) => void
  /**
   * 后端挂盘成功通知。`birthPlace` 为后端从对话里识别到的出生地；
   * `longitude` 是**后端已按该地点算好**的经度（真太阳时口径），有就直接用，
   * 别让前端再靠城市名二次匹配 —— 匹配不到就会排出一张没校正的盘。
   */
  onChartContext?: (birthTime: string, gender: string, birthPlace?: string, longitude?: number) => void
  /** 阶段进度（"正在检索命理知识…"）：长静默期给用户反馈，别让人以为卡死 */
  onProgress?: (text: string) => void
  /**
   * done/error 之前连接就断了（后端长静默期里切页面、被系统回收、网关掐断等）。
   * 页面应清掉"推演中"状态并去会话记录里把已生成好的回答取回来。
   */
  onDisconnect?: (reason: string) => void
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

let currentTarotActive = false
let wsConnId = 0

export function closeAllWS() {
  try { wx.closeSocket() } catch { }
  dropXianzhiSocket('连接已关闭', false)
  currentTarotActive = false
  currentStreamActive = false
}

/**
 * 先知对话：一条 socket 跑多轮（多路复用）。
 *
 * 为什么这么做：小程序同一页面只有一条 socket —— 全局 `wx.onSocketMessage` 收包时
 * **分不出来源**，真机上 `SocketTask` 的方法又全是空的（见文件头踩坑记录），
 * 所以"多个会话同时生成"不可能靠多开连接（也吃 5 条 socket 上限）。
 * 改成一条连接并发跑多轮：
 *   - 每轮带一个 turnId（同时是服务端的 request_id 与 client_msg_id）；
 *   - 服务端推送的每一帧原样带回 request_id，这里按它路由到对应轮次；
 *   - 因此切会话不会再串台，也不必像旧实现那样"发新消息先掐掉旧连接"
 *     （那正是"上一轮还在生成时新建会话就崩"的根源）。
 */
export interface XianzhiChatOptions {
  conversationId: string
  /** 本轮唯一标识：既是 request_id（前端按它路由帧）也是 client_msg_id（服务端防重放） */
  turnId: string
  birthTime?: string
  gender?: string
  birthPlace?: string
  /** 出生地经度：显式传入优先于 birthPlace 反查，保证聊天挂载的盘与详情页一致 */
  longitude?: number
  sect?: number
  yunSect?: number
  token?: string
}

export interface XianzhiTurnHandle {
  turnId: string
  /**
   * 放弃接收本轮推送（例如会话被删了）。
   * 注意：**不会中断服务端生成** —— 那一轮照样跑完并落库，只是前端不再收帧。
   */
  detach: () => void
}

/** turnId → 本轮回调：帧按 request_id 路由到这里，找不到就静默丢弃 */
const xzTurns = new Map<string, XianzhiTurnHandlers>()
/** 还没连上时排队的轮次（连上后按序发出，各轮在服务端并发跑） */
let xzQueue: { payload: Record<string, any>; turnId: string }[] = []
let xzSocketOpen = false
let xzConnecting = false
/** 本连接的序号：与全模块共用的 wsConnId 比对，判断"这条连接还是不是我的" */
let xzConnId = 0
let xzConnectTimer: any = null

/** 正在生成中的轮次（页面隐藏时据此决定要不要留着连接） */
export function runningXianzhiTurns(): string[] {
  return [...xzTurns.keys()]
}

/** 连接是否还活着（页面回到前台时用它判断要不要走"取回答案"兜底） */
export function xianzhiSocketAlive(): boolean {
  return xzSocketOpen && xzConnId === wsConnId
}

/**
 * 丢弃连接并把结果告知在跑的轮次。
 *
 * `asError` 区分两类失败：
 * - true（连不上/发送失败）：重试才有用，直接 onError；
 * - false（连接断了/被关掉）：后端**不中止**生成（见后端 WS 断线策略），
 *   走 onDisconnect 让页面去会话记录里把答案取回来。
 */
function dropXianzhiSocket(reason: string, asError: boolean) {
  if (xzConnectTimer) { clearTimeout(xzConnectTimer); xzConnectTimer = null }
  xzSocketOpen = false
  xzConnecting = false
  xzQueue = []
  const pending = [...xzTurns.entries()]
  xzTurns.clear()
  for (const [, handlers] of pending) {
    if (asError) handlers.onError(reason)
    else if (handlers.onDisconnect) handlers.onDisconnect(reason)
    else handlers.onError(reason)
  }
}

function routeXianzhiFrame(frame: any) {
  if (!frame || typeof frame !== 'object') return
  const type = String(frame.type || '')
  if (type === 'ping') return
  const turnId = String(frame.request_id || '')
  if (turnId) {
    const handlers = xzTurns.get(turnId)
    // 多路复用的关键：不是本连接上"还在跑的那一轮"就丢弃。
    // 少了这一句，另一会话的 chunk 会被写进当前会话（串台）。
    if (!handlers) return
    if (type === 'message') {
      handlers.onMessage(typeof frame.data === 'string' ? frame.data : String(frame.data ?? ''))
    } else if (type === 'progress') {
      handlers.onProgress?.(String(frame.data || ''))
    } else if (type === 'chart_context') {
      const d = frame.data || {}
      handlers.onChartContext?.(d.birth_time, d.gender, d.birth_place, d.longitude)
    } else if (type === 'done') {
      xzTurns.delete(turnId)
      handlers.onDone()
    } else if (type === 'error') {
      xzTurns.delete(turnId)
      handlers.onError(String(frame.data || '服务错误'))
    }
    return
  }
  // 没有 request_id 的帧只可能是连接级错误：广播给所有在跑的轮次
  if (type === 'error') {
    const msg = String(frame.data || '服务错误')
    const pending = [...xzTurns.entries()]
    xzTurns.clear()
    for (const [, handlers] of pending) handlers.onError(msg)
  }
}

function bindXianzhiSocket(connId: number) {
  const mine = () => wsConnId === connId && xzConnId === connId
  wx.onSocketOpen(() => {
    if (!mine()) return
    if (xzConnectTimer) { clearTimeout(xzConnectTimer); xzConnectTimer = null }
    xzConnecting = false
    xzSocketOpen = true
    const queue = xzQueue
    xzQueue = []
    for (const item of queue) sendXianzhiPayload(item.payload, item.turnId)
  })
  wx.onSocketMessage((res: any) => {
    if (!mine()) return
    try {
      routeXianzhiFrame(JSON.parse(res.data as string))
    } catch (e: any) {
      console.error('[WS] 先知的帧解析失败', e)
    }
  })
  wx.onSocketError((err: any) => {
    if (!mine()) return
    dropXianzhiSocket(extractErrMsg(err, '连接错误'), true)
  })
  wx.onSocketClose(() => {
    if (!mine()) return
    dropXianzhiSocket('连接已断开', false)
  })
}

function sendXianzhiPayload(payload: Record<string, any>, turnId: string) {
  wx.sendSocketMessage({
    data: JSON.stringify(payload),
    fail: (err: any) => {
      console.error('[WS] 先知轮次发送失败 turn=', turnId, err)
      const handlers = xzTurns.get(turnId)
      if (!handlers) return
      xzTurns.delete(turnId)
      handlers.onError(extractErrMsg(err, '发送失败'))
    },
  })
}

function ensureXianzhiSocket() {
  if (xzSocketOpen || xzConnecting) return
  xzConnecting = true
  xzConnId = ++wsConnId
  bindXianzhiSocket(xzConnId)
  uni.connectSocket({ url: resolveWsBase() + wsPath('/api/ai/xianzhi/ws'), complete: () => { } })
  if (xzConnectTimer) clearTimeout(xzConnectTimer)
  xzConnectTimer = setTimeout(() => {
    xzConnectTimer = null
    if (!xzConnecting) return
    // 握手超时：如实报超时，不要盲发（未连通的 socket 必定发送失败，见 armConnectTimeout）
    try { wx.closeSocket() } catch { }
    dropXianzhiSocket('连接超时，请检查网络后重试', true)
  }, WS_CONNECT_TIMEOUT_MS)
}

/**
 * 发一轮对话。
 *
 * 可以同时发多轮（不同会话）：一条连接上各轮并发跑，帧按 turnId 各回各家。
 * 同一会话仍由服务端串行（会话锁），页面侧也不该并发发同一会话。
 */
export function sendXianzhiTurn(
  message: string,
  opts: XianzhiChatOptions,
  handlers: XianzhiTurnHandlers,
): XianzhiTurnHandle {
  const turnId = opts.turnId
  xzTurns.set(turnId, handlers)
  const payload = {
    message,
    conversation_id: opts.conversationId,
    birth_time: opts.birthTime,
    gender: opts.gender,
    birth_place: opts.birthPlace,
    longitude: opts.longitude ?? '',
    sect: opts.sect ?? 2,
    yun_sect: opts.yunSect ?? 1,
    token: opts.token || '',
    // 同一个 id 兼作防重放键：网络抖动重发时服务端直接回放上一轮结果
    client_msg_id: turnId,
    request_id: turnId,
  }
  // 别的页面（塔罗/六爻等）调过 wx.closeSocket 把连接换走了：当作断线并重连
  if (xzSocketOpen && xzConnId !== wsConnId) {
    xzSocketOpen = false
    xzQueue = []
  }
  if (xzSocketOpen) sendXianzhiPayload(payload, turnId)
  else {
    xzQueue.push({ payload, turnId })
    ensureXianzhiSocket()
  }
  return {
    turnId,
    detach: () => {
      xzTurns.delete(turnId)
      xzQueue = xzQueue.filter((item) => item.turnId !== turnId)
    },
  }
}

/**
 * 关掉先知连接（页面隐藏/离开时用）：在跑的轮次收到 onDisconnect，
 * 后端照旧跑完并落库，切回来时从会话记录取回。
 */
export function closeXianzhiSocket() {
  try { wx.closeSocket() } catch { }
  dropXianzhiSocket('连接已关闭', false)
}

export interface TarotDrawCallbacks { onCards: (cards: any[]) => void; onError: (err: string) => void }
export interface TarotInterpretCallbacks { onMessage: (chunk: string) => void; onDone: () => void; onError: (err: string) => void }

/** 塔罗抽牌 */
export function drawTarotCards(spread: 'daily' | 'three_card' | 'relationship' | 'decision' | 'celtic_cross', cb: TarotDrawCallbacks) {
  try { wx.closeSocket() } catch { }
  currentTarotActive = false
  const myId = ++wsConnId
  const url = resolveWsBase() + withTokenUrl(wsPath('/api/ai/tarot/ws'))

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
  const url = resolveWsBase() + withTokenUrl(wsPath('/api/ai/tarot/ws'))

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
  /**
   * 服务端 `{"type":"status"}` 到达时回调（可选，不实现则忽略）。
   * 用途：LLM 首个 chunk 到达前给出「已收到请求」反馈 —— 首字可能要十几秒，
   * 没有它用户会以为按钮没生效。后端在开始调模型前先发这条。
   */
  onStatus?: (message: string) => void
}

let currentStreamActive = false

function startStreamWS(path: string, payload: Record<string, any>, cb: StreamCallbacks) {
  try { wx.closeSocket() } catch { }
  currentStreamActive = false
  const myId = ++wsConnId
  const url = resolveWsBase() + withTokenUrl(wsPath(path))

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
      if (d.type === 'status') {
        // 「已收到请求」类状态：首字可能十几秒才来，没有它用户会以为按钮没生效。
        // 收到即置位 receivedMessage —— 否则随后连接抖动会被 onSocketError
        // 判成"一个字都没收到"而误报连接错误。
        receivedMessage = true
        cb.onStatus?.(d.message || '')
      } else if (d.type === 'message') {
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