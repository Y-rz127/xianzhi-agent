<template>
  <scroll-view class="page" scroll-y>
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
</script>

<style lang="scss" scoped>
.page {
  height: 100vh;
  background: $color-bg;
  box-sizing: border-box;
  overflow: hidden;
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
