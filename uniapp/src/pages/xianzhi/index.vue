<template>
  <view class="page">
    <!-- 水墨山水背景 -->
    <view class="landscape" aria-hidden="true">
      <view class="mountain mountain-far"></view>
      <view class="mountain mountain-mid"></view>
      <view class="mountain-mist"></view>
      <view class="mountain mountain-near"></view>
      <!-- 飞鸟 -->
      <view class="bird bird-1"></view>
      <view class="bird bird-2"></view>
      <view class="bird bird-3"></view>
      <!-- 落款印章 -->
      <!-- <view class="seal">易</view> -->
    </view>

    <!-- 状态栏占位 -->
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

    <!-- 顶部能量渐变头：标题 + 设置 + 模式 pill -->
    <view class="header">
      <view class="header-top">
        <text class="header-title display-font">先知</text>
        <view class="header-icons">
          <text class="icon-btn" @tap="openHistoryDrawer">☰</text>
          <text class="icon-btn" @tap="goSettings">⚙</text>
          <text class="icon-btn" @tap="confirmClear">🗑</text>
          <text class="icon-btn" @tap="confirmNew">+</text>
        </view>
      </view>
      <view class="mode-tabs">
        <text
          :class="['tab', mode === 'agent' && 'active']"
          @tap="switchMode('agent')"
        >排盘</text>
        <text
          :class="['tab', mode === 'rag' && 'active']"
          @tap="switchMode('rag')"
        >问答</text>
        <text class="tab" @tap="goHehun">合婚</text>
      </view>
    </view>

    <!-- 出生信息玻璃面板（仅 agent 模式） -->
    <view v-if="mode === 'agent'" class="birth-panel">
      <view class="birth-bar" @tap="showBirth = !showBirth">
        <view class="birth-bar-left">
          <text class="birth-icon">✦</text>
          <text class="birth-summary">{{ birthSummary }}</text>
        </view>
        <text class="arrow">{{ showBirth ? '▲' : '▼' }}</text>
      </view>
      <view v-if="showBirth" class="birth-form">
        <view class="form-row">
          <text class="label">出生日期</text>
          <picker mode="date" :value="birthDate" :end="today" @change="onDateChange">
            <view class="picker">
              <text class="picker-text">{{ birthDate || '选择日期' }}</text>
              <text class="picker-icon">▤</text>
            </view>
          </picker>
        </view>
        <view class="form-row">
          <text class="label">出生时辰</text>
          <picker mode="time" :value="birthTime" @change="onTimeChange">
            <view class="picker">
              <text class="picker-text">{{ birthTime || '选择时间' }}</text>
              <text class="picker-icon">◷</text>
            </view>
          </picker>
        </view>
        <view class="form-row">
          <text class="label">性别</text>
          <view class="seg-group">
            <text :class="['seg', gender === '男' && 'active']" @tap="gender = '男'">男</text>
            <text :class="['seg', gender === '女' && 'active']" @tap="gender = '女'">女</text>
          </view>
        </view>
        <view class="form-row">
          <text class="label">子时派</text>
          <view class="seg-group">
            <text :class="['seg', sect === 2 && 'active']" @tap="sect = 2">晚子时</text>
            <text :class="['seg', sect === 1 && 'active']" @tap="sect = 1">早子时</text>
          </view>
        </view>
        <view class="legal-link" @tap="goDisclaimer">查看免责声明 ›</view>
      </view>
    </view>

    <!-- 消息列表 -->
    <scroll-view class="messages" scroll-y :scroll-top="scrollTop" scroll-with-animation>
      <view v-if="!messages.length" class="empty-state">
        <view class="empty-avatar display-font">{{ mode === 'agent' ? '易' : '问' }}</view>
        <text class="empty-title">{{ mode === 'agent' ? '先知命理' : '命理问答' }}</text>
        <text class="empty-desc">{{ mode === 'agent' ? '输入出生时间，开启命理推演' : '向先知请教命理理论' }}</text>
      </view>

      <view v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
        <view class="avatar display-font">{{ msg.role === 'assistant' ? '易' : '我' }}</view>
        <view class="msg-body">
          <!-- 排盘可视化组件：优先用后端直排盘数据（保证四柱完整），否则从回答文本解析 -->

          <view class="msg-text" :class="{ thinking: isThinking(msg.content) }">
            <MarkdownRender v-if="msg.role === 'assistant' && msg.content" :content="formatContent(msg.content)" />
            <text v-else-if="!msg.content" class="typing">推演中…</text>
            <text v-else>{{ formatContent(msg.content) }}</text>
          </view>
          <!-- 最后一条助手消息的操作栏 -->
          <view v-if="mode === 'agent' && msg.role === 'assistant' && msg.content && i === messages.length - 1 && !thinking && lastBirthInfo" class="report-bar">
            <text class="report-btn" @tap="openBaziModal">查看命盘详情</text>
            <text class="report-btn" @tap="downloadPdfReport">下载 PDF 报告</text>
          </view>
        </view>
      </view>

      <!-- 示例问题 -->
      <view v-if="!messages.length" class="examples">
        <text class="examples-title">你可以问我</text>
        <view class="examples-list">
          <text
            v-for="ex in currentExamples"
            :key="ex"
            class="example-chip"
            @tap="useExample(ex)"
          >{{ ex }}</text>
        </view>
      </view>
    </scroll-view>

    <!-- 输入栏 -->
    <view class="input-bar">
      <view class="input-wrap">
        <textarea
          class="input"
          v-model="inputText"
          :placeholder="placeholderText"
          placeholder-class="input-placeholder"
          :auto-height="true"
          :show-confirm-bar="false"
          confirm-type="send"
          @confirm="onSend"
        />
      </view>
      <view
        :class="['send-btn', (thinking || !inputText.trim()) && 'disabled']"
        @tap="onSend"
      >
        <text class="send-icon">➤</text>
      </view>
    </view>

    <!-- 命盘详情弹窗 -->
    <BaziModal
      :visible="showBaziModal"
      :pillars="modalPillars"
      :wuxing="modalWuxing"
      :dayun="modalDayun"
      :liunian="chartData?.liunian || []"
      :shensha="modalShensha"
      :analysis="chartData?.analysis"
      :startYun="chartData?.startYun"
      :warnings="chartData?.warnings || []"
      :birthTime="lastBirthInfo?.time"
      :gender="lastBirthInfo?.gender"
      :mingGong="chartData?.mingGong"
      :shenGong="chartData?.shenGong"
      @close="showBaziModal = false"
    />

    <!-- 历史会话抽屉 -->
    <view v-if="showHistoryDrawer" class="drawer-mask" @tap="closeHistoryDrawer">
      <view class="drawer-panel" @tap.stop>
        <view class="drawer-header">
          <text class="drawer-title">历史会话</text>
          <text class="drawer-close" @tap="closeHistoryDrawer">✕</text>
        </view>
        <view v-if="historyLoading" class="drawer-loading">加载中…</view>
        <view v-else-if="historySessions.length === 0" class="drawer-empty">暂无历史会话</view>
        <scroll-view v-else scroll-y class="drawer-list">
          <view
            v-for="s in historySessions"
            :key="s.id"
            :class="['drawer-item', s.id === conversationId && 'active']"
            @tap="switchToSession(s)"
          >
            <view class="drawer-item-top">
              <text class="drawer-item-title">{{ s.title || '新会话' }}</text>
              <text class="drawer-item-del" @tap.stop="deleteHistorySession(s.id)">✕</text>
            </view>
            <text class="drawer-item-msg">{{ s.lastMessage || '（暂无消息）' }}</text>
            <view class="drawer-item-meta">
              <text class="drawer-item-time">{{ formatSessionTime(s.lastTime) }}</text>
              <text class="drawer-item-count">{{ s.messageCount }} 条</text>
            </view>
          </view>
        </scroll-view>
        <view class="drawer-footer">
          <text class="drawer-new-btn" @tap="closeHistoryDrawer(); newSession()">+ 新建会话</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, reactive } from 'vue'
import { onLoad, onHide, onShow } from '@dcloudio/uni-app'
import { requireLogin } from '@/utils/authGuard'
import { chatWithXianzhiWS, chatWithRagWS, closeAllWS } from '@/api/chat'
import {
  parsePillars, parseWuxing, parseDayun, parseShensha,
  downloadReport, getChart,
  fetchSessions, fetchMySessions, deleteSession as deleteSessionApi, clearSessionMessages, getSessionMessages,
  getSessionBirthInfo,
  type ChartData, type ChatSession,
} from '@/api'
import { getLocalDateString } from '@/utils/datetimePicker'
import { currentUserId, isLoggedIn } from '@/utils/storage'

interface Message { role: 'user' | 'assistant'; content: string }
interface BirthInfo { time: string; gender: string }

// 十二时辰 → HH:MM（用于把后端返回的"辰时"等标准化为 time picker 友好的格式）
const ZHI_HOUR_MAP: Record<string, string> = {
  '子': '00:00', '丑': '02:00', '寅': '04:00', '卯': '06:00',
  '辰': '08:00', '巳': '10:00', '午': '12:00', '未': '14:00',
  '申': '16:00', '酉': '18:00', '戌': '20:00', '亥': '22:00',
}
function zhiHourToHHMM(t?: string): string {
  if (!t) return ''
  // 已是 HH:MM 格式（如 "08:00"）
  if (/^\d{1,2}:\d{2}$/.test(t)) return t
  // 提取"辰时"中的"辰"
  const m = t.match(/([子丑寅卯辰巳午未申酉戌亥])/)
  if (m) return ZHI_HOUR_MAP[m[1]] || ''
  return t
}

const mode = ref<'agent' | 'rag'>('agent')
const showBirth = ref(false)
const birthDate = ref('')
const birthTime = ref('')
const gender = ref<'男' | '女'>('男')
const sect = ref<number>(2)
const inputText = ref('')
const thinking = ref(false)
// 排盘与问答使用独立的会话历史，互不干扰
const agentMessages = ref<Message[]>([])
const ragMessages = ref<Message[]>([])
// 命例 tab 单独有页面，cases 模式下不显示聊天
const messages = computed(() => mode.value === 'rag' ? ragMessages.value : agentMessages.value)
const scrollTop = ref(0)
const lastBirthInfo = ref<BirthInfo | null>(null)
// 防止 watch 与显式 getChart 调用重复请求的标志
let _skipNextChartWatch = false
const showBaziModal = ref(false)
const chartData = ref<ChartData | null>(null)
// 会话ID：编码 user_id（mp-xianzhi__<userId>__<ts>），实现多用户会话隔离
function genConversationId(): string {
  const uid = currentUserId()
  return `mp-xianzhi__${uid || 'guest'}__${Date.now()}`
}
const conversationId = ref(genConversationId())

// 历史会话抽屉
const showHistoryDrawer = ref(false)
const historySessions = ref<ChatSession[]>([])
const historyLoading = ref(false)

async function loadHistorySessions() {
  historyLoading.value = true
  try {
    // 登录后只显示自己的会话，避免多人共享后端时串号
    historySessions.value = isLoggedIn() ? await fetchMySessions() : await fetchSessions('xianzhi')
  } catch (e) {
    uni.showToast({ title: '加载历史失败', icon: 'none' })
    historySessions.value = []
  } finally {
    historyLoading.value = false
  }
}

function openHistoryDrawer() {
  showHistoryDrawer.value = true
  loadHistorySessions()
}

function closeHistoryDrawer() {
  showHistoryDrawer.value = false
}

async function switchToSession(session: ChatSession) {
  if (!session?.id) return
  conversationId.value = session.id
  // 拉取该会话的历史消息
  try {
    const msgs = await getSessionMessages('xianzhi', session.id)
    const target: Message[] = msgs.map(m => ({ role: m.role, content: m.content }))
    if (mode.value === 'rag') {
      ragMessages.value = target
    } else {
      agentMessages.value = target
      // 从后端恢复命盘上下文（支持农历/节日/时辰等自然语言输入场景）
      lastBirthInfo.value = null
      chartData.value = null
      birthDate.value = ''
      birthTime.value = ''
      gender.value = '男' as '男' | '女'
      const bi = await getSessionBirthInfo(session.id)
      if (bi.time && bi.gender) {
        lastBirthInfo.value = { time: bi.time, gender: bi.gender }
        const [d, t] = bi.time.split(' ')
        birthDate.value = d || ''
        // 时辰（如"辰时"）映射为 HH:MM，确保 time picker 能正常显示
        birthTime.value = zhiHourToHHMM(t)
        gender.value = bi.gender as '男' | '女'
        _skipNextChartWatch = true
        try { chartData.value = await getChart(bi.time, bi.gender, 2, 1) } catch { chartData.value = null }
      }
    }
  } catch (e) {
    uni.showToast({ title: '加载消息失败', icon: 'none' })
  }
  closeHistoryDrawer()
}

async function deleteHistorySession(id: string) {
  uni.showModal({
    title: '删除会话',
    content: '确定删除该会话的所有记录吗？',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await deleteSessionApi('xianzhi', id)
        // 如果删除的是当前会话，新建一个
        if (id === conversationId.value) {
          newSession()
        }
        await loadHistorySessions()
      } catch (e) {
        uni.showToast({ title: '删除失败', icon: 'none' })
      }
    },
  })
}

function formatSessionTime(t: string): string {
  if (!t) return ''
  // 后端返回形如 "2026-07-14 12:34:56+08:00"，截取到分钟
  return t.replace('T', ' ').slice(0, 16)
}

// 状态栏高度（自定义导航栏需要）
const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getWindowInfo()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}

const today = getLocalDateString()
const birthTimeFull = computed(() =>
  birthDate.value && birthTime.value ? `${birthDate.value} ${birthTime.value}` : ''
)
const birthSummary = computed(() =>
  birthTimeFull.value ? `${birthTimeFull.value} ${gender.value}` : '点击设置出生信息'
)

const agentExamples = ['男，1990-05-20 14:30，排盘并分析事业', '女，1995-08-15 08:00，看近五年运势', '男，1988-12-01 23:30，大运流年推算']
const ragExamples = ['什么是七杀？', '用神怎么取？', '大运顺逆排的规则？']
const currentExamples = computed(() => mode.value === 'agent' ? agentExamples : ragExamples)
const placeholderText = computed(() => mode.value === 'agent' ? '如：男，1990-05-20 14:30，分析事业' : '请教命理理论问题…')

// 出生信息面板手动修改时，自动重拉 chartData
watch([birthDate, birthTime, gender], async ([d, t, g]) => {
  // 显式调用 getChart 的地方（applyBirth/onChartContext/switchToSession/tryExtractBirth）
  // 已自行处理 chartData，跳过 watch 避免重复请求
  if (_skipNextChartWatch) { _skipNextChartWatch = false; return }
  if (d && t && g) {
    const time = `${d} ${t}`
    lastBirthInfo.value = { time, gender: g }
    try { chartData.value = await getChart(time, g, 2, 1) } catch { chartData.value = null }
  }
})

/** 预填出生信息并自动发起排盘（来自命例/档案带入） */
async function applyBirth(bt: string, g: '男' | '女', name?: string) {
  const [d, t] = bt.split(' ')
  birthDate.value = d || ''
  birthTime.value = zhiHourToHHMM(t)
  gender.value = g
  lastBirthInfo.value = { time: bt, gender: g }
  _skipNextChartWatch = true
  try { chartData.value = await getChart(bt, g, 2, 1) } catch { chartData.value = null }
  const autoMsg = name
    ? `${g}，${bt}，排盘并分析（来自：${name}）`
    : `${g}，${bt}，排盘并分析整体命盘`
  inputText.value = autoMsg
  onSend()
}

// 接收命例页跳转参数，自动预填并排盘
onLoad(async (query) => {
  if (query?.birthTime && query?.gender) {
    await applyBirth(query.birthTime as string, query.gender as '男' | '女', query.name as string | undefined)
  }
})

// 从「我的」页带入对话 / 继续会话：通过本地存储传递参数（tabBar 页无法用 navigateTo 传参）
onShow(() => {
  if (!requireLogin()) return
  const lp = uni.getStorageSync('XZ_LAUNCH')
  if (!lp) return
  uni.removeStorageSync('XZ_LAUNCH')
  if (lp.conversationId) {
    switchToSession({ id: lp.conversationId } as ChatSession)
  } else if (lp.birthTime && lp.gender) {
    newSession()
    applyBirth(lp.birthTime, lp.gender, lp.name)
  }
})

// 切走 tab / 页面隐藏时关闭 WS，避免 socket 累积超过小程序 5 个上限
onHide(() => { closeAllWS() })

function onDateChange(e: any) { birthDate.value = e.detail.value }
function onTimeChange(e: any) { birthTime.value = e.detail.value }
function goDisclaimer() { uni.navigateTo({ url: '/pages/legal/disclaimer' }) }
function goSettings() { uni.navigateTo({ url: '/pages/settings/index' }) }
function useExample(ex: string) { inputText.value = ex; onSend() }

function switchMode(m: 'agent' | 'rag') {
  if (mode.value === m) return
  mode.value = m
}

/** 跳转合婚页面 */
function goHehun() {
  uni.navigateTo({ url: '/pages/hehun/index' })
}

/** 清空当前会话的消息记录，保留会话ID与命盘上下文 */
async function clearChat() {
  try {
    await clearSessionMessages('xianzhi', conversationId.value)
  } catch {}
  // 按当前 mode 清空对应的会话数组
  const target = mode.value === 'rag' ? ragMessages.value : agentMessages.value
  target.splice(0, target.length)
  inputText.value = ''
}

/** 清空前确认 */
function confirmClear() {
  uni.showModal({
    title: '清空对话',
    content: '确定清空当前会话的所有消息吗？命盘信息会保留。',
    success: (res) => { if (res.confirm) clearChat() },
  })
}

/** 新建会话：生成新会话ID并清空命盘上下文 */
function newSession() {
  conversationId.value = genConversationId()
  agentMessages.value.splice(0, agentMessages.value.length)
  ragMessages.value.splice(0, ragMessages.value.length)
  inputText.value = ''
  lastBirthInfo.value = null
  chartData.value = null
  birthDate.value = ''
  birthTime.value = ''
}

/** 新建会话前确认 */
function confirmNew() {
  uni.showModal({
    title: '新建会话',
    content: '确定新建会话吗？当前对话和命盘信息将被清空。',
    success: (res) => { if (res.confirm) newSession() },
  })
}

/** 从 ReAct 输出中提取 [回答] 部分（用于解析可视化数据） */
function extractAnswer(text: string): string {
  if (!text) return ''
  const m = text.match(/\[回答\]\s*([\s\S]*)/)
  return m ? m[1] : text
}

/** 判断是否还在思考（含 ReAct 标记） */
function isThinking(content: string) {
  return typeof content === 'string' && (content.includes('[思考]') || content.includes('[行动]') || content.includes('[观察]'))
}

/** 格式化显示内容：处理 ReAct 标记 */
function formatContent(text: string): string {
  if (!text) return ''
  return text
    .replace(/\[思考\]\s*/g, '【思考】 ')
    .replace(/\[行动\]\s*/g, '【行动】 ')
    .replace(/\[观察\]\s*/g, '【观察】 ')
    .replace(/\[回答\]\s*/g, '')
    .replace(/\[结束\].*/g, '')
}

function scrollToBottom() {
  nextTick(() => {
    scrollTop.value = scrollTop.value === 99998 ? 99999 : 99998
  })
}

/** 最后一条助手消息（用于解析命盘数据给 modal） */
const lastAssistantContent = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === 'assistant') return messages.value[i].content
  }
  return ''
})
const modalPillars = computed(() => chartData.value?.pillars?.length ? chartData.value.pillars : parsePillars(extractAnswer(lastAssistantContent.value)))
const modalWuxing = computed(() => chartData.value?.wuxing?.length ? chartData.value.wuxing : parseWuxing(extractAnswer(lastAssistantContent.value)))
const modalDayun = computed(() => chartData.value?.dayun?.length ? chartData.value.dayun : parseDayun(extractAnswer(lastAssistantContent.value)))
const modalShensha = computed(() => chartData.value?.shensha?.length ? chartData.value.shensha : parseShensha(extractAnswer(lastAssistantContent.value)))

function openBaziModal() {
  if (!modalPillars.value.length && !modalWuxing.value.length) {
    uni.showToast({ title: '暂无可显示的命盘', icon: 'none' })
    return
  }
  showBaziModal.value = true
}

/** 从用户消息中提取出生信息，同步更新顶部表单（watch 会自动拉取 chartData 并设置 lastBirthInfo） */
async function tryExtractBirth(text: string) {
  const m = text.match(/(男|女)/)
  const t = text.match(/(\d{4}[-年/]\d{1,2}[-月/]\d{1,2}[日 ]+\d{1,2}[:：]\d{1,2})/)
  if (m && t) {
    const time = t[1].replace(/年|月/g, '-').replace('日', '').replace('：', ':').trim()
    // 同步设置 lastBirthInfo + 表单字段，确保按钮立即显示
    lastBirthInfo.value = { time, gender: m[1] as '男' | '女' }
    const [d, tm] = time.split(' ')
    birthDate.value = d || ''
    birthTime.value = zhiHourToHHMM(tm)
    gender.value = m[1] as '男' | '女'
    // 主动拉取 chartData（对齐 web 端 tryExtractBirth + fetchChartData 行为）
    _skipNextChartWatch = true
    try { chartData.value = await getChart(time, m[1] as '男' | '女', 2, 1) } catch { chartData.value = null }
  }
}

function downloadPdfReport() {
  if (!birthTimeFull.value && !lastBirthInfo.value) {
    uni.showToast({ title: '请先设置出生信息', icon: 'none' })
    return
  }
  const time = birthTimeFull.value || lastBirthInfo.value?.time
  const g = gender.value || lastBirthInfo.value?.gender
  if (time && g) downloadReport(time, g)
}

function onSend() {
  const text = inputText.value.trim()
  if (!text || thinking.value) return
  // 排盘 / 问答 写入不同的会话数组
  const targetList = mode.value === 'rag' ? ragMessages.value : agentMessages.value
  targetList.push({ role: 'user', content: text })
  inputText.value = ''
  if (mode.value === 'agent') tryExtractBirth(text)
  thinking.value = true
  scrollToBottom()

  const assistantMsg: Message = { role: 'assistant', content: '' }
  targetList.push(assistantMsg)
  const idx = targetList.length - 1

  const onMessage = (chunk: string) => {
    targetList[idx].content += chunk
    scrollToBottom()
  }
  const onDone = () => { thinking.value = false }
  const onError = (err: string) => {
    thinking.value = false
    targetList[idx].content = targetList[idx].content || `[出错] ${err}`
  }
  // 后端从 LLM 工具调用中提取到出生信息时回调（覆盖自然语言输入场景）
  const onChartContext = async (bt: string, g: string) => {
    if (!bt || !g) return
    const [d, t] = bt.split(' ')
    birthDate.value = d || ''
    birthTime.value = zhiHourToHHMM(t)
    gender.value = g as '男' | '女'
    lastBirthInfo.value = { time: bt, gender: g as '男' | '女' }
    // 主动拉取结构化命盘数据（命盘详情弹窗内容）
    _skipNextChartWatch = true
    try {
      chartData.value = await getChart(bt, g, 2, 1)
    } catch {
      chartData.value = null
    }
  }

  if (mode.value === 'agent') {
    chatWithXianzhiWS(text, {
      conversationId: conversationId.value,
      birthTime: birthTimeFull.value || undefined,
      gender: gender.value,
      sect: sect.value,
      onMessage, onDone, onError, onChartContext,
    })
  } else {
    chatWithRagWS(text, {
      sessionId: 'rag-' + Date.now(),
      onMessage, onDone, onError,
    })
  }
}

// 初始欢迎语
messages.value.push({
  role: 'assistant',
  content: mode.value === 'agent'
    ? '您好，我是先知。请设置出生信息后提问，如「男，1990-05-20 14:30，排盘分析事业」。'
    : '您好，可向我请教命理理论问题，如「什么是七杀？」。',
})
</script>

<style lang="scss">
/* === 先知 · 白底黑字水墨风 + 太极图背景 === */
.page {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  box-sizing: border-box;
  overflow-x: hidden;
  background: $color-bg;
  color: $color-ink;
}

/* === 水墨山水背景 === */
.landscape {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

/* 山的通用样式 */
.mountain {
  position: absolute;
  left: 0;
  right: 0;
  pointer-events: none;
}

/* 远山 - 最浅、最低起伏 */
.mountain-far {
  bottom: 0;
  height: 45%;
  background: linear-gradient(to top,
    rgba(26, 26, 26, 0.22) 0%,
    rgba(26, 26, 26, 0.12) 60%,
    rgba(26, 26, 26, 0) 100%);
  clip-path: polygon(
    0% 100%,
    0% 75%, 8% 68%, 15% 72%, 22% 60%, 30% 65%, 38% 55%, 45% 62%, 52% 50%, 60% 58%, 68% 52%, 75% 60%, 82% 55%, 90% 62%, 100% 58%,
    100% 100%
  );
}

/* 中山 - 中等深度 */
.mountain-mid {
  bottom: 0;
  height: 38%;
  background: linear-gradient(to top,
    rgba(26, 26, 26, 0.38) 0%,
    rgba(26, 26, 26, 0.22) 50%,
    rgba(26, 26, 26, 0.08) 100%);
  clip-path: polygon(
    0% 100%,
    0% 70%, 6% 60%, 14% 68%, 20% 55%, 28% 62%, 35% 50%, 42% 58%, 50% 45%, 58% 55%, 65% 48%, 72% 58%, 80% 52%, 88% 60%, 95% 55%, 100% 62%,
    100% 100%
  );
}

/* 山间云雾 */
.mountain-mist {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 28%;
  height: 12%;
  background: linear-gradient(to bottom,
    rgba(250, 250, 248, 0.85) 0%,
    rgba(250, 250, 248, 0.4) 50%,
    rgba(250, 250, 248, 0) 100%);
  pointer-events: none;
  z-index: 1;
}

/* 近山 - 最深、最高 */
.mountain-near {
  bottom: 0;
  height: 32%;
  background: linear-gradient(to top,
    rgba(26, 26, 26, 0.6) 0%,
    rgba(26, 26, 26, 0.35) 50%,
    rgba(26, 26, 26, 0.1) 100%);
  clip-path: polygon(
    0% 100%,
    0% 65%, 10% 50%, 18% 58%, 28% 42%, 38% 52%, 48% 38%, 56% 48%, 66% 40%, 74% 52%, 84% 45%, 92% 55%, 100% 48%,
    100% 100%
  );
}

/* 飞鸟 - V 形 */
.bird {
  position: absolute;
  width: 28rpx;
  height: 16rpx;
  pointer-events: none;
  z-index: 2;
}
.bird::before,
.bird::after {
  content: '';
  position: absolute;
  top: 0;
  width: 14rpx;
  height: 14rpx;
  border: 2rpx solid rgba(26, 26, 26, 0.45);
  border-bottom: none;
  border-right: none;
  border-radius: 50% 0 0 0;
}
.bird::before { left: 0; transform: rotate(45deg); }
.bird::after { right: 0; transform: rotate(135deg) scaleX(-1); transform-origin: top right; }

.bird-1 {
  top: 22%;
  left: 20%;
  animation: birdDrift 18s ease-in-out infinite;
}
.bird-2 {
  top: 18%;
  left: 55%;
  transform: scale(0.8);
  opacity: 0.7;
  animation: birdDrift 20s ease-in-out infinite -6s;
}
.bird-3 {
  top: 28%;
  right: 18%;
  transform: scale(0.9);
  opacity: 0.5;
  animation: birdDrift 22s ease-in-out infinite -12s;
}
@keyframes birdDrift {
  0% { transform: translate(0, 0) scale(var(--s, 1)); }
  50% { transform: translate(40rpx, -20rpx) scale(var(--s, 1)); }
  100% { transform: translate(0, 0) scale(var(--s, 1)); }
}

/* 落款印章 */
.seal {
  position: absolute;
  bottom: 10%;
  right: 6%;
  width: 56rpx;
  height: 56rpx;
  line-height: 52rpx;
  text-align: center;
  background: $color-vermilion;
  color: $color-bg;
  font-size: 32rpx;
  font-weight: 600;
  font-family: $font-family-display;
  border: 2rpx solid $color-vermilion;
  box-shadow: 0 0 12rpx rgba(184, 72, 60, 0.25);
  opacity: 0.78;
  transform: rotate(-3deg);
  pointer-events: none;
  z-index: 2;
}

/* 状态栏占位 */
.status-bar {
  background: $color-bg;
  width: 100%;
  position: relative;
  z-index: 1;
}

/* === 顶部标题头 === */
.header {
  width: 100%;
  box-sizing: border-box;
  background: $color-bg;
  border-bottom: 1rpx solid $color-border;
  padding: 16rpx 32rpx 28rpx;
  overflow: hidden;
  position: relative;
  z-index: 1;
}
.header-top {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-start;
}
.header-icons {
  position: absolute;
  left: 0;
  right: 0;
  display: flex;
  justify-content: center;
  gap: 24rpx;
  pointer-events: none;
}
.header-icons .icon-btn {
  pointer-events: auto;
}
.header-title {
  font-size: 40rpx;
  font-weight: 600;
  color: $color-primary;
  letter-spacing: 0.12em;
}
.icon-btn {
  width: 64rpx;
  height: 64rpx;
  line-height: 60rpx;
  text-align: center;
  color: $color-ink-light;
  font-size: 36rpx;
}

/* 模式切换 pill */
.mode-tabs {
  display: flex;
  gap: 16rpx;
  margin-top: 24rpx;
  width: 100%;
  box-sizing: border-box;
  overflow: hidden;
  align-items: center;
}
.tab {
  flex: 1;
  min-width: 0;
  max-width: 160rpx;
  padding: 12rpx 0;
  font-size: 26rpx;
  text-align: center;
  color: $color-ink-light;
  border-radius: 9999rpx;
  border: 1rpx solid $color-border;
}
.tab.active {
  background: $color-primary;
  color: $color-bg;
  font-weight: 600;
  border: none;
}

/* === 出生信息面板 === */
.birth-panel {
  background: $color-bg-card;
  border-bottom: 1rpx solid $color-border;
  position: relative;
  z-index: 1;
}
.birth-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 32rpx;
}
.birth-bar-left {
  display: flex;
  align-items: center;
  gap: 16rpx;
}
.birth-icon {
  color: $color-vermilion;
  font-size: 28rpx;
}
.birth-summary {
  color: $color-ink;
  font-size: 26rpx;
  letter-spacing: 0.05em;
}
.arrow {
  color: $color-ink-lighter;
  font-size: 22rpx;
}
.birth-form {
  padding: 16rpx 32rpx 28rpx;
}
.form-row {
  display: flex;
  align-items: center;
  margin-bottom: 20rpx;
  gap: 16rpx;
}
.label {
  width: 140rpx;
  font-size: 24rpx;
  color: $color-ink-lighter;
}
.picker {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18rpx 24rpx;
  background: $color-bg-warm;
  border-radius: 20rpx;
  border: 1rpx solid $color-border;
}
.picker-text {
  font-size: 26rpx;
  color: $color-ink;
}
.picker-icon {
  color: $color-ink-lighter;
  font-size: 28rpx;
}
.seg-group {
  flex: 1;
  display: flex;
  border: 1rpx solid $color-border;
  border-radius: 20rpx;
  overflow: hidden;
}
.seg {
  flex: 1;
  text-align: center;
  padding: 16rpx 0;
  font-size: 26rpx;
  color: $color-ink-light;
  background: $color-bg-warm;
}
.seg.active {
  background: rgba(44, 44, 44, 0.08);
  color: $color-primary;
}
.legal-link {
  font-size: 22rpx;
  color: $color-ink-light;
  margin-top: 8rpx;
}

/* === 消息列表 === */
.messages {
  flex: 1;
  padding: 24rpx 24rpx;
  overflow-x: hidden;
  width: 100%;
  box-sizing: border-box;
  position: relative;
  z-index: 1;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60rpx 0;
}
.empty-avatar {
  width: 128rpx;
  height: 128rpx;
  line-height: 128rpx;
  text-align: center;
  background: $color-primary;
  color: $color-bg;
  border-radius: 50%;
  font-size: 56rpx;
  font-weight: 600;
  margin-bottom: 24rpx;
  border: 1rpx solid $color-primary;
}
.empty-title {
  font-size: 34rpx;
  font-weight: 600;
  color: $color-ink;
  margin-bottom: 12rpx;
  letter-spacing: 0.05em;
}
.empty-desc {
  font-size: 24rpx;
  color: $color-ink-lighter;
}

.examples {
  margin-top: 48rpx;
}
.examples-title {
  display: block;
  font-size: 22rpx;
  color: $color-ink-lighter;
  margin-bottom: 16rpx;
}
.examples-list {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
}
.example-chip {
  display: inline-block;
  padding: 12rpx 24rpx;
  font-size: 24rpx;
  color: $color-ink-light;
  background: rgba(44, 44, 44, 0.04);
  border: 1rpx solid $color-border;
  border-radius: 28rpx;
}

/* === 消息项 === */
.msg {
  display: flex;
  margin-bottom: 32rpx;
  gap: 16rpx;
  align-items: flex-start;
  padding: 0 8rpx;
  width: 100%;
  box-sizing: border-box;
}
.msg.user {
  flex-direction: row-reverse;
}
.avatar {
  flex-shrink: 0;
  width: 64rpx;
  height: 64rpx;
  line-height: 64rpx;
  text-align: center;
  background: $color-primary;
  color: $color-bg;
  border-radius: 50%;
  font-size: 24rpx;
  font-weight: 600;
  border: 1rpx solid $color-primary;
  position: relative;
  z-index: 2;
}
.msg.user .avatar {
  background: $color-vermilion;
  border-color: $color-vermilion;
}
.msg-body {
  flex: 1;
  min-width: 0;
  max-width: calc(100% - 80rpx);
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
  box-sizing: border-box;
}
.msg.user .msg-body {
  align-items: flex-end;
}
.msg-text {
  padding: 20rpx 28rpx;
  border-radius: 8rpx 28rpx 28rpx 28rpx;
  font-size: 28rpx;
  line-height: 1.6;
  word-break: break-all;
  overflow-wrap: break-word;
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  color: $color-ink;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  overflow: hidden;
  box-shadow: $shadow-sm;
}
.msg.user .msg-text {
  background: $color-primary;
  border-radius: 28rpx 8rpx 28rpx 28rpx;
  color: $color-bg;
  border: none;
}
.msg-text.thinking { opacity: 0.7; }
.typing { color: $color-ink-light; }

.report-bar {
  margin-top: 16rpx;
  display: flex;
  gap: 16rpx;
  max-width: 100%;
  box-sizing: border-box;
}
.report-btn {
  padding: 12rpx 24rpx;
  font-size: 22rpx;
  color: $color-primary;
  background: rgba(44, 44, 44, 0.04);
  border: 1rpx solid $color-border;
  border-radius: 20rpx;
}

/* === 输入栏 === */
.input-bar {
  display: flex;
  align-items: flex-end;
  padding: 16rpx 32rpx 16rpx;
  background: $color-bg-card;
  border-top: 1rpx solid $color-border;
  gap: 16rpx;
  position: relative;
  z-index: 1;
  margin-bottom: -16rpx;
}
.input-wrap {
  flex: 1;
  background: $color-bg-warm;
  border-radius: 32rpx;
  border: 1rpx solid $color-border;
  padding: 8rpx 28rpx;
}
.input {
  width: 100%;
  min-height: 64rpx;
  max-height: 200rpx;
  padding: 14rpx 0;
  font-size: 28rpx;
  color: $color-ink;
}
.input-placeholder {
  color: $color-ink-lighter;
}
.send-btn {
  flex-shrink: 0;
  width: 80rpx;
  height: 80rpx;
  line-height: 80rpx;
  text-align: center;
  background: $color-primary;
  border-radius: 50%;
  border: 1rpx solid $color-primary;
}
.send-btn.disabled { opacity: 0.5; }
.send-icon {
  color: $color-bg;
  font-size: 32rpx;
}

/* ============ 历史会话抽屉 ============ */
.drawer-mask {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 1000;
}
.drawer-panel {
  position: fixed;
  top: 0; left: 0; bottom: 0;
  width: 80%;
  max-width: 600rpx;
  background: $color-bg-warm;
  display: flex;
  flex-direction: column;
  z-index: 1001;
  box-shadow: 4rpx 0 24rpx rgba(0, 0, 0, 0.15);
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 30rpx 32rpx 20rpx;
  border-bottom: 1rpx solid rgba(44, 44, 44, 0.1);
}
.drawer-title {
  font-size: 34rpx;
  font-weight: 600;
  color: $color-primary;
  font-family: 'STKaiti', 'KaiTi', serif;
}
.drawer-close {
  font-size: 36rpx;
  color: $color-ink-light;
  padding: 8rpx 16rpx;
}
.drawer-loading, .drawer-empty {
  padding: 60rpx 0;
  text-align: center;
  font-size: 26rpx;
  color: $color-ink-light;
}
.drawer-list {
  flex: 1;
  padding: 12rpx 0;
}
.drawer-item {
  padding: 24rpx 32rpx;
  border-bottom: 1rpx solid rgba(44, 44, 44, 0.06);
  transition: background 0.2s;
}
.drawer-item.active {
  background: rgba(44, 44, 44, 0.04);
}
.drawer-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8rpx;
}
.drawer-item-title {
  font-size: 28rpx;
  color: $color-ink;
  font-weight: 500;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.drawer-item-del {
  font-size: 28rpx;
  color: $color-ink-light;
  padding: 4rpx 12rpx;
}
.drawer-item-msg {
  display: block;
  font-size: 24rpx;
  color: $color-ink-light;
  margin-bottom: 6rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.drawer-item-meta {
  display: flex;
  justify-content: space-between;
}
.drawer-item-time, .drawer-item-count {
  font-size: 22rpx;
  color: $color-ink-light;
}
.drawer-footer {
  padding: 20rpx 32rpx 30rpx;
  border-top: 1rpx solid rgba(44, 44, 44, 0.08);
}
.drawer-new-btn {
  display: block;
  text-align: center;
  padding: 18rpx 0;
  font-size: 28rpx;
  color: $color-bg-warm;
  background: $color-primary;
  border-radius: 12rpx;
}
</style>
