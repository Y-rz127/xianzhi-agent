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
        <text class="hero-title">服务条款</text>
        <text class="hero-sub">最后更新：2026年7月</text>
      </view>
    </view>

    <view class="content">
      <view class="section">
        <text class="h2">一、服务说明</text>
        <text class="p">「先知」（以下简称"本服务"）为用户提供八字命理分析、合婚、黄历查询等传统文化相关内容服务。</text>
      </view>

      <view class="section">
        <text class="h2">二、用户协议</text>
        <text class="p">使用本服务即表示您已阅读、理解并同意本条款。若不同意，请勿使用本服务。</text>
      </view>

      <view class="section">
        <text class="h2">三、使用规范</text>
        <text class="p">用户不得利用本服务从事违法违规活动，不得发布违法信息，不得干扰服务正常运行。</text>
      </view>

      <view class="section">
        <text class="h2">四、知识产权</text>
        <text class="p">本服务中的算法、界面、内容（用户输入除外）的知识产权归本服务所有，未经授权不得复制或传播。</text>
      </view>

      <view class="section">
        <text class="h2">五、免责</text>
        <text class="p">本服务提供的内容仅供娱乐与文化参考，不构成专业建议。因使用本服务产生的任何损失，服务方不承担责任。详见《免责声明》。</text>
      </view>

      <view class="section">
        <text class="h2">六、条款修改</text>
        <text class="p">本服务保留修改本条款的权利，修改后的条款自公布之日起生效。</text>
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
