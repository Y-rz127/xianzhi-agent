<template>
  <view class="page">
    <view class="nav-placeholder" :style="{ height: (statusBarHeight + navBarHeight) + 'px' }"></view>
    <view class="nav-bar">
      <text class="back" @tap="goBack">‹</text>
      <text class="title">我的对话</text>
      <view style="width: 120rpx;"></view>
    </view>

    <scroll-view v-if="loading && !sessions.length" class="body" scroll-y>
      <view class="empty-state">
        <text class="empty-icon">✦</text>
        <text class="empty-text">加载中…</text>
      </view>
    </scroll-view>

    <scroll-view v-else-if="!sessions.length" class="body" scroll-y>
      <view class="empty-state">
        <text class="empty-icon">💬</text>
        <text class="empty-text">还没有对话记录</text>
        <text class="empty-hint">在先知页面开始你的第一次命理咨询</text>
      </view>
    </scroll-view>

    <scroll-view v-else class="body" scroll-y>
      <view
        v-for="s in sessions"
        :key="s.id"
        class="card"
        @tap="continueSession(s)"
      >
        <view class="card-head">
          <text class="card-title">{{ s.title || '新会话' }}</text>
          <text class="card-arrow" @tap.stop="continueSession(s)">›</text>
        </view>
        <text class="card-sub">{{ s.lastMessage || '（暂无消息）' }}</text>
        <view class="card-actions">
          <text class="action-btn primary" @tap.stop="continueSession(s)">继续对话</text>
          <text class="action-btn danger" @tap.stop="onDelete(s)">删除</text>
        </view>
      </view>
      <view class="bottom-spacer"></view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { fetchMySessions, deleteSession as deleteSessionApi, type ChatSession } from '@/api'

const statusBarHeight = ref(20)
const navBarHeight = ref(44)
try {
  const s = uni.getWindowInfo()
  const btn = uni.getMenuButtonBoundingClientRect()
  statusBarHeight.value = Math.max(s.statusBarHeight || 0, 44)
  navBarHeight.value = Math.max((btn.bottom - s.statusBarHeight) + (s.statusBarHeight - btn.top), 44)
} catch {}

const sessions = ref<ChatSession[]>([])
const loading = ref(false)

onShow(() => {
  loadSessions()
})

async function loadSessions() {
  loading.value = true
  try { sessions.value = await fetchMySessions() }
  catch { sessions.value = [] }
  finally { loading.value = false }
}

function goBack() { uni.navigateBack({ fail: () => uni.switchTab({ url: '/pages/mine/index' }) }) }

function continueSession(s: ChatSession) {
  uni.setStorageSync('XZ_LAUNCH', { conversationId: s.id })
  uni.switchTab({ url: '/pages/xianzhi/index' })
}

function onDelete(s: ChatSession) {
  uni.showModal({ title: '删除会话', content: '删除该会话的所有记录？', success: async (r) => {
    if (!r.confirm) return
    try { await deleteSessionApi('xianzhi', s.id); sessions.value = sessions.value.filter(x => x.id !== s.id) }
    catch (e: any) { uni.showToast({ title: e?.message || '删除失败', icon: 'none' }) }
  }})
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: $color-bg; display: flex; flex-direction: column; overflow-x: hidden; width: 100%; box-sizing: border-box; }
.nav-placeholder { width: 100%; flex-shrink: 0; }
.nav-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16rpx 24rpx;
  background: linear-gradient(135deg, $color-bg-warm 0%, $color-bg 100%);
  border-bottom-left-radius: 36rpx; border-bottom-right-radius: 36rpx;
  position: relative; z-index: 1;
}
.back { font-size: 44rpx; color: $color-ink; padding: 0 8rpx; }
.title { font-size: 34rpx; font-weight: 600; color: $color-primary; letter-spacing: 4rpx; }

.body { flex: 1; padding: 28rpx 28rpx 0; overflow-x: hidden; width: 100%; box-sizing: border-box; }

.empty-state { display: flex; flex-direction: column; align-items: center; padding-top: 180rpx; gap: 16rpx; }
.empty-icon { font-size: 96rpx; opacity: 0.25; }
.empty-text { font-size: 30rpx; color: $color-ink-light; letter-spacing: 4rpx; }
.empty-hint { font-size: 24rpx; color: $color-ink-lighter; }

.card {
  width: 100%; box-sizing: border-box;
  background: $color-bg-card; border: 1rpx solid $color-border; border-radius: 28rpx;
  padding: 28rpx 28rpx 24rpx; margin-bottom: 24rpx;
  box-shadow: $shadow-sm; position: relative; overflow: hidden;
}
.card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2rpx; background: linear-gradient(90deg, transparent, $color-primary, $color-vermilion, transparent); }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10rpx; gap: 12rpx; }
.card-title { font-size: 30rpx; font-weight: 600; color: $color-ink; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
.card-arrow { font-size: 36rpx; color: $color-primary; padding: 4rpx 8rpx; flex-shrink: 0; }
.card-sub { display: block; font-size: 24rpx; color: $color-ink-light; line-height: 1.5; margin-bottom: 16rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-actions { display: flex; gap: 14rpx; flex-wrap: wrap; }
.action-btn {
  font-size: 23rpx; padding: 10rpx 22rpx; border-radius: 18rpx;
  background: rgba(107,123,142,0.06); border: 1rpx solid $color-border; color: $color-ink-light;
}
.action-btn.primary { color: $color-bg; background: $color-primary; border: none; }
.action-btn.danger { color: $color-vermilion; background: rgba(184,72,60,0.04); border-color: rgba(184,72,60,0.2); }

.bottom-spacer { height: 50rpx; }
</style>
