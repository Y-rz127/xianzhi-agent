/**
 * WebSocket 聊天层 - 基于 uni.connectSocket
 *
 * 用 WebSocket 替代小程序不支持的 SSE(EventSource)。
 * 生产环境必须使用 wss:// (小程序强制)。
 *
 * 后端 WS 接口:
 *   - /ai/xianzhi/ws      先知智能体
 *   - /ai/love_app/ws      恋爱大师
 *   - /ai/xianzhi/rag/ws   RAG 知识库
 *
 * 协议:
 *   发送: JSON 对象（各接口字段略有差异）
 *   接收: { type: 'message'|'done'|'error', data: string }
 *
 * 基址来自 config.ts，运行时可调用 setConfig({ wsBase }) 覆盖
 */
import { resolveWsBase, getConfig } from '@/config'

export interface ChatWSCallbacks {
  onMessage: (data: string) => void
  onDone: () => void
  onError: (err: string) => void
  onChartContext?: (birthTime: string, gender: string) => void
  onCards?: (cards: any[]) => void
}

/** H5 dev 下走 vite proxy 的 path 前缀，prod 直连 */
function wsPath(path: string): string {
  // #ifdef H5
  if (getConfig().apiBase.startsWith('/api')) return `/ws${path}`
  return path
  // #endif
  // #ifndef H5
  return path
  // #endif
}

/**
 * 通用 WebSocket 聊天连接
 * @param path 接口 path，如 /api/ai/xianzhi/ws
 * @param payload 发送的消息体
 * @param cb 回调
 * @returns SocketTask，可调用 .close() 主动断开
 */

// 模块级引用：新建连接前先关闭旧的，避免 socket 累积超过微信小程序 5 个上限
let currentChatTask: UniApp.SocketTask | null = null
let currentTarotTask: UniApp.SocketTask | null = null

function closeTask(task: UniApp.SocketTask | null) {
  if (!task) return
  try { task.close({}) } catch {}
}

/** 关闭所有 WS 连接（页面 onHide / 切 tab 时调用） */
export function closeAllWS() {
  closeTask(currentChatTask); currentChatTask = null
  closeTask(currentTarotTask); currentTarotTask = null
}

function connectChatWS(path: string, payload: Record<string, any>, cb: ChatWSCallbacks) {
  // 发送前先关闭旧连接，保证同时只有 1 个聊天 socket
  closeTask(currentChatTask)
  const url = resolveWsBase() + wsPath(path)
  const task = uni.connectSocket({ url, complete: () => {} })
  currentChatTask = task

  task.onOpen(() => {
    task.send({ data: JSON.stringify(payload) })
  })

  task.onMessage((res) => {
    try {
      const data = JSON.parse(res.data as string)
      if (data.type === 'message') {
        cb.onMessage(data.data)
      } else if (data.type === 'cards') {
        cb.onCards?.(data.data)
      } else if (data.type === 'chart_context') {
        cb.onChartContext?.(data.data?.birth_time, data.data?.gender)
      } else if (data.type === 'done') {
        cb.onDone()
      } else if (data.type === 'error') {
        cb.onError(data.data || '服务错误')
      }
    } catch {
      cb.onError('解析消息失败')
    }
  })

  task.onError(() => cb.onError('连接错误'))
  task.onClose(() => { if (currentChatTask === task) currentChatTask = null })

  return task
}

export interface XianzhiChatOptions extends ChatWSCallbacks {
  conversationId: string
  birthTime?: string
  gender?: string
  sect?: number
  yunSect?: number
}

/** 与先知智能体流式聊天 */
export function chatWithXianzhiWS(message: string, opts: XianzhiChatOptions) {
  return connectChatWS(
    '/api/ai/xianzhi/ws',
    {
      message,
      conversation_id: opts.conversationId,
      birth_time: opts.birthTime,
      gender: opts.gender,
      sect: opts.sect ?? 2,
      yun_sect: opts.yunSect ?? 1,
    },
    opts
  )
}

export interface LoveChatOptions extends ChatWSCallbacks {
  chatId: string
}

/** 与恋爱大师流式聊天 */
export function chatWithLoveWS(message: string, opts: LoveChatOptions) {
  return connectChatWS(
    '/api/ai/love_app/ws',
    { message, chat_id: opts.chatId },
    opts
  )
}

export interface RagChatOptions extends ChatWSCallbacks {
  sessionId: string
}

/** 与 RAG 知识库流式问答 */
export function chatWithRagWS(message: string, opts: RagChatOptions) {
  return connectChatWS(
    '/api/ai/xianzhi/rag/ws',
    { message, session_id: opts.sessionId },
    opts
  )
}

export interface TarotDrawCallbacks {
  onCards: (cards: any[]) => void
  onError: (err: string) => void
}

export interface TarotInterpretCallbacks {
  onMessage: (chunk: string) => void
  onDone: () => void
  onError: (err: string) => void
}

/** 塔罗阶段一：抽牌（不调用 LLM） */
export function drawTarotCards(
  spread: 'daily' | 'three_card' | 'relationship',
  cb: TarotDrawCallbacks
) {
  closeTask(currentTarotTask)
  const url = resolveWsBase() + wsPath('/api/ai/tarot/ws')
  const task = uni.connectSocket({ url, complete: () => {} })
  currentTarotTask = task

  task.onOpen(() => {
    task.send({ data: JSON.stringify({ action: 'draw', spread }) })
  })

  task.onMessage((res) => {
    try {
      const data = JSON.parse(res.data as string)
      if (data.type === 'cards') cb.onCards(data.data || [])
      else if (data.type === 'error') cb.onError(data.data || '抽牌失败')
    } catch {
      cb.onError('解析消息失败')
    }
  })

  task.onError(() => cb.onError('连接错误'))
  task.onClose(() => { if (currentTarotTask === task) currentTarotTask = null })
  return task
}

/** 塔罗阶段二：LLM 流式解读（需要把抽到的牌组回传） */
export function interpretTarotWS(
  opts: {
    spread: 'daily' | 'three_card' | 'relationship'
    question?: string
    cards: any[]
  },
  cb: TarotInterpretCallbacks
) {
  closeTask(currentTarotTask)
  const url = resolveWsBase() + wsPath('/api/ai/tarot/ws')
  const task = uni.connectSocket({ url, complete: () => {} })
  currentTarotTask = task

  task.onOpen(() => {
    task.send({
      data: JSON.stringify({
        action: 'interpret',
        spread: opts.spread,
        question: opts.question || '',
        cards: opts.cards,
      }),
    })
  })

  task.onMessage((res) => {
    try {
      const data = JSON.parse(res.data as string)
      if (data.type === 'message') cb.onMessage(data.data)
      else if (data.type === 'done') cb.onDone()
      else if (data.type === 'error') cb.onError(data.data || '解读失败')
    } catch {
      cb.onError('解析消息失败')
    }
  })

  task.onError(() => cb.onError('连接错误'))
  task.onClose(() => { if (currentTarotTask === task) currentTarotTask = null })
  return task
}
