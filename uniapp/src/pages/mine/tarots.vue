<template>
  <view class="page">
    <view class="nav-placeholder" :style="{ height: (statusBarHeight + navBarHeight) + 'px' }"></view>
    <view class="nav-bar">
      <text class="back" @tap="goBack">‹</text>
      <text class="title">塔罗记录</text>
      <view style="width: 120rpx;"></view>
    </view>

    <scroll-view v-if="loading && !tarots.length" class="body" scroll-y>
      <view class="empty-state">
        <text class="empty-icon">✦</text>
        <text class="empty-text">加载中…</text>
      </view>
    </scroll-view>

    <scroll-view v-else-if="!tarots.length" class="body" scroll-y>
      <view class="empty-state">
        <text class="empty-icon">🃏</text>
        <text class="empty-text">还没有塔罗记录</text>
        <text class="empty-hint">在塔罗页面开始一次牌阵解读</text>
      </view>
    </scroll-view>

    <scroll-view v-else class="body" scroll-y>
      <view
        v-for="t in tarots"
        :key="t.id"
        class="card"
        @tap="toggleTarot(t)"
      >
        <view class="card-head">
          <view class="card-title-row">
            <text class="card-title">{{ spreadName(t.spread) }}</text>
            <text v-if="t.question" class="card-tag">{{ t.question }}</text>
          </view>
          <text
            :class="['expand-icon', expandedTarot === t.id && 'expanded']"
            @tap.stop="toggleTarot(t)"
          >{{ expandedTarot === t.id ? '∧' : '∨' }}</text>
        </view>
        <text class="card-sub">{{ t.createdAt }}</text>
        <view v-if="expandedTarot === t.id" class="tarot-detail">
          <MarkdownRender :content="t.interpretation" />
        </view>
        <view class="card-actions">
          <text class="action-btn danger" @tap.stop="onDelete(t)">删除</text>
        </view>
      </view>
      <view class="bottom-spacer"></view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { fetchTarotRecords, deleteTarotRecord, type TarotRecord } from '@/api'

const statusBarHeight = ref(20)
const navBarHeight = ref(44)
try {
  const s = uni.getWindowInfo()
  const btn = uni.getMenuButtonBoundingClientRect()
  statusBarHeight.value = Math.max(s.statusBarHeight || 0, 44)
  navBarHeight.value = Math.max((btn.bottom - s.statusBarHeight) + (s.statusBarHeight - btn.top), 44)
} catch {}

const tarots = ref<TarotRecord[]>([])
const expandedTarot = ref('')
const loading = ref(false)

onShow(() => {
  loadTarots()
})

async function loadTarots() {
  loading.value = true
  try { tarots.value = await fetchTarotRecords() }
  catch { tarots.value = [] }
  finally { loading.value = false }
}

function goBack() { uni.navigateBack({ fail: () => uni.switchTab({ url: '/pages/mine/index' }) }) }
function toggleTarot(t: TarotRecord) { expandedTarot.value = expandedTarot.value === t.id ? '' : t.id }
function spreadName(s: string) {
  return s === 'three_card' ? '过去现在未来' : s === 'relationship' ? '关系牌阵' : '每日一牌'
}

function onDelete(t: TarotRecord) {
  uni.showModal({ title: '删除记录', content: '删除这条塔罗记录？', success: async (r) => {
    if (!r.confirm) return
    try { await deleteTarotRecord(t.id); tarots.value = tarots.value.filter(x => x.id !== t.id) }
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
.card-title-row { display: flex; align-items: center; gap: 14rpx; flex: 1; min-width: 0; }
.card-title { font-size: 30rpx; font-weight: 600; color: $color-ink; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-tag { font-size: 21rpx; color: $color-primary; background: rgba(107,123,142,0.12); border-radius: 14rpx; padding: 3rpx 14rpx; flex-shrink: 0; max-width: 300rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.expand-icon {
  flex-shrink: 0; font-size: 32rpx; color: $color-ink-light; padding: 8rpx 12rpx;
  transition: transform 0.2s;
}
.expand-icon.expanded { color: $color-primary; }
.card-sub { display: block; font-size: 24rpx; color: $color-ink-light; margin-bottom: 16rpx; }
.tarot-detail {
  padding: 20rpx 24rpx; background: rgba(107,123,142,0.06);
  border-radius: 18rpx; margin-bottom: 16rpx;
  font-size: 25rpx; color: $color-ink; line-height: 1.7;
}
.card-actions { display: flex; gap: 14rpx; flex-wrap: wrap; }
.action-btn {
  font-size: 23rpx; padding: 10rpx 22rpx; border-radius: 18rpx;
  background: rgba(107,123,142,0.06); border: 1rpx solid $color-border; color: $color-ink-light;
}
.action-btn.danger { color: $color-vermilion; background: rgba(184,72,60,0.04); border-color: rgba(184,72,60,0.2); }

.bottom-spacer { height: 50rpx; }
</style>
