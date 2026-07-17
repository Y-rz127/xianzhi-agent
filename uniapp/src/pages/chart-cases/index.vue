<template>
  <view class="page">
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

    <!-- 紫蓝渐变头部 -->
    <view class="hero">
      <view class="hero-bg"></view>
      <view class="hero-orb orb-1"></view>
      <view class="hero-orb orb-2"></view>
      <view class="hero-content">
        <text class="back-btn" @tap="goBack">‹ 返回</text>
        <text class="hero-title">命例库</text>
        <text class="hero-sub">收藏命盘 · 便捷复盘</text>
        <view class="hero-meta" v-if="cases.length">
          <text class="meta-dot">✦</text>
          <text class="meta-text">共 {{ cases.length }} 条命例</text>
        </view>
      </view>
    </view>

    <view class="body">
      <view v-if="loading && !cases.length" class="empty">
        <text class="empty-icon">✦</text>
        <text class="empty-text">星轨推演中…</text>
      </view>
      <view v-else-if="!cases.length" class="empty">
        <text class="empty-icon">✦</text>
        <text class="empty-text">尚无命例</text>
      </view>

      <view v-else class="list">
        <view v-for="c in cases" :key="c.id" class="case-card" @tap="loadChartCase(c)">
          <view class="case-top">
            <view class="case-head">
              <text class="case-name">{{ c.name }}</text>
              <text class="case-gender">{{ c.gender }}</text>
            </view>
            <view class="case-birth-row">
              <text class="case-birth">◷ {{ c.birthTime }}</text>
              <text v-if="c.bazi" class="bazi-text">{{ c.bazi }}</text>
            </view>
          </view>
          <view class="tag-list" v-if="c.tags?.length">
            <text v-for="(t, i) in c.tags" :key="i" class="tag">{{ t }}</text>
          </view>
          <view class="case-actions">
            <text class="action-btn view-btn" @tap.stop="loadChartCase(c)">去排盘 ➤</text>
            <text :class="['action-btn', 'fav-btn', isFav(c) && 'active']" @tap.stop="toggleFav(c)">{{ isFav(c) ? '★ 已收藏' : '☆ 收藏' }}</text>
            <text class="action-btn detail-btn" @tap.stop="viewDetail(c)">查看</text>
          </view>
        </view>
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
      :birthTime="detailCase?.birthTime"
      :gender="detailCase?.gender"
      :mingGong="activeChart?.mingGong"
      :shenGong="activeChart?.shenGong"
      @close="closeDetail"
    />

  </view>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { fetchChartCases, fetchFavorites, addFavorite, removeFavorite, getChart, type ChartCase, type ChartData } from '@/api'
import { isLoggedIn } from '@/utils/storage'
import BaziModal from '@/components/BaziModal/BaziModal.vue'

const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getWindowInfo()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}

const cases = ref<ChartCase[]>([])
const favIds = ref<Set<string>>(new Set())
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    cases.value = await fetchChartCases()
  } catch {
    cases.value = []
  } finally {
    loading.value = false
  }
  loadFavs()
}

async function loadFavs() {
  if (!isLoggedIn()) { favIds.value = new Set(); return }
  try {
    const f = await fetchFavorites()
    favIds.value = new Set(f.map((x) => x.caseId))
  } catch {
    favIds.value = new Set()
  }
}

function isFav(c: ChartCase) {
  return favIds.value.has(c.id)
}

async function toggleFav(c: ChartCase) {
  if (!isLoggedIn()) {
    uni.showToast({ title: '请先登录', icon: 'none' })
    return
  }
  try {
    if (isFav(c)) {
      await removeFavorite(c.id)
      favIds.value.delete(c.id)
    } else {
      await addFavorite(c.id)
      favIds.value.add(c.id)
    }
    favIds.value = new Set(favIds.value)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '操作失败', icon: 'none' })
  }
}

function goBack() {
  uni.navigateBack({ fail: () => uni.switchTab({ url: '/pages/xianzhi/index' }) })
}

function loadChartCase(c: ChartCase) {
  uni.setStorageSync('XZ_LAUNCH', { birthTime: c.birthTime, gender: c.gender, name: c.name })
  uni.switchTab({ url: '/pages/xianzhi/index' })
}

// ---------- 查看详情 ----------
const detailCase = ref<ChartCase | null>(null)
const showBazi = ref(false)
const activeChart = ref<ChartData | null>(null)

async function viewDetail(c: ChartCase) {
  detailCase.value = c
  uni.showLoading({ title: '加载中…' })
  try {
    const chart = await getChart(c.birthTime, c.gender)
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
  detailCase.value = null
  activeChart.value = null
}

onMounted(load)
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background: $color-bg;
  display: flex;
  flex-direction: column;
}

/* 状态栏占位 */
.status-bar { width: 100%; }

/* 水墨渐变头部 */
.hero {
  position: relative;
  padding: 40rpx 32rpx 60rpx;
  overflow: hidden;
  background: linear-gradient(135deg, $color-bg-warm 0%, $color-bg 100%);
  border-bottom-left-radius: 48rpx;
  border-bottom-right-radius: 48rpx;
}
.hero-bg {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background:
    radial-gradient(circle at 20% 30%, rgba(107, 123, 142, 0.35), transparent 50%),
    radial-gradient(circle at 80% 70%, rgba(184, 72, 60, 0.2), transparent 50%);
}
.hero-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(40rpx);
  pointer-events: none;
}
.orb-1 {
  top: -60rpx; right: -40rpx;
  width: 200rpx; height: 200rpx;
  background: rgba(107, 123, 142, 0.45);
}
.orb-2 {
  bottom: -80rpx; left: -60rpx;
  width: 220rpx; height: 220rpx;
  background: rgba(184, 72, 60, 0.3);
}
.hero-content { position: relative; z-index: 1; }
.back-btn {
  display: inline-block;
  font-size: 28rpx;
  color: $color-ink-light;
  margin-bottom: 8rpx;
  padding: 6rpx 16rpx;
  border-radius: 16rpx;
  background: rgba(255,255,255,0.06);
}
.hero-title {
  display: block;
  font-size: 52rpx;
  font-weight: 800;
  color: $color-paper;
  letter-spacing: 8rpx;
  text-shadow: 0 0 24rpx rgba(107, 123, 142, 0.6);
}
.hero-sub {
  display: block;
  margin-top: 12rpx;
  font-size: 24rpx;
  color: $color-ink-light;
  letter-spacing: 4rpx;
}
.hero-meta {
  display: flex;
  align-items: center;
  margin-top: 20rpx;
}
.meta-dot {
  color: $color-vermilion;
  font-size: 20rpx;
  margin-right: 10rpx;
}
.meta-text {
  font-size: 22rpx;
  color: $color-ink-light;
  letter-spacing: 2rpx;
}
/* 主体 */
.body {
  flex: 1;
  padding: 24rpx;
}

/* 空状态 */
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 120rpx 0;
}
.empty-icon {
  font-size: 80rpx;
  color: $color-primary;
  margin-bottom: 24rpx;
  text-shadow: 0 0 24rpx rgba(107, 123, 142, 0.6);
}
.empty-text {
  font-size: 30rpx;
  color: $color-ink-light;
  margin-bottom: 8rpx;
  letter-spacing: 4rpx;
}

/* 命例卡片列表 */
.list {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}
.case-card {
  position: relative;
  background: $color-bg-card;
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid $color-border;
  border-radius: 32rpx;
  padding: 28rpx;
  overflow: hidden;
}
.case-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2rpx;
  background: linear-gradient(90deg, transparent, $color-primary, $color-vermilion, transparent);
}
.case-top {
  display: flex;
  flex-direction: column;
}
.case-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10rpx;
}
.case-name {
  font-size: 32rpx;
  font-weight: 600;
  color: $color-ink;
  letter-spacing: 4rpx;
}
.case-gender {
  font-size: 22rpx;
  color: $color-primary;
  background: rgba(107, 123, 142, 0.12);
  border: 1rpx solid rgba(107, 123, 142, 0.4);
  padding: 6rpx 20rpx;
  border-radius: 24rpx;
}
.case-birth-row { display: flex; align-items: center; gap: 16rpx; flex-wrap: wrap; }
.case-birth {
  font-size: 24rpx;
  color: $color-ink-light;
  letter-spacing: 2rpx;
}
.bazi-text {
  font-size: 20rpx;
  letter-spacing: 4rpx;
  color: $color-primary;
  background: rgba(107, 123, 142, 0.1);
  padding: 2rpx 14rpx;
  border-radius: 8rpx;
}

/* 标签 */
.tag-list {
  display: flex;
  flex-wrap: wrap;
  margin-top: 16rpx;
}
.tag {
  font-size: 20rpx;
  color: $color-vermilion;
  background: rgba(184, 72, 60, 0.1);
  border: 1rpx solid rgba(184, 72, 60, 0.3);
  padding: 4rpx 16rpx;
  border-radius: 20rpx;
  margin: 8rpx 12rpx 0 0;
  letter-spacing: 1rpx;
}

/* 操作按钮 */
.case-actions {
  display: flex;
  justify-content: flex-end;
  gap: 16rpx;
  margin-top: 20rpx;
  padding-top: 20rpx;
  border-top: 1rpx solid $color-surface-divider;
}
.action-btn {
  font-size: 24rpx;
  padding: 10rpx 28rpx;
  border-radius: 24rpx;
  letter-spacing: 2rpx;
}
.view-btn {
  color: $color-bg;
  background: linear-gradient(135deg, $color-primary, $color-primary-dark);
  box-shadow: $glow-gold;
}
.detail-btn {
  color: $color-primary;
  background: rgba(107, 123, 142, 0.1);
  border: 1rpx solid $color-border;
}

.fav-btn { color: $color-vermilion; background: rgba(184, 72, 60, 0.08); border: 1rpx solid rgba(184, 72, 60, 0.25); }
.fav-btn.active { color: #fff; background: $color-vermilion; border-color: $color-vermilion; }
</style>
