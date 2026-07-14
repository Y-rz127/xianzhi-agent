<template>
  <scroll-view class="page" scroll-y>
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

    <!-- 紫蓝渐变头部 -->
    <view class="hero">
      <view class="hero-bg"></view>
      <view class="hero-orb orb-1"></view>
      <view class="hero-orb orb-2"></view>
      <view class="hero-content">
        <text class="hero-icon">✦</text>
        <text class="hero-title">隐私政策</text>
        <text class="hero-sub">最后更新：2026年7月</text>
      </view>
    </view>

    <view class="content">
      <view class="section">
        <text class="h2">一、信息收集</text>
        <text class="p">本应用在提供服务时，会收集您主动输入的出生日期、出生时辰、性别等命理分析所需信息。上述信息仅用于生成命理分析结果。</text>
      </view>

      <view class="section">
        <text class="h2">二、信息使用</text>
        <text class="p">收集的信息仅用于本应用内的命理分析服务，不会用于其他用途。对话内容可能被用于提升服务质量。</text>
      </view>

      <view class="section">
        <text class="h2">三、信息存储与安全</text>
        <text class="p">您的对话与命例数据存储于服务器，我们采取合理的技术措施保护信息安全，但不保证信息绝对安全。</text>
      </view>

      <view class="section">
        <text class="h2">四、信息共享</text>
        <text class="p">除法律法规要求或您另行同意外，我们不会向第三方共享您的个人信息。</text>
      </view>

      <view class="section">
        <text class="h2">五、未成年人隐私</text>
        <text class="p">我们重视未成年人隐私保护。未成年人使用本应用应在监护人陪同下进行，并提供必要授权。</text>
      </view>

      <view class="section">
        <text class="h2">六、您的权利</text>
        <text class="p">您有权访问、更正或删除您的个人信息。如需操作，可通过应用内的会话管理功能删除相关记录。</text>
      </view>

      <view class="section">
        <text class="h2">七、联系我们</text>
        <text class="p">如您对本隐私政策有任何疑问，可通过应用内反馈渠道与我们联系。</text>
      </view>
    </view>
  </scroll-view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getWindowInfo()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}
</script>

<style lang="scss" scoped>
.page {
  height: 100vh;
  background: $color-bg;
  box-sizing: border-box;
  overflow: hidden;
}

.status-bar { width: 100%; }

/* 水墨渐变头部 */
.hero {
  position: relative;
  padding: 48rpx 32rpx 60rpx;
  overflow: hidden;
  background: linear-gradient(135deg, $color-bg-warm 0%, $color-bg 100%);
  border-bottom-left-radius: 48rpx;
  border-bottom-right-radius: 48rpx;
}
.hero-bg {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background:
    radial-gradient(circle at 20% 30%, rgba(107, 123, 142, 0.35), transparent 50%),
    radial-gradient(circle at 80% 70%, rgba(184, 72, 60, 0.2), transparent 50%);
}
.hero-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(40rpx);
  pointer-events: none;
}
.orb-1 {
  top: -60rpx; right: -40rpx;
  width: 200rpx; height: 200rpx;
  background: rgba(107, 123, 142, 0.45);
}
.orb-2 {
  bottom: -80rpx; left: -60rpx;
  width: 220rpx; height: 220rpx;
  background: rgba(184, 72, 60, 0.3);
}
.hero-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.hero-icon {
  font-size: 56rpx;
  color: $color-vermilion;
  margin-bottom: 16rpx;
  text-shadow: 0 0 24rpx rgba(184, 72, 60, 0.6);
}
.hero-title {
  font-size: 44rpx;
  font-weight: 800;
  color: $color-paper;
  letter-spacing: 8rpx;
  text-shadow: 0 0 24rpx rgba(107, 123, 142, 0.5);
}
.hero-sub {
  margin-top: 10rpx;
  font-size: 22rpx;
  color: $color-ink-light;
  letter-spacing: 4rpx;
}

/* 正文 */
.content {
  padding: 32rpx;
  box-sizing: border-box;
}
.section {
  position: relative;
  background: $color-bg-card;
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid $color-border;
  border-radius: 24rpx;
  padding: 28rpx;
  margin-bottom: 20rpx;
  overflow: hidden;
  box-sizing: border-box;
}
.section::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 4rpx;
  background: linear-gradient(180deg, $color-primary, $color-vermilion);
}
.h2 {
  display: block;
  font-size: 30rpx;
  font-weight: 600;
  color: $color-ink;
  letter-spacing: 4rpx;
  margin-bottom: 16rpx;
}
.p {
  display: block;
  font-size: 26rpx;
  line-height: 1.8;
  color: $color-ink-light;
  letter-spacing: 1rpx;
}
</style>
