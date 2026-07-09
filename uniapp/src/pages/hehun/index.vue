<template>
  <view class="page">
    <scroll-view class="scroll" scroll-y>
      <!-- 状态栏占位 -->
      <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

      <!-- 页面头 -->
      <view class="page-header">
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
  background: linear-gradient(180deg, #160F2E 0%, #0F0B1E 100%);
  color: #E2E8F0;
}
.scroll { height: 100%; }

/* 状态栏占位 */
.status-bar { width: 100%; }

/* === 页面头 === */
.page-header {
  padding: 40rpx 32rpx 28rpx;
  align-items: center;
  text-align: center;
}
.page-title {
  display: block;
  font-size: 40rpx;
  font-weight: 600;
  color: #C4B5FD;
  text-shadow: 0 0 48rpx rgba(124, 58, 237, 0.4);
  line-height: 1.25;
  margin-bottom: 12rpx;
}
.page-sub {
  display: block;
  margin-top: 10rpx;
  font-size: 24rpx;
  color: #94A3B8;
  line-height: 1.5;
}

/* === 人物卡片 === */
.person-card {
  margin: 0 28rpx;
  background: rgba(30, 22, 56, 0.8);
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 32rpx;
  overflow: hidden;
}
.card-gradient-top {
  height: 4rpx;
}
.gradient-a {
  background: linear-gradient(90deg, transparent, #7C3AED, #06B6D4, transparent);
}
.gradient-b {
  background: linear-gradient(90deg, transparent, #06B6D4, #7C3AED, transparent);
}
.gradient-result {
  background: linear-gradient(90deg, transparent, #06B6D4, #F59E0B, transparent);
}
.card-body { padding: 32rpx; }
.person-card .card-body { padding: 28rpx 28rpx 30rpx; }
.card-head {
  display: flex;
  align-items: center;
  gap: 16rpx;
  margin-bottom: 24rpx;
}
.badge {
  width: 52rpx;
  height: 52rpx;
  line-height: 52rpx;
  text-align: center;
  border-radius: 50%;
  font-size: 26rpx;
  font-weight: 600;
  border: 1rpx solid;
}
.badge-a {
  background: rgba(124, 58, 237, 0.2);
  border-color: #7C3AED;
  color: #C4B5FD;
  box-shadow: 0 0 24rpx rgba(124, 58, 237, 0.3);
}
.badge-b {
  background: rgba(6, 182, 212, 0.15);
  border-color: #06B6D4;
  color: #67E8F9;
  box-shadow: 0 0 24rpx rgba(6, 182, 212, 0.3);
}
.badge-result {
  background: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.3);
  color: #F59E0B;
}
.card-title {
  font-size: 32rpx;
  font-weight: 600;
  color: #E2E8F0;
}

/* 表单 */
.form-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 20rpx;
  margin-bottom: 20rpx;
}
.label {
  flex: 0 0 140rpx;
  font-size: 24rpx;
  color: #94A3B8;
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
  height: 72rpx;
  padding: 0 20rpx;
  background: rgba(124, 58, 237, 0.08);
  border: 1rpx solid rgba(124, 58, 237, 0.1);
  border-radius: 20rpx;
}
.person-b .picker {
  background: rgba(6, 182, 212, 0.06);
  border-color: rgba(6, 182, 212, 0.1);
}
.picker-text {
  font-size: 26rpx;
  color: #E2E8F0;
}
.picker-icon {
  color: #64748B;
  font-size: 28rpx;
}
.seg-group {
  display: flex;
  height: 72rpx;
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 20rpx;
  overflow: hidden;
}
.seg {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26rpx;
  color: #94A3B8;
  background: rgba(124, 58, 237, 0.06);
}
.person-b .seg {
  background: rgba(6, 182, 212, 0.06);
}
.seg.active {
  background: rgba(124, 58, 237, 0.25);
  color: #C4B5FD;
}
.person-b .seg.active {
  background: rgba(6, 182, 212, 0.2);
  color: #67E8F9;
}

/* === 能量连接器 === */
.connector {
  display: flex;
  align-items: center;
  padding: 24rpx 32rpx;
}
.line {
  flex: 1;
  height: 2rpx;
}
.line-left {
  background: linear-gradient(90deg, transparent, rgba(6, 182, 212, 0.5));
}
.line-right {
  background: linear-gradient(270deg, transparent, rgba(6, 182, 212, 0.5));
}
.connector-icon {
  margin: 0 24rpx;
  width: 56rpx;
  height: 56rpx;
  line-height: 56rpx;
  text-align: center;
  border-radius: 50%;
  border: 3rpx solid #06B6D4;
  background: rgba(6, 182, 212, 0.1);
  box-shadow: 0 0 24rpx rgba(6, 182, 212, 0.3);
}
.connector-glyph {
  color: #67E8F9;
  font-size: 30rpx;
}

/* === CTA 按钮 === */
.cta-wrap {
  padding: 28rpx 28rpx 32rpx;
}
.cta-btn {
  height: 88rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16rpx;
  background: linear-gradient(135deg, #7C3AED 0%, #6D28D9 100%);
  border-radius: 24rpx;
  box-shadow: 0 0 40rpx rgba(124, 58, 237, 0.3);
}
.cta-btn.disabled { opacity: 0.5; }
.cta-glyph {
  color: #ffffff;
  font-size: 30rpx;
}
.cta-text {
  color: #ffffff;
  font-size: 30rpx;
  font-weight: 600;
  letter-spacing: 0.08em;
}

/* === 结果卡片 === */
.result-card {
  margin: 0 28rpx 40rpx;
  background: rgba(30, 22, 56, 0.8);
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 32rpx;
  overflow: hidden;
}
.result-text {
  font-size: 28rpx;
  line-height: 1.7;
  color: #E2E8F0;
  white-space: pre-wrap;
}

.bottom-spacer { height: 40rpx; }
</style>
