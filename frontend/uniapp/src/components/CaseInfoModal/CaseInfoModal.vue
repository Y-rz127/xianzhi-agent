<template>
  <view v-if="show" class="cim-mask" @tap="$emit('close')">
    <view class="cim-card" @tap.stop>
      <view class="cim-header">
        <text class="cim-title">{{ title }}</text>
        <text class="cim-close" @tap="$emit('close')">✕</text>
      </view>
      <view class="cim-body">
        <view v-if="bio" class="cim-section">
          <text class="cim-label">生平简介</text>
          <view class="cim-box"><text class="cim-text">{{ bio }}</text></view>
        </view>
        <view v-if="analysis" class="cim-section">
          <text class="cim-label">命局结构分析</text>
          <view class="cim-box"><text class="cim-text">{{ analysis }}</text></view>
        </view>
        <view v-if="keypoints" class="cim-section">
          <text class="cim-label">命理特征要点</text>
          <view class="cim-box"><text class="cim-text">{{ keypoints }}</text></view>
        </view>
        <text v-if="!bio && !analysis && !keypoints" class="cim-empty">暂无简介资料</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
defineProps<{
  show: boolean
  title: string
  bio?: string
  analysis?: string
  keypoints?: string
}>()

defineEmits<{ close: [] }>()
</script>

<style lang="scss" scoped>
/* 配色走 $color-*（映射 var(--x-*)），随页面根节点 .t-light/.t-dark 自动换肤 */
.cim-mask {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.cim-card {
  width: 82%; max-width: 640rpx; max-height: 78%;
  background: $color-paper;
  border: 1rpx solid $color-border;
  border-radius: 20rpx;
  box-shadow: $shadow-elevated;
  display: flex; flex-direction: column; overflow: hidden;
}
.cim-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 28rpx 32rpx 16rpx;
  border-bottom: 1rpx solid $color-border;
}
.cim-title {
  flex: 1;
  font-size: 34rpx; font-weight: 600;
  color: $color-ink;
  letter-spacing: 2rpx;
}
.cim-close { font-size: 36rpx; color: $color-ink-light; padding: 0 8rpx; }
.cim-body { padding: 24rpx 32rpx 32rpx; overflow-y: auto; }
.cim-section { margin-bottom: 24rpx; }
.cim-section:last-child { margin-bottom: 0; }
.cim-label {
  display: block;
  font-size: 26rpx; font-weight: 600;
  color: $color-ink-light;
  letter-spacing: 2rpx;
  margin-bottom: 12rpx;
}
.cim-box {
  background: $color-paper-warm;
  border: 1rpx solid $color-border;
  border-radius: 12rpx;
  padding: 20rpx 24rpx;
}
.cim-text {
  display: block;
  font-size: 27rpx;
  color: $color-ink;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-all;
}
.cim-empty {
  display: block;
  text-align: center;
  font-size: 26rpx;
  color: $color-ink-lighter;
  padding: 48rpx 0;
  letter-spacing: 2rpx;
}
</style>
