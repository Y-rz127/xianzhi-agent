<template>
  <view class="page">
    <scroll-view class="scroll" scroll-y>
      <!-- 状态栏占位 -->
      <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

      <!-- 页面头 -->
      <view class="page-header">
        <view class="back-btn" @tap="goBack">
          <text class="back-arrow">‹</text>
        </view>
        <text class="page-title display-font">合婚分析</text>
        <text class="page-sub">输入双方出生信息，探寻命理姻缘</text>
      </view>

      <!-- 甲方卡片 -->
      <view class="person-card person-a">
        <view class="card-gradient-top gradient-a"></view>
        <view class="card-body">
          <view class="card-head">
            <view class="badge badge-a">甲</view>
            <text class="card-title display-font">甲方信息</text>
          </view>

          <view class="form-row">
            <text class="label">出生日期</text>
            <picker mode="date" :value="a.date" :end="today" @change="(e: any) => a.date = e.detail.value">
              <view class="picker">
                <text class="picker-text">{{ a.date || '选择日期' }}</text>
                <text class="picker-icon">▤</text>
              </view>
            </picker>
          </view>

          <view class="form-row">
            <text class="label">出生时辰</text>
            <picker mode="time" :value="a.time" @change="(e: any) => a.time = e.detail.value">
              <view class="picker">
                <text class="picker-text">{{ a.time || '选择时间' }}</text>
                <text class="picker-icon">◷</text>
              </view>
            </picker>
          </view>

          <view class="form-row">
            <text class="label">性别</text>
            <view class="seg-group">
              <text :class="['seg', a.gender === '男' && 'active']" @tap="a.gender = '男'">男</text>
              <text :class="['seg', a.gender === '女' && 'active']" @tap="a.gender = '女'">女</text>
            </view>
          </view>
        </view>
      </view>

      <!-- 能量连接器 -->
      <view class="connector">
        <view class="line line-left"></view>
        <view class="connector-icon">
          <text class="connector-glyph">⚡</text>
        </view>
        <view class="line line-right"></view>
      </view>

      <!-- 乙方卡片 -->
      <view class="person-card person-b">
        <view class="card-gradient-top gradient-b"></view>
        <view class="card-body">
          <view class="card-head">
            <view class="badge badge-b">乙</view>
            <text class="card-title display-font">乙方信息</text>
          </view>

          <view class="form-row">
            <text class="label">出生日期</text>
            <picker mode="date" :value="b.date" :end="today" @change="(e: any) => b.date = e.detail.value">
              <view class="picker">
                <text class="picker-text">{{ b.date || '选择日期' }}</text>
                <text class="picker-icon">▤</text>
              </view>
            </picker>
          </view>

          <view class="form-row">
            <text class="label">出生时辰</text>
            <picker mode="time" :value="b.time" @change="(e: any) => b.time = e.detail.value">
              <view class="picker">
                <text class="picker-text">{{ b.time || '选择时间' }}</text>
                <text class="picker-icon">◷</text>
              </view>
            </picker>
          </view>

          <view class="form-row">
            <text class="label">性别</text>
            <view class="seg-group">
              <text :class="['seg', b.gender === '男' && 'active']" @tap="b.gender = '男'">男</text>
              <text :class="['seg', b.gender === '女' && 'active']" @tap="b.gender = '女'">女</text>
            </view>
          </view>
        </view>
      </view>

      <!-- 开始分析按钮 -->
      <view class="cta-wrap">
        <view
          :class="['cta-btn', (loading || !canSubmit) && 'disabled']"
          @tap="onAnalyze"
        >
          <text class="cta-glyph">✦</text>
          <text class="cta-text">{{ loading ? '分析中…' : '开始分析' }}</text>
        </view>
      </view>

      <!-- 结果卡片 -->
      <view v-if="result" class="result-card">
        <view class="card-gradient-top gradient-result"></view>
        <view class="card-body">
          <view class="card-head">
            <view class="badge badge-result">☰</view>
            <text class="card-title display-font">合婚报告</text>
          </view>
          <text class="result-text">{{ result }}</text>
        </view>
      </view>

      <view class="bottom-spacer"></view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { hehun } from '@/api'

const today = new Date().toISOString().slice(0, 10)
const a = reactive({ date: '', time: '', gender: '男' as '男' | '女' })
const b = reactive({ date: '', time: '', gender: '女' as '男' | '女' })
const loading = ref(false)
const result = ref('')

// 状态栏高度
const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getWindowInfo()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}

function goBack() {
  uni.navigateBack()
}

const canSubmit = computed(() => a.date && a.time && b.date && b.time)

async function onAnalyze() {
  if (!canSubmit.value || loading.value) return
  loading.value = true
  result.value = ''
  try {
    const res = await hehun({
      birthTimeA: `${a.date} ${a.time}`,
      genderA: a.gender,
      birthTimeB: `${b.date} ${b.time}`,
      genderB: b.gender,
    })
    result.value = res.result || '无结果'
  } catch (e: any) {
    uni.showToast({ title: e.message || '分析失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss">
.page {
  height: calc(100vh - var(--window-bottom));
  overflow: hidden;
  background: $color-bg;
  color: $color-ink;
}
.scroll { height: 100%; }

/* 状态栏占位 */
.status-bar { width: 100%; }

/* === 页面头 === */
.page-header {
  position: relative;
  padding: 88rpx 32rpx 48rpx;
  align-items: center;
  text-align: center;
}
.back-btn {
  position: absolute;
  left: 32rpx;
  top: 88rpx;
  width: 56rpx;
  height: 56rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}
.back-arrow {
  font-size: 48rpx;
  color: $color-primary;
  line-height: 1;
}
.page-title {
  display: block;
  font-family: $font-family-display;
  font-size: 44rpx;
  font-weight: 600;
  color: $color-primary;
  line-height: 1.3;
  margin-bottom: 16rpx;
  letter-spacing: 0.12em;
}
.page-sub {
  display: block;
  margin-top: 12rpx;
  font-size: 24rpx;
  color: $color-ink-light;
  line-height: 1.6;
  letter-spacing: 0.04em;
}

/* === 人物卡片 === */
.person-card {
  margin: 0 32rpx;
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: 24rpx;
  overflow: hidden;
  box-shadow: $shadow-sm;
}
.card-gradient-top {
  height: 4rpx;
}
.gradient-a {
  background: linear-gradient(90deg, transparent, $color-primary, $color-primary-lighter, transparent);
}
.gradient-b {
  background: linear-gradient(90deg, transparent, $color-vermilion, $color-vermilion-light, transparent);
}
.gradient-result {
  background: linear-gradient(90deg, transparent, $color-primary, $color-vermilion, transparent);
}
.card-body { padding: 36rpx; }
.person-card .card-body { padding: 36rpx 32rpx 38rpx; }
.card-head {
  display: flex;
  align-items: center;
  gap: 18rpx;
  margin-bottom: 32rpx;
}
.badge {
  width: 56rpx;
  height: 56rpx;
  line-height: 56rpx;
  text-align: center;
  border-radius: 50%;
  font-family: $font-family-display;
  font-size: 28rpx;
  font-weight: 600;
  border: 1rpx solid;
}
.badge-a {
  background: rgba(44, 44, 44, 0.06);
  border-color: $color-primary;
  color: $color-primary;
}
.badge-b {
  background: rgba(184, 72, 60, 0.06);
  border-color: $color-vermilion;
  color: $color-vermilion;
}
.badge-result {
  background: rgba(44, 44, 44, 0.04);
  border-color: $color-border;
  color: $color-primary;
}
.card-title {
  font-family: $font-family-display;
  font-size: 32rpx;
  font-weight: 600;
  color: $color-ink;
  letter-spacing: 0.06em;
}

/* 表单 */
.form-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 20rpx;
  margin-bottom: 28rpx;
}
.label {
  flex: 0 0 140rpx;
  font-size: 24rpx;
  color: $color-ink-light;
  letter-spacing: 0.04em;
}
.form-row picker,
.seg-group {
  flex: 1;
  min-width: 0;
}
.picker {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 76rpx;
  padding: 0 24rpx;
  background: $color-bg-warm;
  border: 1rpx solid $color-border-light;
  border-radius: 12rpx;
}
.person-b .picker {
  background: rgba(184, 72, 60, 0.03);
  border-color: rgba(184, 72, 60, 0.1);
}
.picker-text {
  font-size: 26rpx;
  color: $color-ink;
}
.picker-icon {
  color: $color-ink-lighter;
  font-size: 28rpx;
}
.seg-group {
  display: flex;
  height: 76rpx;
  border: 1rpx solid $color-border;
  border-radius: 12rpx;
  overflow: hidden;
}
.seg {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26rpx;
  color: $color-ink-light;
  background: $color-bg-warm;
}
.person-b .seg {
  background: rgba(184, 72, 60, 0.03);
}
.seg.active {
  background: rgba(44, 44, 44, 0.08);
  color: $color-primary;
}
.person-b .seg.active {
  background: rgba(184, 72, 60, 0.08);
  color: $color-vermilion;
}

/* === 能量连接器 === */
.connector {
  display: flex;
  align-items: center;
  padding: 32rpx 32rpx;
}
.line {
  flex: 1;
  height: 2rpx;
}
.line-left {
  background: linear-gradient(90deg, transparent, rgba(44, 44, 44, 0.2));
}
.line-right {
  background: linear-gradient(270deg, transparent, rgba(44, 44, 44, 0.2));
}
.connector-icon {
  margin: 0 24rpx;
  width: 60rpx;
  height: 60rpx;
  line-height: 60rpx;
  text-align: center;
  border-radius: 50%;
  border: 2rpx solid $color-primary;
  background: rgba(44, 44, 44, 0.04);
}
.connector-glyph {
  color: $color-primary;
  font-size: 30rpx;
}

/* === CTA 按钮 === */
.cta-wrap {
  padding: 40rpx 32rpx 48rpx;
}
.cta-btn {
  height: 92rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16rpx;
  background: $color-primary;
  border-radius: 16rpx;
}
.cta-btn.disabled { opacity: 0.5; }
.cta-glyph {
  color: $color-bg;
  font-size: 30rpx;
}
.cta-text {
  color: $color-bg;
  font-size: 30rpx;
  font-weight: 600;
  letter-spacing: 0.12em;
}

/* === 结果卡片 === */
.result-card {
  margin: 0 32rpx 48rpx;
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: 24rpx;
  overflow: hidden;
  box-shadow: $shadow-sm;
}
.result-text {
  font-size: 28rpx;
  line-height: 1.8;
  color: $color-ink;
  white-space: pre-wrap;
  letter-spacing: 0.02em;
}

.bottom-spacer { height: 48rpx; }
</style>
