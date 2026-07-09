<template>
  <view class="page">
    <!-- 状态栏占位 -->
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

    <!-- 顶部能量渐变头：标题 + 设置 + 模式 pill -->
    <view class="header">
      <view class="header-top">
        <text class="header-title display-font">先知</text>
        <view class="header-icons">
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
          :class="['tab', mode === 'cases' && 'active']"
          @tap="switchMode('cases')"
        >命例</text>
        <text
          :class="['tab', mode === 'rag' && 'active']"
          @tap="switchMode('rag')"
        >问答</text>
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

    <!-- 输入栏：深色玻璃 + 紫色渐变发送按钮 -->
    <view v-if="mode !== 'cases'" class="input-bar">
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

    <!-- 命例列表（cases 模式） -->
    <scroll-view v-if="mode === 'cases'" class="cases-scroll" scroll-y>
      <view class="cases-header">
        <view>
          <text class="cases-title">命例库</text>
          <text class="cases-sub">共 {{ cases.length }} 条命例</text>
        </view>
        <text class="cases-add-btn" @tap="openCreateCase">+ 新建</text>
      </view>

      <view v-if="loadingCases && !cases.length" class="cases-empty">
        <text class="cases-empty-icon">✦</text>
        <text class="cases-empty-text">加载中…</text>
      </view>
      <view v-else-if="!cases.length" class="cases-empty">
        <text class="cases-empty-icon">✦</text>
        <text class="cases-empty-text">尚无命例</text>
        <text class="cases-empty-hint">点击右上「新建」收藏命盘</text>
      </view>

      <view v-else class="cases-list">
        <view
          v-for="c in cases"
          :key="c.id"
          :class="['case-card', lastBirthInfo?.time === c.birthTime && 'active']"
          @tap="loadChartCase(c)"
        >
          <view class="case-head">
            <text class="case-name">{{ c.name }}</text>
            <text class="case-gender">{{ c.gender }}</text>
          </view>
          <text class="case-birth">◷ {{ c.birthTime }}</text>
          <view v-if="c.tags?.length" class="case-tags">
            <text v-for="(t, i) in c.tags" :key="i" class="case-tag">{{ t }}</text>
          </view>
          <view class="case-actions">
            <text class="case-action view" @tap.stop="loadChartCase(c)">去排盘 ➤</text>
            <text class="case-action del" @tap.stop="deleteCase(c)">删除</text>
          </view>
        </view>
      </view>
    </scroll-view>

    <!-- 新建命例弹窗（cases 模式） -->
    <view v-if="showCreateCase" class="case-modal-overlay" @tap="closeCreateCase">
      <view class="case-modal" @tap.stop>
        <view class="case-modal-header">
          <text class="case-modal-title">新建命例</text>
          <text class="case-modal-close" @tap="closeCreateCase">✕</text>
        </view>
        <view class="case-modal-body">
          <view class="cm-row">
            <text class="cm-label">名称</text>
            <input class="cm-input" v-model="caseForm.name" placeholder="如：我的命盘" cursor-spacing="120" confirm-type="next" @tap.stop />
          </view>
          <view class="cm-row">
            <text class="cm-label">出生日期</text>
            <picker class="cm-picker-wrap" mode="date" :value="caseForm.date || today" :end="today" @change="onCaseDateChange">
              <view :class="['cm-picker', caseForm.date && 'selected']">
                <text class="cm-picker-text">{{ caseForm.date || '选择日期' }}</text>
              </view>
            </picker>
          </view>

          <view class="cm-row">
            <text class="cm-label">出生时辰</text>
            <picker class="cm-picker-wrap" mode="time" :value="caseForm.time || '00:00'" @change="onCaseTimeChange">
              <view :class="['cm-picker', caseForm.time && 'selected']">
                <text class="cm-picker-text">{{ caseForm.time || '选择时间' }}</text>
              </view>
            </picker>
          </view>

          <view class="cm-row">
            <text class="cm-label">性别</text>
            <view class="cm-seg-group">
              <text :class="['cm-seg', caseForm.gender === '男' && 'active']" @tap="caseForm.gender = '男'">男</text>
              <text :class="['cm-seg', caseForm.gender === '女' && 'active']" @tap="caseForm.gender = '女'">女</text>
            </view>
          </view>
          <view class="cm-row">
            <text class="cm-label">标签</text>
            <input class="cm-input" v-model="caseForm.tags" placeholder="逗号分隔，如：事业,婚姻" cursor-spacing="120" confirm-type="done" @tap.stop />
          </view>
        </view>
        <view class="case-modal-footer">
          <text class="cm-btn" @tap="closeCreateCase">取消</text>
          <text :class="['cm-btn', 'cm-btn-primary', !canSaveCase && 'disabled']" @tap="onSaveCase">保存</text>
        </view>
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
      @close="showBaziModal = false"
    />
  </view>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, reactive } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { chatWithXianzhiWS, chatWithRagWS } from '@/api/chat'
import {
  parsePillars, parseWuxing, parseDayun, parseShensha,
  downloadReport, getChart,
  fetchChartCases, createChartCase, deleteChartCase,
  clearSessionMessages,
  type ChartData, type ChartCase,
} from '@/api'
import { getLocalDateString } from '@/utils/datetimePicker'

interface Message { role: 'user' | 'assistant'; content: string }
interface BirthInfo { time: string; gender: string }

const mode = ref<'agent' | 'cases' | 'rag'>('agent')
const showBirth = ref(false)
const birthDate = ref('')
const birthTime = ref('')
const gender = ref<'男' | '女'>('男')
const sect = ref<number>(2)
const inputText = ref('')
const thinking = ref(false)
const messages = ref<Message[]>([])
const scrollTop = ref(0)
const lastBirthInfo = ref<BirthInfo | null>(null)
const showBaziModal = ref(false)
const chartData = ref<ChartData | null>(null)
// 会话ID：同一会话内多轮对话保持一致，切换/新建会话时才重新生成
const conversationId = ref('mp-' + Date.now())

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
  if (d && t && g) {
    const time = `${d} ${t}`
    lastBirthInfo.value = { time, gender: g }
    try { chartData.value = await getChart(time, g, 2, 1) } catch { chartData.value = null }
  }
})

// 接收命例页跳转参数，自动预填并排盘
onLoad(async (query) => {
  const bt = query?.birthTime as string | undefined
  const g = query?.gender as '男' | '女' | undefined
  const name = query?.name as string | undefined
  if (bt && g) {
    const [d, t] = bt.split(' ')
    birthDate.value = d || ''
    birthTime.value = t || ''
    gender.value = g
    lastBirthInfo.value = { time: bt, gender: g }
    // 主动拉取结构化命盘
    try {
      chartData.value = await getChart(bt, g, 2, 1)
    } catch { chartData.value = null }
    // 自动发起排盘请求
    const autoMsg = name
      ? `${g}，${bt}，排盘并分析（来自命例：${name}）`
      : `${g}，${bt}，排盘并分析整体命盘`
    inputText.value = autoMsg
    onSend()
  }
})

function onDateChange(e: any) { birthDate.value = e.detail.value }
function onTimeChange(e: any) { birthTime.value = e.detail.value }
function goDisclaimer() { uni.navigateTo({ url: '/pages/legal/disclaimer' }) }
function goSettings() { uni.navigateTo({ url: '/pages/settings/index' }) }
function useExample(ex: string) { inputText.value = ex }

function switchMode(m: 'agent' | 'cases' | 'rag') {
  if (mode.value === m) return
  mode.value = m
  if (m === 'cases') {
    // 进入命例 tab 时拉取最新列表
    loadCases()
  }
}

/** 清空当前会话的消息记录，保留会话ID与命盘上下文 */
async function clearChat() {
  try {
    await clearSessionMessages('xianzhi', conversationId.value)
  } catch {}
  messages.value = []
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
  conversationId.value = 'mp-' + Date.now()
  messages.value = []
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

// =================== 命例管理 ===================
const cases = ref<ChartCase[]>([])
const loadingCases = ref(false)
const showCreateCase = ref(false)

const caseForm = reactive({
  name: '',
  date: '',
  time: '',
  gender: '男' as '男' | '女',
  tags: '',
})
const canSaveCase = computed(() => caseForm.name.trim() && caseForm.date && caseForm.time)

async function loadCases() {
  loadingCases.value = true
  try { cases.value = await fetchChartCases() }
  catch { cases.value = [] }
  finally { loadingCases.value = false }
}

function openCreateCase() {
  caseForm.name = ''
  caseForm.date = ''
  caseForm.time = ''
  caseForm.gender = '男'
  caseForm.tags = ''
  showCreateCase.value = true
}
function closeCreateCase() { showCreateCase.value = false }

function onCaseDateChange(e: any) { caseForm.date = e.detail.value }
function onCaseTimeChange(e: any) { caseForm.time = e.detail.value }

async function onSaveCase() {
  if (!canSaveCase.value) return
  const birthTime = `${caseForm.date} ${caseForm.time}`
  try {
    uni.showLoading({ title: '排盘中…' })
    await createChartCase({
      name: caseForm.name.trim(),
      birthTime,
      gender: caseForm.gender,
      tags: caseForm.tags.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
    })
    uni.hideLoading()
    uni.showToast({ title: '保存成功', icon: 'success' })
    showCreateCase.value = false
    loadCases()
  } catch (e: any) {
    uni.hideLoading()
    uni.showToast({ title: e?.message || '保存失败', icon: 'none' })
  }
}

function deleteCase(c: ChartCase) {
  uni.showModal({
    title: '确认删除',
    content: `删除命例「${c.name}」？`,
    success: async (r) => {
      if (!r.confirm) return
      try {
        await deleteChartCase(c.id)
        uni.showToast({ title: '已删除', icon: 'success' })
        loadCases()
      } catch (e: any) {
        uni.showToast({ title: e?.message || '删除失败', icon: 'none' })
      }
    },
  })
}

function loadChartCase(c: ChartCase) {
  // 把命例信息塞回 agent 模式出生信息，并切换到排盘 tab
  const [d, t] = c.birthTime.split(' ')
  birthDate.value = d || ''
  birthTime.value = t || ''
  gender.value = (c.gender as '男' | '女') || '男'
  lastBirthInfo.value = { time: c.birthTime, gender: c.gender }
  mode.value = 'agent'
  messages.value = []
  inputText.value = `${c.gender}，${c.birthTime}，排盘并分析（来自命例：${c.name}）`
  uni.showToast({ title: `已载入：${c.name}`, icon: 'none' })
  // 自动发起排盘
  nextTick(() => onSend())
}
// ==================================================

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
function tryExtractBirth(text: string) {
  const m = text.match(/(男|女)/)
  const t = text.match(/(\d{4}[-年/]\d{1,2}[-月/]\d{1,2}[日 ]+\d{1,2}[:：]\d{1,2})/)
  if (m && t) {
    const time = t[1].replace(/年|月/g, '-').replace('日', ' ').replace('：', ':').trim()
    const [d, tm] = time.split(' ')
    birthDate.value = d || ''
    birthTime.value = tm || ''
    gender.value = m[1] as '男' | '女'
    // 同步设置 lastBirthInfo，确保按钮立即显示；watch 会异步拉取 chartData
    lastBirthInfo.value = { time, gender: m[1] as '男' | '女' }
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
  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  if (mode.value === 'agent') tryExtractBirth(text)
  thinking.value = true
  scrollToBottom()

  const assistantMsg: Message = { role: 'assistant', content: '' }
  messages.value.push(assistantMsg)
  const idx = messages.value.length - 1

  const onMessage = (chunk: string) => {
    messages.value[idx].content += chunk
    scrollToBottom()
  }
  const onDone = () => { thinking.value = false }
  const onError = (err: string) => {
    thinking.value = false
    messages.value[idx].content = messages.value[idx].content || `[出错] ${err}`
  }
  // 后端从 LLM 工具调用中提取到出生信息时回调（覆盖自然语言输入场景）
  const onChartContext = async (bt: string, g: string) => {
    if (!bt || !g) return
    const [d, t] = bt.split(' ')
    birthDate.value = d || ''
    birthTime.value = t || ''
    gender.value = g as '男' | '女'
    lastBirthInfo.value = { time: bt, gender: g as '男' | '女' }
    // 主动拉取结构化命盘数据（命盘详情弹窗内容）
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
.page {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  box-sizing: border-box;
  overflow-x: hidden;
  background: linear-gradient(180deg, #160F2E 0%, #0F0B1E 100%);
  color: #E2E8F0;
}

/* 状态栏占位 - 紫青渐变 */
.status-bar {
  background: linear-gradient(135deg, #6D28D9 0%, #0891B2 100%);
  width: 100%;
}

/* === 顶部能量渐变头 === */
.header {
  width: 100%;
  box-sizing: border-box;
  background: linear-gradient(135deg, #6D28D9 0%, #7C3AED 50%, #0891B2 100%);
  padding: 16rpx 32rpx 28rpx;
  overflow: hidden;
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
  color: #ffffff;
  letter-spacing: 0.1em;
  text-shadow: 0 0 24rpx rgba(124, 58, 237, 0.5);
}
.header-actions { display: flex; }
.icon-btn {
  width: 64rpx;
  height: 64rpx;
  line-height: 60rpx;
  text-align: center;
  color: rgba(255, 255, 255, 0.85);
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
  max-width: 140rpx;
  padding: 12rpx 0;
  font-size: 26rpx;
  text-align: center;
  color: rgba(255, 255, 255, 0.7);
  border-radius: 9999rpx;
  border: 1rpx solid rgba(255, 255, 255, 0.3);
}
.tab.active {
  background: rgba(255, 255, 255, 0.95);
  color: #5B21B6;
  font-weight: 600;
  border: none;
  box-shadow: 0 0 24rpx rgba(124, 58, 237, 0.4);
}

/* === 出生信息玻璃面板 === */
.birth-panel {
  background: rgba(30, 22, 56, 0.8);
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border-bottom: 1rpx solid rgba(124, 58, 237, 0.1);
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
  color: #06B6D4;
  font-size: 28rpx;
}
.birth-summary {
  color: #E2E8F0;
  font-size: 26rpx;
  letter-spacing: 0.05em;
}
.arrow {
  color: #64748B;
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
  color: #64748B;
}
.picker {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18rpx 24rpx;
  background: rgba(15, 11, 30, 0.6);
  border-radius: 20rpx;
  border: 1rpx solid rgba(124, 58, 237, 0.2);
}
.picker-text {
  font-size: 26rpx;
  color: #E2E8F0;
}
.picker-icon {
  color: #64748B;
  font-size: 28rpx;
}
.seg-group {
  flex: 1;
  display: flex;
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 20rpx;
  overflow: hidden;
}
.seg {
  flex: 1;
  text-align: center;
  padding: 16rpx 0;
  font-size: 26rpx;
  color: #94A3B8;
  background: rgba(124, 58, 237, 0.06);
}
.seg.active {
  background: rgba(124, 58, 237, 0.25);
  color: #C4B5FD;
}
.legal-link {
  font-size: 22rpx;
  color: #94A3B8;
  margin-top: 8rpx;
}

/* === 消息列表 === */
.messages {
  flex: 1;
  padding: 24rpx 24rpx;
  overflow-x: hidden;
  width: 100%;
  box-sizing: border-box;
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
  background: linear-gradient(135deg, #7C3AED 0%, #8B5CF6 100%);
  color: #ffffff;
  border-radius: 50%;
  font-size: 56rpx;
  font-weight: 600;
  margin-bottom: 24rpx;
  box-shadow: 0 0 40rpx rgba(124, 58, 237, 0.3);
}
.empty-title {
  font-size: 34rpx;
  font-weight: 600;
  color: #E2E8F0;
  margin-bottom: 12rpx;
  letter-spacing: 0.05em;
}
.empty-desc {
  font-size: 24rpx;
  color: #64748B;
}

.examples {
  margin-top: 48rpx;
}
.examples-title {
  display: block;
  font-size: 22rpx;
  color: #64748B;
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
  color: #94A3B8;
  background: rgba(124, 58, 237, 0.1);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
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
  background: linear-gradient(135deg, #7C3AED 0%, #8B5CF6 100%);
  color: #ffffff;
  border-radius: 50%;
  font-size: 24rpx;
  font-weight: 600;
  box-shadow: 0 0 24rpx rgba(124, 58, 237, 0.3);
}
.msg.user .avatar {
  background: linear-gradient(135deg, #6D28D9 0%, #5B21B6 100%);
}
.msg-body {
  flex: 1;
  min-width: 0;
  max-width: calc(100% - 80rpx);
  display: flex;
  flex-direction: column;
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
  background: rgba(30, 22, 56, 0.8);
  backdrop-filter: blur(16rpx);
  -webkit-backdrop-filter: blur(16rpx);
  border: 1rpx solid rgba(124, 58, 237, 0.1);
  color: #E2E8F0;
  max-width: 100%;
  box-sizing: border-box;
  overflow: hidden;
}
.msg.user .msg-text {
  background: linear-gradient(135deg, #6D28D9 0%, #7C3AED 100%);
  border-radius: 28rpx 8rpx 28rpx 28rpx;
  color: #ffffff;
  border: none;
}
.msg-text.thinking { opacity: 0.7; }
.typing { color: #94A3B8; }

.report-bar {
  margin-top: 16rpx;
  display: flex;
  gap: 16rpx;
}
.report-btn {
  padding: 12rpx 24rpx;
  font-size: 22rpx;
  color: #C4B5FD;
  background: rgba(124, 58, 237, 0.1);
  border: 1rpx solid rgba(124, 58, 237, 0.3);
  border-radius: 20rpx;
}

/* === 输入栏 === */
.input-bar {
  display: flex;
  align-items: flex-end;
  padding: 20rpx 32rpx;
  background: rgba(30, 22, 56, 0.8);
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border-top: 1rpx solid rgba(124, 58, 237, 0.1);
  padding-bottom: calc(20rpx + env(safe-area-inset-bottom));
  gap: 16rpx;
}
.input-wrap {
  flex: 1;
  background: rgba(15, 11, 30, 0.6);
  border-radius: 32rpx;
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  padding: 8rpx 28rpx;
}
.input {
  width: 100%;
  min-height: 64rpx;
  max-height: 200rpx;
  padding: 14rpx 0;
  font-size: 28rpx;
  color: #E2E8F0;
}
.input-placeholder {
  color: #64748B;
}
.send-btn {
  flex-shrink: 0;
  width: 80rpx;
  height: 80rpx;
  line-height: 80rpx;
  text-align: center;
  background: linear-gradient(135deg, #7C3AED 0%, #6D28D9 100%);
  border-radius: 50%;
  box-shadow: 0 0 32rpx rgba(124, 58, 237, 0.3);
}
.send-btn.disabled { opacity: 0.5; }
.send-icon {
  color: #ffffff;
  font-size: 32rpx;
}

/* === 命例列表 === */
.cases-scroll {
  flex: 1;
  width: 100%;
  box-sizing: border-box;
  padding: 24rpx 32rpx env(safe-area-inset-bottom);
  overflow-x: hidden;
}
.cases-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  box-sizing: border-box;
  gap: 20rpx;
  margin-bottom: 24rpx;
}
.cases-header > view {
  flex: 1;
  min-width: 0;
}
.cases-title {
  font-size: 36rpx;
  font-weight: 600;
  color: #FFFFFF;
  letter-spacing: 2rpx;
}
.cases-sub {
  display: block;
  font-size: 22rpx;
  color: #94A3B8;
  margin-top: 4rpx;
}
.cases-add-btn {
  flex: 0 0 auto;
  max-width: 180rpx;
  box-sizing: border-box;
  padding: 12rpx 28rpx;
  font-size: 26rpx;
  line-height: 1.2;
  color: #FFFFFF;
  background: linear-gradient(135deg, #7C3AED, #06B6D4);
  border-radius: 32rpx;
  box-shadow: 0 4rpx 16rpx rgba(124, 58, 237, 0.35);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cases-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 120rpx 0;
  gap: 16rpx;
}
.cases-empty-icon {
  font-size: 96rpx;
  color: #7C3AED;
  opacity: 0.4;
}
.cases-empty-text {
  font-size: 30rpx;
  color: #C4B5FD;
}
.cases-empty-hint {
  font-size: 24rpx;
  color: #64748B;
}
.cases-list {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
  width: 100%;
  box-sizing: border-box;
}
.case-card {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 24rpx;
  background: rgba(30, 22, 56, 0.6);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 24rpx;
}
.case-card.active {
  border-color: #06B6D4;
  box-shadow: 0 0 0 2rpx rgba(6, 182, 212, 0.3);
}
.case-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16rpx;
  margin-bottom: 12rpx;
}
.case-name {
  flex: 1;
  min-width: 0;
  font-size: 30rpx;
  font-weight: 500;
  color: #FFFFFF;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.case-gender {
  flex: 0 0 auto;
  padding: 4rpx 16rpx;
  font-size: 22rpx;
  color: #C4B5FD;
  background: rgba(124, 58, 237, 0.2);
  border-radius: 16rpx;
}
.case-birth {
  display: block;
  width: 100%;
  font-size: 24rpx;
  color: #94A3B8;
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.case-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
  margin-top: 12rpx;
}
.case-tag {
  padding: 4rpx 12rpx;
  font-size: 20rpx;
  color: #94A3B8;
  background: rgba(6, 182, 212, 0.1);
  border-radius: 12rpx;
}
.case-actions {
  display: flex;
  gap: 16rpx;
  width: 100%;
  box-sizing: border-box;
  margin-top: 16rpx;
  padding-top: 16rpx;
  border-top: 1rpx solid rgba(124, 58, 237, 0.1);
}
.case-action {
  flex: 1;
  min-width: 0;
  box-sizing: border-box;
  text-align: center;
  padding: 10rpx 0;
  font-size: 24rpx;
  border-radius: 16rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.case-action.view {
  color: #FFFFFF;
  background: linear-gradient(135deg, #7C3AED, #06B6D4);
}
.case-action.del {
  color: #94A3B8;
  background: rgba(124, 58, 237, 0.1);
}

/* === 命例弹窗 === */
.case-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}
.case-modal {
  width: 86vw;
  max-width: 640rpx;
  max-height: 86vh;
  box-sizing: border-box;
  background: linear-gradient(160deg, rgba(30, 22, 56, 0.98), rgba(15, 11, 30, 0.98));
  border: 1rpx solid rgba(124, 58, 237, 0.3);
  border-radius: 32rpx;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.case-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  box-sizing: border-box;
  padding: 28rpx 32rpx 16rpx;
  border-bottom: 1rpx solid rgba(124, 58, 237, 0.15);
}
.case-modal-title {
  font-size: 32rpx;
  font-weight: 600;
  color: #FFFFFF;
  letter-spacing: 2rpx;
}
.case-modal-close {
  font-size: 32rpx;
  color: #94A3B8;
  padding: 8rpx 16rpx;
}
.case-modal-body {
  flex: 1;
  width: 100%;
  box-sizing: border-box;
  padding: 16rpx 32rpx;
  max-height: 60vh;
}
.case-modal-footer {
  display: flex;
  gap: 20rpx;
  width: 100%;
  box-sizing: border-box;
  padding: 20rpx 32rpx;
  padding-bottom: calc(20rpx + env(safe-area-inset-bottom));
  border-top: 1rpx solid rgba(124, 58, 237, 0.15);
}
.cm-btn {
  flex: 1;
  text-align: center;
  padding: 20rpx 0;
  font-size: 28rpx;
  border-radius: 24rpx;
  color: #94A3B8;
  background: rgba(124, 58, 237, 0.1);
}
.cm-btn-primary {
  background: linear-gradient(135deg, #7C3AED, #06B6D4);
  color: #FFFFFF;
  box-shadow: 0 4rpx 16rpx rgba(124, 58, 237, 0.4);
}
.cm-btn.disabled,
.cm-btn-primary.disabled {
  opacity: 0.4;
}
.cm-row {
  display: flex;
  align-items: center;
  gap: 20rpx;
  padding: 16rpx 0;
  width: 100%;
  box-sizing: border-box;
}
.cm-label {
  flex: 0 0 120rpx;
  font-size: 26rpx;
  color: #C4B5FD;
}
.cm-input {
  flex: 1;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
  height: 68rpx;
  line-height: 68rpx;
  padding: 0 20rpx;
  background: rgba(124, 58, 237, 0.08);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 16rpx;
  font-size: 26rpx;
  color: #FFFFFF;
}
.cm-picker-wrap {
  flex: 1;
  min-width: 0;
  display: block;
}
.cm-picker {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  height: 68rpx;
  line-height: 68rpx;
  padding: 0 20rpx;
  background: rgba(124, 58, 237, 0.08);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 16rpx;
  font-size: 26rpx;
  color: #FFFFFF;
  overflow: hidden;
}
.cm-picker.selected {
  border-color: #7C3AED;
  background: rgba(124, 58, 237, 0.18);
}
.cm-picker-text {
  display: block;
  height: 68rpx;
  line-height: 68rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cm-seg-group {
  flex: 1;
  min-width: 0;
  display: flex;
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 16rpx;
  overflow: hidden;
}
.cm-seg {
  flex: 1;
  text-align: center;
  padding: 16rpx 0;
  font-size: 26rpx;
  color: #94A3B8;
  background: rgba(124, 58, 237, 0.06);
}
.cm-seg.active {
  background: rgba(124, 58, 237, 0.25);
  color: #C4B5FD;
}
</style>
