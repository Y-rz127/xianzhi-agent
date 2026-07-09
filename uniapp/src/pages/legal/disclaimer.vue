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
        <text class="hero-title">免责声明</text>
        <text class="hero-sub">最后更新：2026年7月</text>
      </view>
    </view>

    <view class="content">
      <view class="section">
        <text class="h2">一、服务性质</text>
        <text class="p">「先知」（以下简称"本应用"）提供的八字命理、合婚、黄历、塔罗等内容，均基于传统文化与算法模型生成，仅供文化交流、娱乐参考之用，不构成任何专业建议（包括但不限于医疗、法律、财务、心理咨询）。</text>
      </view>

      <view class="section">
        <text class="h2">二、非科学预测</text>
        <text class="p">命理学说属传统文化范畴，其结论未经现代科学证实。本应用不对分析结果的准确性、完整性作任何明示或暗示的保证，用户不应据此作出重大人生决策。</text>
      </view>

      <view class="section">
        <text class="h2">三、用户责任</text>
        <text class="p">用户应自行判断内容的适用性。因使用本应用内容而产生的任何直接或间接损失，本应用及开发者不承担责任。</text>
      </view>

      <view class="section">
        <text class="h2">四、未成年人</text>
        <text class="p">未成年人应在监护人指导下使用本应用。</text>
      </view>

      <view class="section">
        <text class="h2">五、其他</text>
        <text class="p">本应用保留在法律允许范围内修改免责声明的权利。</text>
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
  background: #0F0B1E;
}

.status-bar { width: 100%; }

/* 紫蓝渐变头部 */
.hero {
  position: relative;
  padding: 48rpx 32rpx 60rpx;
  overflow: hidden;
  background: linear-gradient(135deg, #2D1B5E 0%, #1A1238 100%);
  border-bottom-left-radius: 48rpx;
  border-bottom-right-radius: 48rpx;
}
.hero-bg {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background:
    radial-gradient(circle at 20% 30%, rgba(124, 58, 237, 0.4), transparent 50%),
    radial-gradient(circle at 80% 70%, rgba(6, 182, 212, 0.25), transparent 50%);
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
  background: rgba(124, 58, 237, 0.5);
}
.orb-2 {
  bottom: -80rpx; left: -60rpx;
  width: 220rpx; height: 220rpx;
  background: rgba(6, 182, 212, 0.35);
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
  color: #06B6D4;
  margin-bottom: 16rpx;
  text-shadow: 0 0 24rpx rgba(6, 182, 212, 0.8);
}
.hero-title {
  font-size: 44rpx;
  font-weight: 800;
  color: #FFFFFF;
  letter-spacing: 8rpx;
  text-shadow: 0 0 24rpx rgba(124, 58, 237, 0.6);
}
.hero-sub {
  margin-top: 10rpx;
  font-size: 22rpx;
  color: rgba(196, 181, 253, 0.8);
  letter-spacing: 4rpx;
}

/* 正文 */
.content {
  padding: 32rpx;
}
.section {
  position: relative;
  background: rgba(30, 22, 56, 0.6);
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid rgba(124, 58, 237, 0.18);
  border-radius: 24rpx;
  padding: 28rpx;
  margin-bottom: 20rpx;
  overflow: hidden;
}
.section::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 4rpx;
  background: linear-gradient(180deg, #7C3AED, #06B6D4);
}
.h2 {
  display: block;
  font-size: 30rpx;
  font-weight: 600;
  color: #FFFFFF;
  letter-spacing: 4rpx;
  margin-bottom: 16rpx;
}
.p {
  display: block;
  font-size: 26rpx;
  line-height: 1.8;
  color: #C4B5FD;
  letter-spacing: 1rpx;
}
</style>
