<template>
  <view class="page" :class="themeClass">
    <!-- 头部 -->
    <view class="hero">
      <view class="hero-bg"></view>
      <view class="hero-orb orb-1"></view>
      <view class="hero-orb orb-2"></view>
      <view class="hero-content">
        <text class="hero-icon">⚙</text>
        <text class="hero-sub">配置后端连接地址</text>
      </view>
    </view>

    <view class="body">
      <!-- 设置卡片 -->
      <view class="card form-card">
        <view class="card-title-row">
          <text class="card-dot">✦</text>
          <text class="card-title">连接配置</text>
        </view>

        <view class="form-row">
          <text class="label">API 地址</text>
          <input
            class="input"
            v-model="apiBase"
            placeholder="如 http://192.168.1.100:8123/api"
            placeholder-class="ph"
          />
        </view>
        <view class="form-row">
          <text class="label">WebSocket</text>
          <input
            class="input"
            v-model="wsBase"
            placeholder="留空时自动从 API 推导"
            placeholder-class="ph"
          />
        </view>

        <view class="hint-card">
          <text class="hint-line">调试本地后端：电脑与手机同 WiFi，把 IP 换成电脑局域网 IP（如 192.168.1.100），端口 8123</text>
          <text class="hint-line warn">小程序必须使用 HTTP 域名（不可用 127.0.0.1），生产必须用 HTTPS 已备案域名</text>
        </view>
      </view>

      <!-- 外观主题 -->
      <view class="card form-card">
        <view class="card-title-row">
          <text class="card-dot">✦</text>
          <text class="card-title">外观主题</text>
        </view>
        <view class="theme-row">
          <view :class="['theme-opt', !isDark && 'on']" @tap="setTheme('light')">
            <text class="theme-emoji">☀</text>
            <text class="theme-name">白天 · 纸墨</text>
          </view>
          <view :class="['theme-opt', isDark && 'on']" @tap="setTheme('dark')">
            <text class="theme-emoji">☾</text>
            <text class="theme-name">暗夜 · 玻璃</text>
          </view>
        </view>
        <view class="hint-card">
          <text class="hint-line">切换立即生效并自动记住；重新进入小程序保持所选主题</text>
        </view>
      </view>

      <!-- 操作按钮 -->
      <view class="actions">
        <text class="btn btn-ghost" @tap="onReset">恢复默认</text>
        <text class="btn btn-primary" @tap="onSave">保存并测试</text>
      </view>

      <!-- 测试结果 -->
      <view v-if="testResult" :class="['test-result', testOk ? 'ok' : 'fail']">
        <text class="test-icon">{{ testOk ? '✓' : '✕' }}</text>
        <text class="test-text">{{ testResult }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { setConfig, getConfig } from '@/config'
import { getHealth } from '@/api'
import { useTheme } from '@/composables/useTheme'

const { isDark, setTheme, themeClass } = useTheme()

const apiBase = ref('')
const wsBase = ref('')
const testResult = ref('')
const testOk = ref(false)

onMounted(() => {
  const c = getConfig()
  apiBase.value = c.apiBase
  wsBase.value = c.wsBase
})

function onReset() {
  apiBase.value = '/api'
  wsBase.value = ''
  setConfig({ apiBase: apiBase.value, wsBase: wsBase.value })
  testResult.value = '已恢复默认（H5 dev 走 vite proxy，小程序走 localhost）'
  testOk.value = true
}

async function onSave() {
  setConfig({ apiBase: apiBase.value, wsBase: wsBase.value })
  testResult.value = '测试中…'
  testOk.value = false
  try {
    const res = await getHealth()
    testResult.value = `连通成功（status=${res.status || 'ok'}, rag_ready=${res.rag_ready}）`
    testOk.value = true
  } catch (e: any) {
    testResult.value = `连通失败：${e.message || '请检查地址与后端状态'}`
    testOk.value = false
  }
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background: $color-bg;
  display: flex;
  flex-direction: column;
}

/* 主题选择 */
.theme-row { display: flex; gap: 20rpx; margin: 8rpx 0 20rpx; }
.theme-opt {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 10rpx;
  padding: 28rpx 0; border: 1rpx solid $color-border; border-radius: 16rpx;
  background: $color-bg-card; color: $color-ink-light;
}
.theme-opt.on { border-color: $color-primary; color: $color-primary; box-shadow: $glow-primary; }
.theme-emoji { font-size: 44rpx; line-height: 1; }
.theme-name { font-size: 26rpx; }

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
    radial-gradient(circle at 20% 30%, var(--x-glow-blue), transparent 50%),
    radial-gradient(circle at 80% 70%, var(--x-glow-red), transparent 50%);
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
  background: var(--x-glow-blue);
}
.orb-2 {
  bottom: -80rpx; left: -60rpx;
  width: 220rpx; height: 220rpx;
  background: var(--x-glow-red);
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
  color: $color-paper;
  margin-bottom: 16rpx;
  text-shadow: var(--x-hero-shadow);
}
.hero-sub {
  margin-top: 10rpx;
  font-size: 28rpx;
  color: $color-ink-light;
  letter-spacing: 4rpx;
}

/* 主体 */
.body {
  flex: 1;
  padding: 32rpx 24rpx;
}

/* 卡片 */
.card {
  position: relative;
  background: $color-bg-card;
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid $color-border;
  border-radius: 32rpx;
  padding: 32rpx;
  margin-bottom: 28rpx;
  overflow: hidden;
}
.card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2rpx;
  background: linear-gradient(90deg, transparent, $color-primary, $color-vermilion, transparent);
}
.card-title-row {
  display: flex;
  align-items: center;
  margin-bottom: 28rpx;
}
.card-dot {
  color: $color-vermilion;
  font-size: 26rpx;
  margin-right: 12rpx;
}
.card-title {
  font-size: 32rpx;
  font-weight: 600;
  color: $color-ink;
  letter-spacing: 4rpx;
}

/* 表单 */
.form-row {
  display: flex;
  flex-direction: column;
  margin-bottom: 24rpx;
}
.label {
  font-size: 28rpx;
  color: $color-ink-light;
  margin-bottom: 12rpx;
  letter-spacing: 2rpx;
}
.input {
  padding: 22rpx 24rpx;
  background: var(--x-hint-bg);
  border: 1rpx solid $color-border;
  border-radius: 20rpx;
  font-size: 30rpx;
  color: $color-ink;
}
.ph {
  color: $color-ink-lighter;
}

/* 提示卡 */
.hint-card {
  margin-top: 8rpx;
  padding: 20rpx 24rpx;
  background: var(--x-warn-bg);
  border: 1rpx solid var(--x-warn-border);
  border-radius: 20rpx;
}
.hint-line {
  display: block;
  font-size: 26rpx;
  color: $color-vermilion-light;
  line-height: 1.7;
  letter-spacing: 1rpx;
}
.hint-line.warn {
  color: $color-vermilion;
  margin-top: 12rpx;
}

/* 操作按钮 */
.actions {
  display: flex;
  gap: 20rpx;
  margin-bottom: 24rpx;
}
.btn {
  flex: 1;
  text-align: center;
  padding: 28rpx 0;
  border-radius: 24rpx;
  font-size: 32rpx;
  letter-spacing: 4rpx;
}
.btn-ghost {
  color: $color-ink-light;
  background: var(--x-hint-bg);
  border: 1rpx solid $color-border;
}
.btn-primary {
  color: $color-bg;
  background: linear-gradient(135deg, $color-primary, $color-primary-dark);
  box-shadow: $glow-gold;
}

/* 测试结果 */
.test-result {
  display: flex;
  align-items: center;
  padding: 26rpx;
  border-radius: 24rpx;
  font-size: 30rpx;
}
.test-result.ok {
  background: var(--x-ok-bg);
  border: 1rpx solid var(--x-ok-border);
}
.test-result.fail {
  background: var(--x-fail-bg);
  border: 1rpx solid var(--x-fail-border);
}
.test-icon {
  margin-right: 16rpx;
  font-size: 32rpx;
}
.test-result.ok .test-icon { color: $state-success; }
.test-result.fail .test-icon { color: $color-vermilion; }
.test-text {
  flex: 1;
  color: $color-ink;
  word-break: break-word;
  white-space: pre-line;
  letter-spacing: 1rpx;
}
</style>
