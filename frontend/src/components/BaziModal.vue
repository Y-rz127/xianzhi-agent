<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="close">
      <div class="modal-content" :style="{ animationDelay: '0s' }">
        <div class="modal-header">
          <div class="modal-title">命盘详情</div>
          <div class="header-actions">
            <button class="modal-action" @click="copyChartText" :aria-label="copyLabel" :title="copyLabel">
              <svg v-if="!copied" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
              {{ copyLabel }}
            </button>
            <button class="modal-close" @click="close" aria-label="关闭">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>
        <div class="tab-bar" role="tablist" aria-label="命盘分节" v-if="birthTime">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="tab-btn"
            :class="{ active: activeTab === tab.key }"
            role="tab"
            :aria-selected="activeTab === tab.key"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>
        <div v-if="!birthTime" class="modal-body empty-state-modal">
          <div class="empty-chart">
            <div class="empty-chart-icon">易</div>
            <h3>还没知道你的命盘</h3>
            <p>请先提供你的出生时间（年月日时）和性别，我才能为你排盘分析。</p>
            <div class="empty-chart-tip">例如：男 2004-06-22 08:00</div>
          </div>
        </div>
        <div v-else class="modal-body">
          <div v-if="activeTab === 'pillars'" class="tab-panel" role="tabpanel">
            <div class="section-title-row">
              <span class="section-title">四柱命盘</span>
              <span v-if="props.mingGong || props.shenGong" class="gong-info">
                <template v-if="props.mingGong">命宫 {{ props.mingGong }}</template>
                <template v-if="props.mingGong && props.shenGong"> · </template>
                <template v-if="props.shenGong">身宫 {{ props.shenGong }}</template>
              </span>
            </div>
            <div class="pillars-grid">
              <div v-for="p in pillars" :key="p.name" :class="['pillar-card', p.name === '日柱' ? 'day-master' : '']">
                <div class="pillar-name">{{ p.name }}</div>
                <div class="pillar-gan">{{ p.ganzhi[0] }}</div>
                <div class="pillar-zhi">{{ p.ganzhi[1] }}</div>
                <div class="pillar-nayin">{{ p.nayin }}</div>
                <!-- 该柱神煞竖排（点击查看寓意） -->
                <div v-if="shenshaByPillar[p.name]?.length" class="pillar-shensha">
                  <span
                    v-for="(s, i) in shenshaByPillar[p.name]"
                    :key="i"
                    class="ps-tag"
                    :class="['ps-' + s._cat, { 'ps-active': activeShensha === s }]"
                    @click.stop="toggleShensha(s)"
                  >{{ s.name }}</span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="activeTab === 'wuxing'" class="tab-panel" role="tabpanel">
            <div class="section-title">五行分布</div>
            <div class="wuxing-grid" :class="{ animate: wuxingAnimated }">
              <div v-for="(w, i) in wuxing" :key="w.name" class="wuxing-item" :style="{ '--stagger': i }">
                <div class="wuxing-bar-container">
                  <div
                    class="wuxing-bar"
                    :style="{
                      height: wuxingAnimated ? (w.count / maxWuxing * 100) + '%' : '0%',
                      transitionDelay: `calc(var(--stagger) * 60ms)`,
                      background: w.color
                    }"
                  ></div>
                </div>
                <div class="wuxing-label" :style="{ color: w.color }">{{ w.name }}</div>
                <div class="wuxing-count">{{ w.count }}</div>
              </div>
            </div>
          </div>

          <div v-if="activeTab === 'dayun'" class="tab-panel" role="tabpanel">
            <div v-if="dayun.length" class="dayun-section">
              <div class="section-title">大运</div>
              <div class="dayun-grid">
                <div v-for="(d, i) in dayun" :key="i" class="dayun-card">
                  <div class="dayun-year">{{ d.year }}</div>
                  <div class="dayun-range">{{ d.startYear }}-{{ d.startYear + 9 }}</div>
                  <div class="dayun-age">{{ d.startAge }}-{{ d.startAge + 9 }}岁</div>
                </div>
              </div>
            </div>
            <div v-if="hasConsultationContext" class="consult-section">
              <div class="section-title">咨询依据</div>
              <div class="consult-grid">
                <div v-if="currentDayun" class="consult-card">
                  <div class="consult-label">当前大运</div>
                  <div class="consult-main">{{ currentDayun.ganzhi || currentDayun.year }}</div>
                  <div class="consult-sub">{{ currentDayun.startYear }}-{{ currentDayun.endYear || currentDayun.startYear + 9 }} · {{ currentDayun.startAge }}-{{ currentDayun.endAge || currentDayun.startAge + 9 }}岁</div>
                </div>
                <div v-if="startYun" class="consult-card">
                  <div class="consult-label">起运口径</div>
                  <div class="consult-main">{{ startYun.direction || '-' }}</div>
                  <div class="consult-sub">{{ startYun.startDate || '-' }}</div>
                </div>
                <div v-if="analysis?.strength" class="consult-card">
                  <div class="consult-label">日主强弱</div>
                  <div class="consult-main">{{ analysis.day_master }}{{ analysis.strength }}</div>
                  <div class="consult-sub">置信度 {{ analysis.confidence || '-' }}</div>
                </div>
                <div v-if="analysis?.season" class="consult-card wide">
                  <div class="consult-label">调候提示</div>
                  <div class="consult-text">{{ analysis.adjustment }}</div>
                </div>
              </div>
              <div v-if="analysis?.patternHint" class="consult-note">{{ analysis.patternHint }}</div>
              <div v-if="relationText" class="consult-note">{{ relationText }}</div>
              <div v-if="warnings.length" class="warning-list">
                <div v-for="w in warnings" :key="w" class="warning-item">{{ w }}</div>
              </div>
            </div>
          </div>

          <div v-if="activeTab === 'liunian'" class="tab-panel" role="tabpanel">
            <div class="section-title">流年</div>
            <div v-if="liunian.length" class="liunian-strip">
              <div v-for="l in liunian" :key="l.year" class="liunian-pill">
                <span>{{ l.year }}</span><b>{{ l.ganzhi }}</b><em>{{ l.dayun || '-' }}</em>
              </div>
            </div>
            <div v-else class="tab-empty">暂无流年数据</div>
          </div>

          <div v-if="activeTab === 'report'" class="tab-panel" role="tabpanel">
            <div class="report-section">
              <div class="section-title">完整命理报告</div>
              <div v-if="reportLoading" class="report-loading">
                <span class="loading-dots"><span></span><span></span><span></span></span>
                正在由先知生成报告...
              </div>
              <div v-else-if="reportContent" class="report-content">
                <MarkdownRender :content="reportContent" />
              </div>
              <div v-else class="report-placeholder">点击下方按钮生成 AI 分节命理报告</div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="handleDownload" aria-label="下载PDF报告">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M12 18v-6"/><path d="M9 15l3 3 3-3"/></svg>
            下载 PDF 报告
          </button>
          <button class="btn" @click="generateReport" :disabled="reportLoading || !birthTime || !gender" aria-label="生成完整命理报告">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
            {{ reportLoading ? "生成中..." : "生成完整命理报告" }}
          </button>
          <button v-if="reportContent" class="btn" @click="downloadMarkdown" aria-label="导出Markdown">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M12 18v-6"/><path d="M9 15l3 3 3-3"/></svg>
            导出 Markdown
          </button>
          <button v-if="reportContent" class="btn" @click="downloadFullPDF" aria-label="导出完整PDF">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M12 18v-6"/><path d="M9 15l3 3 3-3"/></svg>
            导出完整 PDF
          </button>
          <button class="btn btn-primary" @click="close" aria-label="关闭">关闭</button>
        </div>
        <!-- 神煞寓意浮层（点击 ps-tag 触发） -->
        <div v-if="activeShensha" class="ps-popover" @click="activeShensha = null">
          <div class="ps-popover-card" @click.stop>
            <div class="ps-popover-title" :class="'ps-' + activeShensha._cat">{{ activeShensha.name }}</div>
            <div class="ps-popover-desc">{{ activeShensha.description }}</div>
            <button class="ps-popover-close" @click="activeShensha = null" aria-label="关闭">关闭</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from "vue"
import type { Pillar, WuxingItem, DayunItem, ShenshaItem, LiuNianItem, ChartAnalysis } from "../api"
import { downloadReport, generateFullReport, downloadFullReportPDF } from "../api"
import MarkdownRender from "./MarkdownRender.vue"

type TabKey = 'pillars' | 'wuxing' | 'dayun' | 'liunian' | 'report'

const props = defineProps<{
  visible: boolean
  pillars: Pillar[]
  wuxing: WuxingItem[]
  dayun: DayunItem[]
  liunian?: LiuNianItem[]
  shensha: ShenshaItem[]
  analysis?: ChartAnalysis
  startYun?: Record<string, any>
  warnings?: string[]
  birthTime?: string
  gender?: string
  chartText?: string
  mingGong?: string
  shenGong?: string
}>()

const emit = defineEmits<{ close: [] }>()

const tabs = [
  { key: 'pillars' as TabKey, label: '四柱' },
  { key: 'wuxing' as TabKey, label: '五行' },
  { key: 'dayun' as TabKey, label: '大运' },
  { key: 'liunian' as TabKey, label: '流年' },
  { key: 'report' as TabKey, label: '报告' },
]
const activeTab = ref<TabKey>('pillars')
const wuxingAnimated = ref(false)

// 神煞寓意浮层状态：点击 ps-tag 触发显示/隐藏
type TaggedShensha = ShenshaItem & { _cat: string }
const activeShensha = ref<TaggedShensha | null>(null)
const toggleShensha = (s: TaggedShensha) => {
  activeShensha.value = activeShensha.value === s ? null : s
}

const maxWuxing = computed(() => Math.max(...props.wuxing.map(w => w.count), 1))
const liunian = computed(() => props.liunian || [])
const warnings = computed(() => props.warnings || [])
const currentYear = new Date().getFullYear()
const currentDayun = computed(() =>
  props.dayun.find(d => d.startYear <= currentYear && (d.endYear || d.startYear + 9) >= currentYear) || props.dayun[0]
)
const relationText = computed(() => {
  const a = props.analysis
  if (!a) return ""
  const parts = [
    ...(a.combinations || []).map(v => `合：${v}`),
    ...(a.clashes || []).map(v => `冲：${v}`),
    ...(a.harms || []).map(v => `害：${v}`),
    ...(a.punishments || []).map(v => `刑：${v}`),
  ]
  return parts.join("；")
})
const hasConsultationContext = computed(() =>
  !!props.analysis || !!props.startYun || liunian.value.length > 0 || warnings.value.length > 0
)

function triggerWuxingAnimation() {
  wuxingAnimated.value = false
  nextTick(() => { wuxingAnimated.value = true })
}

watch(() => props.visible, (v) => {
  if (v) {
    activeTab.value = 'pillars'
  } else {
    activeShensha.value = null
  }
})

watch(activeTab, (tab) => {
  if (tab === 'wuxing') triggerWuxingAnimation()
})

function classifyShensha(item: ShenshaItem): string {
  const text = `${item.name} ${item.description}`
  if (/桃花|红鸾|天喜|沐浴|咸池|红艳|情缘|感情|姻缘|婚/.test(text)) return 'love'
  if (/羊刃|劫煞|亡神|灾煞|元辰|空亡|十恶大败|阴差阳错|天罗地网|飞刃|勾绞|孤辰|寡宿|丧门|吊客|白虎|血刃|截路|悬针|冲|刑|害|破/.test(text)) return 'bad'
  if (/驿马|禄神|将星|国印|金舆|官|财|事业|职场/.test(text)) return 'career'
  if (/天乙|太极|文昌|福星|月德|天德|学堂|词馆|贵人|三奇|魁罡/.test(text)) return 'good'
  return 'other'
}

const shenshaByPillar = computed(() => {
  const pillarNames = ['年柱', '月柱', '日柱', '时柱']
  const groups: Record<string, (ShenshaItem & { _cat: string })[]> = {}
  // 每柱独立去重：同一柱内同名神煞只保留一条
  const seenByPillar: Record<string, Set<string>> = {}
  for (const s of props.shensha) {
    // 从 description 中提取柱名（后端格式："{pillar_name}：{desc}"）
    let pillarName = ''
    for (const pn of pillarNames) {
      if (s.description.includes(pn)) {
        pillarName = pn
        break
      }
    }
    if (!pillarName) {
      // 兜底：理论上所有神煞都应有柱名
      pillarName = '日柱'
    }
    const seen = seenByPillar[pillarName] ??= new Set<string>()
    if (seen.has(s.name)) continue
    seen.add(s.name)
    const tagged = { ...s, _cat: classifyShensha(s) }
    ;(groups[pillarName] ||= []).push(tagged)
  }
  return groups
})

const formattedChartText = computed(() => {
  if (props.chartText) return props.chartText
  const lines: string[] = ['命盘详情']
  if (props.pillars.length) {
    lines.push('')
    lines.push('【四柱命盘】')
    props.pillars.forEach(p => lines.push(`${p.name}: ${p.ganzhi} (${p.nayin})`))
  }
  if (props.wuxing.length) {
    lines.push('')
    lines.push('【五行分布】')
    lines.push(props.wuxing.map(w => `${w.name}: ${w.count}`).join('、'))
  }
  if (props.dayun.length) {
    lines.push('')
    lines.push('【大运】')
    props.dayun.forEach(d => lines.push(`${d.startYear}-${d.startYear + 9}岁 ${d.year}`))
  }
  if (props.shensha.length) {
    lines.push('')
    lines.push('【神煞】')
    props.shensha.forEach(s => lines.push(`${s.name}: ${s.description}`))
  }
  return lines.join('\n')
})

const copied = ref(false)
const copyLabel = computed(() => copied.value ? '已复制' : '复制命盘')
let copyTimer: ReturnType<typeof setTimeout> | null = null

async function copyChartText() {
  const text = formattedChartText.value
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      fallbackCopy(text)
    }
    copied.value = true
  } catch {
    fallbackCopy(text)
    copied.value = true
  }
  if (copyTimer) clearTimeout(copyTimer)
  copyTimer = setTimeout(() => { copied.value = false }, 1600)
}

function fallbackCopy(text: string) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  document.execCommand('copy')
  document.body.removeChild(ta)
}

const close = () => emit("close")
const handleDownload = () => {
  if (props.birthTime && props.gender) downloadReport(props.birthTime, props.gender)
}

const reportContent = ref("")
const reportLoading = ref(false)

const generateReport = async () => {
  if (!props.birthTime || !props.gender || reportLoading.value) return
  reportLoading.value = true
  try {
    reportContent.value = await generateFullReport(props.birthTime, props.gender)
  } catch (e) {
    reportContent.value = "报告生成失败，请稍后重试。"
  } finally {
    reportLoading.value = false
  }
}

const downloadMarkdown = () => {
  if (!reportContent.value || !props.birthTime) return
  const blob = new Blob([reportContent.value], { type: "text/markdown;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `先知命理报告_${props.birthTime.replace(/[ :]/g, "_")}.md`
  a.click()
  URL.revokeObjectURL(url)
}

const downloadFullPDF = () => {
  if (props.birthTime && props.gender) downloadFullReportPDF(props.birthTime, props.gender)
}
</script>

<style scoped>
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.75); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; z-index: 1000; animation: fadeIn 0.2s ease; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.modal-content { width: 90%; max-width: 720px; max-height: 85vh; background: linear-gradient(135deg, rgba(18,26,42,0.98), rgba(12,18,32,0.98));
  border: 1px solid var(--border-bright); border-radius: var(--radius); overflow: hidden;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5), 0 0 40px rgba(212,175,55,0.1);
  animation: slideUp 0.3s ease-out; display: flex; flex-direction: column; }
@keyframes slideUp { from { opacity: 0; transform: translateY(20px) scale(0.96); } to { opacity: 1; transform: translateY(0) scale(1); } }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px;
  border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.02); }
.modal-title { font-size: 16px; color: var(--accent-light); letter-spacing: 3px; font-weight: 600; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.modal-action { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; background: transparent;
  border: 1px solid var(--border); border-radius: 6px; color: var(--text-dim); cursor: pointer; transition: all 0.2s;
  font-size: 12px; }
.modal-action:hover { border-color: var(--accent); color: var(--accent); }
.modal-close { padding: 6px; background: transparent; border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-dim); cursor: pointer; transition: all 0.2s; }
.modal-close:hover { border-color: var(--danger); color: var(--danger); }
.tab-bar { display: flex; gap: 4px; padding: 10px 20px 0; border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.02); overflow-x: auto; }
.tab-btn { flex: 1; min-width: 56px; padding: 8px 6px; background: transparent; border: none; border-bottom: 2px solid transparent;
  color: var(--text-dim); font-size: 13px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--accent-light); border-bottom-color: var(--accent); }
.modal-body { padding: 20px; overflow-y: auto; max-height: 55vh; }
.empty-state-modal { display: flex; align-items: center; justify-content: center; min-height: 200px; }
.empty-chart { text-align: center; padding: 20px; }
.empty-chart-icon {
  width: 56px; height: 56px; margin: 0 auto 14px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; color: var(--accent);
  border: 2px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
}
.empty-chart h3 { font-size: 16px; margin-bottom: 8px; color: var(--text); }
.empty-chart p { font-size: 13px; color: var(--text-dim); line-height: 1.6; margin-bottom: 12px; }
.empty-chart-tip {
  display: inline-block; padding: 6px 14px;
  font-size: 12px; color: var(--accent);
  border: 1px dashed var(--border); border-radius: 6px;
}
.tab-panel { animation: fadeIn 0.25s ease; }
.tab-empty { color: var(--text-dim); font-size: 13px; text-align: center; padding: 30px 20px; }
.section-title { font-size: 13px; color: var(--accent); letter-spacing: 3px; margin-bottom: 14px;
  padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.section-title-row { display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 14px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.gong-info { font-size: 11px; color: var(--text-dim); letter-spacing: normal; }
.pillars-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 10px; }
.pillar-card { background: rgba(255,255,255,0.03); border-radius: 12px; padding: 14px 8px; text-align: center;
  border: 1px solid var(--border); transition: all 0.25s; }
.pillar-card.day-master { background: linear-gradient(135deg, rgba(212,175,55,0.1), rgba(139,92,246,0.06));
  border-color: rgba(212,175,55,0.35); box-shadow: 0 0 16px rgba(212,175,55,0.1); }
.pillar-card:hover { transform: translateY(-2px); border-color: rgba(212,175,55,0.2); }
.pillar-name { font-size: 10px; color: var(--text-dim); margin-bottom: 8px; }
.pillar-gan { font-size: 26px; font-weight: bold; color: var(--text); margin-bottom: 2px; }
.pillar-card.day-master .pillar-gan { color: var(--accent-light); text-shadow: 0 0 10px rgba(212,175,55,0.4); }
.pillar-zhi { font-size: 20px; color: var(--text-dim); margin-bottom: 6px; }
.pillar-nayin { font-size: 10px; color: rgba(138,155,176,0.7); }
.wuxing-grid { display: flex; justify-content: space-around; align-items: flex-end; height: 140px; margin-bottom: 10px; }
.wuxing-item { display: flex; flex-direction: column; align-items: center; gap: 6px; width: 16%; }
.wuxing-bar-container { width: 100%; height: 90px; background: rgba(255,255,255,0.03); border-radius: 6px 6px 0 0;
  display: flex; align-items: flex-end; overflow: hidden; }
.wuxing-bar { width: 100%; border-radius: 6px 6px 0 0; min-height: 4px;
  transition: height 0.7s cubic-bezier(0.34, 1.56, 0.64, 1); }
.wuxing-label { font-size: 14px; font-weight: bold; }
.wuxing-count { font-size: 12px; color: var(--text-dim); }
.dayun-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 24px; }
.dayun-card { background: rgba(255,255,255,0.03); border-radius: 10px; padding: 10px; text-align: center;
  border: 1px solid var(--border); }
.dayun-year { font-size: 16px; font-weight: bold; color: var(--accent-light); margin-bottom: 4px; }
.dayun-range { font-size: 10px; color: var(--text-dim); margin-bottom: 2px; }
.dayun-age { font-size: 10px; color: rgba(138,155,176,0.6); }
.consult-section { margin-bottom: 10px; }
.consult-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 10px; }
.consult-card { background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 10px; padding: 10px; min-width: 0; }
.consult-card.wide { grid-column: span 3; }
.consult-label { font-size: 10px; color: var(--text-muted); margin-bottom: 4px; }
.consult-main { font-size: 15px; color: var(--accent-light); font-weight: 700; margin-bottom: 3px; }
.consult-sub,
.consult-text { font-size: 11px; color: var(--text-dim); line-height: 1.5; }
.consult-note { font-size: 12px; line-height: 1.6; color: var(--text-dim); background: rgba(212,175,55,0.05); border: 1px solid rgba(212,175,55,0.12); border-radius: 10px; padding: 9px 10px; margin-top: 8px; }
.liunian-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.liunian-pill { display: grid; grid-template-columns: auto auto 1fr; gap: 6px; align-items: center; padding: 8px 9px; border-radius: 9px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); font-size: 11px; color: var(--text-dim); }
.liunian-pill b { color: var(--text); font-size: 13px; }
.liunian-pill em { font-style: normal; color: var(--accent); text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.warning-list { margin-top: 10px; display: grid; gap: 6px; }
.warning-item { font-size: 11px; color: #d8bf7a; line-height: 1.5; padding: 8px 10px; border-radius: 9px; background: rgba(212,175,55,0.06); border: 1px solid rgba(212,175,55,0.12); }
/* ===== 每柱神煞竖排 ===== */
.pillar-shensha { display: flex; flex-wrap: wrap; gap: 4px; justify-content: center;
  margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.05); }
.ps-tag { font-size: 10px; padding: 2px 7px; border-radius: 5px; line-height: 1.6; cursor: pointer;
  transition: all 0.2s; white-space: nowrap; user-select: none; }
.ps-tag:hover { filter: brightness(1.2); }
.ps-active { outline: 1px solid currentColor; }
.ps-good { color: #4ade80; background: rgba(74,222,128,0.1); }
.ps-bad { color: #f87171; background: rgba(248,113,113,0.1); }
.ps-love { color: #f472b6; background: rgba(244,114,182,0.1); }
.ps-career { color: #60a5fa; background: rgba(96,165,250,0.1); }
.ps-other { color: #94a3b8; background: rgba(148,163,184,0.1); }
/* 神煞寓意浮层 */
.ps-popover { position: fixed; inset: 0; background: rgba(0,0,0,0.55); display: flex; align-items: center;
  justify-content: center; z-index: 1100; padding: 20px; box-sizing: border-box; cursor: pointer;
  animation: fadeIn 0.15s ease; }
.ps-popover-card { background: linear-gradient(135deg, rgba(28,36,56,0.98), rgba(18,24,40,0.98));
  border: 1px solid var(--border-bright); border-radius: 12px; padding: 16px 20px; max-width: 340px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.5); cursor: default; animation: slideUp 0.2s ease-out; }
.ps-popover-title { font-size: 15px; font-weight: 600; margin-bottom: 10px; letter-spacing: 1px; }
.ps-popover-desc { font-size: 13px; color: var(--text-dim); line-height: 1.7; margin-bottom: 12px; }
.ps-popover-close { display: inline-block; padding: 6px 14px; background: rgba(255,255,255,0.05);
  border: 1px solid var(--border); border-radius: 6px; color: var(--text-dim); font-size: 12px;
  cursor: pointer; transition: all 0.2s; }
.ps-popover-close:hover { border-color: var(--accent); color: var(--accent); }
.report-section { }
.report-loading { display: flex; align-items: center; gap: 10px; color: var(--accent); font-size: 13px; padding: 20px; }
.report-placeholder { color: var(--text-dim); font-size: 13px; text-align: center; padding: 20px; }
.report-content { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.loading-dots { display: inline-flex; gap: 4px; }
.loading-dots span { width: 6px; height: 6px; background: var(--accent); border-radius: 50%; animation: dot 1.4s infinite both; }
.loading-dots span:nth-child(1) { animation-delay: 0s; }
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot { 0%, 80%, 100% { transform: scale(0); opacity: 0.5; } 40% { transform: scale(1); opacity: 1; } }
.modal-footer { display: flex; justify-content: flex-end; gap: 10px; padding: 16px 20px;
  border-top: 1px solid var(--border); background: rgba(255,255,255,0.02); flex-wrap: wrap; }
.modal-footer .btn { display: inline-flex; align-items: center; gap: 6px; }

@media (max-width: 640px) {
  .pillars-grid { grid-template-columns: repeat(2, 1fr); }
  .dayun-grid { grid-template-columns: repeat(2, 1fr); }
  .consult-grid { grid-template-columns: repeat(2, 1fr); }
  .consult-card.wide { grid-column: span 2; }
  .liunian-strip { grid-template-columns: repeat(2, 1fr); }
  .modal-body { max-height: 50vh; }
}
</style>
