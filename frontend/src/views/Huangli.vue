<template>
  <div class="huangli-page">
    <div class="hl-card glass-card">
      <div class="hl-header">
        <div class="hl-date-picker">
          <input id="hl-date" name="hl-date" aria-label="选择日期" type="date" v-model="dateStr" @change="loadHuangli" class="hl-date-input" />
          <button class="btn" @click="goToday"  aria-label="今天">今天</button>
        </div>
      </div>

      <div v-if="loading" class="hl-loading">加载中...</div>
      <div v-else-if="error" class="hl-error">{{ error }}</div>
      <div v-else-if="data" class="hl-body">
        <div class="hl-main">
          <div class="hl-lunar-date">
            <div class="hl-lunar-text">{{ data.lunar }}</div>
            <div class="hl-solar-text">{{ data.solar }}</div>
          </div>
          <div class="hl-ganzhi-row">
            <span class="hl-gz-item">年 {{ data.yearGanZhi }}</span>
            <span class="hl-gz-sep">·</span>
            <span class="hl-gz-item">月 {{ data.monthGanZhi }}</span>
            <span class="hl-gz-sep">·</span>
            <span class="hl-gz-item day-master">日 {{ data.dayGanZhi }}</span>
          </div>
          <div class="hl-meta">
            <span>{{ data.shengXiao }}年</span>
            <span v-if="data.naYin">纳音 {{ data.naYin }}</span>
            <span v-if="data.xiu">星宿 {{ data.xiu }}</span>
          </div>
        </div>

        <div class="hl-grid">
          <div class="hl-section">
            <div class="hl-section-title good">宜</div>
            <div class="hl-tag-list">
              <span v-for="y in data.yi" :key="y" class="hl-tag good">{{ y }}</span>
              <span v-if="!data.yi.length" class="hl-empty">无</span>
            </div>
          </div>
          <div class="hl-section">
            <div class="hl-section-title bad">忌</div>
            <div class="hl-tag-list">
              <span v-for="j in data.ji" :key="j" class="hl-tag bad">{{ j }}</span>
              <span v-if="!data.ji.length" class="hl-empty">无</span>
            </div>
          </div>
        </div>

        <div class="hl-info-row">
          <div class="hl-info-item">
            <span class="hl-info-label">冲煞</span>
            <span class="hl-info-value">{{ data.chong || "无" }}</span>
          </div>
          <div class="hl-info-item">
            <span class="hl-info-label">煞方</span>
            <span class="hl-info-value">{{ data.sha || "无" }}</span>
          </div>
          <div class="hl-info-item" v-if="data.jieQi">
            <span class="hl-info-label">节气</span>
            <span class="hl-info-value">{{ data.jieQi }}</span>
          </div>
        </div>

        <div class="hl-times">
          <div class="hl-section-title">吉时</div>
          <div class="hl-time-grid">
            <div v-for="t in data.jiShi" :key="t.ganzhi" class="hl-time-card good">
              <div class="hl-time-gz">{{ t.ganzhi }}</div>
              <div class="hl-time-range">{{ t.time }}</div>
            </div>
            <span v-if="!data.jiShi.length" class="hl-empty">无</span>
          </div>
          <div class="hl-section-title" style="margin-top: 16px;">凶时</div>
          <div class="hl-time-grid">
            <div v-for="t in data.xiongShi" :key="t.ganzhi" class="hl-time-card bad">
              <div class="hl-time-gz">{{ t.ganzhi }}</div>
              <div class="hl-time-range">{{ t.time }}</div>
            </div>
            <span v-if="!data.xiongShi.length" class="hl-empty">无</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"

const API_BASE = import.meta.env.DEV ? "http://localhost:8123/api" : "/api"
const dateStr = ref("")
const loading = ref(false)
const error = ref("")
const data = ref<any>(null)

const goToday = () => {
  const today = new Date()
  dateStr.value = today.toISOString().split("T")[0]
  loadHuangli()
}

const loadHuangli = async () => {
  if (!dateStr.value) return
  loading.value = true
  error.value = ""
  try {
    const [y, m, d] = dateStr.value.split("-")
    const res = await fetch(`${API_BASE}/ai/xianzhi/huangli?year=${y}&month=${m}&day=${d}`)
    const json = await res.json()
    if (json.error) { error.value = json.error; data.value = null }
    else data.value = json
  } catch { error.value = "加载失败" }
  finally { loading.value = false }
}

onMounted(() => {
  const today = new Date()
  dateStr.value = today.toISOString().split("T")[0]
  loadHuangli()
})
</script>

<style scoped>
.huangli-page {
  min-height: 100%; overflow-y: auto; padding: 20px;
  display: flex; justify-content: center;
}
.hl-card { width: 100%; max-width: 560px; padding: 24px; }
.hl-header { margin-bottom: 20px; }
.hl-date-picker { display: flex; gap: 10px; align-items: center; }
.hl-date-input {
  background: rgba(255,255,255,0.04); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 12px; color: var(--text); font-size: 14px;
  outline: none;
}
.hl-date-input:focus { border-color: var(--accent); }
.hl-loading, .hl-error { text-align: center; padding: 40px; color: var(--text-dim); }
.hl-error { color: var(--danger); }
.hl-main { text-align: center; margin-bottom: 24px; }
.hl-lunar-date { margin-bottom: 12px; }
.hl-lunar-text { font-size: 28px; color: var(--accent-light); letter-spacing: 3px; }
.hl-solar-text { font-size: 12px; color: var(--text-dim); margin-top: 4px; }
.hl-ganzhi-row { display: flex; justify-content: center; align-items: center; gap: 8px; margin-bottom: 10px; }
.hl-gz-item { font-size: 14px; color: var(--text); }
.hl-gz-item.day-master { color: var(--accent-light); font-weight: bold; }
.hl-gz-sep { color: var(--border); }
.hl-meta { font-size: 12px; color: var(--text-dim); display: flex; justify-content: center; gap: 16px; }
.hl-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
.hl-section-title { font-size: 13px; letter-spacing: 2px; margin-bottom: 10px; }
.hl-section-title.good { color: #4a7c3a; }
.hl-section-title.bad { color: #c0392b; }
.hl-tag-list { display: flex; flex-wrap: wrap; gap: 6px; }
.hl-tag { font-size: 12px; padding: 4px 10px; border-radius: 6px; }
.hl-tag.good { background: rgba(74,124,58,0.1); color: #6a9c5a; border: 1px solid rgba(74,124,58,0.2); }
.hl-tag.bad { background: rgba(192,57,43,0.1); color: #d0584a; border: 1px solid rgba(192,57,43,0.2); }
.hl-empty { font-size: 12px; color: var(--text-dim); }
.hl-info-row { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
.hl-info-item { display: flex; gap: 6px; font-size: 13px; }
.hl-info-label { color: var(--text-dim); }
.hl-info-value { color: var(--text); }
.hl-time-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.hl-time-card { font-size: 12px; padding: 6px 12px; border-radius: 8px; text-align: center; }
.hl-time-card.good { background: rgba(74,124,58,0.08); border: 1px solid rgba(74,124,58,0.15); }
.hl-time-card.bad { background: rgba(192,57,43,0.06); border: 1px solid rgba(192,57,43,0.1); }
.hl-time-gz { color: var(--text); font-weight: bold; margin-bottom: 2px; }
.hl-time-range { color: var(--text-dim); font-size: 10px; }
</style>