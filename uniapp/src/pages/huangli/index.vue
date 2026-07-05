<template>
  <view class="page">
    <!-- 顶部紫青渐变头：日期信息 -->
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>
    <view class="header">
      <text class="header-eyebrow">公历</text>
      <text class="header-title">{{ data?.solar || '加载中…' }}</text>
      <text v-if="data" class="header-lunar">{{ data.lunar }} {{ data.shengXiao }}年</text>
      <view class="header-deco"></view>
    </view>

    <scroll-view class="scroll" scroll-y>
      <view class="content">
        <!-- 干支卡片 -->
        <view v-if="data" class="card ganzhi-card">
          <text class="card-title">今日干支</text>
          <view class="ganzhi-row">
            <view class="ganzhi-item">
              <text class="gz-label">年柱</text>
              <view class="gz-hex">
                <text class="gz-gan">{{ data.yearGanZhi[0] }}</text>
                <view class="gz-divider"></view>
                <text class="gz-zhi">{{ data.yearGanZhi[1] }}</text>
              </view>
            </view>
            <view class="ganzhi-item">
              <text class="gz-label">月柱</text>
              <view class="gz-hex">
                <text class="gz-gan">{{ data.monthGanZhi[0] }}</text>
                <view class="gz-divider"></view>
                <text class="gz-zhi">{{ data.monthGanZhi[1] }}</text>
              </view>
            </view>
            <view class="ganzhi-item">
              <text class="gz-label">日柱</text>
              <view class="gz-hex">
                <text class="gz-gan">{{ data.dayGanZhi[0] }}</text>
                <view class="gz-divider"></view>
                <text class="gz-zhi">{{ data.dayGanZhi[1] }}</text>
              </view>
            </view>
          </view>

          <view class="info-grid">
            <view v-if="data.jieQi" class="info-cell">
              <text class="info-label">节气</text>
              <text class="info-val info-val-accent">{{ data.jieQi }}</text>
            </view>
            <view v-if="data.naYin" class="info-cell">
              <text class="info-label">纳音</text>
              <text class="info-val">{{ data.naYin }}</text>
            </view>
            <view class="info-cell">
              <text class="info-label">冲</text>
              <text class="info-val">{{ data.chong }}</text>
            </view>
            <view class="info-cell">
              <text class="info-label">煞</text>
              <text class="info-val">{{ data.sha }}</text>
            </view>
          </view>
        </view>

        <!-- 宜 / 忌 卡片 -->
        <view v-if="data" class="card yiji-card">
          <view class="yiji-section">
            <text class="yiji-title">宜</text>
            <view class="tag-list">
              <text v-for="(y, i) in data.yi" :key="'y'+i" class="tag tag-yi">{{ y }}</text>
            </view>
          </view>
          <view class="yiji-divider"></view>
          <view class="yiji-section">
            <text class="yiji-title">忌</text>
            <view class="tag-list">
              <text v-for="(j, i) in data.ji" :key="'j'+i" class="tag tag-ji">{{ j }}</text>
            </view>
          </view>
        </view>

        <!-- 吉时卡片 -->
        <view v-if="data?.jiShi?.length" class="card jishi-card">
          <text class="card-title">吉时</text>
          <view class="jishi-list">
            <view
              v-for="(t, i) in data.jiShi"
              :key="'jt'+i"
              class="jishi-item"
            >
              <view class="jishi-dot"></view>
              <text class="jishi-ganzhi">{{ t.ganzhi }}</text>
              <view class="jishi-info">
                <text class="jishi-time">{{ t.time }}</text>
                <text class="jishi-desc">吉</text>
              </view>
            </view>
          </view>
        </view>

        <view class="bottom-spacer"></view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getHuangli, type HuangliData } from '@/api'

const data = ref<HuangliData | null>(null)

// 状态栏高度
const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getSystemInfoSync()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}

onMounted(async () => {
  try {
    data.value = await getHuangli()
  } catch (e: any) {
    uni.showToast({ title: e.message || '加载失败', icon: 'none' })
  }
})
</script>

<style lang="scss">
.page {
  height: 100vh;
  background: linear-gradient(180deg, #160F2E 0%, #0F0B1E 100%);
  color: #E2E8F0;
  display: flex;
  flex-direction: column;
}

/* 状态栏占位 */
.status-bar { width: 100%; }

/* === 顶部紫青渐变头 === */
.header {
  position: relative;
  padding: 32rpx 40rpx 56rpx;
  background: linear-gradient(135deg, #7C3AED 0%, #06B6D4 100%);
  overflow: hidden;
}
.header-eyebrow {
  font-size: 22rpx;
  color: rgba(255, 255, 255, 0.5);
}
.header-title {
  display: block;
  margin-top: 8rpx;
  font-size: 48rpx;
  font-weight: 600;
  color: #ffffff;
  letter-spacing: 0.04em;
  line-height: 1.2;
}
.header-lunar {
  display: block;
  margin-top: 16rpx;
  font-size: 30rpx;
  color: rgba(255, 255, 255, 0.85);
  line-height: 1.5;
}
/* 装饰几何元素 */
.header-deco {
  position: absolute;
  top: 32rpx;
  right: 40rpx;
  width: 80rpx;
  height: 80rpx;
  border: 1rpx solid rgba(255, 255, 255, 0.15);
  /* 六边形 clip-path */
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
}

/* 滚动区上移覆盖头部 */
.scroll { flex: 1; }
.content {
  padding: 0 32rpx;
  margin-top: -32rpx;
  position: relative;
  z-index: 2;
}

/* === 通用卡片 === */
.card {
  background: rgba(30, 22, 56, 0.8);
  backdrop-filter: blur(32rpx);
  -webkit-backdrop-filter: blur(32rpx);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 32rpx;
  padding: 40rpx;
  margin-bottom: 32rpx;
}
.card-title {
  display: block;
  font-size: 30rpx;
  font-weight: 600;
  color: #E2E8F0;
  letter-spacing: 0.04em;
  margin-bottom: 32rpx;
}

/* === 干支 === */
.ganzhi-row {
  display: flex;
  justify-content: space-around;
  align-items: flex-start;
}
.ganzhi-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12rpx;
}
.gz-label {
  font-size: 22rpx;
  color: #64748B;
}
.gz-hex {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24rpx 32rpx;
  min-width: 112rpx;
  background: #160F2E;
  border: 1rpx solid #8B5CF6;
  box-shadow: 0 0 24rpx rgba(124, 58, 237, 0.3);
  /* 六边形形状 */
  clip-path: polygon(15% 0%, 85% 0%, 100% 50%, 85% 100%, 15% 100%, 0% 50%);
}
.gz-gan {
  font-size: 40rpx;
  font-weight: 600;
  color: #A78BFA;
  line-height: 1;
}
.gz-divider {
  width: 40rpx;
  height: 2rpx;
  background: rgba(124, 58, 237, 0.3);
  margin: 12rpx 0;
}
.gz-zhi {
  font-size: 40rpx;
  font-weight: 600;
  color: #E2E8F0;
  line-height: 1;
}

/* 干支信息网格 */
.info-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 24rpx 40rpx;
  margin-top: 40rpx;
  padding-top: 32rpx;
  border-top: 1rpx solid rgba(148, 163, 184, 0.12);
}
.info-cell {
  display: flex;
  align-items: center;
  gap: 12rpx;
}
.info-label {
  font-size: 22rpx;
  color: #64748B;
}
.info-val {
  font-size: 26rpx;
  font-weight: 500;
  color: #E2E8F0;
}
.info-val-accent { color: #06B6D4; }

/* === 宜 / 忌 === */
.yiji-section {
  /* */
}
.yiji-title {
  display: block;
  font-size: 30rpx;
  font-weight: 600;
  color: #E2E8F0;
  letter-spacing: 0.04em;
  margin-bottom: 24rpx;
}
.yiji-divider {
  height: 1rpx;
  background: rgba(148, 163, 184, 0.12);
  margin: 32rpx 0;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
}
.tag {
  padding: 12rpx 24rpx;
  border-radius: 20rpx;
  font-size: 24rpx;
  border: 1rpx solid;
}
.tag-yi {
  background: rgba(16, 185, 129, 0.12);
  color: #34D399;
  border-color: rgba(16, 185, 129, 0.2);
  box-shadow: 0 0 16rpx rgba(16, 185, 129, 0.15);
}
.tag-ji {
  background: rgba(239, 68, 68, 0.1);
  color: #EF4444;
  border-color: rgba(239, 68, 68, 0.2);
  box-shadow: 0 0 16rpx rgba(239, 68, 68, 0.12);
}

/* === 吉时 === */
.jishi-list {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
  position: relative;
}
.jishi-item {
  display: flex;
  align-items: center;
  gap: 24rpx;
  padding: 24rpx 32rpx;
  background: #160F2E;
  border: 1rpx solid rgba(124, 58, 237, 0.1);
  border-radius: 24rpx;
}
.jishi-dot {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  background: #06B6D4;
  box-shadow: 0 0 20rpx rgba(6, 182, 212, 0.5);
  flex-shrink: 0;
}
.jishi-ganzhi {
  font-size: 32rpx;
  font-weight: 600;
  color: #F59E0B;
  font-family: 'Orbitron', 'Rajdhani', 'PingFang SC', sans-serif;
  letter-spacing: 0.04em;
  flex-shrink: 0;
  min-width: 80rpx;
}
.jishi-info {
  display: flex;
  flex-direction: column;
  gap: 4rpx;
  flex: 1;
}
.jishi-time {
  font-size: 26rpx;
  color: #E2E8F0;
}
.jishi-desc {
  font-size: 22rpx;
  color: #64748B;
}

.bottom-spacer { height: 80rpx; }
</style>
