<template>
  <view class="page">
    <!-- 状态栏占位（粉紫渐变） -->
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

    <!-- 顶部粉紫渐变头 -->
    <view class="header">
      <view class="header-glow"></view>
      <view class="header-content">
        <view class="header-icon">
          <text class="header-heart">♥</text>
        </view>
        <view class="header-text">
          <text class="header-title display-font">恋爱大师</text>
          <text class="header-sub">探索心动的频率</text>
        </view>
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
        <view v-if="msg.role === 'assistant'" class="avatar">
          <text class="avatar-dot"></text>
          <text class="avatar-heart">♥</text>
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

    <!-- 输入栏：深色玻璃 + 粉紫渐变发送按钮 -->
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
  </view>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { chatWithLoveWS } from '@/api/chat'

interface Message { role: 'user' | 'assistant'; content: string }

const messages = ref<Message[]>([])
const inputText = ref('')
const thinking = ref(false)
const scrollTop = ref(0)
const currentStreaming = ref(false)

// 状态栏高度
const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getSystemInfoSync()
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
    chatId: 'love-' + Date.now(),
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

// 初始欢迎语
messages.value.push({
  role: 'assistant',
  content: '你好，我是恋爱大师。无论是暗恋的忐忑、热恋的甜蜜，还是分手后的迷茫，都可以跟我说说。每段感情都值得被认真对待。',
})
</script>

<style lang="scss">
.page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--window-bottom));
  overflow: hidden;
  background: linear-gradient(180deg, #1A0F2E 0%, #0F0B1E 100%);
  color: #E2E8F0;
}

/* 状态栏占位 - 粉紫渐变 */
.status-bar {
  background: linear-gradient(135deg, #EC4899 0%, #8B5CF6 100%);
  width: 100%;
}

/* === 顶部粉紫渐变头 === */
.header {
  position: relative;
  padding: 18rpx 28rpx 22rpx;
  background: linear-gradient(135deg, #EC4899 0%, #8B5CF6 100%);
  overflow: hidden;
}
.header-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at 30% 50%, rgba(255, 255, 255, 0.15) 0%, transparent 70%);
  opacity: 0.2;
  pointer-events: none;
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
  background: rgba(255, 255, 255, 0.2);
  box-shadow: 0 0 24rpx rgba(236, 72, 153, 0.4);
}
.header-heart {
  color: #ffffff;
  font-size: 30rpx;
}
.header-text {
  display: flex;
  flex-direction: column;
}
.header-title {
  font-size: 34rpx;
  font-weight: 600;
  color: #ffffff;
  line-height: 1.25;
  text-shadow: 0 0 32rpx rgba(236, 72, 153, 0.5);
}
.header-sub {
  font-size: 22rpx;
  color: rgba(255, 255, 255, 0.8);
  margin-top: 4rpx;
}

/* === 消息列表 === */
.messages {
  flex: 1;
  min-height: 0;
  padding: 20rpx 28rpx 16rpx;
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
  background: rgba(236, 72, 153, 0.15);
  border-radius: 50%;
  margin-bottom: 14rpx;
  box-shadow: 0 0 24rpx rgba(236, 72, 153, 0.3);
}
.empty-heart {
  color: #EC4899;
  font-size: 40rpx;
}
.empty-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #EC4899;
  margin-bottom: 6rpx;
}
.empty-desc {
  font-size: 24rpx;
  color: #64748B;
}

.examples {
  margin-top: 20rpx;
}
.examples-title {
  display: block;
  font-size: 22rpx;
  color: #64748B;
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
  color: #94A3B8;
  background: rgba(236, 72, 153, 0.12);
  border: 1rpx solid rgba(236, 72, 153, 0.2);
  border-radius: 20rpx;
}

/* === 消息项 === */
.msg {
  display: flex;
  margin-bottom: 20rpx;
  gap: 14rpx;
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
  background: rgba(236, 72, 153, 0.15);
  border-radius: 50%;
  box-shadow: 0 0 20rpx rgba(236, 72, 153, 0.3);
}
.avatar-heart {
  color: #EC4899;
  font-size: 28rpx;
}
.avatar-dot {
  position: absolute;
  top: -2rpx;
  right: -2rpx;
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  background: #EC4899;
  box-shadow: 0 0 12rpx #EC4899;
}
.msg-body {
  max-width: 82%;
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
  word-break: break-word;
  background: rgba(30, 22, 56, 0.7);
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid rgba(236, 72, 153, 0.15);
  color: #E2E8F0;
}
.msg.user .msg-text {
  background: linear-gradient(135deg, #EC4899 0%, #8B5CF6 100%);
  border-radius: 28rpx 8rpx 28rpx 28rpx;
  color: #ffffff;
  border: none;
}
.typing { color: #94A3B8; }

/* === 输入栏 === */
.input-bar {
  flex-shrink: 0;
  display: flex;
  align-items: flex-end;
  padding: 14rpx 28rpx;
  background: rgba(15, 11, 30, 0.9);
  backdrop-filter: blur(32rpx);
  -webkit-backdrop-filter: blur(32rpx);
  border-top: 1rpx solid rgba(236, 72, 153, 0.12);
  padding-bottom: calc(14rpx + env(safe-area-inset-bottom));
  gap: 12rpx;
}
.input-wrap {
  flex: 1;
  background: rgba(30, 22, 56, 0.6);
  border-radius: 9999rpx;
  border: 1rpx solid rgba(236, 72, 153, 0.15);
  padding: 4rpx 26rpx;
}
.input {
  width: 100%;
  min-height: 56rpx;
  max-height: 150rpx;
  padding: 10rpx 0;
  font-size: 26rpx;
  color: #E2E8F0;
}
.input-placeholder {
  color: #64748B;
}
.send-btn {
  flex-shrink: 0;
  width: 64rpx;
  height: 64rpx;
  line-height: 64rpx;
  text-align: center;
  background: linear-gradient(135deg, #EC4899 0%, #8B5CF6 100%);
  border-radius: 50%;
  box-shadow: 0 0 28rpx rgba(236, 72, 153, 0.4);
}
.send-btn.disabled { opacity: 0.5; }
.send-icon {
  color: #ffffff;
  font-size: 32rpx;
}
</style>
