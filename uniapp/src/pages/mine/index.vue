<template>
  <view class="page">
    <view class="nav-placeholder" :style="{ height: (statusBarHeight + navBarHeight) + 'px' }"></view>

    <!-- 用户头部 -->
    <view class="hero">
      <view class="hero-bg"></view>
      <view class="hero-orb orb-1"></view>
      <view class="hero-orb orb-2"></view>
      <view class="hero-content" @tap="onHeaderTap">
        <view class="avatar">{{ avatarText }}</view>
        <view class="hero-info">
          <text class="nickname">{{ user ? user.nickname : '未登录' }}</text>
          <text class="sub">{{ user ? '点击编辑昵称' : '点击登录以同步命理档案' }}</text>
        </view>
        <text class="arrow">›</text>
      </view>
    </view>

    <scroll-view class="scroll" scroll-y>
      <!-- 未登录提示 -->
      <view v-if="!user" class="login-tip" @tap="goLogin">
        <text>登录后可保存八字档案、收藏命例、同步对话与塔罗记录</text>
      </view>

      <!-- 八字档案 -->
      <view v-if="user" class="card entry-card" @tap="uni.navigateTo({ url: '/pages/mine/profiles' })">
        <view class="entry-head">
          <view class="card-title-row"><text class="card-dot">✦</text><text class="card-title">我的八字档案</text></view>
          <text class="entry-arrow">›</text>
        </view>
        <text class="entry-hint">{{ profiles.length ? `共 ${profiles.length} 条档案` : '还没有档案' }}</text>
      </view>

      <!-- 命例收藏 -->
      <view v-if="user" class="card entry-card" @tap="uni.navigateTo({ url: '/pages/mine/favorites' })">
        <view class="entry-head">
          <view class="card-title-row"><text class="card-dot">✦</text><text class="card-title">命例收藏</text></view>
          <text class="entry-arrow">›</text>
        </view>
        <text class="entry-hint">{{ favorites.length ? `共 ${favorites.length} 条收藏` : '还没有收藏' }}</text>
      </view>

      <!-- 我的对话 -->
      <view v-if="user" class="card entry-card" @tap="uni.navigateTo({ url: '/pages/mine/sessions' })">
        <view class="entry-head">
          <view class="card-title-row"><text class="card-dot">✦</text><text class="card-title">我的对话</text></view>
          <text class="entry-arrow">›</text>
        </view>
        <text class="entry-hint">{{ sessions.length ? `共 ${sessions.length} 条对话` : '还没有对话记录' }}</text>
      </view>

      <!-- 塔罗记录 -->
      <view v-if="user" class="card entry-card" @tap="uni.navigateTo({ url: '/pages/mine/tarots' })">
        <view class="entry-head">
          <view class="card-title-row"><text class="card-dot">✦</text><text class="card-title">塔罗记录</text></view>
          <text class="entry-arrow">›</text>
        </view>
        <text class="entry-hint">{{ tarots.length ? `共 ${tarots.length} 条记录` : '还没有塔罗记录' }}</text>
      </view>

      <!-- 通用链接 -->
      <view class="card links">
        <view class="link-row" @tap="goAbout"><text>关于我们</text><text class="link-arrow">›</text></view>
        <view class="link-row" @tap="goFeedback"><text>问题反馈</text><text class="link-arrow">›</text></view>
        <view class="link-row" @tap="goPrivacy"><text>隐私政策</text><text class="link-arrow">›</text></view>
        <view class="link-row" @tap="goSettings"><text>服务器设置</text><text class="link-arrow">›</text></view>
      </view>

      <view v-if="user" class="logout-btn" @tap="onLogout">退出登录</view>
      <view class="bottom-spacer"></view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getUser, clearAuth } from '@/utils/storage'
import { requireLogin } from '@/utils/authGuard'
import {
  fetchProfiles,
  fetchFavorites,
  fetchMySessions,
  fetchTarotRecords,
  updateMe,
} from '@/api'

const statusBarHeight = ref(20)
const navBarHeight = ref(44)
try {
  const s = uni.getWindowInfo()
  const btn = uni.getMenuButtonBoundingClientRect()
  statusBarHeight.value = s.statusBarHeight || 20
  navBarHeight.value = (btn.bottom - s.statusBarHeight) + (s.statusBarHeight - btn.top)
} catch {}

const user = ref<any>(null)
const profiles = ref<any[]>([])
const favorites = ref<any[]>([])
const sessions = ref<any[]>([])
const tarots = ref<any[]>([])

const avatarText = computed(() => (user.value?.nickname ? user.value.nickname.slice(0, 1) : '☯'))

onShow(() => {
  if (!requireLogin()) return
  user.value = getUser()
  if (user.value) {
    loadProfiles()
    loadFavorites()
    loadSessions()
    loadTarots()
  } else {
    profiles.value = []
    favorites.value = []
    sessions.value = []
    tarots.value = []
  }
})

async function loadProfiles() { try { profiles.value = await fetchProfiles() } catch { profiles.value = [] } }
async function loadFavorites() { try { favorites.value = await fetchFavorites() } catch { favorites.value = [] } }
async function loadSessions() { try { sessions.value = await fetchMySessions() } catch { sessions.value = [] } }
async function loadTarots() { try { tarots.value = await fetchTarotRecords() } catch { tarots.value = [] } }

function goLogin() { uni.navigateTo({ url: '/pages/login/index' }) }
function goAbout() { uni.navigateTo({ url: '/pages/about/index' }) }
function goFeedback() { uni.navigateTo({ url: '/pages/feedback/index' }) }
function goPrivacy() { uni.navigateTo({ url: '/pages/legal/privacy' }) }
function goSettings() { uni.navigateTo({ url: '/pages/settings/index' }) }

function onHeaderTap() {
  if (!user.value) { goLogin(); return }
  uni.showModal({
    title: '修改昵称',
    editable: true,
    content: user.value.nickname,
    placeholderText: '2-20 个字符',
    success: async (r) => {
      if (!r.confirm) return
      const name = (r.content || '').trim()
      if (name.length < 2 || name.length > 20) { uni.showToast({ title: '昵称需 2-20 字', icon: 'none' }); return }
      try {
        const res = await updateMe({ nickname: name })
        user.value = res.user
        uni.setStorageSync('XZ_USER', res.user)
        uni.showToast({ title: '已更新', icon: 'success' })
      } catch (e: any) {
        uni.showToast({ title: e?.message || '更新失败', icon: 'none' })
      }
    },
  })
}

function onLogout() {
  uni.showModal({ title: '退出登录', content: '确定退出当前账号？', success: (r) => {
    if (!r.confirm) return
    clearAuth()
    user.value = null
    profiles.value = []
    favorites.value = []
    sessions.value = []
    tarots.value = []
    uni.showToast({ title: '已退出', icon: 'none' })
  }})
}
</script>

<style lang="scss" scoped>
.page { height: 100vh; background: $color-bg; display: flex; flex-direction: column; overflow-x: hidden; }
.nav-placeholder { width: 100%; flex-shrink: 0; }
.hero {
  position: relative; padding: 48rpx 32rpx 64rpx; overflow: hidden;
  background: linear-gradient(135deg, $color-bg-warm 0%, $color-bg 100%);
  border-bottom-left-radius: 48rpx; border-bottom-right-radius: 48rpx;
}
.hero-bg { position: absolute; inset: 0; background: radial-gradient(circle at 20% 30%, rgba(107,123,142,0.35), transparent 50%), radial-gradient(circle at 80% 70%, rgba(184,72,60,0.2), transparent 50%); }
.hero-orb { position: absolute; border-radius: 50%; filter: blur(40rpx); pointer-events: none; }
.orb-1 { top: -60rpx; right: -40rpx; width: 200rpx; height: 200rpx; background: rgba(107,123,142,0.45); }
.orb-2 { bottom: -80rpx; left: -60rpx; width: 220rpx; height: 220rpx; background: rgba(184,72,60,0.3); }
.hero-content { position: relative; z-index: 1; display: flex; align-items: center; }
.avatar {
  width: 120rpx; height: 120rpx; line-height: 120rpx; text-align: center;
  border-radius: 50%; background: linear-gradient(135deg, $color-primary, $color-primary-dark);
  color: $color-bg; font-size: 52rpx; font-weight: 600; box-shadow: $glow-gold;
}
.hero-info { flex: 1; margin-left: 28rpx; }
.nickname { display: block; font-size: 38rpx; font-weight: 700; color: $color-paper; letter-spacing: 4rpx; }
.sub { display: block; margin-top: 10rpx; font-size: 25rpx; color: $color-ink-light; }
.arrow { color: $color-ink-light; font-size: 40rpx; }

.scroll { flex: 1; padding: 28rpx 28rpx 0; overflow-x: hidden; width: 100%; box-sizing: border-box; }
.login-tip {
  padding: 30rpx; background: rgba(107,123,142,0.08); border: 1rpx solid $color-border;
  border-radius: 24rpx; font-size: 25rpx; color: $color-ink-light; line-height: 1.7; margin-bottom: 28rpx;
  width: 100%; box-sizing: border-box;
}

/* 入口卡片（八字档案 / 收藏 / 对话 / 塔罗） */
.entry-card { cursor: pointer; }
.entry-card:active { transform: scale(0.98); opacity: 0.9; transition: all 0.15s ease; }
.entry-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12rpx; }
.card-title-row { display: flex; align-items: center; min-width: 0; overflow: hidden; }
.card-dot { color: $color-vermilion; font-size: 24rpx; margin-right: 14rpx; flex-shrink: 0; }
.card-title { font-size: 31rpx; font-weight: 600; color: $color-ink; letter-spacing: 4rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.entry-arrow { font-size: 36rpx; color: $color-primary; flex-shrink: 0; padding-left: 16rpx; }
.entry-hint { display: block; font-size: 25rpx; color: $color-ink-lighter; letter-spacing: 2rpx; }

/* 卡片基础 */
.card {
  background: $color-bg-card; border: 1rpx solid $color-border; border-radius: 28rpx;
  padding: 32rpx 28rpx; margin-bottom: 28rpx; position: relative; overflow: hidden;
  box-sizing: border-box; width: 100%;
}
.card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2rpx; background: linear-gradient(90deg, transparent, $color-primary, $color-vermilion, transparent); }

/* 链接列表 */
.links { padding: 10rpx 28rpx; }
.link-row { display: flex; align-items: center; justify-content: space-between; padding: 30rpx 0; border-bottom: 1rpx solid $color-border; font-size: 29rpx; color: $color-ink; }
.link-row:last-child { border-bottom: none; }
.link-arrow { color: $color-ink-lighter; font-size: 34rpx; }

.logout-btn { text-align: center; padding: 30rpx 0; margin: 16rpx 0 28rpx; border-radius: 24rpx; font-size: 29rpx; color: $color-vermilion; background: rgba(184,72,60,0.08); border: 1rpx solid rgba(184,72,60,0.25); width: 100%; box-sizing: border-box; }
.bottom-spacer { height: 50rpx; width: 100%; }
</style>
