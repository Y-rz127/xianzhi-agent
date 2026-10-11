<template>
  <view v-if="st.visible" class="td-mask" @tap="dialogCancel">
    <view class="td-card" @tap.stop>
      <text v-if="st.title" class="td-title">{{ st.title }}</text>

      <!-- 输入态：对应 uni.showModal 的 editable，content 作为初值 -->
      <input
        v-if="st.editable"
        class="td-input"
        v-model="draft"
        :placeholder="st.placeholder"
        placeholder-class="td-input-ph"
        :maxlength="st.maxlength"
        :focus="true"
        confirm-type="done"
        @confirm="onConfirm"
      />
      <text v-else-if="st.content" class="td-content">{{ st.content }}</text>

      <view class="td-btns">
        <text class="td-btn" @tap="dialogCancel">{{ st.cancelText }}</text>
        <text :class="['td-btn', 'primary', st.danger && 'danger']" @tap="onConfirm">{{ st.confirmText }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDialogState, dialogCancel, dialogConfirm } from '@/composables/useDialog'

const st = useDialogState()
const draft = ref('')

// 每次弹出都用 options.content 重置草稿，避免上一次输入残留
watch(() => st.visible, (v) => { if (v) draft.value = st.editable ? st.content : '' })

function onConfirm() {
  dialogConfirm(draft.value)
}
</script>

<style lang="scss" scoped>
/* 配色全走 $color-*（映射 var(--x-*)），随页面根节点 .t-light/.t-dark 换肤；
   自定义属性可跨组件边界继承，与 CaseInfoModal 同一套做法 */
.td-mask {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  /* 压过输入栏(100)/抽屉(1000)/聊天页反馈弹窗(2000) */
  z-index: 2100;
}
.td-card {
  width: 600rpx;
  max-width: 86%;
  background: $color-bg-elevated;
  border: 1rpx solid $color-border;
  border-radius: 24rpx;
  padding: 40rpx 32rpx 32rpx;
  display: flex;
  flex-direction: column;
  gap: 28rpx;
  box-sizing: border-box;
}
.td-title {
  font-size: 32rpx;
  font-weight: 600;
  color: $color-ink;
  text-align: center;
  line-height: 1.4;
}
.td-content {
  font-size: 28rpx;
  color: $color-ink-light;
  text-align: center;
  line-height: 1.6;
}
.td-input {
  width: 100%;
  padding: 20rpx 24rpx;
  font-size: 30rpx;
  color: $color-ink;
  background: $color-bg-warm;
  border: 1rpx solid $color-border;
  border-radius: 16rpx;
  box-sizing: border-box;
}
.td-input-ph {
  color: $color-ink-lighter;
}
.td-btns {
  display: flex;
  gap: 20rpx;
}
.td-btn {
  flex: 1;
  text-align: center;
  padding: 20rpx 0;
  font-size: 28rpx;
  color: $color-ink-light;
  background: $color-bg-warm;
  border: 1rpx solid $color-border;
  border-radius: 16rpx;
}
.td-btn.primary {
  color: $color-bg;
  background: $color-primary;
  border-color: transparent;
  font-weight: 600;
}
.td-btn.danger {
  background: $color-vermilion;
}
</style>
