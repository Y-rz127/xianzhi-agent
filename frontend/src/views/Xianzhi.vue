<template>
  <div class="chat-view">
    <div class="sidebar-mask" v-if="!sidebarCollapsed && isMobile" @click="sidebarCollapsed = true"></div>
    <div class="chat-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <span v-if="!sidebarCollapsed" class="sidebar-title">历史会话</span>
        <button class="sidebar-toggle" @click="sidebarCollapsed = !sidebarCollapsed" aria-label="收起侧边栏">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
        </button>
      </div>
      <div class="sessions-list" v-if="!sidebarCollapsed">
        <div v-if="sessions.length === 0" class="no-sessions">暂无历史会话</div>
        <div v-for="s in sessions" :key="s.id" :class="['session-item', { active: s.id === conversationId }]" @click="loadSession(s)">
          <div class="session-title">{{ s.title }}</div>
          <div class="session-meta">{{ formatTime(s.lastTime) }} · {{ s.messageCount }}条</div>
          <button class="session-delete" @click.stop="deleteSessionItem(s.id)" aria-label="删除会话">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      </div>
      <div class="cases-header" v-if="!sidebarCollapsed">
        <span class="sidebar-title">命例快照</span>
        <div class="cases-actions">
          <button class="btn btn-xs" @click="exportCaseCard" title="导出命例卡片" :disabled="chartCases.length === 0">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>
          </button>
          <button class="btn btn-xs" @click="openManualCaseModal" title="手动录入命例">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          </button>
        </div>
      </div>
      <div class="cases-list" v-if="!sidebarCollapsed">
        <div v-if="chartCases.length === 0" class="no-sessions">暂无命例</div>
        <div v-for="c in chartCases" :key="c.id" :class="['session-item', { active: c.birthTime === lastBirthInfo?.time }]" @click="loadChartCase(c)">
          <div class="session-title">{{ c.name }}</div>
          <div class="session-meta">{{ c.birthTime }} · {{ c.gender }}</div>
          <div class="case-tags">
            <span v-for="tag in c.tags" :key="tag" class="case-tag">{{ tag }}</span>
          </div>
          <button class="session-delete" @click.stop="deleteChartCaseItem(c.id)" aria-label="删除命例">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      </div>
    </div>

    <div class="chat-main">
      <header class="chat-header">
        <div class="header-left">
          <button class="app-sidebar-toggle" @click="toggleAppSidebar" aria-label="切换导航">
            <svg v-if="appSidebarOpen" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 18L18 6M6 6l12 12"/></svg>
            <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
          </button>
          <button class="pc-sidebar-toggle" @click="toggleSidebar" :aria-label="sidebarCollapsed ? '展开历史会话' : '收起历史会话'">
            <svg v-if="sidebarCollapsed" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
            <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
          </button>
          <div>
            <h2>{{ mode === "agent" ? "先知·八字命理" : "命理知识库" }}</h2>
            <div class="header-info">{{ mode === "agent" ? "更懂你的AI命理师" : "探索命理奥秘" }}</div>
          </div>
        </div>
        <div class="header-right">
          <div class="sect-selector" v-if="mode === 'agent'">
            <select id="sect-select" name="sect-select" aria-label="日柱精度" v-model="sect" class="sect-select">
              <option :value="2">精确2</option>
              <option :value="1">精确1</option>
            </select>
            <select id="yun-sect-select" name="yun-sect-select" aria-label="大运精度" v-model="yunSect" class="sect-select">
              <option :value="1">天数时辰</option>
              <option :value="2">分钟数</option>
            </select>
          </div>
          <div class="mode-tabs">
            <button :class="['tab', { active: mode === 'agent' }]" @click="switchMode('agent')" aria-label="智能体排盘">排盘</button>
            <button :class="['tab', { active: mode === 'rag' }]" @click="switchMode('rag')" aria-label="知识问答">问答</button>
          </div>
          <button v-if="mode === 'agent'" class="btn header-btn btn-accent" @click="showBaziModal" title="命盘详情">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
            命盘
          </button>
          <button class="btn header-btn" @click="clearChat" title="清空">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
          <button class="btn header-btn" @click="newSession" title="新会话">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          </button>
          <button class="btn header-btn" @click="exportChat" title="导出">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>
          </button>
          <button v-if="mode === 'agent' && lastBirthInfo" class="btn header-btn btn-accent" @click="openCaseModal" title="保存命例">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            存命例
          </button>
        </div>
      </header>

      <div class="messages" ref="messagesEl" @scroll="onScroll">
        <div v-if="!messages.length" class="empty-state">
          <div class="orbit-ring"></div>
          <div class="empty-center">
            <div class="empty-icon">{{ mode === "agent" ? "易" : "问" }}</div>
            <h3>{{ mode === "agent" ? "欢迎来到先知命理" : "命理知识问答" }}</h3>
            <p>{{ mode === "agent" ? "输入出生时间与性别，开启你的命理推演之旅" : "向先知请教命理理论" }}</p>
          </div>
          <div class="examples">
            <button v-for="ex in currentExamples" :key="ex" class="example-btn" @click="useExample(ex)" aria-label="示例">{{ ex }}</button>
          </div>
        </div>

        <div v-if="hasMoreHistory" class="load-more-bar">
          <button class="load-more-btn" @click="loadMoreHistory">查看更多历史消息</button>
        </div>

        <template v-for="(msg, i) in visibleMessages" :key="messages.length - visibleMessages.length + i">
          <div v-if="msg.content || !loading" :class="msgClass(msg.role)" :style="{ animationDelay: `${i * 0.05}s` }">
            <div class="msg-avatar-wrap">
              <div class="msg-avatar">
                <svg v-if="msg.role === 'user'" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><path d="M2 12h20"/></svg>
              </div>
              <div class="msg-role">{{ msg.role === "user" ? "你" : "先知" }}</div>
            </div>
            <div class="msg-body">
              <BaziCard v-if="mode === 'agent' && msg.role === 'assistant'" :pillars="parsePillars(msg.content)" />
              <WuxingChart v-if="mode === 'agent' && msg.role === 'assistant'" :items="parseWuxing(msg.content)" />
              <DayunTimeline v-if="mode === 'agent' && msg.role === 'assistant' && parsedDayun.length" :dayun="parsedDayun" />
              <div class="msg-content" :class="{ 'thinking': isThinking(msg.content) }">
                <MarkdownRender v-if="msg.role === 'assistant'" :content="formatContent(msg.content)" />
                <pre v-else>{{ msg.content }}</pre>
              </div>
              <div v-if="mode === 'agent' && msg.role === 'assistant' && lastBirthInfo" class="report-bar">
                <button class="report-btn" @click="showBaziModal" aria-label="查看命盘详情">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                  查看命盘详情
                </button>
                <button class="report-btn" @click="downloadReport(lastBirthInfo.time, lastBirthInfo.gender)" aria-label="下载 PDF 报告">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M12 18v-6"/><path d="M9 15l3 3 3-3"/></svg>
                  下载 PDF 报告
                </button>
              </div>
            </div>
          </div>
        </template>

        <div v-if="loading" class="msg assistant loading-msg">
          <div class="msg-avatar-wrap">
            <div class="msg-avatar">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><path d="M2 12h20"/></svg>
            </div>
            <div class="msg-role">先知</div>
          </div>
          <div class="msg-body">
            <div class="msg-content loading-content">
              <span class="loading-text">正在为您推演分析，请稍候</span>
              <div class="loading-dots"><span></span><span></span><span></span></div>
            </div>
          </div>
        </div>

        <div v-if="showScrollTop" class="scroll-top-btn" @click="scrollToBottom" aria-label="回到底部">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><polyline points="7 13 12 18 17 13"/><line x1="12" y1="18" x2="12" y2="3"/></svg>
        </div>
      </div>

      <div class="input-area">
        <div class="input-wrap">
          <textarea id="chat-input" name="chat-input" aria-label="消息输入" v-model="input" @keydown="handleKeydown" :placeholder="placeholderText" :disabled="loading" rows="1"></textarea>
          <div class="input-actions">
            <button class="btn send-btn" @click="send" :disabled="loading || !input.trim()" aria-label="发送">
              <span v-if="!loading">发送</span>
              <span v-else>推演中</span>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polyline points="22 2 15 22 11 13 2 9 22 2"/></svg>
            </button>
          </div>
        </div>
        <div class="input-hint">按 Enter 发送 · Shift+Enter 换行</div>
      </div>
    </div>

    <BaziModal
      :visible="showModal"
      :pillars="modalPillars"
      :wuxing="modalWuxing"
      :dayun="modalDayun"
      :liunian="modalLiunian"
      :shensha="modalShensha"
      :analysis="chartData?.analysis"
      :startYun="chartData?.startYun"
      :warnings="chartData?.warnings || []"
      :birthTime="lastBirthInfo?.time"
      :gender="lastBirthInfo?.gender"
      @close="showModal = false"
    />

    <Teleport to="body">
      <div v-if="showCaseModal" class="case-modal-overlay" @click.self="closeCaseModal">
        <div class="case-modal">
          <div class="case-modal-header">
            <div class="case-modal-title">{{ caseModalMode === 'manual' ? '新建命例' : '保存命例' }}</div>
            <button class="modal-close" @click="closeCaseModal" aria-label="关闭">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="case-modal-body">
            <div class="form-row">
              <label for="case-name">名称</label>
              <input id="case-name" name="case-name" v-model="caseName" placeholder="例如：我的命盘" />
            </div>
            <div class="form-row">
              <label for="case-tags">标签</label>
              <input id="case-tags" name="case-tags" v-model="caseTags" placeholder="用逗号分隔，如：事业,婚姻" />
            </div>
            <div class="form-row">
              <label for="case-birth-time">出生时间</label>
              <input id="case-birth-time" name="case-birth-time" aria-label="出生时间" v-model="caseBirthTime" :disabled="caseModalMode !== 'manual'" placeholder="1990-05-20 14:30" />
            </div>
            <div class="form-row">
              <label for="case-gender">性别</label>
              <select id="case-gender" name="case-gender" aria-label="性别" v-model="caseGender" :disabled="caseModalMode !== 'manual'">
                <option value="男">男</option>
                <option value="女">女</option>
              </select>
            </div>
          </div>
          <div class="case-modal-footer">
            <button class="btn" @click="closeCaseModal" aria-label="取消">取消</button>
            <button class="btn btn-primary" @click="saveChartCase" :disabled="!canSaveCase" aria-label="保存">保存</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'Xianzhi' })
import { ref, nextTick, computed, onMounted, onActivated, onUnmounted } from "vue"
import { chatWithXianzhi, chatWithRag, downloadReport, parsePillars, parseWuxing, parseDayun, parseShensha, fetchSessions, deleteSession as deleteSessionApi, clearSessionMessages, getSessionMessages, fetchChartCases, createChartCase, deleteChartCase, getChart, type ChatSession, type SessionMessage, type ChartCase, type ChartData, type SSECallbacks } from "../api"
import BaziCard from "../components/BaziCard.vue"
import WuxingChart from "../components/WuxingChart.vue"
import DayunTimeline from "../components/DayunTimeline.vue"
import BaziModal from "../components/BaziModal.vue"
import MarkdownRender from "../components/MarkdownRender.vue"

interface BirthInfo { time: string; gender: string }

const messages = ref<SessionMessage[]>([])
const input = ref("")
const loading = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const mode = ref<"agent" | "rag">("agent")
const lastBirthInfo = ref<BirthInfo | null>(null)
const chartData = ref<ChartData | null>(null)
const conversationId = ref("web-xianzhi-" + Date.now())
const ragSessionId = ref("rag-" + Date.now())
const sidebarCollapsed = ref(true)
const isMobile = ref(false)
const appSidebarOpen = ref(false)
const sessions = ref<ChatSession[]>([])
const showModal = ref(false)
const chartCases = ref<ChartCase[]>([])
const showCaseModal = ref(false)
const caseModalMode = ref<"save" | "manual">("save")
const caseName = ref("")
const caseTags = ref("")
const caseBirthTime = ref("")
const caseGender = ref<"男" | "女">("男")
const sect = ref(2)
const yunSect = ref(1)
const showScrollTop = ref(false)
const pageSize = 30
const visibleCount = ref(pageSize)
const hasMoreHistory = computed(() => visibleCount.value < messages.value.length)
const visibleMessages = computed(() => {
  const total = messages.value.length
  const start = Math.max(0, total - visibleCount.value)
  return messages.value.slice(start)
})

const agentExamples = ["男，1990-05-20 14:30，排盘并分析事业", "女，1995-08-15 08:00，看近五年运势", "男，1988-12-01 23:30，大运流年推算"]
const ragExamples = ["什么是七杀？有什么含义？", "用神怎么取？", "大运顺逆排的规则是什么？"]
const currentExamples = computed(() => mode.value === "agent" ? agentExamples : ragExamples)
const placeholderText = computed(() => mode.value === "agent" ? "例如：男，1990-05-20 14:30，排盘分析事业" : "请教命理理论问题...")

const lastAssistantMsg = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === "assistant") return messages.value[i]
  }
  return null
})

function extractAnswer(text: string): string {
  if (!text) return ""
  const answer = text.match(/\[回答\]\s*([\s\S]*)/)
  const observations = text.match(/\[观察\]\s*([\s\S]*?)(?=\[|\n\n|$)/g) || []
  const parts = [answer ? answer[1] : ""]
  observations.forEach(o => parts.push(o.replace(/^\[观察\]\s*/, "")))
  return parts.join("\n").trim()
}

const pillars = computed(() => lastAssistantMsg.value ? parsePillars(extractAnswer(lastAssistantMsg.value.content)) : [])
const wuxing = computed(() => lastAssistantMsg.value ? parseWuxing(extractAnswer(lastAssistantMsg.value.content)) : [])
const dayun = computed(() => lastAssistantMsg.value ? parseDayun(extractAnswer(lastAssistantMsg.value.content)) : [])
const shensha = computed(() => lastAssistantMsg.value ? parseShensha(extractAnswer(lastAssistantMsg.value.content)) : [])
const modalPillars = computed(() => chartData.value?.pillars?.length ? chartData.value.pillars : pillars.value)
const modalWuxing = computed(() => chartData.value?.wuxing?.length ? chartData.value.wuxing : wuxing.value)
const modalDayun = computed(() => chartData.value?.dayun?.length ? chartData.value.dayun : dayun.value)
const modalLiunian = computed(() => chartData.value?.liunian || [])
const modalShensha = computed(() => chartData.value?.shensha?.length ? chartData.value.shensha : shensha.value)
const parsedDayun = computed(() => dayun.value.map(d => ({ ...d, liunian: [] })))
const canSaveCase = computed(() =>
  caseName.value.trim() && caseBirthTime.value.trim() && (caseGender.value === "男" || caseGender.value === "女")
)
const activeChartCase = computed(() =>
  chartCases.value.find(c => c.birthTime === lastBirthInfo.value?.time) || chartCases.value[0] || null
)

const isThinking = (content: string | undefined) => typeof content === "string" && (content.includes("[思考]") || content.includes("[行动]") || content.includes("[观察]"))
const msgClass = (role: string) => ["msg", role, "animate-fade-in-up"]
const formatTime = (time: string) => time ? time.split("T")[0] : ""

const scrollToBottom = async () => {
  await nextTick()
  await new Promise(r => setTimeout(r, 100))
  if (messagesEl.value) {
    messagesEl.value.scrollTo({ top: messagesEl.value.scrollHeight, behavior: "smooth" })
    showScrollTop.value = false
  }
}

const onScroll = () => {
  if (!messagesEl.value) return
  const el = messagesEl.value
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
  showScrollTop.value = !atBottom
}

const loadMoreHistory = async () => {
  const el = messagesEl.value
  if (!el) return
  const prevHeight = el.scrollHeight
  visibleCount.value = Math.min(visibleCount.value + pageSize, messages.value.length)
  await nextTick()
  // 保持视口位置不跳动
  if (el) {
    const newHeight = el.scrollHeight
    el.scrollTop = newHeight - prevHeight
  }
}

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey) {
    e.preventDefault()
    e.stopPropagation()
    send()
  }
}

const fetchChartData = async (birthTime: string, gender: string) => {
  try {
    chartData.value = await getChart(birthTime, gender, sect.value, yunSect.value)
  } catch {
    chartData.value = null
  }
}

const tryExtractBirth = (text: string) => {
  const m = text.match(/(男|女)/)
  const t = text.match(/(\d{4}[-年/]\d{1,2}[-月/]\d{1,2}[日 ]+\d{1,2}[:：]\d{1,2})/)
  if (m && t) {
    const time = t[1].replace(/年|月/g, "-").replace("日", "").replace("：", ":").trim()
    lastBirthInfo.value = { time, gender: m[1] }
    fetchChartData(time, m[1])
  }
}

const formatContent = (text: string) => {
  if (!text) return ""
  return text
    .replace(/\[思考\]\s*/g, "**思考：** ")
    .replace(/\[行动\]\s*/g, "**行动：** ")
    .replace(/\[观察\]\s*/g, "**观察：** ")
    .replace(/\[回答\]\s*/g, "")
    .replace(/\[结束\].*/g, "")
}

const switchMode = (m: "agent" | "rag") => {
  if (mode.value === m) return
  mode.value = m
  messages.value = []
  input.value = ""
  lastBirthInfo.value = null
}

const clearChat = async () => {
  // 清空当前会话：删除数据库消息记录，保留会话ID与命盘上下文
  if (conversationId.value) {
    await clearSessionMessages("xianzhi", conversationId.value)
  }
  messages.value = []
  input.value = ""
  loadSessions()
}

const newSession = () => {
  conversationId.value = "web-xianzhi-" + Date.now()
  ragSessionId.value = "rag-" + Date.now()
  messages.value = []
  lastBirthInfo.value = null
  chartData.value = null
  input.value = ""
  loadSessions()
}

const exportChat = () => {
  const text = messages.value.map(m => `${m.role === 'user' ? '你' : '先知'}：${m.content}`).join("\n\n")
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `先知对话_${new Date().toLocaleDateString()}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

const useExample = (ex: string) => { input.value = ex }
const showBaziModal = async () => {
  if (lastBirthInfo.value && !chartData.value) {
    await fetchChartData(lastBirthInfo.value.time, lastBirthInfo.value.gender)
  }
  showModal.value = true
}
const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem("xianzhi-sidebar-collapsed", String(sidebarCollapsed.value))
}
const toggleAppSidebar = () => window.dispatchEvent(new CustomEvent("app-toggle-sidebar"))
const onAppSidebarState = (e: Event) => {
  const ev = e as CustomEvent
  appSidebarOpen.value = !!ev.detail?.open
}

const loadSessions = async () => {
  sessions.value = await fetchSessions("xianzhi")
}

const loadSession = async (s: ChatSession) => {
  if (!s?.id) return
  conversationId.value = s.id
  messages.value = await getSessionMessages("xianzhi", s.id)
  visibleCount.value = pageSize
  // 从历史用户消息里恢复命盘上下文
  lastBirthInfo.value = null
  chartData.value = null
  for (const m of messages.value) {
    if (m.role === "user") tryExtractBirth(m.content)
  }
  scrollToBottom()
}

const deleteSessionItem = async (id: string) => {
  await deleteSessionApi("xianzhi", id)
  loadSessions()
}

const loadChartCases = async () => {
  chartCases.value = await fetchChartCases()
}

const openCaseModal = () => {
  if (!lastBirthInfo.value) return
  caseModalMode.value = "save"
  caseName.value = lastBirthInfo.value.time + " " + lastBirthInfo.value.gender + "命盘"
  caseTags.value = ""
  caseBirthTime.value = lastBirthInfo.value.time
  caseGender.value = lastBirthInfo.value.gender === "女" ? "女" : "男"
  showCaseModal.value = true
}

const openManualCaseModal = () => {
  caseModalMode.value = "manual"
  caseName.value = ""
  caseTags.value = ""
  caseBirthTime.value = ""
  caseGender.value = "男"
  showCaseModal.value = true
}

const closeCaseModal = () => {
  showCaseModal.value = false
}

const saveChartCase = async () => {
  if (!canSaveCase.value) return
  await createChartCase({
    name: caseName.value.trim(),
    birthTime: caseBirthTime.value.trim(),
    gender: caseGender.value,
    tags: caseTags.value.split(/[,，]/).map(s => s.trim()).filter(Boolean),
  })
  closeCaseModal()
  loadChartCases()
}

const deleteChartCaseItem = async (id: string) => {
  await deleteChartCase(id)
  loadChartCases()
}

const loadChartCase = (c: ChartCase) => {
  if (!c?.birthTime || !c?.gender) return
  lastBirthInfo.value = { time: c.birthTime, gender: c.gender }
  chartData.value = c.chartData || null
  if (!chartData.value) fetchChartData(c.birthTime, c.gender)
  input.value = "请分析这个命盘：" + c.name
}

const exportCaseCard = () => {
  const c = activeChartCase.value
  if (!c) return
  const tags = c.tags?.length ? c.tags.join(" / ") : "未设置标签"
  const svg = buildCaseCardSvg(c, tags)
  const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `命例卡片_${safeFileName(c.name)}.svg`
  a.click()
  URL.revokeObjectURL(url)
}

function buildCaseCardSvg(c: ChartCase, tags: string): string {
  const name = escapeXml(c.name || "未命名命例")
  const birth = escapeXml(c.birthTime || "未填写")
  const gender = escapeXml(c.gender || "未填写")
  const tagText = escapeXml(tags)
  const createdAt = escapeXml(formatTime(c.createdAt || ""))
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="900" height="540" viewBox="0 0 900 540">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#111827"/>
      <stop offset="0.55" stop-color="#0b1120"/>
      <stop offset="1" stop-color="#18122b"/>
    </linearGradient>
    <linearGradient id="gold" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#f0d878"/>
      <stop offset="1" stop-color="#d4af37"/>
    </linearGradient>
  </defs>
  <rect width="900" height="540" rx="32" fill="url(#bg)"/>
  <circle cx="760" cy="96" r="120" fill="#d4af37" opacity="0.08"/>
  <circle cx="128" cy="470" r="160" fill="#8b5cf6" opacity="0.08"/>
  <rect x="36" y="36" width="828" height="468" rx="24" fill="rgba(255,255,255,0.035)" stroke="rgba(240,216,120,0.32)"/>
  <text x="72" y="98" fill="#f0d878" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="30" font-weight="700">先知命例卡片</text>
  <text x="72" y="138" fill="#7c8fa5" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="18">Xianzhi Chart Snapshot</text>
  <text x="72" y="218" fill="#ffffff" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="42" font-weight="700">${name}</text>
  <rect x="72" y="272" width="756" height="1" fill="rgba(240,216,120,0.22)"/>
  <text x="72" y="326" fill="#7c8fa5" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="18">出生时间</text>
  <text x="188" y="326" fill="#f5f7fa" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="24" font-weight="600">${birth}</text>
  <text x="72" y="376" fill="#7c8fa5" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="18">性别</text>
  <text x="188" y="376" fill="#f5f7fa" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="24" font-weight="600">${gender}</text>
  <text x="72" y="426" fill="#7c8fa5" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="18">标签</text>
  <text x="188" y="426" fill="#f5f7fa" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="24" font-weight="600">${tagText}</text>
  <text x="72" y="470" fill="#5a6c82" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="16">创建于 ${createdAt || "本地命例库"}</text>
  <text x="742" y="470" fill="url(#gold)" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="22" font-weight="700">先知</text>
</svg>`
}

function escapeXml(value: string): string {
  return value.replace(/[<>&"']/g, (ch) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "\"": "&quot;", "'": "&apos;" }[ch] || ch))
}

function safeFileName(value: string): string {
  return (value || "命例").replace(/[\\/:*?"<>|]/g, "_").slice(0, 40)
}

const send = () => {
  if (!input.value.trim() || loading.value) return
  const userMsg = input.value
  messages.value.push({ role: "user", content: userMsg })
  input.value = ""
  loading.value = true
  if (mode.value === "agent") tryExtractBirth(userMsg)
  const aiMsg: SessionMessage = { role: "assistant", content: "" }
  messages.value.push(aiMsg)
  scrollToBottom()

  const sessionId = mode.value === "agent" ? conversationId.value : ragSessionId.value
  const chatFn = mode.value === "agent" ? chatWithXianzhi : chatWithRag

  const opts = mode.value === "agent" && lastBirthInfo.value ? {
    birth_time: lastBirthInfo.value.time,
    gender: lastBirthInfo.value.gender,
    sect: sect.value,
    yun_sect: yunSect.value,
  } : undefined

  chatFn(userMsg, sessionId, {
    onMessage: (data) => { aiMsg.content += data; scrollToBottom() },
    onError: () => { aiMsg.content += "\n[连接中断]"; loading.value = false },
    onDone: () => { loading.value = false; scrollToBottom(); loadSessions(); loadChartCases() },
    // 后端从 LLM 工具调用中提取到出生信息时回调（覆盖自然语言输入场景）
    onChartContext: async (birthTime, gender) => {
      if (!birthTime || !gender) return
      lastBirthInfo.value = { time: birthTime, gender }
      await fetchChartData(birthTime, gender)
    },
  } as SSECallbacks, opts)
}

const checkMobile = () => {
  isMobile.value = window.innerWidth <= 768
}

onMounted(() => {
  loadSessions(); loadChartCases(); checkMobile(); window.addEventListener("resize", checkMobile)
  window.addEventListener("app-sidebar-state", onAppSidebarState)
})
onActivated(() => {
  // keep-alive 切换回来时刷新会话列表，确保历史记录最新
  loadSessions(); loadChartCases()
})
onUnmounted(() => {
  window.removeEventListener("resize", checkMobile)
  window.removeEventListener("app-sidebar-state", onAppSidebarState)
})
</script>

<style scoped>
.chat-view { display: flex; min-height: 100%; position: relative; }

.sidebar-expand-btn {
  position: fixed; left: 4px; top: 80px; z-index: 50;
  width: 40px; height: 40px; border-radius: 10px;
  background: rgba(15,21,32,0.95); border: 1px solid var(--border);
  color: var(--accent-light); cursor: pointer; display: none; align-items: center; justify-content: center;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4); transition: all 0.25s;
}
.sidebar-expand-btn:hover { background: rgba(212,175,55,0.15); border-color: var(--accent); }
.sidebar-expand-btn.always-show { display: flex; }

.sidebar-mask {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.65); z-index: 45; display: none;
}

.chat-sidebar { width: 280px; background: rgba(10,15,26,0.98);
  border-right: 1px solid var(--border); display: flex; flex-direction: column; transition: width 0.3s; z-index: 50; }
.chat-sidebar.collapsed { width: 0; overflow: hidden; }

.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 18px 16px;
  border-bottom: 1px solid var(--border); }
.sidebar-title { font-size: 13px; color: var(--text-dim); letter-spacing: 2px; font-weight: 500; }
.sidebar-toggle { padding: 6px; background: transparent; border: 1px solid var(--border); border-radius: 8px;
  color: var(--text-dim); cursor: pointer; transition: all 0.2s; }
.sidebar-toggle:hover { border-color: var(--accent); color: var(--accent-light); }

.sessions-list { flex: 1; overflow-y: auto; padding: 10px; }
.no-sessions { text-align: center; color: var(--text-muted); font-size: 12px; padding: 24px; }

.session-item { padding: 14px; background: rgba(255,255,255,0.02); border-radius: 12px; margin-bottom: 8px;
  cursor: pointer; border: 1px solid transparent; transition: all 0.2s; position: relative; }
.session-item:hover { background: rgba(212,175,55,0.04); border-color: rgba(212,175,55,0.12); }
.session-item.active { background: rgba(212,175,55,0.08); border-color: rgba(212,175,55,0.2); }

.session-title { font-size: 13px; color: var(--text); margin-bottom: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session-meta { font-size: 11px; color: var(--text-muted); }

.session-delete { position: absolute; right: 10px; top: 10px; padding: 4px; background: transparent;
  border: none; color: var(--text-muted); cursor: pointer; opacity: 0; transition: opacity 0.2s; }
.session-item:hover .session-delete { opacity: 1; }
.session-delete:hover { color: var(--danger); }

.cases-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px;
  border-top: 1px solid var(--border); }
.cases-actions { display: flex; gap: 6px; }
.cases-actions .btn:disabled { opacity: 0.45; cursor: not-allowed; }

.case-tags { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; }
.case-tag { font-size: 10px; padding: 2px 8px; background: rgba(212,175,55,0.1);
  border-radius: 6px; color: var(--accent-light); }

.chat-main { flex: 1; display: flex; flex-direction: column; padding: 16px; min-height: 100%; }

.chat-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px;
  background: rgba(15,21,32,0.85); border: 1px solid var(--border); border-radius: var(--radius);
  backdrop-filter: blur(12px); margin-bottom: 16px; }

.header-left { display: flex; align-items: center; gap: 14px; }

.pc-sidebar-toggle {
  padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 8px;
  color: var(--text-dim); cursor: pointer; display: none; transition: all 0.2s; align-items: center; justify-content: center;
}
.pc-sidebar-toggle:hover { border-color: var(--accent); color: var(--accent-light); background: rgba(212,175,55,0.08); }
.pc-sidebar-toggle:active { transform: scale(0.96); }

.app-sidebar-toggle {
  padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 8px;
  color: var(--text-dim); cursor: pointer; display: flex; transition: all 0.2s; align-items: center; justify-content: center;
}
.app-sidebar-toggle:hover { border-color: var(--accent); color: var(--accent-light); background: rgba(212,175,55,0.08); }
.app-sidebar-toggle:active { transform: scale(0.96); }
.chat-header h2 { font-size: 17px; color: var(--text); letter-spacing: 1px; margin-bottom: 2px; font-weight: 600; }
.header-info { font-size: 12px; color: var(--text-muted); }

.header-right { display: flex; align-items: center; gap: 10px; }
.header-btn { padding: 7px 12px; font-size: 12px; }

.sect-selector { display: flex; gap: 8px; margin-right: 10px; }
.sect-select { padding: 6px 10px; font-size: 12px; background: rgba(255,255,255,0.04);
  border: 1px solid var(--border); border-radius: 8px; color: var(--text-dim); outline: none;
  cursor: pointer; }
.sect-select:focus { border-color: var(--accent); color: var(--text); }
.sect-select option { background: #0f1520; color: var(--text); }

.mode-tabs { display: flex; background: rgba(255,255,255,0.03); border-radius: 8px; padding: 3px; }
.tab { padding: 6px 16px; font-size: 12px; border: none; background: transparent;
  color: var(--text-dim); cursor: pointer; border-radius: 6px; transition: all 0.2s; }
.tab:hover { color: var(--text); }
.tab.active { background: rgba(212,175,55,0.15); color: var(--accent-light); }

.messages { flex: 1; overflow-y: auto; padding: 8px; min-height: 0; }

.load-more-bar { display: flex; justify-content: center; padding: 12px 0 6px; }
.load-more-btn { padding: 8px 18px; font-size: 12px; color: var(--text-dim);
  background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 20px;
  cursor: pointer; transition: all 0.2s; }
.load-more-btn:hover { color: var(--accent); border-color: var(--accent); background: rgba(212,175,55,0.08); }

.scroll-top-btn { position: fixed; bottom: 120px; right: 32px;
  width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  background: rgba(12,18,32,0.95); border: 1px solid var(--border); color: var(--accent);
  cursor: pointer; z-index: 100; box-shadow: 0 4px 16px rgba(0,0,0,0.4); transition: all 0.2s; }
.scroll-top-btn:hover { border-color: var(--accent); box-shadow: 0 0 16px rgba(212,175,55,0.3); }

.empty-state { position: relative; text-align: center; padding: 60px 20px; display: flex;
  flex-direction: column; align-items: center; justify-content: center; min-height: 400px; }

.orbit-ring { position: absolute; width: 280px; height: 280px; border: 1px solid rgba(212,175,55,0.1);
  border-radius: 50%; animation: spin-slow 25s linear infinite; }
.orbit-ring::before { content: ""; position: absolute; top: -2px; left: 50%; width: 8px; height: 8px;
  background: var(--accent); border-radius: 50%; box-shadow: 0 0 12px rgba(212,175,55,0.5); }

.empty-center { position: relative; z-index: 1; }

.empty-icon { width: 90px; height: 90px; margin: 0 auto 24px; background: linear-gradient(135deg, var(--accent), #b8942a);
  border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 42px; color: #0a0f1a;
  font-weight: bold; box-shadow: 0 0 40px rgba(212,175,55,0.25); animation: pulse-glow 3s ease-in-out infinite; }

.empty-state h3 { color: var(--text); margin-bottom: 10px; font-size: 20px; font-weight: 600; }
.empty-state p { font-size: 14px; color: var(--text-muted); max-width: 420px; margin: 0 auto; line-height: 1.7; }

.examples { margin-top: 32px; display: flex; flex-direction: column; gap: 10px; align-items: center; width: 100%; max-width: 380px; }
.example-btn { padding: 12px 20px; background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  border-radius: 10px; color: var(--text-dim); font-size: 13px; cursor: pointer; width: 100%;
  text-align: left; transition: all 0.2s; }
.example-btn:hover { background: rgba(212,175,55,0.06); border-color: rgba(212,175,55,0.2); color: var(--text); }

.msg { display: flex; gap: 12px; margin-bottom: 20px; }
.msg.user { flex-direction: row-reverse; }
.msg.user .msg-body { align-items: flex-end; }
.msg.user .msg-role { text-align: right; }

.msg-avatar-wrap { display: flex; flex-direction: column; align-items: center; gap: 4px; flex-shrink: 0; }
.msg-avatar { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,0.05); border: 1px solid var(--border); color: var(--text-dim); }
.msg.user .msg-avatar { background: linear-gradient(135deg, #2a5298, #1e3c72); border-color: rgba(42,82,152,0.5); color: #fff; }
.msg-role { font-size: 11px; color: var(--text-muted); }

.msg-body { flex: 1; display: flex; flex-direction: column; gap: 8px; max-width: 75%; }
.msg.user .msg-body { max-width: 75%; }

.msg-content { padding: 14px 18px; background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  border-radius: 14px; line-height: 1.7; font-size: 14px; }
.msg.user .msg-content { background: linear-gradient(135deg, rgba(42,82,152,0.3), rgba(30,60,114,0.2));
  border-color: rgba(42,82,152,0.3); }
.msg-content.thinking { opacity: 0.85; }

.loading-msg { opacity: 1 !important; }
.loading-content { display: flex; align-items: center; gap: 10px; min-width: 140px; }
.loading-text { color: var(--accent); font-size: 13px; }
.loading-dots { display: flex; gap: 4px; }
.loading-dots span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: bounce 1.4s infinite ease-in-out; }
.loading-dots span:nth-child(2) { animation-delay: 0.16s; }
.loading-dots span:nth-child(3) { animation-delay: 0.32s; }
@keyframes bounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }

.report-bar { display: flex; gap: 10px; padding-top: 8px; }
.report-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; font-size: 12px;
  background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 8px;
  color: var(--text-dim); cursor: pointer; transition: all 0.2s; }
.report-btn:hover { border-color: var(--accent); color: var(--accent-light); }

.input-area { margin-top: 12px; }
.input-wrap { display: flex; gap: 10px; align-items: flex-end; padding: 8px; background: rgba(15,21,32,0.85);
  border: 1px solid var(--border); border-radius: var(--radius); }

textarea { flex: 1; padding: 12px 14px; background: rgba(255,255,255,0.03); border: none; border-radius: 10px;
  color: var(--text); font-size: 14px; outline: none; resize: none; font-family: inherit; min-height: 44px; }
textarea::placeholder { color: var(--text-muted); }
textarea:focus { background: rgba(255,255,255,0.05); }
textarea:disabled { opacity: 0.5; cursor: not-allowed; }

.input-actions { flex-shrink: 0; }
.send-btn { padding: 12px 20px; font-size: 14px; font-weight: 600; }
.send-btn:disabled { opacity: 0.5; }

.input-hint { text-align: center; font-size: 11px; color: var(--text-muted); margin-top: 8px; }

@media (min-width: 769px) {
  .pc-sidebar-toggle { display: flex; }
  .sidebar-mask { display: none !important; }
  .chat-main { min-height: 0; overflow: hidden; }
  .chat-view { overflow: hidden; }
}

.case-modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7);
  display: flex; align-items: center; justify-content: center; z-index: 100; }
.case-modal { width: 90%; max-width: 420px; background: rgba(15,21,32,0.95); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden; }
.case-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px;
  border-bottom: 1px solid var(--border); }
.case-modal-title { font-size: 15px; font-weight: 600; color: var(--text); }
.modal-close { padding: 6px; background: transparent; border: 1px solid var(--border); border-radius: 8px;
  color: var(--text-dim); cursor: pointer; }
.modal-close:hover { border-color: var(--danger); color: var(--danger); }
.case-modal-body { padding: 20px; }
.form-row { margin-bottom: 16px; }
.form-row label { display: block; font-size: 12px; color: var(--text-dim); margin-bottom: 6px; }
.form-row input,
.form-row select { width: 100%; padding: 10px 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  border-radius: 8px; color: var(--text); font-size: 13px; outline: none; }
.form-row input:focus,
.form-row select:focus { border-color: var(--accent); }
.form-row input:disabled,
.form-row select:disabled { opacity: 0.5; cursor: not-allowed; }
.form-row select option { background: #0f1520; color: var(--text); }
.case-modal-footer { display: flex; justify-content: flex-end; gap: 10px; padding: 16px 20px;
  border-top: 1px solid var(--border); }

@media (max-width: 768px) {
  .app-sidebar-toggle { display: none !important; }
  .pc-sidebar-toggle { display: flex; }
  .chat-sidebar { position: fixed; left: 0; top: 0; bottom: 0; width: 260px; z-index: 100;
    box-shadow: 4px 0 24px rgba(0,0,0,0.5); transition: transform 0.35s ease; will-change: transform; }
  .chat-sidebar.collapsed { transform: translateX(-100%); width: 260px; }
  .chat-sidebar:not(.collapsed) { transform: translateX(0); }
  .sidebar-expand-btn { display: none; }
  .sidebar-mask { display: block; }
  .chat-main { padding: 10px; padding-top: 60px; }
  .chat-header { padding: 10px 12px; flex-wrap: wrap; gap: 8px; align-items: center; }
  .header-left { flex: 1; align-items: center; }
  .header-right { margin-left: 0; flex-wrap: wrap; gap: 4px; justify-content: flex-end; }
  .header-btn { padding: 5px 8px; font-size: 11px; min-width: 34px; }
  .header-btn span { display: none; }
  .sect-select { padding: 4px 6px; font-size: 11px; }
  .tab { padding: 4px 8px; font-size: 11px; }
  .msg-body { max-width: 88%; }
  .msg.user .msg-body { max-width: 88%; }
  .empty-icon { width: 60px; height: 60px; font-size: 28px; }
  .empty-state h3 { font-size: 15px; }
  .empty-state p { font-size: 12px; }
  .examples { max-width: 100%; }
  .example-btn { padding: 10px 14px; font-size: 12px; }
  .input-area { margin-top: 8px; }
  .input-wrap { padding: 6px; }
  textarea { padding: 10px 12px; font-size: 13px; }
  .send-btn { padding: 10px 14px; font-size: 13px; }
}

@media (max-width: 480px) {
  .chat-header { padding: 10px 12px; }
  .chat-header h2 { font-size: 15px; }
  .header-info { font-size: 11px; }
  .examples { max-width: 100%; }
  .example-btn { padding: 10px 16px; font-size: 12px; }
}
</style>
