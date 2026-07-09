<template>
  <view class="page">
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

    <!-- 紫蓝渐变头部 -->
    <view class="hero">
      <view class="hero-bg"></view>
      <view class="hero-orb orb-1"></view>
      <view class="hero-orb orb-2"></view>
      <view class="hero-content">
        <text class="hero-icon">⚙</text>
        <text class="hero-title">服务器设置</text>
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

const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getWindowInfo()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}

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
  background: #0F0B1E;
  display: flex;
  flex-direction: column;
}

/* 状态栏占位 */
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
  color: #FFFFFF;
  margin-bottom: 16rpx;
  text-shadow: 0 0 24rpx rgba(124, 58, 237, 0.8);
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
  font-size: 24rpx;
  color: rgba(196, 181, 253, 0.9);
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
  background: rgba(30, 22, 56, 0.8);
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
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
  background: linear-gradient(90deg, transparent, #7C3AED, #06B6D4, transparent);
}
.card-title-row {
  display: flex;
  align-items: center;
  margin-bottom: 28rpx;
}
.card-dot {
  color: #06B6D4;
  font-size: 22rpx;
  margin-right: 12rpx;
}
.card-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #FFFFFF;
  letter-spacing: 4rpx;
}

/* 表单 */
.form-row {
  display: flex;
  flex-direction: column;
  margin-bottom: 24rpx;
}
.label {
  font-size: 24rpx;
  color: #C4B5FD;
  margin-bottom: 12rpx;
  letter-spacing: 2rpx;
}
.input {
  padding: 20rpx 24rpx;
  background: rgba(124, 58, 237, 0.08);
  border: 1rpx solid rgba(124, 58, 237, 0.25);
  border-radius: 20rpx;
  font-size: 26rpx;
  color: #FFFFFF;
}
.ph {
  color: rgba(196, 181, 253, 0.4);
}

/* 提示卡 */
.hint-card {
  margin-top: 8rpx;
  padding: 20rpx 24rpx;
  background: rgba(245, 158, 11, 0.08);
  border: 1rpx solid rgba(245, 158, 11, 0.25);
  border-radius: 20rpx;
}
.hint-line {
  display: block;
  font-size: 22rpx;
  color: #FCD34D;
  line-height: 1.7;
  letter-spacing: 1rpx;
}
.hint-line.warn {
  color: #F59E0B;
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
  padding: 24rpx 0;
  border-radius: 24rpx;
  font-size: 28rpx;
  letter-spacing: 4rpx;
}
.btn-ghost {
  color: #C4B5FD;
  background: rgba(196, 181, 253, 0.08);
  border: 1rpx solid rgba(124, 58, 237, 0.25);
}
.btn-primary {
  color: #FFFFFF;
  background: linear-gradient(135deg, #7C3AED, #06B6D4);
  box-shadow: 0 4rpx 20rpx rgba(124, 58, 237, 0.5);
}

/* 测试结果 */
.test-result {
  display: flex;
  align-items: center;
  padding: 24rpx;
  border-radius: 24rpx;
  font-size: 26rpx;
}
.test-result.ok {
  background: rgba(16, 185, 129, 0.12);
  border: 1rpx solid rgba(16, 185, 129, 0.4);
}
.test-result.fail {
  background: rgba(239, 68, 68, 0.12);
  border: 1rpx solid rgba(239, 68, 68, 0.4);
}
.test-icon {
  margin-right: 16rpx;
  font-size: 28rpx;
}
.test-result.ok .test-icon { color: #10B981; }
.test-result.fail .test-icon { color: #EF4444; }
.test-text {
  flex: 1;
  color: #FFFFFF;
  word-break: break-word;
  white-space: pre-line;
  letter-spacing: 1rpx;
}
</style>
