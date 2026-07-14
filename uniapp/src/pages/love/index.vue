<template>
  <view class="page">
    <!-- 暗夜星空背景 -->
    <view class="night-bg" aria-hidden="true">
      <view class="stars">
        <view class="star" v-for="n in 30" :key="n" :style="starStyle(n)"></view>
      </view>
      <view class="meteors">
        <view class="meteor" v-for="n in 4" :key="'m'+n" :style="meteorStyle(n)"></view>
      </view>
    </view>

    <!-- 状态栏占位 -->
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

    <!-- 顶部标题头 -->
    <view class="header">
      <view class="header-content">
        <view class="header-icon">
          <text class="header-heart">♥</text>
        </view>
        <view class="header-text">
          <text class="header-title display-font">恋爱大师</text>
          <text class="header-sub">探索心动的频率</text>
        </view>
      </view>
      <view class="header-actions">
        <text class="icon-btn" @tap="openHistoryDrawer">☰</text>
        <text class="icon-btn" @tap="confirmClear">🗑</text>
        <text class="icon-btn" @tap="confirmNew">+</text>
      </view>
    </view>

    <!-- 消息列表 -->
    <scroll-view class="messages" scroll-y :scroll-top="scrollTop" scroll-with-animation>
      <view v-if="!messages.length" class="empty-state">
        <view class="empty-avatar">
          <text class="empty-heart">♥</text>
        </view>
        <text class="empty-title">恋爱大师</text>
        <text class="empty-desc">可倾诉单身、恋爱、婚姻中的困惑</text>
      </view>

      <view v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
        <view class="avatar">
          <text v-if="msg.role === 'assistant'" class="avatar-dot"></text>
          <text class="avatar-heart">{{ msg.role === 'assistant' ? '♥' : '我' }}</text>
        </view>
        <view class="msg-body">
          <view class="msg-text">
            <MarkdownRender v-if="msg.role === 'assistant' && msg.content" :content="msg.content" />
            <text v-else-if="!msg.content" class="typing">思考中…</text>
            <text v-else>{{ msg.content }}</text>
          </view>
        </view>
      </view>
      <view v-if="thinking && !currentStreaming" class="msg assistant">
        <view class="avatar">
          <text class="avatar-dot"></text>
          <text class="avatar-heart">♥</text>
        </view>
        <view class="msg-body">
          <view class="msg-text"><text class="typing">思考中…</text></view>
        </view>
      </view>

      <!-- 示例问题 -->
      <view v-if="!messages.length" class="examples">
        <text class="examples-title">试试问我这些问题</text>
        <view class="examples-list">
          <text class="example-chip" @tap="useExample('如何判断他喜欢我？')">如何判断他喜欢我？</text>
          <text class="example-chip" @tap="useExample('异地恋怎么维持感情？')">异地恋怎么维持感情？</text>
          <text class="example-chip" @tap="useExample('分手后还能做朋友吗？')">分手后还能做朋友吗？</text>
          <text class="example-chip" @tap="useExample('对方冷暴力怎么办？')">对方冷暴力怎么办？</text>
        </view>
      </view>
    </scroll-view>

    <!-- 输入栏 -->
    <view class="input-bar">
      <view class="input-wrap">
        <textarea
          class="input"
          v-model="inputText"
          placeholder="说说你的恋爱故事…"
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
import { ref, nextTick } from 'vue'
import { onHide } from '@dcloudio/uni-app'
import { chatWithLoveWS, closeAllWS } from '@/api/chat'
import {
  clearSessionMessages,
  fetchSessions, deleteSession as deleteSessionApi, getSessionMessages,
  type ChatSession,
} from '@/api'

interface Message { role: 'user' | 'assistant'; content: string }

const messages = ref<Message[]>([])
const inputText = ref('')
const thinking = ref(false)
const scrollTop = ref(0)
const currentStreaming = ref(false)
const conversationId = ref('mp-love-' + Date.now())

// 历史会话抽屉
const showHistoryDrawer = ref(false)
const historySessions = ref<ChatSession[]>([])
const historyLoading = ref(false)

// 切走 tab / 页面隐藏时关闭 WS，避免 socket 累积超过小程序 5 个上限
onHide(() => { closeAllWS() })

async function loadHistorySessions() {
  historyLoading.value = true
  try {
    historySessions.value = await fetchSessions('love')
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
  try {
    const msgs = await getSessionMessages('love', session.id)
    messages.value = msgs.map(m => ({ role: m.role, content: m.content }))
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
        await deleteSessionApi('love', id)
        if (id === conversationId.value) newSession()
        await loadHistorySessions()
      } catch (e) {
        uni.showToast({ title: '删除失败', icon: 'none' })
      }
    },
  })
}
function formatSessionTime(t: string): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 16)
}

const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getWindowInfo()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}

function useExample(text: string) {
  inputText.value = text
}

function scrollToBottom() {
  nextTick(() => {
    scrollTop.value = scrollTop.value === 99998 ? 99999 : 99998
  })
}

function onSend() {
  const text = inputText.value.trim()
  if (!text || thinking.value) return
  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  thinking.value = true
  currentStreaming.value = true
  scrollToBottom()

  const assistantMsg: Message = { role: 'assistant', content: '' }
  messages.value.push(assistantMsg)
  const idx = messages.value.length - 1

  chatWithLoveWS(text, {
    chatId: conversationId.value,
    onMessage: (chunk) => {
      messages.value[idx].content += chunk
      scrollToBottom()
    },
    onDone: () => {
      thinking.value = false
      currentStreaming.value = false
    },
    onError: (err) => {
      thinking.value = false
      currentStreaming.value = false
      messages.value[idx].content = messages.value[idx].content || `[出错] ${err}`
    },
  })
}

async function clearChat() {
  try {
    await clearSessionMessages('love', conversationId.value)
  } catch {}
  messages.value = []
  inputText.value = ''
}

function confirmClear() {
  uni.showModal({
    title: '清空对话',
    content: '确定清空当前会话的所有消息吗？',
    success: (res) => { if (res.confirm) clearChat() },
  })
}

function newSession() {
  conversationId.value = 'mp-love-' + Date.now()
  messages.value = []
  inputText.value = ''
}

function confirmNew() {
  uni.showModal({
    title: '新建会话',
    content: '确定新建会话吗？当前对话将被清空。',
    success: (res) => { if (res.confirm) newSession() },
  })
}

/* 星空 + 流星动画样式生成 */
function starStyle(n: number) {
  const size = Math.random() * 3 + 1
  const top = Math.random() * 100
  const left = Math.random() * 100
  const opacity = Math.random() * 0.6 + 0.2
  const delay = Math.random() * 4
  return {
    width: size + 'rpx',
    height: size + 'rpx',
    top: top + '%',
    left: left + '%',
    opacity,
    animationDelay: delay + 's',
  }
}

function meteorStyle(n: number) {
  const top = 5 + Math.random() * 30
  const left = 20 + Math.random() * 60
  const delay = n * 3 + Math.random() * 2
  const duration = 1.5 + Math.random() * 1
  return {
    top: top + '%',
    left: left + '%',
    animationDelay: delay + 's',
    animationDuration: duration + 's',
  }
}

messages.value.push({
  role: 'assistant',
  content: '你好，我是恋爱大师。无论是暗恋的忐忑、热恋的甜蜜，还是分手后的迷茫，都可以跟我说说。每段感情都值得被认真对待。',
})
</script>

<style lang="scss">
/* === 恋爱大师 · 暗夜星空 + 流星动画 === */
.page {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: linear-gradient(180deg, #0a0a1a 0%, #12122a 40%, #1a1a3e 100%);
  color: #ffffff;
  font-family: $font-family-body;
}

/* === 暗夜星空背景 === */
.night-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}
.stars {
  position: absolute;
  inset: 0;
}
.star {
  position: absolute;
  border-radius: 50%;
  background: #ffffff;
  animation: twinkle 3s ease-in-out infinite alternate;
}
@keyframes twinkle {
  0% { opacity: 0.2; }
  100% { opacity: 0.8; }
}

/* 流星动画 */
.meteors {
  position: absolute;
  inset: 0;
}
.meteor {
  position: absolute;
  width: 120rpx;
  height: 2rpx;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.8), rgba(255, 255, 255, 0));
  border-radius: 2rpx;
  transform: rotate(-35deg);
  animation: meteorFall 2s linear infinite;
  opacity: 0;
}
@keyframes meteorFall {
  0% {
    opacity: 0;
    transform: rotate(-35deg) translateX(0);
  }
  10% {
    opacity: 1;
  }
  70% {
    opacity: 0.6;
  }
  100% {
    opacity: 0;
    transform: rotate(-35deg) translateX(-400rpx);
  }
}

/* 状态栏占位 */
.status-bar {
  background: transparent;
  width: 100%;
  position: relative;
  z-index: 1;
}

/* === 顶部标题头 === */
.header {
  position: relative;
  padding: 24rpx 28rpx 28rpx;
  background: linear-gradient(180deg, rgba(10, 10, 26, 0.95) 0%, rgba(18, 18, 42, 0.8) 100%);
  border-bottom: 1rpx solid rgba(255, 255, 255, 0.06);
  z-index: 1;
}
.header-actions {
  position: absolute;
  left: 0;
  right: 0;
  top: 24rpx;
  height: 60rpx;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 24rpx;
  pointer-events: none;
}
.header-actions .icon-btn {
  pointer-events: auto;
}
.header-content {
  position: relative;
  display: flex;
  align-items: center;
  gap: 18rpx;
}
.header-icon {
  width: 60rpx;
  height: 60rpx;
  line-height: 60rpx;
  text-align: center;
  border-radius: 50%;
  background: rgba(184, 72, 60, 0.2);
  box-shadow: 0 0 24rpx rgba(184, 72, 60, 0.3);
}
.header-heart {
  color: #e8c4c0;
  font-size: 30rpx;
}
.header-text {
  display: flex;
  flex-direction: column;
}
.icon-btn {
  width: 56rpx;
  height: 56rpx;
  line-height: 56rpx;
  text-align: center;
  font-size: 30rpx;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.08);
  border-radius: 50%;
}
.header-title {
  font-size: 34rpx;
  font-weight: 600;
  color: #e8c4c0;
  line-height: 1.25;
  font-family: $font-family-display;
}
.header-sub {
  font-size: 22rpx;
  color: rgba(255, 255, 255, 0.45);
  margin-top: 4rpx;
}

/* === 消息列表 === */
.messages {
  flex: 1;
  min-height: 0;
  padding: 100rpx 24rpx 20rpx;
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
  padding: 32rpx 0 24rpx;
}
.empty-avatar {
  width: 88rpx;
  height: 88rpx;
  line-height: 88rpx;
  text-align: center;
  background: rgba(184, 72, 60, 0.15);
  border-radius: 50%;
  margin-bottom: 14rpx;
  box-shadow: 0 0 24rpx rgba(184, 72, 60, 0.2);
}
.empty-heart {
  color: #e8c4c0;
  font-size: 40rpx;
}
.empty-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #e8c4c0;
  margin-bottom: 6rpx;
  font-family: $font-family-display;
}
.empty-desc {
  font-size: 24rpx;
  color: rgba(255, 255, 255, 0.4);
}

.examples {
  margin-top: 20rpx;
}
.examples-title {
  display: block;
  font-size: 22rpx;
  color: rgba(255, 255, 255, 0.35);
  margin-bottom: 12rpx;
}
.examples-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10rpx;
}
.example-chip {
  display: inline-block;
  padding: 8rpx 18rpx;
  font-size: 22rpx;
  color: rgba(255, 255, 255, 0.6);
  background: rgba(184, 72, 60, 0.1);
  border: 1rpx solid rgba(184, 72, 60, 0.15);
  border-radius: 20rpx;
}

/* === 消息项 === */
.msg {
  display: flex;
  margin-bottom: 20rpx;
  gap: 14rpx;
  align-items: flex-start;
  padding: 0 8rpx;
  width: 100%;
  box-sizing: border-box;
  overflow: hidden;
}
.msg.user {
  flex-direction: row-reverse;
}
.avatar {
  position: relative;
  flex-shrink: 0;
  width: 52rpx;
  height: 52rpx;
  line-height: 52rpx;
  text-align: center;
  background: rgba(184, 72, 60, 0.15);
  border-radius: 50%;
  box-shadow: 0 0 20rpx rgba(184, 72, 60, 0.2);
}
.msg.user .avatar {
  background: rgba(184, 72, 60, 0.3);
  box-shadow: 0 0 20rpx rgba(184, 72, 60, 0.3);
}
.avatar-heart {
  color: #e8c4c0;
  font-size: 28rpx;
}
.msg.user .avatar-heart {
  color: #ffffff;
  font-size: 22rpx;
  font-weight: 600;
}
.avatar-dot {
  position: absolute;
  top: -2rpx;
  right: -2rpx;
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  background: #e8c4c0;
  box-shadow: 0 0 12rpx rgba(232, 196, 192, 0.5);
}
.msg-body {
  flex: 1;
  min-width: 0;
  max-width: calc(100% - 66rpx);
  display: flex;
  flex-direction: column;
}
.msg.user .msg-body {
  align-items: flex-end;
}
.msg-text {
  padding: 16rpx 22rpx;
  border-radius: 8rpx 28rpx 28rpx 28rpx;
  font-size: 26rpx;
  line-height: 1.55;
  word-break: break-all;
  overflow-wrap: break-word;
  background: rgba(20, 20, 45, 0.75);
  backdrop-filter: blur(16rpx);
  -webkit-backdrop-filter: blur(16rpx);
  border: 1rpx solid rgba(255, 255, 255, 0.06);
  color: #ffffff;
  max-width: 100%;
  box-sizing: border-box;
  overflow: hidden;
}
.msg.user .msg-text {
  background: rgba(184, 72, 60, 0.25);
  border-radius: 28rpx 8rpx 28rpx 28rpx;
  color: #ffffff;
  border: 1rpx solid rgba(184, 72, 60, 0.2);
}
.typing { color: rgba(255, 255, 255, 0.4); }

/* === 输入栏 === */
.input-bar {
  flex-shrink: 0;
  display: flex;
  align-items: flex-end;
  padding: 14rpx 28rpx;
  background: rgba(10, 10, 26, 0.92);
  backdrop-filter: blur(32rpx);
  -webkit-backdrop-filter: blur(32rpx);
  border-top: 1rpx solid rgba(255, 255, 255, 0.06);
  padding-bottom: calc(14rpx + env(safe-area-inset-bottom));
  gap: 12rpx;
  position: relative;
  z-index: 1;
}
.input-wrap {
  flex: 1;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 9999rpx;
  border: 1rpx solid rgba(255, 255, 255, 0.08);
  padding: 4rpx 26rpx;
}
.input {
  width: 100%;
  min-height: 56rpx;
  max-height: 150rpx;
  padding: 10rpx 0;
  font-size: 26rpx;
  color: #ffffff;
}
.input-placeholder {
  color: rgba(255, 255, 255, 0.3);
}
.send-btn {
  flex-shrink: 0;
  width: 64rpx;
  height: 64rpx;
  line-height: 64rpx;
  text-align: center;
  background: rgba(184, 72, 60, 0.35);
  border-radius: 50%;
  box-shadow: 0 0 20rpx rgba(184, 72, 60, 0.25);
}
.send-btn.disabled { opacity: 0.4; }
.send-icon {
  color: #e8c4c0;
  font-size: 32rpx;
}

/* ============ 历史会话抽屉（暗夜主题） ============ */
.drawer-mask {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 1000;
}
.drawer-panel {
  position: fixed;
  top: 0; left: 0; bottom: 0;
  width: 80%;
  max-width: 600rpx;
  background: #1a1530;
  display: flex;
  flex-direction: column;
  z-index: 1001;
  box-shadow: 4rpx 0 24rpx rgba(0, 0, 0, 0.4);
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 30rpx 32rpx 20rpx;
  border-bottom: 1rpx solid rgba(232, 196, 192, 0.15);
}
.drawer-title {
  font-size: 34rpx;
  font-weight: 600;
  color: #e8c4c0;
}
.drawer-close {
  font-size: 36rpx;
  color: #a89890;
  padding: 8rpx 16rpx;
}
.drawer-loading, .drawer-empty {
  padding: 60rpx 0;
  text-align: center;
  font-size: 26rpx;
  color: #a89890;
}
.drawer-list {
  flex: 1;
  padding: 12rpx 0;
}
.drawer-item {
  padding: 24rpx 32rpx;
  border-bottom: 1rpx solid rgba(232, 196, 192, 0.08);
  transition: background 0.2s;
}
.drawer-item.active {
  background: rgba(232, 196, 192, 0.08);
}
.drawer-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8rpx;
}
.drawer-item-title {
  font-size: 28rpx;
  color: #e8c4c0;
  font-weight: 500;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.drawer-item-del {
  font-size: 28rpx;
  color: #a89890;
  padding: 4rpx 12rpx;
}
.drawer-item-msg {
  display: block;
  font-size: 24rpx;
  color: #a89890;
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
  color: #786868;
}
.drawer-footer {
  padding: 20rpx 32rpx 30rpx;
  border-top: 1rpx solid rgba(232, 196, 192, 0.1);
}
.drawer-new-btn {
  display: block;
  text-align: center;
  padding: 18rpx 0;
  font-size: 28rpx;
  color: #1a1530;
  background: #e8c4c0;
  border-radius: 12rpx;
}
</style>
