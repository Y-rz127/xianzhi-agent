<template>
  <view class="page" :class="themeClass">
    <view class="hero">
      <view class="hero-bg"></view>
      <view class="hero-orb orb-1"></view>
      <view class="hero-orb orb-2"></view>
      <view class="hero-content">
        <text class="hero-icon">☯</text>
        <text class="hero-title">先知</text>
        <text class="hero-sub">{{ mode === 'login' ? '登录以同步你的命理档案' : '注册账号，开启专属命理空间' }}</text>
      </view>
    </view>

    <view class="body">
      <!-- 服务器地址配置 -->
      <view class="server-url-row">
        <text class="url-label">服务器地址</text>
        <view class="url-input-wrap">
          <input class="url-input" v-model="serverUrl" placeholder="如：https://your-domain.com/api" />
          <text :class="['url-btn', serverUrl && 'active']" @tap="onSaveUrl">保存</text>
        </view>
        <text v-if="currentUrl && currentUrl !== defaultServerUrl" class="url-current">当前：{{ currentUrl }}</text>
      </view>

      <view class="card">
        <view class="seg-tabs">
          <text :class="['seg', mode === 'login' && 'active']" @tap="mode = 'login'">登录</text>
          <text :class="['seg', mode === 'register' && 'active']" @tap="mode = 'register'">注册</text>
        </view>
        <view class="form-row">
          <text class="label">昵称</text>
          <input class="input" v-model="nickname" placeholder="2-20 个字符" maxlength="20" />
        </view>
        <view class="form-row">
          <text class="label">密码</text>
          <input class="input" v-model="password" placeholder="至少 6 位" password maxlength="40" />
        </view>
        <view class="form-row" v-if="mode === 'register'">
          <text class="label">确认</text>
          <input class="input" v-model="confirmPwd" placeholder="再次输入密码" password maxlength="40" />
        </view>
        <view v-if="errMsg" class="err">{{ errMsg }}</view>
        <view class="btn-primary" @tap="onSubmit">{{ mode === 'login' ? '登录' : '注册并登录' }}</view>
        <view v-if="loggedUser" class="logout-row">
          <text class="lu-text">当前已登录：{{ loggedUser.nickname }}</text>
          <text class="link" @tap="onLogout">退出</text>
        </view>
      </view>

      <!-- 微信一键登录 -->
      <view class="wx-login-row">
        <view class="divider-line"><text class="divider-text">其他方式</text></view>
        <view :class="['wx-btn', wxLoggingIn && 'disabled']" @tap="onWxLogin">
          <text class="wx-icon">微信</text>
          <text>{{ wxLoggingIn ? '登录中…' : '一键登录' }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { login, register, wxLogin } from '@/api'
import { getUser, setToken, setUser, clearAuth } from '@/utils/storage'
import { getConfig, setConfig } from '@/config'


const { themeClass } = useTheme()
const mode = ref<'login' | 'register'>('login')
const nickname = ref('')
const password = ref('')
const confirmPwd = ref('')
const errMsg = ref('')
const loggedUser = ref<any>(null)
const wxLoggingIn = ref(false)

// 服务器地址
const defaultServerUrl = 'http://localhost:8123/api'
const serverUrl = ref('')
const currentUrl = ref('')

onShow(() => {
  loggedUser.value = getUser()
  // 读取当前配置的地址
  const cfg = getConfig()
  currentUrl.value = cfg.apiBase || ''
  // 如果不是默认值，显示在输入框
  if (cfg.apiBase && cfg.apiBase !== defaultServerUrl) {
    serverUrl.value = cfg.apiBase
  }
})

/** 保存服务器地址 */
function onSaveUrl() {
  const url = serverUrl.value.trim()
  if (!url) {
    errMsg.value = '请输入服务器地址'
    return
  }
  // 自动补 /api 后缀
  let apiBase = url
  if (!apiBase.endsWith('/api')) {
    apiBase = apiBase.replace(/\/+$/, '') + '/api'
  }
  // 补全协议
  if (!apiBase.startsWith('http://') && !apiBase.startsWith('https://')) {
    apiBase = 'https://' + apiBase
  }
  setConfig({ apiBase: apiBase })
  currentUrl.value = apiBase
  uni.showToast({ title: '已保存', icon: 'success' })
}

/** 微信一键登录 */
async function onWxLogin() {
  errMsg.value = ''
  wxLoggingIn.value = true
  try {
    // #ifdef MP-WEIXIN
    const loginRes: any = await new Promise((resolve, reject) => {
      uni.login({ provider: 'weixin', success: resolve, fail: reject })
    })
    if (!loginRes.code) throw new Error('获取微信 code 失败')
    uni.showLoading({ title: '登录中…' })
    const res = await wxLogin(loginRes.code)
    uni.hideLoading()
    setToken(res.token)
    setUser(res.user)
    wxLoggingIn.value = false
    uni.showToast({ title: '登录成功', icon: 'success' })
    setTimeout(() => uni.reLaunch({ url: '/pages/mine/index' }), 500)
    // #endif
    // #ifndef MP-WEIXIN
    wxLoggingIn.value = false
    uni.showToast({ title: '当前环境不支持微信登录', icon: 'none' })
    // #endif
  } catch (e: any) {
    wxLoggingIn.value = false
    uni.hideLoading()
    errMsg.value = e?.message || '微信登录失败'
  }
}

async function onSubmit() {
  errMsg.value = ''
  const n = nickname.value.trim()
  const p = password.value
  if (n.length < 2 || n.length > 20) {
    errMsg.value = '昵称需为 2-20 个字符'
    return
  }
  if (p.length < 6) {
    errMsg.value = '密码至少 6 位'
    return
  }
  if (mode.value === 'register' && p !== confirmPwd.value) {
    errMsg.value = '两次密码不一致'
    return
  }
  try {
    uni.showLoading({ title: '处理中…' })
    const res = mode.value === 'login' ? await login(n, p) : await register(n, p)
    setToken(res.token)
    setUser(res.user)
    uni.hideLoading()
    uni.showToast({ title: '成功', icon: 'success' })
    uni.reLaunch({ url: '/pages/mine/index' })
  } catch (e: any) {
    uni.hideLoading()
    errMsg.value = e?.message || '操作失败'
  }
}

function onLogout() {
  clearAuth()
  loggedUser.value = null
  uni.showToast({ title: '已退出', icon: 'none' })
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background: $color-bg;
  display: flex;
  flex-direction: column;
}
.hero {
  position: relative;
  padding: 56rpx 32rpx 80rpx;
  overflow: hidden;
  background: linear-gradient(135deg, $color-bg-warm 0%, $color-bg 100%);
  border-bottom-left-radius: 48rpx;
  border-bottom-right-radius: 48rpx;
}
.hero-bg {
  position: absolute; inset: 0;
  background:
    radial-gradient(circle at 20% 30%, rgba(107, 123, 142, 0.35), transparent 50%),
    radial-gradient(circle at 80% 70%, rgba(184, 72, 60, 0.2), transparent 50%);
}
.hero-orb { position: absolute; border-radius: 50%; filter: blur(40rpx); pointer-events: none; }
.orb-1 { top: -60rpx; right: -40rpx; width: 200rpx; height: 200rpx; background: rgba(107, 123, 142, 0.45); }
.orb-2 { bottom: -80rpx; left: -60rpx; width: 220rpx; height: 220rpx; background: rgba(184, 72, 60, 0.3); }
.hero-content { position: relative; z-index: 1; display: flex; flex-direction: column; align-items: center; }
.hero-icon { font-size: 72rpx; color: $color-paper; text-shadow: 0 0 24rpx rgba(107, 123, 142, 0.8); }
.hero-title { font-size: 52rpx; font-weight: 800; color: $color-paper; letter-spacing: 12rpx; margin-top: 12rpx; }
.hero-sub { margin-top: 16rpx; font-size: 28rpx; color: $color-ink-light; letter-spacing: 2rpx; }

.body { flex: 1; padding: 40rpx 32rpx; }
.server-url-row {
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: 24rpx;
  padding: 24rpx 28rpx;
  margin-bottom: 24rpx;
}
.url-label { font-size: 28rpx; color: $color-ink-light; margin-bottom: 16rpx; display: block; }
.url-input-wrap {
  display: flex; align-items: center; gap: 12rpx;
}
.url-input {
  flex: 1;
  padding: 18rpx 22rpx;
  background: rgba(107, 123, 142, 0.06);
  border: 1rpx solid $color-border;
  border-radius: 18rpx;
  font-size: 28rpx;
  color: $color-ink;
}
.url-btn {
  flex: 0 0 auto;
  padding: 14rpx 28rpx;
  border-radius: 16rpx;
  font-size: 28rpx;
  color: $color-ink-lighter;
  background: rgba(107, 123, 142, 0.08);
  &.active { color: #fff; background: linear-gradient(135deg, $color-primary, $color-primary-dark); }
}
.url-current { font-size: 26rpx; color: $color-ink-lighter; margin-top: 12rpx; display: block; word-break: break-all; }
.card {
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: 32rpx;
  padding: 32rpx;
}
.seg-tabs {
  display: flex;
  background: rgba(107, 123, 142, 0.08);
  border-radius: 20rpx;
  padding: 6rpx;
  margin-bottom: 32rpx;
}
.seg {
  flex: 1;
  text-align: center;
  padding: 20rpx 0;
  font-size: 32rpx;
  color: $color-ink-light;
  border-radius: 16rpx;
}
.seg.active { background: $color-bg; color: $color-primary; font-weight: 600; box-shadow: $shadow-sm; }
.form-row { display: flex; align-items: center; margin-bottom: 24rpx; }
.label { flex: 0 0 120rpx; font-size: 30rpx; color: $color-ink-light; }
.input {
  flex: 1;
  padding: 20rpx 24rpx;
  background: rgba(107, 123, 142, 0.06);
  border: 1rpx solid $color-border;
  border-radius: 20rpx;
  font-size: 32rpx;
  color: $color-ink;
}
.err { font-size: 28rpx; color: $color-vermilion; margin-bottom: 16rpx; }
.btn-primary {
  margin-top: 12rpx;
  text-align: center;
  padding: 28rpx 0;
  border-radius: 24rpx;
  font-size: 34rpx;
  letter-spacing: 6rpx;
  color: $color-bg;
  background: linear-gradient(135deg, $color-primary, $color-primary-dark);
  box-shadow: $glow-gold;
}
.logout-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 24rpx;
  font-size: 24rpx;
  color: $color-ink-light;
}
.link { color: $color-vermilion; }
.wx-login-row { margin-top: 40rpx; }
.divider-line {
  display: flex; align-items: center; margin-bottom: 32rpx;
  &::before, &::after {
    content: ''; flex: 1; height: 1rpx; background: $color-border;
  }
}
.divider-text {
  font-size: 26rpx; color: $color-ink-lighter;
  padding: 0 24rpx; white-space: nowrap;
}
.wx-btn {
  display: flex; align-items: center; justify-content: center;
  gap: 12rpx; padding: 28rpx 0; border-radius: 24rpx;
  font-size: 34rpx; font-weight: 600; letter-spacing: 4rpx;
  background: #07C160; color: #fff;
  &.disabled { opacity: 0.6; }
  &:active { opacity: 0.85; transform: scale(0.98); }
}
.wx-icon { font-size: 32rpx; }
</style>
