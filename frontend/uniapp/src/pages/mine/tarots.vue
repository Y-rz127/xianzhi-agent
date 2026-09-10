<template>
  <view class="page">
    <view class="nav-placeholder"></view>
    <view class="nav-bar">
      <text class="back" @tap="goBack">‹</text>
      <text class="title">AI 解读记录</text>
      <view style="width: 120rpx;"></view>
    </view>
    <view class="body empty-state">
      <text class="empty-icon">✦</text>
      <text class="empty-text">已统一迁移到通用 AI 解读记录页</text>
    </view>
  </view>
</template>

<script setup lang="ts">
function goBack() { uni.navigateBack({ fail: () => uni.reLaunch({ url: '/pages/mine/index' }) }) }
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
</style>

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
