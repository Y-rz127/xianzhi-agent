<template>
  <view class="bazi-card" v-if="pillars.length">
    <view class="card-header">
      <text class="card-title">四柱命盘</text>
      <text class="card-sub">年 · 月 · 日 · 时</text>
    </view>
    <view class="pillars">
      <view
        v-for="(p, idx) in pillars"
        :key="p.name"
        :class="['pillar', p.name === '日柱' && 'day-master']"
      >
        <text class="pillar-name">{{ p.name }}</text>
        <text class="pillar-gan">{{ p.ganzhi[0] }}</text>
        <text class="pillar-zhi">{{ p.ganzhi[1] }}</text>
        <text class="pillar-nayin">{{ p.nayin }}</text>
        <text v-if="p.name === '日柱'" class="day-badge">日主</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import type { Pillar } from '@/api'
defineProps<{ pillars: Pillar[] }>()
</script>

<style lang="scss" scoped>
.bazi-card {
  position: relative;
  border-radius: 16rpx;
  padding: 32rpx;
  margin-bottom: 24rpx;
  background: rgba(15, 21, 32, 0.92);
  border: 1rpx solid rgba(212, 175, 55, 0.2);
  box-shadow: 0 8rpx 32rpx rgba(0, 0, 0, 0.35);
  overflow: hidden;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 28rpx;
}
.card-title {
  font-size: 24rpx;
  color: #e6c068;
  letter-spacing: 6rpx;
  font-weight: 600;
}
.card-sub {
  font-size: 20rpx;
  color: #64748b;
  letter-spacing: 4rpx;
}
.pillars {
  display: flex;
  justify-content: space-between;
}
.pillar {
  position: relative;
  flex: 1;
  margin: 0 8rpx;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 16rpx;
  padding: 24rpx 12rpx;
  text-align: center;
  border: 1rpx solid rgba(255, 255, 255, 0.08);
}
.pillar.day-master {
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.08), rgba(139, 92, 246, 0.05));
  border-color: rgba(212, 175, 55, 0.35);
  box-shadow: 0 0 16rpx rgba(212, 175, 55, 0.1);
}
.pillar-name {
  display: block;
  font-size: 20rpx;
  color: #64748b;
  margin-bottom: 16rpx;
  letter-spacing: 4rpx;
}
.pillar-gan {
  display: block;
  font-size: 40rpx;
  font-weight: bold;
  color: #e5e7eb;
  letter-spacing: 4rpx;
  margin-bottom: 6rpx;
}
.pillar.day-master .pillar-gan {
  color: #e6c068;
}
.pillar-zhi {
  display: block;
  font-size: 40rpx;
  font-weight: bold;
  color: #e5e7eb;
  letter-spacing: 4rpx;
  margin-bottom: 10rpx;
}
.pillar.day-master .pillar-zhi {
  color: #e6c068;
}
.pillar-nayin {
  display: block;
  font-size: 20rpx;
  color: #64748b;
}
.day-badge {
  position: absolute;
  top: -10rpx;
  right: -6rpx;
  background: #d4af37;
  color: #0a0f1a;
  font-size: 18rpx;
  padding: 4rpx 14rpx;
  border-radius: 16rpx;
  font-weight: bold;
}
</style>
