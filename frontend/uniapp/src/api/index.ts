/**
 * API 请求层 - 基于 uni.request，对齐后端 FastAPI 接口
 * 后端路由前缀: /api/ai
 * 基址来自 config.ts，运行时可调用 setConfig({ apiBase }) 覆盖（小程序切局域网 IP 用）
 */
import { getConfig } from '@/config'
import { getToken } from '@/utils/storage'
import { interpretLiuYaoStreamWS, interpretZiWeiStreamWS, hehunStreamWS } from '@/api/chat'

// R11 共享 API 层：数据模型/文本解析器/端点常量与 Web 端共用，统一在 frontend/shared/api 维护
export type {
  AnswerFeedbackPayload, BaziProfile, ChartAnalysis, ChartCase, ChartData,
  ChatSession, DayunItem, FavoriteCase, HehunParams, KlineAnnotation,
  KlineAnnotationScope, KlineBacktest, KlineBacktestMiss, KlineBacktestSummary,
  KlineCandle, KlineData,
  KlineDayunBand, KlineDimension, KlineDimensionOption, KlineEventDomain,
  KlineEventItem, KlineEventPayload, KlineEventResult, KlineEventStats, KlineFavor,
  KlineFeedbackPayload, KlineFeedbackResult, KlineFeedbackStats, KlineMeta,
  KlinePairBacktest, KlinePairEventItem, KlinePairEventPayload, KlinePairEventResult,
  KlinePairEventStats, KlinePolarity, KlinePredictor, KlineRelation, KlineTermDiagnostic,
  KlineResonance, KlineResonanceAlign, KlineResonanceBase, KlineResonanceKind,
  KlineResonanceMeta, KlineResonanceVerdict, KlineResonanceYear,
  LiuNianItem, Pillar,
  SessionMessage, ShenshaItem, WuxingItem, XzUser,
  XiPanColumn, XiPanCurrent, XiPanDaYun, XiPanData, XiPanLiuNian,
  XiPanLiuYue, XiPanQiYun, XiPanRelationGroup, XiPanRelations, XiPanSiLing,
  XiPanSnapshot, XiPanWuxingState, XiPanMonthMeta, XiPanGanzhiMeta,
} from '@shared/api'
export type { SessionBirthInfo as BirthInfo } from '@shared/api'
export {
  parseDayun, parsePillars, parseShensha, parseWuxing,
  isSameDayun, collapseBySelection,
} from '@shared/api'
import type {
  AnswerFeedbackPayload, BaziProfile, ChartCase, ChartData, ChatSession,
  FavoriteCase, HehunParams, KlineAnnotation, KlineAnnotationScope,
  KlineBacktest, KlineData, KlineDimension, KlineEventDomain, KlineEventItem,
  KlineEventPayload, KlineEventResult, KlineEventStats, KlineFeedbackPayload,
  KlineFeedbackResult, KlineFeedbackStats, KlinePairBacktest, KlinePairEventItem,
  KlinePairEventPayload, KlinePairEventResult, KlinePairEventStats, KlinePredictor,
  KlineRelation, KlineResonance,
  SessionMessage, TarotCard, XzUser, XiPanRelations,
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
      // wx.request / uni.request 默认 60s 会掐断慢请求；主模型做重推理任务（如紫微简批）
      // 需 135s+，故对齐后端 LLM_TIMEOUT 设更长超时，避免前端先超时收不到结果。
      timeout: options.timeout ?? 240000,
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

export const interpretLiuYaoStream = (params: {
  question: string
  result: LiuYaoResult
  onMessage: (chunk: string) => void
  onComplete?: () => void
  onError?: (err: any) => void
}) => new Promise<void>((resolve) => {
  interpretLiuYaoStreamWS(params.question, params.result, {
    onMessage: params.onMessage,
    onDone: () => { params.onComplete?.(); resolve() },
    onError: (err: string) => params.onError?.(new Error(err)),
  })
})

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

export const interpretZiWeiStream = (params: {
  onMessage: (chunk: string) => void
  onComplete?: () => void
  onError?: (err: any) => void
} & ZiWeiCastParams & { focus?: string }) => new Promise<void>((resolve) => {
  interpretZiWeiStreamWS({
    date: params.date,
    time_index: params.time_index,
    gender: params.gender,
    calendar: params.calendar || 'solar',
    leap: params.leap || false,
    focus: params.focus || '',
  }, {
    onMessage: params.onMessage,
    onDone: () => { params.onComplete?.(); resolve() },
    onError: (err: string) => params.onError?.(new Error(err)),
  })
})

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

export const hehunStream = (params: HehunParams & {
  onMessage: (chunk: string) => void
  onComplete?: () => void
  onError?: (err: any) => void
}) => new Promise<void>((resolve) => {
  hehunStreamWS({
    birthTimeA: params.birthTimeA,
    genderA: params.genderA,
    birthTimeB: params.birthTimeB,
    genderB: params.genderB,
    sect: params.sect ?? 2,
    longitudeA: params.longitudeA,
    longitudeB: params.longitudeB,
  }, {
    onMessage: params.onMessage,
    onDone: () => { params.onComplete?.(); resolve() },
    onError: (err: string) => params.onError?.(new Error(err)),
  })
})

export const getCacheStats = () => get('/ai/xianzhi/cache_stats')

export const getHealth = () => get<{ status: string; rag_ready: boolean }>('/ai/health')

/* ============ 直排盘结构化数据（类型见 frontend/shared/api/types） ============ */

export const getChart = (birthTime: string, gender: string, sect = 2, yunSect = 1, longitude?: number) =>
  get<ChartData>(EP.CHART, {
    birth_time: birthTime,
    gender,
    sect,
    yun_sect: yunSect,
    ...(longitude ? { longitude } : {}),
  })

/**
 * 按点选的大运/流年/流月现算「岁运分析 / 原局分析」六栏。
 * 页面初次加载的 xipan.relations 只对应"今天"那一组，点别的年份不会变，所以点选后要回调这个接口。
 * dayun/liunian/liuyue 传干支（如 "壬申"），缺省项自动跳过（童限无大运时可只传流年/流月）。
 */
export const getRelations = (
  birthTime: string,
  gender: string,
  opts: { sect?: number; yunSect?: number; longitude?: number; dayun?: string; liunian?: string; liuyue?: string } = {}
) =>
  get<XiPanRelations>(EP.RELATIONS, {
    birth_time: birthTime,
    gender,
    sect: opts.sect ?? 2,
    yun_sect: opts.yunSect ?? 1,
    ...(opts.longitude ? { longitude: opts.longitude } : {}),
    ...(opts.dayun ? { dayun: opts.dayun } : {}),
    ...(opts.liunian ? { liunian: opts.liunian } : {}),
    ...(opts.liuyue ? { liuyue: opts.liuyue } : {}),
  })

/**
 * 命理 K 线：确定性运势评分 → 年蜡烛 + 大运带。
 * 一次只取一个维度（默认综合）；十神侧重由后端决定，前端只传 key。
 * 命盘走后端 bazi_cache，切换维度只重算评分、无需重新排盘。
 * `dimension` 为综合时不发该参数 —— 默认值由后端定义，前端不抄一份。
 * `maxDayun` 按"第几步大运"收尾（整段，不截在半个大运上）；给了它就以它为准。
 */
export const getKline = (
  birthTime: string,
  gender: string,
  opts: {
    sect?: number; yunSect?: number; longitude?: number
    maxAge?: number; maxDayun?: number; dimension?: KlineDimension
  } = {}
) =>
  get<KlineData>(EP.KLINE, {
    birth_time: birthTime,
    gender,
    sect: opts.sect ?? 2,
    yun_sect: opts.yunSect ?? 1,
    ...(opts.longitude ? { longitude: opts.longitude } : {}),
    ...(opts.maxAge ? { max_age: opts.maxAge } : {}),
    ...(opts.maxDayun ? { max_dayun: opts.maxDayun } : {}),
    ...(opts.dimension && opts.dimension !== 'comprehensive' ? { dimension: opts.dimension } : {}),
  })

/**
 * K 线批注：让大模型解读某一段运势（**不改任何分数**）。
 * 后端先算好分数再交给模型解读，且批注要过事实校验；不过则不返回文本，
 * 由 `factsOk=false` + `issues` 告知前端 —— 故调用方必须判 `ok` 再用 `text`。
 * 按 (盘, 维度, 粒度, 年份, 锚定年) 缓存，同一段二次请求不会重复花钱。
 */
export const getKlineAnnotation = (
  birthTime: string,
  gender: string,
  opts: {
    sect?: number; yunSect?: number; longitude?: number
    dimension?: KlineDimension; scope?: KlineAnnotationScope; year?: number
    maxDayun?: number
  } = {}
) =>
  post<KlineAnnotation>(EP.KLINE_ANNOTATION, {
    birth_time: birthTime,
    gender,
    sect: opts.sect ?? 2,
    yun_sect: opts.yunSect ?? 1,
    ...(opts.longitude ? { longitude: opts.longitude } : {}),
    ...(opts.dimension ? { dimension: opts.dimension } : {}),
    scope: opts.scope ?? 'overview',
    ...(opts.scope === 'year' && opts.year ? { year: opts.year } : {}),
    // 与画图同一段区间：批注里的"全期最高/最低"必须落在图上能看到的年份里
    ...(opts.maxDayun ? { max_dayun: opts.maxDayun } : {}),
  })

/**
 * 合盘共振线：两条单盘 K 线之上的**只读**叠加层，只算「关系顺逆」。
 * 年份取两盘 K 线年份的交集（起运年不同）；后端顺带返回双方喜忌摘要。
 * 权重是待校准先验 —— 调用方应把它读作**相对次序**（哪几年更顺），不是绝对吉凶。
 */
export const getKlineResonance = (
  a: { birthTime: string; gender: string },
  b: { birthTime: string; gender: string },
  opts: {
    sect?: number; yunSect?: number
    longitudeA?: number; longitudeB?: number
    dimension?: KlineDimension; maxAge?: number; maxDayun?: number
  } = {}
) =>
  post<KlineResonance>(EP.KLINE_RESONANCE, {
    birth_time_a: a.birthTime,
    gender_a: a.gender,
    birth_time_b: b.birthTime,
    gender_b: b.gender,
    sect: opts.sect ?? 2,
    yun_sect: opts.yunSect ?? 1,
    ...(opts.longitudeA ? { longitude_a: opts.longitudeA } : {}),
    ...(opts.longitudeB ? { longitude_b: opts.longitudeB } : {}),
    ...(opts.dimension ? { dimension: opts.dimension } : {}),
    ...(opts.maxAge ? { max_age: opts.maxAge } : {}),
    // 与主图同一步数，两条曲线右端才对得齐
    ...(opts.maxDayun ? { max_dayun: opts.maxDayun } : {}),
  })

/**
 * 记一条 K 线反馈（**只写不读，不影响任何分数**）。
 * 维度 + 年份 + 锚定年是必带的：反馈只有能定位到「哪张盘的哪一年」才有校准价值。
 */
export const submitKlineFeedback = (p: KlineFeedbackPayload) =>
  post<KlineFeedbackResult>(EP.KLINE_FEEDBACK, {
    birth_time: p.birthTime,
    gender: p.gender,
    dimension: p.dimension,
    scope: p.scope,
    ...(p.year ? { year: p.year } : {}),
    ...(p.anchorYear ? { anchor_year: p.anchorYear } : {}),
    rating: p.rating,
    accurate: p.accurate ?? null,
    comment: p.comment || '',
    ...(p.snapshot ? { snapshot: p.snapshot } : {}),
  })

/** 反馈汇总（均分 / 吻合率 / 按维度分布），回测校准的输入端 */
export const getKlineFeedbackStats = (dimension?: KlineDimension) =>
  get<KlineFeedbackStats>(EP.KLINE_FEEDBACK_STATS, dimension ? { dimension } : undefined)

/**
 * 录一条**真实事件标注**（回测的真相面：那一年实际发生了什么，不是"解读准不准"）。
 *
 * 命理年与公历年在 1-2 月相差一年，故优先传 `eventDate` 让后端按立春换岁推；
 * 只有年份时传 `ganzhiYear`。两者都给会被后端交叉校验，不符直接报 400。
 */
export const submitKlineEvent = (p: KlineEventPayload) =>
  post<KlineEventResult>(EP.KLINE_EVENTS, {
    birth_time: p.birthTime,
    gender: p.gender,
    sect: p.sect ?? 2,
    yun_sect: p.yunSect ?? 1,
    ...(p.longitude ? { longitude: p.longitude } : {}),
    ...(p.ganzhiYear != null ? { ganzhi_year: p.ganzhiYear } : {}),
    ...(p.eventDate ? { event_date: p.eventDate } : {}),
    polarity: p.polarity,
    domain: p.domain || 'general',
    source: p.source || '',
    note: p.note || '',
    ...(p.caseId ? { case_id: p.caseId } : {}),
  })

/** 列事件标注（可按命盘/年份/领域过滤；全空即"列最近的"） */
export const listKlineEvents = (params: {
  birthTime?: string; gender?: string; ganzhiYear?: number; domain?: KlineEventDomain; limit?: number
} = {}) =>
  get<{ items: KlineEventItem[]; count: number }>(EP.KLINE_EVENTS, {
    birth_time: params.birthTime,
    gender: params.gender,
    ganzhi_year: params.ganzhiYear,
    domain: params.domain,
    limit: params.limit,
  })

/** 删一条录错的标注（标注是人工录的，必须有回退通道） */
export const deleteKlineEvent = (id: string) =>
  del<{ ok: boolean }>(`${EP.KLINE_EVENTS}/${encodeURIComponent(id)}`)

/** 事件库总览：总量 / 吉凶分布 / 领域分布 / 涉及命盘。回测前先看它 */
export const getKlineEventStats = () => get<KlineEventStats>(EP.KLINE_EVENT_STATS)

/**
 * 跑一次回测：命中率 / 随机基线 / lift / 置信区间。
 *
 * 只报命中率没有意义（三分类随机也有约 1/3），务必连 `summary.randomBaseline`
 * 与 `summary.ci95` 一起显示；`birthTime` 为空则把库里所有盘一起回测。
 */
export const runKlineBacktest = (params: {
  birthTime?: string; gender?: string
  dimension?: KlineDimension | 'auto'; predictor?: KlinePredictor
  minSamples?: number
} = {}) =>
  get<KlineBacktest>(EP.KLINE_BACKTEST, {
    birth_time: params.birthTime,
    gender: params.gender,
    dimension: params.dimension,
    predictor: params.predictor,
    min_samples: params.minSamples,
  })

/* ---- 合盘关系事件与合盘回测（共振权重的唯一校准数据源） ----
 *
 * 与单盘事件的分工：单盘事件只能校准单盘打分口径；
 * 「这两人某年顺不顺」才是共振分该对得上的真相。
 */

/**
 * 录一条**关系事件**：那一年这两个人到底顺不顺。
 *
 * `polarity` 是**关系**的吉凶，不是某一方的个人运势 —— 同一年两人可以一个升职
 * 一个生病，但"我们俩这一年"只有一个答案。`relation` 只用于事后按关系类型分组复盘。
 */
export const submitKlinePairEvent = (p: KlinePairEventPayload) =>
  post<KlinePairEventResult>(EP.KLINE_PAIR_EVENTS, {
    birth_time_a: p.birthTimeA,
    gender_a: p.genderA,
    birth_time_b: p.birthTimeB,
    gender_b: p.genderB,
    sect: p.sect ?? 2,
    yun_sect: p.yunSect ?? 1,
    ...(p.longitudeA ? { longitude_a: p.longitudeA } : {}),
    ...(p.longitudeB ? { longitude_b: p.longitudeB } : {}),
    ...(p.ganzhiYear != null ? { ganzhi_year: p.ganzhiYear } : {}),
    ...(p.eventDate ? { event_date: p.eventDate } : {}),
    polarity: p.polarity,
    relation: p.relation || '',
    source: p.source || '',
    note: p.note || '',
  })

/** 列关系事件。四侧生辰都给时按「这一对」过滤，否则列最近的 */
export const listKlinePairEvents = (params: {
  birthTimeA?: string; genderA?: string; birthTimeB?: string; genderB?: string
  ganzhiYear?: number; limit?: number
} = {}) =>
  get<{ items: KlinePairEventItem[]; count: number }>(EP.KLINE_PAIR_EVENTS, {
    birth_time_a: params.birthTimeA,
    gender_a: params.genderA,
    birth_time_b: params.birthTimeB,
    gender_b: params.genderB,
    ganzhi_year: params.ganzhiYear,
    limit: params.limit,
  })

/** 删一条录错的关系事件 */
export const deleteKlinePairEvent = (id: string) =>
  del<{ ok: boolean }>(`${EP.KLINE_PAIR_EVENTS}/${encodeURIComponent(id)}`)

/** 关系事件库总览：总量 / 顺逆分布 / 关系类型分布 / 对数 */
export const getKlinePairEventStats = () => get<KlinePairEventStats>(EP.KLINE_PAIR_EVENT_STATS)

/**
 * 跑一次合盘回测：命中率 / 随机基线 / lift + 逐项 term 诊断。
 *
 * 没有 predictor 参数 —— 合盘只有一个预测源（共振分），给了也没别的可换。
 * `termDiagnostics` 里 `delta <= 0` 的项就是权重该调的地方。
 */
export const runKlinePairBacktest = (params: {
  birthTimeA?: string; genderA?: string; birthTimeB?: string; genderB?: string
  dimension?: KlineDimension; minSamples?: number
} = {}) =>
  get<KlinePairBacktest>(EP.KLINE_PAIR_BACKTEST, {
    birth_time_a: params.birthTimeA,
    gender_a: params.genderA,
    birth_time_b: params.birthTimeB,
    gender_b: params.genderB,
    dimension: params.dimension,
    min_samples: params.minSamples,
  })

export interface BaziCandidate { birth_time: string; ganzhi: string; shi_chen: string }
/** 根据四柱干支反推候选出生日期（用户只知八字、不知精确生辰时） */
export const inferBaziDates = (pillars: string, gender: string, topN = 1) =>
  post<{ pillars: string; gender: string; candidates: BaziCandidate[] }>(EP.INFER_DATES, { pillars, gender, top_n: topN })

/* ============ 命理报告（后台任务：提交 → 轮询 → 取结果） ============ */

export interface ReportTaskStatus {
  task_id: string
  kind: string
  status: 'pending' | 'running' | 'done' | 'failed'
  error?: string
  content?: string
}

const TASK_POLL_INTERVAL = 2000
const TASK_POLL_TIMEOUT = 15 * 60 * 1000

async function runReportTask<T extends ReportTaskStatus>(kind: string, params: Record<string, any>): Promise<T> {
  const { task_id } = await post<{ task_id: string }>('/ai/xianzhi/report/tasks', { kind, ...params })
  const deadline = Date.now() + TASK_POLL_TIMEOUT
  for (; ;) {
    await new Promise((resolve) => setTimeout(resolve, TASK_POLL_INTERVAL))
    const t = await get<T>(`/ai/xianzhi/report/tasks/${task_id}`)
    if (t.status === 'done') return t
    if (t.status === 'failed') throw new Error(t.error || '报告生成失败')
    if (Date.now() > deadline) throw new Error('报告生成超时，请稍后再试')
  }
}

export const generateFullReport = async (birthTime: string, gender: string, sections?: string[]) => {
  const t = await runReportTask<ReportTaskStatus>('full_report', {
    birth_time: birthTime,
    gender,
    sections: sections?.length ? sections.join(',') : undefined,
  })
  return { content: t.content || '' }
}

/**
 * 下载任务产物 PDF
 * 提交任务 → 轮询完成 → 下载 /result 链接
 * 小程序: uni.downloadFile + uni.openDocument
 * H5: 直接打开 URL
 */
function downloadTaskResultUrl(url: string): void {
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

function downloadReportTaskPdf(kind: string, params: Record<string, any>): void {
  runReportTask<ReportTaskStatus>(kind, params)
    .then((t) => downloadTaskResultUrl(`${getConfig().apiBase}/ai/xianzhi/report/tasks/${t.task_id}/result`))
    .catch((e: any) => uni.showToast({ title: e?.message || '报告生成失败', icon: 'none' }))
}

export const downloadReport = (birthTime: string, gender: string) =>
  downloadReportTaskPdf('basic_report', { birth_time: birthTime, gender })

export const downloadFullReportPdf = (birthTime: string, gender: string, sections?: string[]) =>
  downloadReportTaskPdf('full_report_pdf', {
    birth_time: birthTime,
    gender,
    ...(sections?.length ? { sections: sections.join(',') } : {}),
  })

/* ============ 命例管理（类型见 frontend/shared/api/types） ============ */

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

/* ============ 文本解析工具：已上收至 frontend/shared/api/parsers（顶部重导出） ============ */

/* ============ 账号登录（类型见 frontend/shared/api/types） ============ */

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

/* ============ 通用 AI 解读记录（按用户隔离，仅小程序侧） ============ */

export interface AiInterpretationRecord {
  id: string
  source: string
  question: string
  payload: Record<string, unknown>
  interpretation: string
  createdAt: string
}

export const fetchAiInterpretationRecords = () => get<AiInterpretationRecord[]>(EP.AI_INTERPRETATION_RECORDS)
export const createAiInterpretationRecord = (r: { source: string; question?: string; payload?: Record<string, unknown>; interpretation: string }) =>
  post<{ id: string }>(EP.AI_INTERPRETATION_RECORDS, r)
export const deleteAiInterpretationRecord = (id: string) => del(`${EP.AI_INTERPRETATION_RECORDS}/${id}`)

/* ============ 我的聚合 + 我的对话 ============ */

export const fetchMyOverview = () =>
  get<{ user: XzUser; stats: { profiles: number; favorites: number; aiInterpretationRecords: number; sessions: number } }>(EP.ME)
export const fetchMySessions = () => get<ChatSession[]>(EP.SESSIONS_MINE)

/* ============ 问题反馈 ============ */

export const submitFeedback = (content: string, contact?: string) =>
  post(EP.FEEDBACK, { content, contact })

/* ============ 回答反馈（点赞/点踩） ============ */

export const submitAnswerFeedback = (payload: AnswerFeedbackPayload) =>
  post<{ id: string }>(EP.FEEDBACK_ANSWER, payload)