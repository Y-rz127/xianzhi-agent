<template>
  <view class="page">
    <view class="nav-placeholder" :style="{ height: (statusBarHeight + navBarHeight) + 'px' }"></view>
    <view class="nav-bar">
      <text class="back" @tap="goBack">‹</text>
      <text class="title">命例收藏</text>
      <text class="add-btn" @tap="goCases">去命例库</text>
    </view>

    <scroll-view v-if="loading && !favorites.length" class="body" scroll-y>
      <view class="empty-state">
        <text class="empty-icon">✦</text>
        <text class="empty-text">加载中…</text>
      </view>
    </scroll-view>

    <scroll-view v-else-if="!favorites.length" class="body" scroll-y>
      <view class="empty-state">
        <text class="empty-icon">★</text>
        <text class="empty-text">还没有收藏</text>
        <text class="empty-hint">去命例库点亮 ★ 收藏感兴趣的命盘</text>
        <text class="create-hint" @tap="goCases">去命例库</text>
      </view>
    </scroll-view>

    <scroll-view v-else class="body" scroll-y>
      <view
        v-for="f in favorites"
        :key="f.caseId"
        class="card"
      >
        <view class="card-head">
          <text class="card-title">{{ f.name }}</text>
          <text class="card-gender">{{ f.gender }}</text>
        </view>
        <text class="card-birth">◷ {{ f.birthTime }}</text>
        <view class="card-actions">
          <text class="action-btn primary" @tap.stop="bringCaseToChat(f)">带入对话</text>
          <text class="action-btn normal" @tap.stop="viewDetail(f)">查看</text>
          <text class="action-btn danger" @tap.stop="onRemove(f)">取消收藏</text>
        </view>
      </view>

    <!-- 查看详情弹窗 -->
    <BaziModal
      v-if="showBazi"
      :visible="showBazi"
      :pillars="activeChart?.pillars || []"
      :wuxing="activeChart?.wuxing || []"
      :dayun="activeChart?.dayun || []"
      :liunian="activeChart?.liunian || []"
      :shensha="activeChart?.shensha || []"
      :analysis="activeChart?.analysis"
      :startYun="activeChart?.startYun"
      :warnings="activeChart?.warnings || []"
      :birthTime="detailItem?.birthTime"
      :gender="detailItem?.gender"
      :mingGong="activeChart?.mingGong"
      :shenGong="activeChart?.shenGong"
      @close="closeDetail"
    />
      <view class="bottom-spacer"></view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { fetchFavorites, removeFavorite, getChart, type FavoriteCase, type ChartData } from '@/api'
import BaziModal from '@/components/BaziModal/BaziModal.vue'

const statusBarHeight = ref(20)
const navBarHeight = ref(44)
try {
  const s = uni.getWindowInfo()
  const btn = uni.getMenuButtonBoundingClientRect()
  statusBarHeight.value = s.statusBarHeight || 20
  navBarHeight.value = (btn.bottom - s.statusBarHeight) + (s.statusBarHeight - btn.top)
} catch {}

const favorites = ref<FavoriteCase[]>([])
const loading = ref(false)

onShow(() => {
  loadFavorites()
})

async function loadFavorites() {
  loading.value = true
  try { favorites.value = await fetchFavorites() }
  catch { favorites.value = [] }
  finally { loading.value = false }
}

function goBack() { uni.navigateBack({ fail: () => uni.switchTab({ url: '/pages/mine/index' }) }) }
function goCases() { uni.navigateTo({ url: '/pages/chart-cases/index' }) }

function bringCaseToChat(f: FavoriteCase) {
  uni.setStorageSync('XZ_LAUNCH', { birthTime: f.birthTime, gender: f.gender, name: f.name })
  uni.switchTab({ url: '/pages/xianzhi/index' })
}

// 查看详情
const detailItem = ref<FavoriteCase | null>(null)
const showBazi = ref(false)
const activeChart = ref<ChartData | null>(null)

async function viewDetail(f: FavoriteCase) {
  detailItem.value = f
  uni.showLoading({ title: '加载中…' })
  try {
    const chart = await getChart(f.birthTime, f.gender)
    activeChart.value = chart
    showBazi.value = true
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    uni.hideLoading()
  }
}
function closeDetail() {
  showBazi.value = false
  detailItem.value = null
  activeChart.value = null
}

function onRemove(f: FavoriteCase) {
  uni.showModal({ title: '取消收藏', content: `取消收藏「${f.name}」？`, success: async (r) => {
    if (!r.confirm) return
    try { await removeFavorite(f.caseId); favorites.value = favorites.value.filter(x => x.caseId !== f.caseId) }
    catch (e: any) { uni.showToast({ title: e?.message || '操作失败', icon: 'none' }) }
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
.add-btn { font-size: 26rpx; color: $color-bg; padding: 10rpx 26rpx; background: linear-gradient(135deg, $color-primary, $color-primary-dark); border-radius: 28rpx; }

.body { flex: 1; padding: 28rpx 28rpx 0; overflow-x: hidden; width: 100%; box-sizing: border-box; }

.empty-state { display: flex; flex-direction: column; align-items: center; padding-top: 180rpx; gap: 16rpx; }
.empty-icon { font-size: 96rpx; color: $color-primary; opacity: 0.25; }
.empty-text { font-size: 30rpx; color: $color-ink-light; letter-spacing: 4rpx; }
.empty-hint { font-size: 24rpx; color: $color-ink-lighter; text-align: center; max-width: 500rpx; }
.create-hint {
  margin-top: 32rpx; padding: 18rpx 48rpx; font-size: 28rpx; color: $color-bg;
  background: linear-gradient(135deg, $color-primary, $color-primary-dark);
  border-radius: 40rpx; box-shadow: $glow-gold;
}

.card {
  width: 100%; box-sizing: border-box;
  background: $color-bg-card; border: 1rpx solid $color-border; border-radius: 28rpx;
  padding: 28rpx 28rpx 24rpx; margin-bottom: 24rpx;
  box-shadow: $shadow-sm; position: relative; overflow: hidden;
}
.card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2rpx; background: linear-gradient(90deg, transparent, $color-primary, $color-vermilion, transparent); }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12rpx; gap: 16rpx; }
.card-title { font-size: 30rpx; font-weight: 600; color: $color-ink; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
.card-gender { flex-shrink: 0; font-size: 22rpx; color: $color-primary; background: rgba(107,123,142,0.08); border-radius: 16rpx; padding: 4rpx 16rpx; }
.card-birth { display: block; font-size: 24rpx; color: $color-ink-light; font-family: monospace; margin-bottom: 16rpx; }
.card-actions { display: flex; gap: 14rpx; flex-wrap: wrap; }
.action-btn {
  font-size: 23rpx; padding: 10rpx 22rpx; border-radius: 18rpx;
  background: rgba(107,123,142,0.06); border: 1rpx solid $color-border; color: $color-ink-light;
}
.action-btn.primary { color: $color-bg; background: $color-primary; border: none; }
.action-btn.normal { color: $color-primary; border-color: rgba(107,123,142,0.3); }
.action-btn.danger { color: $color-vermilion; background: rgba(184,72,60,0.04); border-color: rgba(184,72,60,0.2); }

.bottom-spacer { height: 50rpx; }
</style>
