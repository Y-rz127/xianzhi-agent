<template>
  <view class="wuxing-chart" v-if="items.length">
    <view class="card-header">
      <text class="chart-title">五行分布</text>
      <text class="chart-sub">金 · 木 · 水 · 火 · 土</text>
    </view>
    <view class="bars">
      <view v-for="item in items" :key="item.name" class="bar-item">
        <text class="bar-count">{{ item.count }}</text>
        <view class="bar-container">
          <view
            class="bar-fill"
            :style="{
              height: barHeight(item.count) + '%',
              background: item.color,
            }"
          ></view>
        </view>
        <text class="bar-label" :style="{ color: item.color }">{{ item.name }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WuxingItem } from '@/api'
const props = defineProps<{ items: WuxingItem[] }>()
const maxCount = computed(() => Math.max(...props.items.map((i) => i.count), 1))
const barHeight = (count: number) => (count / maxCount.value) * 100
</script>

<style lang="scss" scoped>
.wuxing-chart {
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
.chart-title {
  font-size: 24rpx;
  color: #e6c068;
  letter-spacing: 6rpx;
  font-weight: 600;
}
.chart-sub {
  font-size: 20rpx;
  color: #64748b;
  letter-spacing: 4rpx;
}
.bars {
  display: flex;
  justify-content: space-around;
  align-items: flex-end;
  height: 240rpx;
}
.bar-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 18%;
}
.bar-count {
  font-size: 28rpx;
  font-weight: bold;
  color: #e5e7eb;
  margin-bottom: 12rpx;
}
.bar-container {
  width: 100%;
  height: 160rpx;
  display: flex;
  align-items: flex-end;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 12rpx 12rpx 0 0;
  overflow: hidden;
}
.bar-fill {
  width: 100%;
  border-radius: 12rpx 12rpx 0 0;
  min-height: 8rpx;
}
.bar-label {
  font-size: 28rpx;
  font-weight: bold;
  margin-top: 12rpx;
}
</style>
