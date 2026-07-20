<template>
  <div class="admin-login-page">
    <div class="login-card">
      <div class="login-header">
        <h2>管理后台</h2>
        <p>请输入管理员账号</p>
      </div>
      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label>用户名</label>
          <input
            v-model="username"
            type="text"
            placeholder="请输入用户名"
            autocomplete="username"
          />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input
            v-model="password"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
          />
        </div>
        <div v-if="errMsg" class="error-msg">{{ errMsg }}</div>
        <button type="submit" :disabled="loading" class="btn-login">
          {{ loading ? "登录中..." : "登录" }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"
import { setAdminLoggedIn } from "../utils/adminAuth"
import { adminLogin } from "../api"

const router = useRouter()
const username = ref("")
const password = ref("")
const errMsg = ref("")
const loading = ref(false)

async function handleLogin() {
  errMsg.value = ""
  if (!username.value.trim()) {
    errMsg.value = "请输入用户名"
    return
  }
  if (!password.value) {
    errMsg.value = "请输入密码"
    return
  }

  loading.value = true

  try {
    const result = await adminLogin(username.value, password.value)
    setAdminLoggedIn()
    const redirect = (router.currentRoute.value.query.redirect as string) || "/user-admin"
    router.push(redirect)
  } catch (e: any) {
    errMsg.value = e.message || "登录失败，请检查用户名和密码"
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.admin-login-page {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #0a0a1a 0%, #1a1a3e 100%);
}

.login-card {
  width: 360px;
  padding: 40px 32px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-header h2 {
  font-size: 22px;
  color: #e0e0ff;
  letter-spacing: 2px;
  margin-bottom: 8px;
}

.login-header p {
  font-size: 13px;
  color: #8888aa;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  font-size: 12px;
  color: #9999bb;
  margin-bottom: 6px;
}

.form-group input {
  width: 100%;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(0, 0, 0, 0.3);
  color: #e0e0ff;
  font-size: 14px;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.form-group input:focus {
  border-color: #d4af37;
}

.form-group input::placeholder {
  color: #666680;
}

.error-msg {
  font-size: 12px;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
  padding: 8px 12px;
  border-radius: 8px;
  border-left: 3px solid #ef4444;
  margin-bottom: 16px;
}

.btn-login {
  width: 100%;
  padding: 12px;
  border-radius: 10px;
  border: none;
  background: linear-gradient(135deg, #d4af37, #8b6f47);
  color: #0c1220;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-login:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(212, 175, 55, 0.4);
}

.btn-login:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>