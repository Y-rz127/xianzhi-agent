<template>
  <div class="observability">
    <header class="page-header glass-card">
      <div class="header-left">
        <div class="header-icon">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 20V10"/>
            <path d="M12 20V4"/>
            <path d="M6 20v-6"/>
          </svg>
        </div>
        <div>
          <h2 class="text-glow-soft">监测台</h2>
          <div class="header-info">API 指标监控 · 每 5 秒自动刷新</div>
        </div>
      </div>
      <div class="header-right">
        <div v-if="loading" class="loading-dots">
          <span></span><span></span><span></span>
        </div>
        <button class="btn btn-xs" @click="loadMetrics" :disabled="loading" aria-label="刷新指标">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
          <span>刷新</span>
        </button>
      </div>
    </header>

    <section class="summary-grid">
      <div class="summary-card glass-card">
        <div class="summary-label">总请求数</div>
        <div class="summary-value">{{ formatNumber(metrics?.total_requests ?? 0) }}</div>
        <div class="summary-sub">累计 API 调用</div>
      </div>
      <div class="summary-card glass-card">
        <div class="summary-label">平均延迟</div>
        <div class="summary-value">{{ (metrics?.avg_latency_ms ?? 0).toFixed(1) }}<span class="unit">ms</span></div>
        <div class="summary-sub">全端点平均值</div>
      </div>
      <div class="summary-card glass-card">
        <div class="summary-label">错误率</div>
        <div class="summary-value" :class="errorRateClass">{{ (metrics?.error_rate ?? 0).toFixed(2) }}<span class="unit">%</span></div>
        <div class="summary-sub">4xx / 5xx 占比</div>
      </div>
      <div class="summary-card glass-card">
        <div class="summary-label">运行时长</div>
        <div class="summary-value">{{ formatUptime(metrics?.uptime_seconds ?? 0) }}</div>
        <div class="summary-sub">自指标重置起</div>
      </div>
    </section>

    <section class="charts-section glass-card">
      <div class="section-header">
        <div class="section-title">端点请求分布</div>
        <div class="status-legend">
          <span class="legend-item"><span class="dot success"></span>2xx {{ metrics?.status_codes["2xx"] ?? 0 }}</span>
          <span class="legend-item"><span class="dot warning"></span>4xx {{ metrics?.status_codes["4xx"] ?? 0 }}</span>
          <span class="legend-item"><span class="dot danger"></span>5xx {{ metrics?.status_codes["5xx"] ?? 0 }}</span>
        </div>
      </div>

      <div v-if="chartData.length === 0" class="empty-state">
        <p>暂无请求数据</p>
      </div>
      <div v-else class="bar-chart">
        <svg class="chart-svg" :viewBox="`0 0 ${chartWidth} ${chartHeight}`" preserveAspectRatio="none">
          <g class="bars">
            <rect
              v-for="(item, i) in chartData"
              :key="item.key"
              :x="barX(i)"
              :y="barY(item.count)"
              :width="barWidth"
              :height="chartHeight - barY(item.count) - 20"
              rx="4"
              fill="url(#barGradient)"
            />
          </g>
          <defs>
            <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="var(--accent-light)" />
              <stop offset="100%" stop-color="var(--accent)" stop-opacity="0.6" />
            </linearGradient>
          </defs>
        </svg>
        <div class="bar-labels">
          <div v-for="(item, i) in chartData" :key="item.key + '-label'" class="bar-label" :style="{ left: labelLeft(i), width: labelWidth }">
            <div class="label-path" :title="item.method + ' ' + item.path">{{ item.path }}</div>
            <div class="label-count">{{ item.count }}</div>
          </div>
        </div>
      </div>
    </section>

    <section class="llm-section glass-card">
      <div class="section-header">
        <div class="section-title">LLM 调用与成本</div>
        <div class="llm-header-right">
          <button class="btn btn-xs" @click="togglePriceEditor">{{ priceEditing ? "收起单价编辑" : "配置单价" }}</button>
          <div class="llm-summary">
            <span>调用 {{ formatNumber(llmTotals.calls) }} 次</span>
            <span>输入 {{ formatTokens(llmTotals.prompt_tokens) }}</span>
            <span>输出 {{ formatTokens(llmTotals.completion_tokens) }}</span>
            <span class="llm-cost">{{ llmTotals.est_cost > 0 ? `≈ ¥${llmTotals.est_cost.toFixed(4)}` : (llmTotals.price_configured ? "已配置单价" : "未配置单价") }}</span>
          </div>
        </div>
      </div>
      <div v-if="priceEditing" class="price-editor">
        <div class="chain-hint">单价单位：元/百万 token。逐行填写模型名与输入/输出单价；删除全部行保存 = 不折算成本。</div>
        <div class="price-rows">
          <div class="price-row price-row-head"><span>模型</span><span>输入单价</span><span>输出单价</span><span></span></div>
          <div v-for="(row, i) in priceRows" :key="i" class="price-row">
            <input v-model="row.model" class="price-input" placeholder="模型名，如 qwen3.8-27b" spellcheck="false" />
            <input v-model="row.input" class="price-input" type="number" min="0" step="0.1" placeholder="输入" />
            <input v-model="row.output" class="price-input" type="number" min="0" step="0.1" placeholder="输出" />
            <button class="btn btn-xs" @click="priceRows.splice(i, 1)">删除</button>
          </div>
        </div>
        <div class="chain-actions" style="margin-top: var(--spacing-md);">
          <button class="btn btn-xs" @click="priceRows.push({ model: '', input: '', output: '' })">添加模型</button>
          <button class="btn btn-xs" @click="savePrice" :disabled="priceSaving">{{ priceSaving ? "保存中" : "保存单价" }}</button>
          <button class="btn btn-xs" @click="togglePriceEditor">取消</button>
        </div>
        <div v-if="priceMessage" class="chain-message" :class="{ 'chain-error': priceError }">{{ priceMessage }}</div>
      </div>
      <div v-if="llmEntries.length === 0" class="empty-state">
        <p>暂无 LLM 调用数据（需配置 LLM_PRICE_MAP 才显示金额）</p>
      </div>
      <div v-else class="llm-table">
        <div class="llm-row llm-row-head">
          <span>模型</span><span>用途</span><span>次数</span><span>输入 token</span><span>输出 token</span><span>平均耗时</span><span>估算成本</span>
        </div>
        <div v-for="row in llmEntries" :key="row.model + row.tag" class="llm-row">
          <span class="llm-model">{{ row.model }}</span>
          <span class="llm-tag">{{ row.tag }}</span>
          <span>{{ row.calls }}</span>
          <span>{{ formatTokens(row.prompt_tokens) }}</span>
          <span>{{ formatTokens(row.completion_tokens) }}</span>
          <span>{{ row.avg_latency_ms }} ms</span>
          <span class="llm-cost">{{ row.est_cost > 0 ? `¥${row.est_cost.toFixed(4)}` : "-" }}</span>
        </div>
      </div>
    </section>

    <section class="chain-section glass-card">
      <div class="section-header">
        <div class="section-title">模型降级链</div>
        <div class="chain-actions">
          <button class="btn btn-xs" @click="loadChain" :disabled="chainLoading">{{ chainLoading ? "加载中" : "重新加载" }}</button>
          <button class="btn btn-xs" @click="saveChain" :disabled="chainSaving">{{ chainSaving ? "保存中" : "保存" }}</button>
        </div>
      </div>
      <div class="chain-hint">主模型失败（限流/超时/5xx/模型不存在）时按顺序自动降级；每行填一个模型名，第一行为主模型。留空=回退 .env 主模型。</div>
      <textarea
        v-model="chainText"
        class="chain-input"
        rows="4"
        placeholder="qwen3.8-27b&#10;qwen3.8-flash&#10;qwen3.8-2.4t-a95b"
        spellcheck="false"
      ></textarea>
      <div class="chain-candidates">
        <span class="chain-candidate-label">候选：</span>
        <span v-for="c in chainCandidates" :key="c" class="chain-chip" @click="addCandidate(c)" :title="`添加 ${c}`">{{ c }}</span>
      </div>
      <div v-if="chainOrder.length" class="chain-summary">
        当前生效链：<span v-for="(m, i) in chainOrder" :key="m + i" class="chain-item">{{ i + 1 }}. {{ m }}</span>
      </div>
      <div v-if="chainMessage" class="chain-message" :class="{ 'chain-error': chainError }">{{ chainMessage }}</div>
    </section>

    <section class="top-endpoints glass-card">
      <div class="section-title">Top 5 端点</div>
      <div v-if="topEndpoints.length === 0" class="empty-state">
        <p>暂无数据</p>
      </div>
      <div v-else class="endpoint-list">
        <div v-for="(ep, idx) in topEndpoints" :key="ep.method + ep.path" class="endpoint-item">
          <div class="endpoint-rank">{{ idx + 1 }}</div>
          <div class="endpoint-info">
            <div class="endpoint-name" :title="ep.method + ' ' + ep.path">
              <span class="endpoint-method">{{ ep.method }}</span>
              <span class="endpoint-path">{{ ep.path }}</span>
            </div>
            <div class="endpoint-meta">平均 {{ ep.avg_latency_ms.toFixed(1) }} ms · 累计 {{ ep.total_latency_ms.toFixed(0) }} ms</div>
          </div>
          <div class="endpoint-count">{{ ep.count }}</div>
        </div>
      </div>
    </section>

    <section class="errors-section glass-card">
      <div class="section-header">
        <div class="section-title">近期错误</div>
        <div class="section-sub">最近 50 条</div>
      </div>
      <div v-if="recentErrors.length === 0" class="empty-state">
        <p>暂无错误记录</p>
      </div>
      <div v-else class="errors-list">
        <div v-for="err in recentErrors" :key="err.timestamp + err.method + err.path + err.status" class="error-item">
          <div class="error-status">{{ err.status }}</div>
          <div class="error-info">
            <div class="error-title">{{ err.method }} {{ err.path }}</div>
            <div class="error-meta">{{ formatTime(err.timestamp) }} · {{ err.latency_ms }} ms</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue"
import { fetchMetrics, getLlmChain, updateLlmChain, getLlmPrice, updateLlmPrice, type MetricsData, type LlmPriceMap } from "../api"

const metrics = ref<MetricsData | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const chartWidth = 720
const chartHeight = 220
const maxBars = 8

let timer: ReturnType<typeof setInterval> | null = null

const chartData = computed(() => {
  const endpoints = metrics.value?.endpoints ?? []
  return endpoints.slice(0, maxBars).map((ep) => ({
    key: `${ep.method} ${ep.path}`,
    method: ep.method,
    path: truncatePath(ep.path),
    count: ep.count,
  }))
})

const topEndpoints = computed(() => metrics.value?.top_endpoints ?? [])
const llmEntries = computed(() => metrics.value?.llm ?? [])
const llmTotals = computed(() => metrics.value?.llm_totals ?? { calls: 0, prompt_tokens: 0, completion_tokens: 0, est_cost: 0, price_configured: false })
const recentErrors = computed(() => {
  const list = metrics.value?.recent_errors ?? []
  return [...list].reverse()
})

const errorRateClass = computed(() => {
  const rate = metrics.value?.error_rate ?? 0
  if (rate >= 5) return "danger"
  if (rate >= 1) return "warning"
  return "success"
})

const maxCount = computed(() => {
  const vals = chartData.value.map((d) => d.count)
  return vals.length ? Math.max(...vals) : 1
})

const barWidth = computed(() => {
  const n = chartData.value.length || 1
  return (chartWidth / n) * 0.55
})

function barX(index: number): number {
  const n = chartData.value.length || 1
  const step = chartWidth / n
  return step * index + (step - barWidth.value) / 2
}

function barY(count: number): number {
  const ratio = maxCount.value ? count / maxCount.value : 0
  return chartHeight - 20 - ratio * (chartHeight - 60)
}

function labelLeft(index: number): string {
  const n = chartData.value.length || 1
  return `${(index / n) * 100}%`
}

const labelWidth = computed(() => `${100 / (chartData.value.length || 1)}%`)

function truncatePath(path: string): string {
  if (path.length <= 18) return path
  return "..." + path.slice(-15)
}

function formatNumber(n: number): string {
  return n.toLocaleString("zh-CN")
}

function formatTokens(n: number): string {
  if (n >= 1e6) return (n / 1e6).toFixed(2) + "M"
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K"
  return String(n)
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function formatTime(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleString("zh-CN")
  } catch {
    return "-"
  }
}

async function loadMetrics() {
  loading.value = true
  try {
    metrics.value = await fetchMetrics()
    error.value = null
  } catch (e: any) {
    error.value = e.message || "获取指标失败"
  } finally {
    loading.value = false
  }
}

// ---- LLM 降级链配置 ----
const chainText = ref("")
const chainOrder = ref<string[]>([])
const chainCandidates = ref<string[]>([])
const chainLoading = ref(false)
const chainSaving = ref(false)
const chainMessage = ref("")
const chainError = ref(false)

async function loadChain() {
  chainLoading.value = true
  chainError.value = false
  try {
    const data = await getLlmChain()
    chainOrder.value = data.models
    chainCandidates.value = data.candidates
    chainText.value = data.models.join("\n")
    chainMessage.value = ""
  } catch (e: any) {
    chainError.value = true
    chainMessage.value = e.message || "获取降级链失败"
  } finally {
    chainLoading.value = false
  }
}

async function saveChain() {
  const models = chainText.value.split("\n").map((s) => s.trim()).filter(Boolean)
  chainSaving.value = true
  chainError.value = false
  try {
    const data = await updateLlmChain(models)
    chainOrder.value = data.models
    chainText.value = data.models.join("\n")
    chainMessage.value = "已保存并生效"
    setTimeout(() => (chainMessage.value = ""), 3000)
  } catch (e: any) {
    chainError.value = true
    chainMessage.value = e.message || "保存失败"
  } finally {
    chainSaving.value = false
  }
}

function addCandidate(name: string) {
  const current = chainText.value.split("\n").map((s) => s.trim()).filter(Boolean)
  if (!current.includes(name)) {
    current.push(name)
    chainText.value = current.join("\n")
  }
}

// ---- LLM 单价配置 ----
interface PriceRow { model: string; input: string; output: string }
const priceEditing = ref(false)
const priceRows = ref<PriceRow[]>([])
const priceSaving = ref(false)
const priceMessage = ref("")
const priceError = ref(false)

function togglePriceEditor() {
  priceEditing.value = !priceEditing.value
  if (priceEditing.value) {
    priceMessage.value = ""
    loadPrice()
  }
}

function toRows(prices: LlmPriceMap): PriceRow[] {
  const rows = Object.entries(prices).map(([model, p]) => ({ model, input: String(p.input), output: String(p.output) }))
  return rows.length ? rows : [{ model: "", input: "", output: "" }]
}

async function loadPrice() {
  try {
    const data = await getLlmPrice()
    priceRows.value = toRows(data.prices)
    priceError.value = false
  } catch {
    priceError.value = true
  }
}

async function savePrice() {
  const prices: LlmPriceMap = {}
  for (const row of priceRows.value) {
    const model = row.model.trim()
    if (!model) continue
    const input = Number(row.input)
    const output = Number(row.output)
    if (!Number.isFinite(input) || input < 0 || !Number.isFinite(output) || output < 0) {
      priceError.value = true
      priceMessage.value = `「${model}」的输入/输出单价必须是非负数字`
      return
    }
    prices[model] = { input, output }
  }
  priceSaving.value = true
  priceError.value = false
  try {
    const data = await updateLlmPrice(prices)
    priceRows.value = toRows(data.prices)
    priceMessage.value = "单价已保存并生效"
    loadMetrics()
    setTimeout(() => (priceMessage.value = ""), 3000)
  } catch (e: any) {
    priceError.value = true
    priceMessage.value = e.message || "保存失败"
  } finally {
    priceSaving.value = false
  }
}

onMounted(() => {
  loadMetrics()
  loadChain()
  timer = setInterval(loadMetrics, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.observability {
  max-width: 1100px;
  margin: 0 auto;
  padding: var(--spacing-lg) var(--spacing-lg) 60px;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  min-height: 100%;
  overflow-y: auto;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  border-radius: var(--radius);
}
.header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}
.header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}
.header-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(212, 175, 55, 0.12);
  color: var(--accent-light);
  box-shadow: 0 0 16px rgba(212, 175, 55, 0.18);
}
.page-header h2 { font-size: 18px; letter-spacing: 1px; }
.header-info { font-size: 12px; color: var(--text-dim); margin-top: 2px; }

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-md);
}
.summary-card {
  padding: var(--spacing-md) var(--spacing-lg);
  border-radius: var(--radius);
  border-left: 3px solid var(--accent);
}
.summary-label {
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 6px;
}
.summary-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: 1px;
}
.summary-value .unit {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-dim);
  margin-left: 4px;
}
.summary-value.success { color: var(--success); }
.summary-value.warning { color: #e8b48b; }
.summary-value.danger { color: var(--danger); }
.summary-sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

.charts-section, .top-endpoints, .errors-section, .llm-section, .chain-section {
  padding: var(--spacing-lg);
  border-radius: var(--radius);
}
.chain-actions { display: flex; gap: var(--spacing-md); }
.chain-hint { font-size: 12px; color: var(--text-dim); margin-bottom: var(--spacing-md); line-height: 1.6; }
.chain-input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg-bright, rgba(255, 255, 255, 0.04));
  color: var(--text);
  font-family: var(--font-mono, monospace);
  font-size: 13px;
  resize: vertical;
}
.chain-input:focus { outline: none; border-color: var(--accent, #d4af37); }
.chain-candidates {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-8, 8px);
  margin-top: var(--spacing-md);
}
.chain-candidate-label { font-size: 12px; color: var(--text-dim); }
.chain-chip {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.15s ease;
}
.chain-chip:hover { color: var(--text); border-color: var(--accent, #d4af37); }
.chain-summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  align-items: center;
  margin-top: var(--spacing-md);
  font-size: 12px;
  color: var(--text-dim);
}
.chain-item {
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--bg-bright, rgba(255, 255, 255, 0.06));
  font-family: var(--font-mono, monospace);
  color: var(--text);
}
.chain-message { margin-top: var(--spacing-md); font-size: 12px; color: var(--success, #1dc981); }
.chain-message.chain-error { color: var(--danger, #e8463a); }
.llm-summary {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  font-size: 12px;
  color: var(--text-dim);
}
.llm-header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}
.price-editor {
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
}
.price-rows { display: flex; flex-direction: column; gap: 6px; }
.price-row {
  display: grid;
  grid-template-columns: 1.6fr 1fr 1fr auto;
  gap: var(--spacing-md);
  align-items: center;
  font-size: 12px;
}
.price-row-head { color: var(--text-muted); font-weight: 600; }
.price-input {
  width: 100%;
  box-sizing: border-box;
  padding: 6px 10px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border);
  background: var(--bg-bright, rgba(255, 255, 255, 0.04));
  color: var(--text);
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}
.price-input:focus { outline: none; border-color: var(--accent, #d4af37); }
.llm-table {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.llm-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr 0.6fr 1fr 1fr 1fr 1fr;
  gap: var(--spacing-md);
  align-items: center;
  padding: 6px 8px;
  font-size: 12px;
  color: var(--text);
  border-bottom: 1px solid var(--border);
}
.llm-row-head {
  font-weight: 600;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}
.llm-model { font-family: var(--font-mono, monospace); }
.llm-tag {
  display: inline-block;
  width: fit-content;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--bg-bright, rgba(255, 255, 255, 0.06));
  color: var(--text-dim);
}
.llm-cost { color: var(--accent-light, #ffd700); font-weight: 600; white-space: nowrap; }
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-md);
}
.section-title { font-size: 15px; font-weight: 600; }
.section-sub { font-size: 12px; color: var(--text-muted); }

.status-legend {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-dim);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dot.success { background: var(--success); }
.dot.warning { background: #e8b48b; }
.dot.danger { background: var(--danger); }

.bar-chart {
  position: relative;
  padding-bottom: 48px;
}
.chart-svg {
  width: 100%;
  height: 220px;
  display: block;
}
.bars rect {
  transition: all 0.4s ease;
}
.bar-labels {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 48px;
}
.bar-label {
  position: absolute;
  top: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 0 4px;
  text-align: center;
}
.label-path {
  font-size: 11px;
  color: var(--text-dim);
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.label-count {
  font-size: 12px;
  color: var(--accent-light);
  font-weight: 600;
  margin-top: 2px;
}

.endpoint-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}
.endpoint-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid transparent;
  transition: all 0.2s;
}
.endpoint-item:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--border);
}
.endpoint-rank {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  background: rgba(212, 175, 55, 0.12);
  color: var(--accent-light);
  flex-shrink: 0;
}
.endpoint-info {
  flex: 1;
  min-width: 0;
}
.endpoint-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.endpoint-method {
  color: var(--accent-light);
  font-weight: 600;
  font-size: 11px;
  background: rgba(212, 175, 55, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
}
.endpoint-path {
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.endpoint-meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 3px;
}
.endpoint-count {
  font-size: 18px;
  font-weight: 700;
  color: var(--accent-light);
  min-width: 48px;
  text-align: right;
}

.errors-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  max-height: 360px;
  overflow-y: auto;
}
.error-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  border-radius: var(--radius-sm);
  background: rgba(239, 68, 68, 0.05);
  border: 1px solid rgba(239, 68, 68, 0.1);
}
.error-status {
  width: 40px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  background: rgba(239, 68, 68, 0.15);
  color: var(--danger);
  flex-shrink: 0;
}
.error-info {
  flex: 1;
  min-width: 0;
}
.error-title {
  font-size: 13px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.error-meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.empty-state {
  text-align: center;
  padding: var(--spacing-xl) 0;
  color: var(--text-dim);
  font-size: 13px;
}

.loading-dots { display: inline-flex; gap: 5px; align-items: center; }
.loading-dots span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: dotPulse 1.4s infinite ease-in-out both; }
.loading-dots span:nth-child(1) { animation-delay: -0.32s; }
.loading-dots span:nth-child(2) { animation-delay: -0.16s; }
@keyframes dotPulse {
  0%, 80%, 100% { transform: scale(0.5); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

@media (max-width: 900px) {
  .summary-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 768px) {
  .observability { padding: var(--spacing-md); gap: var(--spacing-md); }
  .page-header { flex-direction: column; align-items: flex-start; gap: var(--spacing-md); }
  .summary-grid { grid-template-columns: repeat(2, 1fr); }
  .section-header { flex-direction: column; align-items: flex-start; gap: var(--spacing-sm); }
  .endpoint-item { flex-wrap: wrap; }
}

@media (max-width: 480px) {
  .summary-grid { grid-template-columns: 1fr; }
}
</style>
