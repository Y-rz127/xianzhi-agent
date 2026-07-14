<script setup lang="ts">
import { onLaunch, onShow, onHide } from '@dcloudio/uni-app'

onLaunch(() => {
  console.log('App Launch')
})
onShow(() => {
  console.log('App Show')
})
onHide(() => {
  console.log('App Hide')
})
</script>

<style lang="scss">
/* 全局样式 - 白底黑字水墨主题 */
page {
  background-color: $color-bg;
  background: $color-bg;
  font-family: $font-family-body;
  font-size: 28rpx;
  color: $color-ink;
  min-height: 100vh;
}

/* 通用文本 */
text { color: inherit; }

/* 滚动条隐藏 */
::-webkit-scrollbar { display: none; }

/* 宣纸纹理卡片 */
.ink-card {
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: $radius-lg;
  position: relative;
  overflow: hidden;
}

/* 水墨边角装饰 - 通过伪元素实现四角花纹 */
.ink-card::before,
.ink-card::after {
  content: '';
  position: absolute;
  width: 32rpx;
  height: 32rpx;
  pointer-events: none;
  opacity: 0.2;
}

.ink-card::before {
  top: 0;
  left: 0;
  border-top: 2rpx solid $color-primary;
  border-left: 2rpx solid $color-primary;
  border-radius: $radius-sm 0 0 0;
}

.ink-card::after {
  bottom: 0;
  right: 0;
  border-bottom: 2rpx solid $color-primary;
  border-right: 2rpx solid $color-primary;
  border-radius: 0 0 $radius-sm 0;
}

/* 水墨光晕 */
.glow-gold { box-shadow: $glow-gold; }

/* 书法标题字 */
.display-font {
  font-family: $font-family-display;
  letter-spacing: 0.12em;
  color: $color-primary;
}

/* 通用按钮 - 水墨风格 */
.btn-primary {
  background: $color-primary;
  color: $color-bg;
  border-radius: $radius-md;
  border: none;
  font-weight: 500;
}
.btn-primary[disabled] { opacity: 0.4; }

/* 页面通用容器 */
.page {
  min-height: 100vh;
  background: $color-bg;
  color: $color-ink;
}

/* 宣纸纹理背景（用于浅色弹窗/卡片） */
.paper-bg {
  background-color: $color-paper;
  background-image: 
    radial-gradient(circle at 20% 30%, rgba(0, 0, 0, 0.02) 0%, transparent 50%),
    radial-gradient(circle at 80% 70%, rgba(184, 72, 60, 0.01) 0%, transparent 50%);
}
</style>
