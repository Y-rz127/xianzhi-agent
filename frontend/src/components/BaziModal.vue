<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="close">
      <div class="modal-content" :style="{ animationDelay: '0s' }">
        <div class="modal-header">
          <div class="modal-title">命盘详情</div>
          <button class="modal-close" @click="close" aria-label="关闭">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="bazi-section">
            <div class="section-title">四柱命盘</div>
            <div class="pillars-grid">
              <div v-for="p in pillars" :key="p.name" :class="['pillar-card', p.name === '日柱' ? 'day-master' : '']">
                <div class="pillar-name">{{ p.name }}</div>
                <div class="pillar-gan">{{ p.ganzhi[0] }}</div>
                <div class="pillar-zhi">{{ p.ganzhi[1] }}</div>
                <div class="pillar-nayin">{{ p.nayin }}</div>
              </div>
            </div>
          </div>
          <div class="wuxing-section">
            <div class="section-title">五行分布</div>
            <div class="wuxing-grid">
              <div v-for="w in wuxing" :key="w.name" class="wuxing-item">
                <div class="wuxing-bar-container">
                  <div class="wuxing-bar" :style="{ height: (w.count / maxWuxing * 100) + '%', background: w.color }"></div>
                </div>
                <div class="wuxing-label" :style="{ color: w.color }">{{ w.name }}</div>
                <div class="wuxing-count">{{ w.count }}</div>
              </div>
            </div>
          </div>
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
          <div v-if="shensha.length" class="shensha-section">
            <div class="section-title">神煞</div>
            <div class="shensha-list">
              <div v-for="(s, i) in shensha" :key="i" class="shensha-item">
                <div class="shensha-name">{{ s.name }}</div>
                <div class="shensha-desc">{{ s.description }}</div>
              </div>
            </div>
          </div>
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
          <button class="btn btn-primary" @click="close"  aria-label="关闭">关闭</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from "vue"
import type { Pillar, WuxingItem, DayunItem, ShenshaItem } from "../api"
import { downloadReport, generateFullReport, downloadFullReportPDF } from "../api"
import MarkdownRender from "./MarkdownRender.vue"

const props = defineProps<{
  visible: boolean
  pillars: Pillar[]
  wuxing: WuxingItem[]
  dayun: DayunItem[]
  shensha: ShenshaItem[]
  birthTime?: string
  gender?: string
}>()

const emit = defineEmits<{ close: [] }>()

const maxWuxing = computed(() => Math.max(...props.wuxing.map(w => w.count), 1))
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
  animation: slideUp 0.3s ease-out; }
@keyframes slideUp { from { opacity: 0; transform: translateY(20px) scale(0.96); } to { opacity: 1; transform: translateY(0) scale(1); } }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px;
  border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.02); }
.modal-title { font-size: 16px; color: var(--accent-light); letter-spacing: 3px; font-weight: 600; }
.modal-close { padding: 6px; background: transparent; border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-dim); cursor: pointer; transition: all 0.2s; }
.modal-close:hover { border-color: var(--danger); color: var(--danger); }
.modal-body { padding: 20px; overflow-y: auto; max-height: 65vh; }
.section-title { font-size: 13px; color: var(--accent); letter-spacing: 3px; margin-bottom: 14px;
  padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.pillars-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
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
.wuxing-grid { display: flex; justify-content: space-around; align-items: flex-end; height: 120px; margin-bottom: 24px; }
.wuxing-item { display: flex; flex-direction: column; align-items: center; gap: 6px; width: 16%; }
.wuxing-bar-container { width: 100%; height: 80px; background: rgba(255,255,255,0.03); border-radius: 6px 6px 0 0;
  display: flex; align-items: flex-end; overflow: hidden; }
.wuxing-bar { width: 100%; border-radius: 6px 6px 0 0; transition: height 0.6s cubic-bezier(0.34, 1.56, 0.64, 1); min-height: 4px; }
.wuxing-label { font-size: 14px; font-weight: bold; }
.wuxing-count { font-size: 12px; color: var(--text-dim); }
.dayun-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 24px; }
.dayun-card { background: rgba(255,255,255,0.03); border-radius: 10px; padding: 10px; text-align: center;
  border: 1px solid var(--border); }
.dayun-year { font-size: 16px; font-weight: bold; color: var(--accent-light); margin-bottom: 4px; }
.dayun-range { font-size: 10px; color: var(--text-dim); margin-bottom: 2px; }
.dayun-age { font-size: 10px; color: rgba(138,155,176,0.6); }
.shensha-list { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.shensha-item { background: rgba(255,255,255,0.03); border-radius: 10px; padding: 10px; border: 1px solid var(--border); }
.shensha-name { font-size: 12px; color: var(--accent); font-weight: 600; margin-bottom: 4px; }
.shensha-desc { font-size: 11px; color: var(--text-dim); line-height: 1.5; }
.report-section { margin-top: 24px; }
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
</style>
