<template>
  <view class="page" :class="themeClass">
    <view class="body">
      <view class="card form-card">
        <view class="card-title-row">
          <text class="card-dot">✦</text>
          <text class="card-title">接入你自己的模型</text>
        </view>
        <text class="intro">支持任意公网 OpenAI 兼容接口。配置后命盘问答的生成与修复由该模型完成（生成失败自动回退服务端模型）；意图拆解与事实审核仍用服务端模型，保持独立把关。</text>

        <view class="form-row">
          <text class="label">接口地址（Base URL）</text>
          <input class="input" v-model="baseUrl" placeholder="https://api.example.com/v1" placeholder-class="ph" />
        </view>
        <view class="form-row">
          <text class="label">API Key</text>
          <input class="input" v-model="apiKey" password placeholder="sk-…" placeholder-class="ph" />
          <text v-if="hasKey && !apiKey" class="key-hint">已保存密钥（不再显示），留空则不修改</text>
        </view>
        <view class="form-row">
          <text class="label">模型名</text>
          <input class="input" v-model="modelName" placeholder="如 gpt-4o-mini / qwen-max / deepseek-chat" placeholder-class="ph" />
        </view>

        <view class="hint-card">
          <text class="hint-line">接口由后端服务器调用，仅支持可公网访问的 OpenAI 兼容地址；私网、环回地址与云元数据端点不可用。</text>
          <text class="hint-line">密钥仅加密保存在你的账号下，任何接口都不会回传明文。</text>
        </view>
      </view>

      <view class="actions">
        <text v-if="configured" class="btn btn-ghost" @tap="onClear">移除配置</text>
        <text v-else class="btn btn-ghost" @tap="onReset">清空填写</text>
        <text class="btn btn-primary" @tap="onSave">{{ saving ? '保存中…' : '保存配置' }}</text>
      </view>

      <view class="actions secondary">
        <text class="btn btn-outline" @tap="onTest">测试连通</text>
      </view>

      <view v-if="statusText" :class="['test-result', statusOk ? 'ok' : 'fail']">
        <text class="test-icon">{{ statusOk ? '✓' : '✕' }}</text>
        <text class="test-text">{{ statusText }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useTheme, useThemeNativeBar } from '@/composables/useTheme'
import { fetchUserAiSettings, saveUserAiSettings, testUserModel } from '@/api'
import { isLoggedIn } from '@/utils/storage'

const { themeClass } = useTheme()
useThemeNativeBar()

const baseUrl = ref('')
const apiKey = ref('')
const modelName = ref('')
const hasKey = ref(false)
const configured = ref(false)
const saving = ref(false)
const statusText = ref('')
const statusOk = ref(false)

async function load() {
  if (!isLoggedIn()) {
    uni.showToast({ title: '请先登录', icon: 'none' })
    setTimeout(() => uni.navigateTo({ url: '/pages/login/index' }), 600)
    return
  }
  try {
    const s = await fetchUserAiSettings()
    baseUrl.value = s.llm_base_url || ''
    modelName.value = s.llm_model || ''
    hasKey.value = !!s.has_key
    configured.value = !!(s.llm_base_url && s.llm_model && s.has_key)
  } catch (e: any) {
    statusText.value = `读取配置失败：${e?.message || '未登录或服务不可用'}`
    statusOk.value = false
  }
}
load()

function onReset() {
  baseUrl.value = ''
  apiKey.value = ''
  modelName.value = ''
  statusText.value = ''
}

async function onSave() {
  if (saving.value) return
  const url = baseUrl.value.trim()
  const model = modelName.value.trim()
  if (!url || !model) {
    uni.showToast({ title: '地址与模型名必填', icon: 'none' })
    return
  }
  if (!hasKey.value && !apiKey.value.trim()) {
    uni.showToast({ title: '请填写 API Key', icon: 'none' })
    return
  }
  saving.value = true
  try {
    const s = await saveUserAiSettings({
      llm_base_url: url,
      llm_model: model,
      ...(apiKey.value.trim() ? { llm_api_key: apiKey.value.trim() } : {}),
    })
    hasKey.value = !!s.has_key
    configured.value = !!(s.llm_base_url && s.llm_model && s.has_key)
    apiKey.value = ''
    statusText.value = '已保存'
    statusOk.value = true
    uni.showToast({ title: '已保存', icon: 'success' })
  } catch (e: any) {
    statusText.value = `保存失败：${e?.message || '请检查配置'}`
    statusOk.value = false
  } finally {
    saving.value = false
  }
}

async function onClear() {
  if (saving.value) return
  saving.value = true
  try {
    await saveUserAiSettings({ clear_model: true })
    baseUrl.value = ''
    modelName.value = ''
    apiKey.value = ''
    hasKey.value = false
    configured.value = false
    statusText.value = '已移除自定义模型（恢复服务端模型）'
    statusOk.value = true
  } catch (e: any) {
    statusText.value = `移除失败：${e?.message || ''}`
    statusOk.value = false
  } finally {
    saving.value = false
  }
}

async function onTest() {
  if (saving.value) return
  statusText.value = '测试中…'
  statusOk.value = false
  try {
    const r = await testUserModel()
    statusOk.value = !!r.ok
    statusText.value = r.message
  } catch (e: any) {
    statusText.value = `测试失败：${e?.message || ''}`
    statusOk.value = false
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  background: $color-bg;
}
.body {
  padding: 32rpx 24rpx;
}
.card {
  position: relative;
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: 32rpx;
  padding: 32rpx;
  margin-bottom: 28rpx;
  overflow: hidden;
}
.card-title-row {
  display: flex;
  align-items: center;
  gap: 10rpx;
  padding-left: 28rpx;
  margin: -32rpx -32rpx 24rpx;
  padding-top: 24rpx;
  padding-bottom: 16rpx;
  background: linear-gradient(135deg, $color-bg-warm 0%, $color-bg-card 100%);
  border-bottom: 1rpx solid $color-border;
}
.card-dot {
  font-size: 28rpx;
  color: $color-primary;
}
.card-title {
  font-size: 32rpx;
  font-weight: 700;
  color: $color-primary;
  letter-spacing: 2rpx;
}
.intro {
  display: block;
  font-size: 24rpx;
  color: $color-ink-light;
  line-height: 1.8;
  margin-bottom: 24rpx;
}
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
.key-hint {
  display: block;
  margin-top: 10rpx;
  font-size: 22rpx;
  color: $color-ink-lighter;
}
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
.actions {
  display: flex;
  gap: 20rpx;
  margin-bottom: 24rpx;
}
.actions.secondary {
  justify-content: center;
}
.btn {
  flex: 1;
  text-align: center;
  padding: 26rpx 0;
  border-radius: 24rpx;
  font-size: 28rpx;
  letter-spacing: 2rpx;
}
.btn-primary {
  background: $color-primary;
  color: $color-bg;
  box-shadow: $glow-primary;
}
.btn-ghost {
  background: $color-bg-card;
  color: $color-ink-light;
  border: 1rpx solid $color-border;
}
.btn-outline {
  flex: none;
  width: 320rpx;
  background: transparent;
  color: $color-primary;
  border: 1rpx solid $color-primary;
}
.test-result {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 24rpx;
  border-radius: 20rpx;
  font-size: 26rpx;
}
.test-result.ok {
  background: rgba(76, 175, 80, 0.1);
  color: #4caf50;
}
.test-result.fail {
  background: rgba(244, 67, 54, 0.1);
  color: #f44336;
}
.test-icon {
  font-size: 32rpx;
}
.test-text {
  flex: 1;
  line-height: 1.6;
}
</style>