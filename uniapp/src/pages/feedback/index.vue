<template>
  <view class="page">
    <view class="body">
      <view class="card">
        <text class="label">反馈内容</text>
        <textarea
          class="textarea"
          v-model="content"
          placeholder="请描述你遇到的问题或建议（至少 5 个字）"
          :maxlength="500"
        />
        <text class="counter">{{ content.length }}/500</text>
      </view>
      <view class="form-row">
        <text class="label">联系方式</text>
        <input class="input" v-model="contact" placeholder="选填，方便我们回复你" maxlength="50" />
      </view>
      <view v-if="errMsg" class="err">{{ errMsg }}</view>
      <view class="tip">你的反馈将帮助先知做得更好，感谢支持。</view>

      <button class="submit-btn" :class="{ disabled: submitting }" @tap="onSubmit">
        {{ submitting ? '提交中…' : '提交反馈' }}
      </button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { submitFeedback } from '@/api'

const content = ref('')
const contact = ref('')
const errMsg = ref('')
const submitting = ref(false)

async function onSubmit() {
  errMsg.value = ''
  if (content.value.trim().length < 5) {
    errMsg.value = '反馈内容至少 5 个字'
    return
  }
  if (submitting.value) return
  submitting.value = true
  try {
    await submitFeedback(content.value.trim(), contact.value.trim() || undefined)
    uni.showToast({ title: '已提交，感谢！', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 500)
  } catch (e: any) {
    errMsg.value = e?.message || '提交失败'
  } finally {
    submitting.value = false
  }
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: $color-bg; display: flex; flex-direction: column; }
.body { flex: 1; padding: 28rpx 32rpx 64rpx; }
.card { background: $color-bg-card; border: 1rpx solid $color-border; border-radius: 24rpx; padding: 24rpx; position: relative; }
.label { font-size: 26rpx; color: $color-ink-light; }
.textarea { width: 100%; min-height: 260rpx; margin-top: 16rpx; font-size: 28rpx; color: $color-ink; line-height: 1.6; }
.counter { position: absolute; right: 24rpx; bottom: 16rpx; font-size: 22rpx; color: $color-ink-lighter; }
.form-row { display: flex; align-items: center; margin-top: 28rpx; gap: 20rpx; }
.form-row .label { flex: 0 0 140rpx; font-size: 26rpx; color: $color-ink-light; }
.input { flex: 1; padding: 20rpx 24rpx; background: rgba(107, 123, 142, 0.06); border: 1rpx solid $color-border; border-radius: 20rpx; font-size: 28rpx; color: $color-ink; }
.err { font-size: 24rpx; color: $color-vermilion; margin-top: 16rpx; }
.tip { font-size: 22rpx; color: $color-ink-lighter; margin-top: 24rpx; line-height: 1.6; }
.submit-btn {
  margin-top: 48rpx;
  width: 100%;
  height: 88rpx;
  line-height: 88rpx;
  text-align: center;
  background: linear-gradient(135deg, #6b7b8e 0%, #4a5a6a 100%);
  color: #fff;
  font-size: 30rpx;
  font-weight: 600;
  border-radius: 44rpx;
  border: none;
  &::after { border: none; }
  &.disabled { opacity: 0.6; }
  &:active { transform: scale(0.98); opacity: 0.85; }
}
</style>
