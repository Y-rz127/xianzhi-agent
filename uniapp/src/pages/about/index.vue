<template>
  <view class="page">
    <view class="body">
      <view class="logo">☯</view>
      <text class="app-name">先知 · 玄学命理</text>
      <text class="slogan">知命不惑，顺势而为</text>

      <view class="card">
        <view class="row"><text class="k">版本</text><text class="v">1.0.0</text></view>
        <view class="divider"></view>
        <view class="row"><text class="k">功能</text><text class="v">八字排盘 · 塔罗 · 命理问答</text></view>
        <view class="divider"></view>
        <view class="row"><text class="k">说明</text><text class="v">内容由 AI 生成，仅供娱乐参考</text></view>
      </view>

      <view class="links">
        <view class="link-row" @tap="goFeedback"><text>问题反馈</text><text class="arrow">›</text></view>
        <view class="link-row" @tap="goPrivacy"><text>隐私政策</text><text class="arrow">›</text></view>
        <view class="link-row" @tap="goTerms"><text>服务条款</text><text class="arrow">›</text></view>
      </view>

      <text class="footer">© 2026 先知 · 仅供娱乐，切勿迷信</text>
    </view>
  </view>
</template>

<script setup lang="ts">
function goFeedback() { uni.navigateTo({ url: '/pages/feedback/index' }) }
function goPrivacy() { uni.navigateTo({ url: '/pages/legal/privacy' }) }
function goTerms() { uni.navigateTo({ url: '/pages/legal/terms' }) }
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: $color-bg; display: flex; flex-direction: column; }
.body { padding: 48rpx 32rpx; display: flex; flex-direction: column; align-items: center; }
.logo { font-size: 120rpx; color: $color-primary; text-shadow: 0 0 32rpx rgba(107, 123, 142, 0.5); }
.app-name { font-size: 40rpx; font-weight: 700; color: $color-ink; letter-spacing: 6rpx; margin-top: 16rpx; }
.slogan { font-size: 24rpx; color: $color-ink-light; margin-top: 12rpx; letter-spacing: 4rpx; }
.card { width: 100%; margin-top: 48rpx; background: $color-bg-card; border: 1rpx solid $color-border; border-radius: 24rpx; padding: 12rpx 28rpx; }
.row { display: flex; justify-content: space-between; align-items: center; padding: 22rpx 0; }
.k { font-size: 26rpx; color: $color-ink-light; }
.v { font-size: 26rpx; color: $color-ink; text-align: right; flex: 1; margin-left: 24rpx; }
.divider { height: 1rpx; background: $color-border; }
.links { width: 100%; margin-top: 32rpx; background: $color-bg-card; border: 1rpx solid $color-border; border-radius: 24rpx; overflow: hidden; }
.link-row { display: flex; justify-content: space-between; align-items: center; padding: 28rpx 28rpx; border-bottom: 1rpx solid $color-border; font-size: 28rpx; color: $color-ink; }
.link-row:last-child { border-bottom: none; }
.arrow { color: $color-ink-lighter; font-size: 32rpx; }
.footer { margin-top: 48rpx; font-size: 22rpx; color: $color-ink-lighter; letter-spacing: 2rpx; padding-bottom: 48rpx; }
</style>
