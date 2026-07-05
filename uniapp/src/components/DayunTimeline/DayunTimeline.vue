<template>
  <view class="dayun-timeline" v-if="dayun.length">
    <view class="timeline-header">
      <text class="header-title">大运流年</text>
      <text class="header-sub">每十年一步大运</text>
    </view>
    <view class="timeline-container">
      <view class="timeline-line"></view>
      <view
        v-for="(d, idx) in dayun"
        :key="idx"
        class="dayun-node"
      >
        <view class="node-dot">
          <view class="dot-inner"></view>
        </view>
        <view class="node-content">
          <text class="node-year">{{ d.year }}</text>
          <text class="node-age">{{ d.startAge }}-{{ d.startAge + 9 }}岁</text>
          <text class="node-range">{{ d.startYear }}-{{ d.startYear + 9 }}</text>
          <view v-if="d.liunian && d.liunian.length" class="liunian-list">
            <text
              v-for="(l, i) in d.liunian.slice(0, 5)"
              :key="i"
              class="liunian-item"
            >{{ l.year }} {{ l.ganzhi }}</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
interface LiuNian { year: string; ganzhi: string }
interface Dayun { year: string; ganzhi: string; startAge: number; startYear: number; liunian?: LiuNian[] }
defineProps<{ dayun: Dayun[] }>()
</script>

<style lang="scss" scoped>
.dayun-timeline {
  position: relative;
  padding: 32rpx;
  border-radius: 16rpx;
  margin-bottom: 24rpx;
  background: rgba(15, 21, 32, 0.92);
  border: 1rpx solid rgba(212, 175, 55, 0.2);
  box-shadow: 0 8rpx 32rpx rgba(0, 0, 0, 0.35);
  overflow: hidden;
}
.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 32rpx;
}
.header-title {
  font-size: 24rpx;
  color: #e6c068;
  letter-spacing: 6rpx;
  font-weight: 600;
}
.header-sub {
  font-size: 20rpx;
  color: #64748b;
  letter-spacing: 4rpx;
}
.timeline-container {
  position: relative;
  padding-left: 48rpx;
}
.timeline-line {
  position: absolute;
  left: 20rpx;
  top: 0;
  bottom: 0;
  width: 2rpx;
  background: linear-gradient(180deg, rgba(212, 175, 55, 0.5), rgba(139, 92, 246, 0.2));
}
.dayun-node {
  position: relative;
  padding-left: 24rpx;
  margin-bottom: 32rpx;
}
.dayun-node:last-child {
  margin-bottom: 0;
}
.node-dot {
  position: absolute;
  left: -36rpx;
  top: 8rpx;
  width: 20rpx;
  height: 20rpx;
  border-radius: 50%;
  background: #d4af37;
  box-shadow: 0 0 12rpx rgba(212, 175, 55, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
}
.dot-inner {
  width: 8rpx;
  height: 8rpx;
  background: #0a0f1a;
  border-radius: 50%;
}
.node-content {
  background: rgba(255, 255, 255, 0.02);
  border-radius: 16rpx;
  padding: 20rpx;
  border: 1rpx solid rgba(255, 255, 255, 0.08);
}
.node-year {
  display: block;
  font-size: 32rpx;
  font-weight: bold;
  color: #e6c068;
  letter-spacing: 4rpx;
  margin-bottom: 8rpx;
}
.node-age {
  display: block;
  font-size: 24rpx;
  color: #94a3b8;
  margin-bottom: 4rpx;
}
.node-range {
  display: block;
  font-size: 22rpx;
  color: #64748b;
  margin-bottom: 12rpx;
}
.liunian-list {
  display: flex;
  flex-wrap: wrap;
}
.liunian-item {
  font-size: 22rpx;
  padding: 6rpx 14rpx;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 8rpx;
  color: #94a3b8;
  border: 1rpx solid rgba(255, 255, 255, 0.08);
  margin: 6rpx 8rpx 0 0;
}
</style>
