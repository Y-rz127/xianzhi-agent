<template>
  <div class="hehun-page">
    <div class="hh-card glass-card">
      <div class="hh-header">
        <h2>八字合婚</h2>
        <p>输入双方生辰，AI 智能分析缘分与合婚建议</p>
      </div>

      <div class="hh-form">
        <div class="hh-person">
          <div class="hh-person-title male">男方</div>
          <div class="form-row">
            <label for="male-birth">出生时间</label>
            <input id="male-birth" name="male-birth" v-model="male.birth" placeholder="1990-05-20 14:30" />
          </div>
        </div>
        <div class="hh-vs">VS</div>
        <div class="hh-person">
          <div class="hh-person-title female">女方</div>
          <div class="form-row">
            <label for="female-birth">出生时间</label>
            <input id="female-birth" name="female-birth" v-model="female.birth" placeholder="1992-08-15 08:00" />
          </div>
        </div>
      </div>
      <button class="btn btn-primary hh-btn" @click="analyze" :disabled="loading || !male.birth || !female.birth" aria-label="开始合婚分析">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
        {{ loading ? "分析中..." : "开始合婚分析" }}
      </button>

      <div v-if="loading" class="hh-loading">
        <span class="loading-dots"><span></span><span></span><span></span></span>
        正在由先知分析双方命盘...
      </div>
      <div v-else-if="result" class="hh-result">
        <MarkdownRender :content="result" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import MarkdownRender from "../components/MarkdownRender.vue"

const API_BASE = import.meta.env.DEV ? "http://localhost:8123/api" : "/api"
const male = ref({ birth: "" })
const female = ref({ birth: "" })
const loading = ref(false)
const result = ref("")

const analyze = async () => {
  if (!male.value.birth || !female.value.birth) return
  loading.value = true
  result.value = ""
  try {
    const params = new URLSearchParams({
      birth_time_a: male.value.birth,
      gender_a: "男",
      birth_time_b: female.value.birth,
      gender_b: "女",
    })
    const res = await fetch(`${API_BASE}/ai/xianzhi/hehun?${params}`)
    const data = await res.json()
    if (data.error) result.value = "分析失败：" + data.error
    else result.value = data.result || data.content || JSON.stringify(data)
  } catch {
    result.value = "请求失败，请稍后重试"
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.hehun-page {
  height: 100vh; overflow-y: auto; padding: 20px;
  display: flex; justify-content: center;
}
.hh-card { width: 100%; max-width: 600px; padding: 28px; }
.hh-header { text-align: center; margin-bottom: 24px; }
.hh-header h2 { font-size: 22px; color: var(--love); letter-spacing: 3px; }
.hh-header p { font-size: 12px; color: var(--text-dim); margin-top: 6px; }
.hh-form { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
.hh-person { flex: 1; }
.hh-person-title { font-size: 14px; letter-spacing: 2px; margin-bottom: 10px; text-align: center; }
.hh-person-title.male { color: #5b8def; }
.hh-person-title.female { color: var(--love); }
.hh-vs { font-size: 20px; color: var(--love); font-weight: bold; padding-top: 28px; }
.form-row { margin-bottom: 10px; }
.form-row label { display: block; font-size: 11px; color: var(--text-dim); margin-bottom: 4px; }
.form-row input {
  width: 100%; background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 12px; color: var(--text); font-size: 13px; outline: none;
  box-sizing: border-box;
}
.form-row input:focus { border-color: var(--love); }
.hh-btn { width: 100%; justify-content: center; padding: 12px; font-size: 15px; }
.hh-loading { text-align: center; padding: 20px; color: var(--text-dim); font-size: 13px; }
.hh-result { margin-top: 24px; background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
.loading-dots { display: inline-flex; gap: 4px; margin-right: 8px; }
.loading-dots span { width: 5px; height: 5px; background: var(--love); border-radius: 50%; animation: dot 1.4s infinite both; }
.loading-dots span:nth-child(1) { animation-delay: 0s; }
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot { 0%, 80%, 100% { transform: scale(0); opacity: 0.5; } 40% { transform: scale(1); opacity: 1; } }
@media (max-width: 600px) {
  .hh-form { flex-direction: column; }
  .hh-vs { padding-top: 0; text-align: center; }
}
</style>