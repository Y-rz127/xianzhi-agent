<template>
  <div class="hehun-page page-transition">
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
            <input id="male-birth" name="male-birth" type="datetime-local" autocomplete="off" v-model="male.birth" />
          </div>
          <div class="form-row">
            <label for="male-gender">性别</label>
            <select id="male-gender" name="male-gender" v-model="male.gender">
              <option value="男">男</option>
              <option value="女">女</option>
            </select>
          </div>
          <div class="form-row">
            <label>出生地（用于真太阳时）</label>
            <div class="hh-region">
              <select v-model="male.province" aria-label="男方省份">
                <option value="">省份</option>
                <option v-for="p in regionData" :key="'m-p-' + p.name" :value="p.name">{{ p.name }}</option>
              </select>
              <select v-model="male.city" :disabled="!male.province" aria-label="男方城市">
                <option value="">城市</option>
                <option v-for="c in maleCities" :key="'m-c-' + c.name" :value="c.name">{{ c.name }}</option>
              </select>
              <select v-model="male.district" :disabled="!male.city" aria-label="男区县">
                <option value="">区县</option>
                <option v-for="d in maleDistricts" :key="'m-d-' + d.name" :value="d.name">{{ d.name }}</option>
              </select>
            </div>
            <div v-if="male.longitude !== null" class="hh-region-hint">
              经度 {{ male.longitude.toFixed(2) }}°E · 时差 {{ longitudeDeltaLabel(male.longitude) }}
            </div>
          </div>
        </div>
        <div class="hh-vs">VS</div>
        <div class="hh-person">
          <div class="hh-person-title female">女方</div>
          <div class="form-row">
            <label for="female-birth">出生时间</label>
            <input id="female-birth" name="female-birth" type="datetime-local" autocomplete="off" v-model="female.birth" />
          </div>
          <div class="form-row">
            <label for="female-gender">性别</label>
            <select id="female-gender" name="female-gender" v-model="female.gender">
              <option value="男">男</option>
              <option value="女">女</option>
            </select>
          </div>
          <div class="form-row">
            <label>出生地（用于真太阳时）</label>
            <div class="hh-region">
              <select v-model="female.province" aria-label="女方省份">
                <option value="">省份</option>
                <option v-for="p in regionData" :key="'f-p-' + p.name" :value="p.name">{{ p.name }}</option>
              </select>
              <select v-model="female.city" :disabled="!female.province" aria-label="女方城市">
                <option value="">城市</option>
                <option v-for="c in femaleCities" :key="'f-c-' + c.name" :value="c.name">{{ c.name }}</option>
              </select>
              <select v-model="female.district" :disabled="!female.city" aria-label="女区县">
                <option value="">区县</option>
                <option v-for="d in femaleDistricts" :key="'f-d-' + d.name" :value="d.name">{{ d.name }}</option>
              </select>
            </div>
            <div v-if="female.longitude !== null" class="hh-region-hint">
              经度 {{ female.longitude.toFixed(2) }}°E · 时差 {{ longitudeDeltaLabel(female.longitude) }}
            </div>
          </div>
        </div>
      </div>

      <div class="hh-preview-area">
        <div v-if="previewLoading" class="hh-preview-skeleton">
          <div class="hh-preview-skeleton-card">
            <div class="skeleton skeleton-title" style="width: 40%"></div>
            <div class="skeleton" style="height: 80px; margin-top: 12px"></div>
          </div>
          <div class="hh-preview-skeleton-card">
            <div class="skeleton skeleton-title" style="width: 40%"></div>
            <div class="skeleton" style="height: 80px; margin-top: 12px"></div>
          </div>
        </div>
        <div v-else-if="maleChart && femaleChart" class="hh-preview">
          <div class="hh-preview-card">
            <div class="hh-preview-title male">男方命盘</div>
            <BaziCard :pillars="maleChart.pillars || []" />
          </div>
          <div class="hh-preview-card">
            <div class="hh-preview-title female">女方命盘</div>
            <BaziCard :pillars="femaleChart.pillars || []" />
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
        <div class="hh-skeleton">
          <div class="skeleton skeleton-title" style="width: 50%"></div>
          <div class="skeleton skeleton-text" style="width: 92%"></div>
          <div class="skeleton skeleton-text" style="width: 86%"></div>
          <div class="skeleton skeleton-text" style="width: 78%"></div>
          <div class="skeleton skeleton-text" style="width: 64%"></div>
        </div>
      </div>
      <div v-else-if="result" class="hh-result">
        <MarkdownRender :content="result" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue"
import MarkdownRender from "../components/MarkdownRender.vue"
import BaziCard from "../components/BaziCard.vue"
import { getChart, apiFetch, type ChartData } from "../api"
import { regionData } from "../utils/region-data"

const API_BASE = import.meta.env.DEV ? "http://localhost:8123/api" : "/api"

interface PersonForm {
  birth: string
  gender: string
  province: string
  city: string
  district: string
  longitude: number | null
}

const male = ref<PersonForm>({ birth: "", gender: "男", province: "", city: "", district: "", longitude: null })
const female = ref<PersonForm>({ birth: "", gender: "女", province: "", city: "", district: "", longitude: null })
const loading = ref(false)
const result = ref("")

const previewLoading = ref(false)
const maleChart = ref<ChartData | null>(null)
const femaleChart = ref<ChartData | null>(null)

// datetime-local 返回 "YYYY-MM-DDTHH:MM"，转成后端需要的 "YYYY-MM-DD HH:MM"
const normalizeBirth = (s: string) => s.trim().replace("T", " ")
const birthRegex = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/
const isValidBirth = (s: string) => birthRegex.test(normalizeBirth(s))

// 真太阳时时差标签：相对 120°E（北京时间基准），每度 4 分钟
const longitudeDeltaLabel = (lon: number) => {
  const minutes = Math.round((lon - 120) * 4)
  if (minutes === 0) return "0 分钟"
  const sign = minutes > 0 ? "+" : "-"
  const abs = Math.abs(minutes)
  if (abs < 60) return `${sign}${abs} 分钟`
  const h = Math.floor(abs / 60)
  const m = abs % 60
  return `${sign}${h} 小时${m ? " " + m + " 分钟" : ""}`
}

// 联动数据：当前选中省/市
const maleCities = computed(() => {
  const p = regionData.find(x => x.name === male.value.province)
  return p?.cities || []
})
const maleDistricts = computed(() => {
  const c = maleCities.value.find(x => x.name === male.value.city)
  return c?.districts || []
})
const femaleCities = computed(() => {
  const p = regionData.find(x => x.name === female.value.province)
  return p?.cities || []
})
const femaleDistricts = computed(() => {
  const c = femaleCities.value.find(x => x.name === female.value.city)
  return c?.districts || []
})

// 省份变化时清空下级；城市变化时取该城市经度（区县级同市经度）
watch(() => male.value.province, () => {
  male.value.city = ""
  male.value.district = ""
  male.value.longitude = null
})
watch(() => male.value.city, () => {
  male.value.district = ""
  const c = maleCities.value.find(x => x.name === male.value.city)
  male.value.longitude = c ? c.longitude : null
})
watch(() => female.value.province, () => {
  female.value.city = ""
  female.value.district = ""
  female.value.longitude = null
})
watch(() => female.value.city, () => {
  female.value.district = ""
  const c = femaleCities.value.find(x => x.name === female.value.city)
  female.value.longitude = c ? c.longitude : null
})

let debounceTimer: ReturnType<typeof setTimeout> | null = null
const updatePreview = async () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(async () => {
    const maleValid = isValidBirth(male.value.birth)
    const femaleValid = isValidBirth(female.value.birth)
    if (!maleValid || !femaleValid) {
      maleChart.value = null
      femaleChart.value = null
      previewLoading.value = false
      return
    }
    previewLoading.value = true
    try {
      const [mChart, fChart] = await Promise.all([
        getChart(normalizeBirth(male.value.birth), male.value.gender, undefined, undefined, male.value.longitude ?? undefined),
        getChart(normalizeBirth(female.value.birth), female.value.gender, undefined, undefined, female.value.longitude ?? undefined),
      ])
      maleChart.value = mChart
      femaleChart.value = fChart
    } catch {
      maleChart.value = null
      femaleChart.value = null
    } finally {
      previewLoading.value = false
    }
  }, 600)
}

watch([male, female], updatePreview, { deep: true })

const analyze = async () => {
  if (!male.value.birth || !female.value.birth) return
  loading.value = true
  result.value = ""
  try {
    const params = new URLSearchParams({
      birth_time_a: normalizeBirth(male.value.birth),
      gender_a: male.value.gender,
      birth_time_b: normalizeBirth(female.value.birth),
      gender_b: female.value.gender,
    })
    if (male.value.longitude !== null) params.set("longitude_a", String(male.value.longitude))
    if (female.value.longitude !== null) params.set("longitude_b", String(female.value.longitude))
    const res = await apiFetch(`${API_BASE}/ai/xianzhi/hehun?${params}`)
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
  min-height: 100vh; display: flex; justify-content: center; align-items: flex-start;
  padding: 20px;
}
.hh-card { width: 100%; max-width: 700px; max-height: calc(100vh - 40px); overflow-y: auto; padding: 28px; }
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
.form-row input,
.form-row select {
  width: 100%; background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 12px; color: var(--text); font-size: 13px; outline: none;
  box-sizing: border-box;
}
.form-row input:focus,
.form-row select:focus { border-color: var(--love); }
.form-row select option { background: var(--bg-3); color: var(--text); }
.form-row select:disabled { opacity: 0.5; cursor: not-allowed; }
.hh-region { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
.hh-region-hint { font-size: 11px; color: var(--text-dim); margin-top: 4px; }
.hh-preview-area { margin-bottom: 20px; }
.hh-preview { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.hh-preview-card { animation: fadeInUp 0.5s ease-out forwards; }
.hh-preview-title { font-size: 12px; letter-spacing: 2px; margin-bottom: 8px; text-align: center; }
.hh-preview-title.male { color: #5b8def; }
.hh-preview-title.female { color: var(--love); }
.hh-preview-skeleton { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.hh-preview-skeleton-card {
  background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 12px;
  padding: 16px;
}
.hh-btn { width: 100%; justify-content: center; padding: 12px; font-size: 15px; }
.hh-loading { text-align: center; padding: 20px; color: var(--text-dim); font-size: 13px; }
.hh-skeleton { margin-top: 18px; text-align: left; }
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
  .hh-preview, .hh-preview-skeleton { grid-template-columns: 1fr; }
  .hh-region { grid-template-columns: 1fr; }
}
</style>
