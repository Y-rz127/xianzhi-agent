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
  background-color: #0F0B1E;
  background: linear-gradient(180deg, #160F2E 0%, #0F0B1E 100%);
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif;
  font-size: 28rpx;
  color: #E2E8F0;
  min-height: 100vh;
}

/* 通用文本 */
text { color: inherit; }

/* 滚动条隐藏 */
::-webkit-scrollbar { display: none; }

/* 全局工具类 */
.glass-card {
  background: rgba(30, 22, 56, 0.8);
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 32rpx;
}

.glow-primary { box-shadow: 0 0 40rpx rgba(124, 58, 237, 0.3); }
.glow-energy { box-shadow: 0 0 40rpx rgba(6, 182, 212, 0.3); }
.glow-gold { box-shadow: 0 0 32rpx rgba(245, 158, 11, 0.25); }

/* 渐变标题字 */
.display-font {
  font-family: 'Orbitron', 'Rajdhani', 'PingFang SC', sans-serif;
  letter-spacing: 0.08em;
}

/* 通用按钮 */
.btn-primary {
  background: linear-gradient(135deg, #7C3AED 0%, #6D28D9 100%);
  color: #ffffff;
  border-radius: 32rpx;
  box-shadow: 0 0 40rpx rgba(124, 58, 237, 0.3);
  border: none;
}
.btn-primary[disabled] { opacity: 0.5; }

/* 页面通用容器 */
.page {
  min-height: 100vh;
  background: linear-gradient(180deg, #160F2E 0%, #0F0B1E 100%);
  color: #E2E8F0;
}
</style>
