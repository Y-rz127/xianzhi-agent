<template>
  <div class="chat-view love-view">
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
        <div v-for="s in sessions" :key="s.id" :class="['session-item', { active: s.id === chatId }]" @click="loadSession(s)">
          <div class="session-title">{{ s.title }}</div>
          <div class="session-meta">{{ formatTime(s.lastTime) }} · {{ s.messageCount }}条</div>
          <button class="session-delete" @click.stop="deleteSessionItem(s.id)" aria-label="删除会话">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      </div>
    </div>

    <div class="chat-main">
      <header class="chat-header glass-card">
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
            <h2 class="text-glow-soft">恋爱大师</h2>
            <div class="header-info">情感咨询 · 倾诉恋爱难题 · 守护你的缘分</div>
          </div>
        </div>
        <div class="header-right">
          <button class="btn header-btn" @click="clearChat" title="清空">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
          <button class="btn header-btn" @click="newSession" title="新会话">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          </button>
          <button class="btn header-btn" @click="exportChat" title="导出">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>
          </button>
        </div>
      </header>

      <div class="messages" ref="messagesEl" @scroll="onScroll">
        <div v-if="!messages.length" class="empty">
          <div class="heart-pulse">
            <svg viewBox="0 0 24 24" width="36" height="36" fill="currentColor"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
          </div>
          <div class="empty-icon love-avatar">缘</div>
          <h3>恋爱大师为您服务</h3>
          <p>在这里，你可以倾诉任何恋爱、情感、婚姻中的困惑</p>
          <div class="examples">
            <button v-for="ex in loveExamples" :key="ex" class="example-btn love-example" @click="useExample(ex)" aria-label="示例">{{ ex }}</button>
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
                <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
              </div>
              <div class="msg-role">{{ msg.role === "user" ? "你" : "大师" }}</div>
            </div>
            <div class="msg-body">
              <div class="msg-content"><MarkdownRender v-if="msg.role === 'assistant'" :content="msg.content" /><pre v-else>{{ msg.content }}</pre></div>
            </div>
          </div>
        </template>

        <div v-if="loading" class="msg assistant loading-msg">
          <div class="msg-avatar-wrap">
            <div class="msg-avatar"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg></div>
            <div class="msg-role">大师</div>
          </div>
          <div class="msg-body">
            <div class="msg-content loading-content">
              <span class="loading-text">正在倾听心声</span>
              <div class="loading-dots"><span></span><span></span><span></span></div>
            </div>
          </div>
        </div>

        <div v-if="showScrollTop" class="scroll-top-btn" @click="scrollToBottom" aria-label="回到底部">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><polyline points="7 13 12 18 17 13"/><line x1="12" y1="18" x2="12" y2="3"/></svg>
        </div>
      </div>

      <div class="input-area">
        <div class="input-wrap love-input-wrap">
          <textarea id="love-chat-input" name="love-chat-input" aria-label="恋爱问题输入" v-model="input" @keydown="handleKeydown" placeholder="描述你的恋爱问题，大师会认真倾听..." :disabled="loading" rows="1"></textarea>
          <div class="input-actions">
            <button class="btn send-btn love-send" @click="send" :disabled="loading || !input.trim()" aria-label="发送">
              <span v-if="!loading">发送</span>
              <span v-else>思考中</span>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polyline points="22 2 15 22 11 13 2 9 22 2"/></svg>
            </button>
          </div>
        </div>
        <div class="input-hint">按 Enter 发送 · Shift+Enter 换行</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'Love' })
import { ref, nextTick, onMounted, onUnmounted, computed } from "vue"
import { chatWithLove, fetchSessions, deleteSession as deleteSessionApi, clearSessionMessages, getSessionMessages, type ChatSession, type SessionMessage } from "../api"
import MarkdownRender from "../components/MarkdownRender.vue"

const messages = ref<SessionMessage[]>([])
const input = ref("")
const loading = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const chatId = ref("love-" + Date.now())
const sidebarCollapsed = ref(true)
const isMobile = ref(false)
const appSidebarOpen = ref(false)
const sessions = ref<ChatSession[]>([])
const showScrollTop = ref(false)
const pageSize = 30
const visibleCount = ref(pageSize)
const hasMoreHistory = computed(() => visibleCount.value < messages.value.length)
const visibleMessages = computed(() => {
  const total = messages.value.length
  const start = Math.max(0, total - visibleCount.value)
  return messages.value.slice(start)
})

const loveExamples = ["最近和喜欢的人聊天总是冷场，怎么办？", "分手后一直走不出来，该怎么调整心态？", "如何判断对方是不是对的人？"]

const useExample = (ex: string) => { input.value = ex }
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
  showScrollTop.value = el.scrollHeight - el.scrollTop - el.clientHeight > 120
}

const loadMoreHistory = async () => {
  const el = messagesEl.value
  if (!el) return
  const prevHeight = el.scrollHeight
  visibleCount.value = Math.min(visibleCount.value + pageSize, messages.value.length)
  await nextTick()
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

const clearChat = async () => {
  // 清空当前会话：删除数据库消息记录，保留会话ID
  if (chatId.value) {
    await clearSessionMessages("love", chatId.value)
  }
  messages.value = []
  input.value = ""
  loadSessions()
}
const newSession = () => { chatId.value = "love-" + Date.now(); messages.value = []; input.value = ""; loadSessions() }
const exportChat = () => {
  const text = messages.value.map(m => `${m.role === 'user' ? '你' : '恋爱大师'}：${m.content}`).join("\n\n")
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `恋爱大师对话_${new Date().toLocaleDateString()}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem("love-sidebar-collapsed", String(sidebarCollapsed.value))
}
const toggleAppSidebar = () => window.dispatchEvent(new CustomEvent("app-toggle-sidebar"))
const onAppSidebarState = (e: Event) => {
  const ev = e as CustomEvent
  appSidebarOpen.value = !!ev.detail?.open
}
const loadSessions = async () => { sessions.value = await fetchSessions("love") }
const loadSession = async (s: ChatSession) => { chatId.value = s.id; messages.value = await getSessionMessages("love", s.id); visibleCount.value = pageSize; scrollToBottom() }
const deleteSessionItem = async (id: string) => { await deleteSessionApi("love", id); loadSessions() }

const send = () => {
  if (!input.value.trim() || loading.value) return
  const userMsg = input.value
  messages.value.push({ role: "user", content: userMsg })
  input.value = ""
  loading.value = true
  // 直接复用 onMessage 流式填充同一条消息，避免与 loading 指示器重复
  const aiMsg: SessionMessage = { role: "assistant", content: "" }
  messages.value.push(aiMsg)
  scrollToBottom()
  chatWithLove(userMsg, chatId.value, {
    onMessage: (data) => { aiMsg.content += data; scrollToBottom() },
    onError: () => { aiMsg.content += "\n[连接中断]"; loading.value = false },
    onDone: () => { loading.value = false; scrollToBottom(); loadSessions() },
  })
}

const checkMobile = () => {
  isMobile.value = window.innerWidth <= 768
  if (isMobile.value) {
    sidebarCollapsed.value = true
  }
}

onMounted(() => {
  loadSessions(); checkMobile(); window.addEventListener("resize", checkMobile)
  window.addEventListener("app-sidebar-state", onAppSidebarState)
})
onUnmounted(() => {
  window.removeEventListener("resize", checkMobile)
  window.removeEventListener("app-sidebar-state", onAppSidebarState)
})
</script>

<style scoped>
.chat-view { display: flex; min-height: 100%; position: relative; }

.sidebar-mask {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.65); z-index: 45; display: none;
}
.chat-sidebar { width: 260px; background: linear-gradient(180deg, rgba(12,18,32,0.95), rgba(8,11,16,0.95));
  border-right: 1px solid var(--border); display: flex; flex-direction: column; transition: width 0.3s; z-index: 50; }
.chat-sidebar.collapsed { width: 0; overflow: hidden; }
.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 16px;
  border-bottom: 1px solid var(--border); }
.sidebar-title { font-size: 13px; color: var(--text-dim); letter-spacing: 2px; }
.sidebar-toggle { padding: 6px; background: transparent; border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-dim); cursor: pointer; transition: all 0.2s; }
.sidebar-toggle:hover { border-color: var(--love); color: var(--love); }
.sessions-list { flex: 1; overflow-y: auto; padding: 10px; }
.no-sessions { text-align: center; color: var(--text-dim); font-size: 12px; padding: 20px; }
.session-item { padding: 12px; background: rgba(255,255,255,0.03); border-radius: 10px; margin-bottom: 8px;
  cursor: pointer; border: 1px solid transparent; transition: all 0.2s; position: relative; }
.session-item:hover { background: rgba(232,139,139,0.06); border-color: rgba(232,139,139,0.15); }
.session-item.active { background: linear-gradient(90deg, rgba(232,139,139,0.12), transparent);
  border-color: rgba(232,139,139,0.25); }
.session-title { font-size: 13px; color: var(--text); margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session-meta { font-size: 11px; color: var(--text-dim); }
.session-delete { position: absolute; right: 8px; top: 8px; padding: 4px; background: transparent;
  border: none; color: var(--text-dim); cursor: pointer; opacity: 0; transition: opacity 0.2s; }
.session-item:hover .session-delete { opacity: 1; }
.session-delete:hover { color: var(--danger); }

.chat-main { flex: 1; display: flex; flex-direction: column; padding: 16px 20px 0; min-height: 100%; }
.chat-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 22px; margin-bottom: 16px; }
.header-left { display: flex; align-items: center; gap: 14px; }

.pc-sidebar-toggle {
  padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 8px;
  color: var(--text-dim); cursor: pointer; display: none; transition: all 0.2s; align-items: center; justify-content: center;
}
.pc-sidebar-toggle:hover { border-color: var(--love); color: var(--love); background: rgba(232,139,139,0.08); }
.pc-sidebar-toggle:active { transform: scale(0.96); }
.app-sidebar-toggle {
  padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 8px;
  color: var(--text-dim); cursor: pointer; display: flex; transition: all 0.2s; align-items: center; justify-content: center;
}
.app-sidebar-toggle:hover { border-color: var(--love); color: var(--love); background: rgba(232,139,139,0.08); }
.app-sidebar-toggle:active { transform: scale(0.96); }
.chat-header h2 { font-size: 17px; color: var(--love); letter-spacing: 1px; margin-bottom: 2px; }
.header-info { font-size: 12px; color: var(--text-dim); }
.header-right { display: flex; align-items: center; gap: 10px; }
.header-btn { padding: 7px 12px; font-size: 12px; }

.messages { flex: 1; overflow-y: auto; padding: 8px 12px 20px; min-height: 0; }

.load-more-bar { display: flex; justify-content: center; padding: 12px 0 6px; }
.load-more-btn { padding: 8px 18px; font-size: 12px; color: var(--text-dim);
  background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 20px;
  cursor: pointer; transition: all 0.2s; }
.load-more-btn:hover { color: var(--love); border-color: var(--love); background: rgba(232,139,139,0.08); }

.scroll-top-btn { position: fixed; bottom: 90px; right: 24px;
  width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  background: rgba(12,18,32,0.95); border: 1px solid var(--border); color: var(--love);
  cursor: pointer; z-index: 100; box-shadow: 0 4px 16px rgba(0,0,0,0.4); transition: all 0.2s; }
.scroll-top-btn:hover { border-color: var(--love); box-shadow: 0 0 16px rgba(232,139,139,0.3); }
.empty { position: relative; text-align: center; padding: 70px 20px; color: var(--text-dim); }
.heart-pulse { position: absolute; left: 50%; top: 55px; transform: translateX(-50%); color: rgba(232,139,139,0.15); animation: heartbeat 2s ease-in-out infinite; }
@keyframes heartbeat { 0%, 100% { transform: translateX(-50%) scale(1); } 50% { transform: translateX(-50%) scale(1.15); } }
.empty-icon { width: 80px; height: 80px; margin: 0 auto 20px; background: linear-gradient(135deg, var(--love), var(--love-deep));
  border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 38px; color: #fff;
  font-weight: bold; box-shadow: 0 0 30px rgba(232,139,139,0.3); position: relative; z-index: 1; }
.empty h3 { color: var(--text); margin-bottom: 8px; font-size: 18px; }
.empty p { font-size: 13px; max-width: 400px; margin: 0 auto; }
.examples { margin-top: 24px; display: flex; flex-direction: column; gap: 10px; align-items: center; }
.example-btn { padding: 10px 18px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 10px;
  color: var(--text); cursor: pointer; font-size: 13px; transition: all 0.25s; max-width: 420px; }
.example-btn.love-example:hover { border-color: var(--love); color: var(--love); background: rgba(232,139,139,0.08);
  transform: translateY(-2px); box-shadow: 0 4px 16px rgba(232,139,139,0.15); }

.msg { display: flex; gap: 12px; margin-bottom: 24px; max-width: 88%; opacity: 0; }
.msg.assistant { align-self: flex-start; }
.msg.user { flex-direction: row-reverse; align-self: flex-end; margin-left: auto; }
.msg-avatar-wrap { display: flex; flex-direction: column; align-items: center; gap: 4px; flex-shrink: 0; }
.msg-avatar { width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: bold; border: 2px solid transparent; }
.msg.user .msg-avatar { background: linear-gradient(135deg, #d4a5a5, #b06c6c); color: #fff;
  border-color: rgba(255,255,255,0.1); box-shadow: 0 0 14px rgba(232,139,139,0.3); }
.msg.assistant .msg-avatar { background: linear-gradient(135deg, var(--love), var(--love-deep)); color: #fff;
  border-color: rgba(232,139,139,0.4); box-shadow: 0 0 16px rgba(232,139,139,0.25); }
.msg-role { font-size: 10px; color: var(--text-dim); }
.msg.user .msg-role { color: #e8b8b8; }
.msg.assistant .msg-role { color: var(--love); }
.msg-body { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.msg-content { background: var(--card); padding: 14px 18px; border-radius: 18px;
  border: 1px solid var(--border); backdrop-filter: blur(8px); box-shadow: 0 4px 20px rgba(0,0,0,0.2);
  position: relative; overflow: hidden; }
.msg.user .msg-content { background: linear-gradient(135deg, rgba(212,165,165,0.85), rgba(176,108,108,0.85));
  border-color: rgba(255,255,255,0.08); box-shadow: 0 4px 20px rgba(0,0,0,0.25), 0 0 18px rgba(232,139,139,0.2); }
.msg.assistant .msg-content::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 2px;
  background: linear-gradient(180deg, rgba(232,139,139,0.35), transparent); opacity: 0.45; }
.msg.user .msg-content::before { content: ""; position: absolute; right: 0; top: 0; bottom: 0; width: 2px;
  background: linear-gradient(180deg, rgba(255,255,255,0.15), transparent); opacity: 0.35; }
.msg-content pre { white-space: pre-wrap; word-wrap: break-word; font-family: inherit; font-size: 14px; line-height: 1.75; color: var(--text); }
.msg.user .msg-content pre { color: #fff; }

.loading-msg { opacity: 1 !important; }
.loading-content { display: flex; align-items: center; gap: 10px; min-width: 140px; }
.loading-text { color: var(--love); font-size: 13px; }

.input-area { padding: 14px 0 18px; border-top: 1px solid var(--border); }
.input-wrap { display: flex; gap: 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  border-radius: 18px; padding: 6px; transition: all 0.25s; }
.input-wrap:focus-within { border-color: var(--love); box-shadow: 0 0 20px rgba(232,139,139,0.12); }
.input-wrap textarea { flex: 1; background: transparent; border: none; padding: 10px 14px; color: var(--text);
  font-size: 14px; font-family: inherit; resize: none; outline: none; max-height: 120px; line-height: 1.6; }
.input-wrap textarea::placeholder { color: var(--text-dim); }
.input-actions { display: flex; align-items: flex-end; padding: 4px 6px 4px 0; }
.send-btn { padding: 10px 20px; border-radius: 12px; font-weight: 600; border: none; }
.send-btn.love-send { background: linear-gradient(135deg, var(--love), var(--love-deep)); color: #fff; }
.send-btn:hover:not(:disabled) { box-shadow: 0 0 18px rgba(232,139,139,0.35); }
.send-btn.love-send:hover:not(:disabled) { background: linear-gradient(135deg, #f0a0a0, var(--love)); }
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.input-hint { font-size: 11px; color: var(--text-dim); text-align: center; margin-top: 8px; opacity: 0.7; }

@media (min-width: 769px) {
  .pc-sidebar-toggle { display: flex; }
  .sidebar-mask { display: none !important; }
  .chat-main { min-height: 0; overflow: hidden; }
  .chat-view { overflow: hidden; }
}

@media (max-width: 768px) {
  .app-sidebar-toggle { display: none !important; }
  .pc-sidebar-toggle { display: flex; }
  .sidebar-mask { display: block; }
  .chat-sidebar {
    position: fixed; left: 0; top: 0; bottom: 0; z-index: 100;
    width: 240px; transform: translateX(-100%); transition: transform 0.35s ease;
    will-change: transform;
  }
  .chat-sidebar.collapsed { transform: translateX(-100%); }
  .chat-sidebar:not(.collapsed) { transform: translateX(0); }
  .chat-main { padding: 10px; padding-top: 60px; }
  .chat-header { flex-wrap: wrap; gap: 8px; padding: 10px 12px; margin-bottom: 10px; }
  .header-left { flex: 1; align-items: center; }
  .chat-header h2 { font-size: 14px; }
  .header-info { font-size: 11px; }
  .header-right { gap: 4px; }
  .header-btn { padding: 5px 8px; font-size: 11px; min-width: 32px; }
  .msg { max-width: 96%; gap: 8px; margin-bottom: 16px; }
  .msg-avatar { width: 32px; height: 32px; }
  .msg-content { padding: 10px 14px; border-radius: 14px; }
  .msg-content pre { font-size: 13px; line-height: 1.6; }
  .empty { padding: 50px 15px; }
  .empty-icon { width: 60px; height: 60px; font-size: 28px; }
  .empty h3 { font-size: 16px; }
  .empty p { font-size: 12px; }
  .example-btn { padding: 8px 14px; font-size: 12px; max-width: 100%; }
  .input-area { padding: 10px 0 14px; }
  .input-wrap { padding: 4px; }
  .input-wrap textarea { padding: 8px 10px; font-size: 13px; }
  .send-btn { padding: 8px 14px; font-size: 13px; }
  .input-hint { display: none; }
}
</style>
