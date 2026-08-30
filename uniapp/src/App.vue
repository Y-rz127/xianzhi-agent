<script setup lang="ts">
import { onShow } from '@dcloudio/uni-app'

// 临时关闭全局强制登录拦截，允许未登录直接访问各 tab 页
onShow(() => {})
</script>

<style lang="scss">
/* 主题变量定义：白天纸墨 / 暗夜玻璃两套（页面根节点 .t-light/.t-dark 切换） */
@import './styles/theme.scss';

/* 全局样式（颜色全部经主题变量解析） */
page {
  background-color: $color-bg;
  background: $color-bg;
  font-family: $font-family-body;
  font-size: 28rpx;
  color: $color-ink;
  min-height: 100vh;
}

/* 主题兜底：页面根节点未绑定 .t-light/.t-dark 时按白天渲染（与默认主题一致） */
page {
  --x-bg: #FAFAF8;
  --x-bg-warm: #F5F3EF;
  --x-bg-card: #FFFFFF;
  --x-bg-elevated: #FFFFFF;
  --x-primary: #2C2C2C;
  --x-primary-light: #555555;
  --x-primary-lighter: #888888;
  --x-primary-lightest: #AAAAAA;
  --x-primary-dark: #1A1A1A;
  --x-primary-darker: #111111;
  --x-ink: #1A1A1A;
  --x-ink-light: #555555;
  --x-ink-lighter: #888888;
  --x-ink-lightest: #AAAAAA;
  --x-vermilion: #B8483C;
  --x-vermilion-light: #D45D4F;
  --x-border: rgba(0, 0, 0, 0.08);
  --x-border-light: rgba(0, 0, 0, 0.04);
  --x-divider: rgba(0, 0, 0, 0.06);
  --x-success: #4A7A3A;
  --x-warning: #8B7D3A;
  --x-error: #B8483C;
  --x-info: #3A6B7A;
  --x-gold: #B08A2E;
  --x-gold-light: #8A6A1E;
  --x-mountain-far: rgba(26, 26, 26, 0.22);
  --x-mountain-mid: rgba(26, 26, 26, 0.38);
  --x-mountain-near: rgba(26, 26, 26, 0.6);
  --x-mist: rgba(250, 250, 248, 0.85);
  --x-bird: rgba(26, 26, 26, 0.45);
  --x-panel-bg: #FFFFFF;
  --x-panel-border: rgba(0, 0, 0, 0.08);
  --x-input-bg: #F5F3EF;
  --x-accent-text: #8A6A1E;
  --x-accent-dim: #99895F;
  --x-yi: #4A7A3A;
  --x-ji: #B8483C;
  --x-toast: #B8483C;
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
