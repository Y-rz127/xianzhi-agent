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
/* 全局样式 - 先知深空紫蓝主题 */
page {
  background-color: $color-bg;
  background: linear-gradient(180deg, $color-bg-warm 0%, $color-bg 100%);
  font-family: $font-family-body;
  font-size: 28rpx;
  color: $color-ink;
  min-height: 100vh;
}

/* 通用文本 */
text { color: inherit; }

/* 滚动条隐藏 */
::-webkit-scrollbar { display: none; }

/* 全局工具类 */
.glass-card {
  background: $color-bg-card;
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid $color-border;
  border-radius: $radius-xl;
}

.glow-primary { box-shadow: $glow-primary; }
.glow-energy { box-shadow: $glow-energy; }
.glow-gold { box-shadow: $glow-gold; }

/* 渐变标题字 */
.display-font {
  font-family: 'Orbitron', 'Rajdhani', 'PingFang SC', sans-serif;
  letter-spacing: 0.08em;
}

/* 通用按钮 */
.btn-primary {
  background: linear-gradient(135deg, $color-primary 0%, $color-primary-dark 100%);
  color: $uni-text-color-inverse;
  border-radius: $radius-xl;
  box-shadow: $glow-primary;
  border: none;
}
.btn-primary[disabled] { opacity: 0.5; }

/* 页面通用容器 */
.page {
  min-height: 100vh;
  background: linear-gradient(180deg, $color-bg-warm 0%, $color-bg 100%);
  color: $color-ink;
}
</style>
