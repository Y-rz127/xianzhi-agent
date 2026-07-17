<template>
  <scroll-view class="page" scroll-y>
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
