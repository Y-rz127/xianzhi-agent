<template>
  <view v-if="visible" class="modal-overlay" @tap="close">
    <view class="modal-content" @tap.stop>
      <!-- 头部 -->
      <view class="modal-header">
        <text class="modal-title display-font">命盘详情</text>
        <text class="modal-close" @tap="close">✕</text>
      </view>

      <!-- 内容区 -->
      <scroll-view class="modal-body" scroll-y>
        <!-- 四柱 -->
        <view class="section" v-if="pillars.length">
          <view class="section-title-row">
            <text class="section-title">四柱命盘</text>
            <text v-if="mingGong || shenGong" class="gong-info">
              <template v-if="mingGong">命宫 {{ mingGong }}</template>
              <template v-if="mingGong && shenGong"> · </template>
              <template v-if="shenGong">身宫 {{ shenGong }}</template>
            </text>
          </view>
          <view class="pillars-grid">
            <view
              v-for="p in pillars"
              :key="p.name"
              :class="['pillar-card', p.name === '日柱' && 'day-master']"
            >
              <text class="pillar-name">{{ p.name }}</text>
              <text class="pillar-gan">{{ p.ganzhi[0] }}</text>
              <text class="pillar-zhi">{{ p.ganzhi[1] }}</text>
              <text class="pillar-nayin">{{ p.nayin }}</text>
              <!-- 该柱神煞竖排（点击查看寓意） -->
              <view v-if="shenshaByPillar[p.name]?.length" class="pillar-shensha">
                <text
                  v-for="(s, i) in shenshaByPillar[p.name]"
                  :key="i"
                  class="ps-tag"
                  :class="'ps-' + s._cat"
                  @tap="showShenshaDesc(s)"
                >{{ s.name }}</text>
              </view>
            </view>
          </view>
        </view>

        <!-- 五行 -->
        <view class="section" v-if="wuxing.length">
          <text class="section-title">五行分布</text>
          <view class="wuxing-grid">
            <view v-for="w in wuxing" :key="w.name" class="wuxing-item">
              <view class="wuxing-bar-container">
                <view
                  class="wuxing-bar"
                  :style="{ height: (w.count / maxWuxing * 100) + '%', background: w.color }"
                ></view>
              </view>
              <text class="wuxing-label" :style="{ color: w.color }">{{ w.name }}</text>
              <text class="wuxing-count">{{ w.count }}</text>
            </view>
          </view>
        </view>

        <!-- 大运 -->
        <view class="section" v-if="dayun.length">
          <text class="section-title">大运</text>
          <view class="dayun-grid">
            <view v-for="(d, i) in dayun" :key="i" class="dayun-card">
              <text class="dayun-year">{{ d.year }}</text>
              <text class="dayun-range">{{ d.startYear }}-{{ d.startYear + 9 }}</text>
              <text class="dayun-age">{{ d.startAge }}-{{ d.startAge + 9 }}岁</text>
            </view>
          </view>
        </view>

        <view class="section" v-if="hasConsultationContext">
          <text class="section-title">咨询依据</text>
          <view class="consult-grid">
            <view v-if="currentDayun" class="consult-card">
              <text class="consult-label">当前大运</text>
              <text class="consult-main">{{ currentDayun.ganzhi || currentDayun.year }}</text>
              <text class="consult-sub">{{ currentDayun.startYear }}-{{ currentDayun.endYear || currentDayun.startYear + 9 }}</text>
            </view>
            <view v-if="startYun" class="consult-card">
              <text class="consult-label">起运口径</text>
              <text class="consult-main">{{ startYun.direction || '-' }}</text>
              <text class="consult-sub">{{ startYun.startDate || '-' }}</text>
            </view>
            <view v-if="analysis?.strength" class="consult-card">
              <text class="consult-label">日主强弱</text>
              <text class="consult-main">{{ analysis.day_master }}{{ analysis.strength }}</text>
              <text class="consult-sub">置信度 {{ analysis.confidence || '-' }}</text>
            </view>
          </view>
          <view v-if="analysis?.adjustment" class="consult-note">
            <text>{{ analysis.adjustment }}</text>
          </view>
          <view v-if="analysis?.patternHint" class="consult-note">
            <text>{{ analysis.patternHint }}</text>
          </view>
          <view v-if="relationText" class="consult-note">
            <text>{{ relationText }}</text>
          </view>
          <view v-if="liunian.length" class="liunian-strip">
            <view v-for="l in liunian.slice(0, 6)" :key="l.year" class="liunian-pill">
              <text class="ln-year">{{ l.year }}</text>
              <text class="ln-gz">{{ l.ganzhi }}</text>
              <text class="ln-dy">{{ l.dayun || '-' }}</text>
            </view>
          </view>
          <view v-if="warnings.length" class="warning-list">
            <text v-for="w in warnings" :key="w" class="warning-item">{{ w }}</text>
          </view>
        </view>

        <!-- AI 报告 -->
        <view class="section">
          <text class="section-title">AI 命理报告</text>
          <view v-if="reportLoading" class="report-loading">
            <text>正在由先知生成报告…</text>
          </view>
          <view v-else-if="reportContent" class="report-content">
            <MarkdownRender :content="reportContent" />
          </view>
          <view v-else class="report-placeholder">
            <text>点击下方按钮生成 AI 分节命理报告</text>
          </view>
        </view>
      </scroll-view>

      <!-- 底部操作栏 -->
      <view class="modal-footer">
        <text class="btn" @tap="handleDownloadPdf">下载 PDF</text>
        <text
          :class="['btn', 'btn-primary', reportLoading && 'disabled']"
          @tap="generateReport"
        >{{ reportLoading ? '生成中…' : '生成完整报告' }}</text>
        <text v-if="reportContent" class="btn" @tap="downloadFullPdf">导出完整 PDF</text>
        <text class="btn" @tap="close">关闭</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Pillar, WuxingItem, DayunItem, ShenshaItem, LiuNianItem, ChartAnalysis } from '@/api'
import { generateFullReport, downloadReport, downloadFullReportPdf } from '@/api'
import MarkdownRender from '@/components/MarkdownRender/MarkdownRender.vue'

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
  mingGong?: string
  shenGong?: string
}>()
const emit = defineEmits<{ close: [] }>()

const reportContent = ref('')
const reportLoading = ref(false)

const maxWuxing = computed(() => Math.max(...props.wuxing.map((w) => w.count), 1))
const liunian = computed(() => props.liunian || [])
const warnings = computed(() => props.warnings || [])
const currentYear = new Date().getFullYear()
const currentDayun = computed(() =>
  props.dayun.find((d) => d.startYear <= currentYear && (d.endYear || d.startYear + 9) >= currentYear) || props.dayun[0]
)
const relationText = computed(() => {
  const a = props.analysis
  if (!a) return ''
  const parts = [
    ...(a.combinations || []).map((v) => `合：${v}`),
    ...(a.clashes || []).map((v) => `冲：${v}`),
    ...(a.harms || []).map((v) => `害：${v}`),
    ...(a.punishments || []).map((v) => `刑：${v}`),
  ]
  return parts.join('；')
})
const hasConsultationContext = computed(() =>
  !!props.analysis || !!props.startYun || liunian.value.length > 0 || warnings.value.length > 0
)

function classifyShensha(item: ShenshaItem): string {
  const text = `${item.name} ${item.description}`
  if (/桃花|红鸾|天喜|沐浴|咸池|红艳|情缘|感情|姻缘|婚/.test(text)) return 'love'
  if (/羊刃|劫煞|亡神|灾煞|元辰|空亡|十恶大败|阴差阳错|天罗地网|飞刃|勾绞|孤辰|寡宿|丧门|吊客|白虎|血刃|截路|悬针|冲|刑|害|破/.test(text)) return 'bad'
  if (/驿马|禄神|将星|国印|金舆|官|财|事业|职场/.test(text)) return 'career'
  if (/天乙|太极|文昌|福星|月德|天德|学堂|词馆|贵人|三奇|魁罡/.test(text)) return 'good'
  return 'other'
}

/** 按柱子归属分组神煞 */
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
    if (!pillarName) pillarName = '日柱'
    const seen = seenByPillar[pillarName] ??= new Set<string>()
    if (seen.has(s.name)) continue
    seen.add(s.name)
    const tagged = { ...s, _cat: classifyShensha(s) }
    ;(groups[pillarName] ||= []).push(tagged)
  }
  return groups
})

function close() {
  emit('close')
}

/** 点击神煞标签查看寓意（uni 原生弹窗） */
function showShenshaDesc(s: ShenshaItem & { _cat: string }) {
  uni.showModal({
    title: s.name,
    content: s.description,
    showCancel: false,
    confirmText: '知道了',
  })
}

function handleDownloadPdf() {
  if (!props.birthTime || !props.gender) {
    uni.showToast({ title: '缺少出生信息', icon: 'none' })
    return
  }
  downloadReport(props.birthTime, props.gender)
}

function downloadFullPdf() {
  if (!props.birthTime || !props.gender) return
  downloadFullReportPdf(props.birthTime, props.gender)
}

async function generateReport() {
  if (!props.birthTime || !props.gender || reportLoading.value) return
  reportLoading.value = true
  reportContent.value = ''
  try {
    const res = await generateFullReport(props.birthTime, props.gender)
    reportContent.value = res.content || ''
  } catch (e: any) {
    reportContent.value = `报告生成失败：${e.message || '请稍后重试'}`
  } finally {
    reportLoading.value = false
  }
}
</script>

<style lang="scss" scoped>
/* === 水墨风格：宣纸白底 + 墨黑文字 + 朱砂点缀 === */
.display-font {
  font-family: $font-family-display;
}

.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(26, 26, 26, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-content {
  width: 92%;
  max-height: 85vh;
  background: $color-paper;
  border: 1rpx solid $color-border;
  border-radius: 24rpx;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: $shadow-elevated;
  box-sizing: border-box;
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 28rpx 32rpx;
  border-bottom: 1rpx solid $color-border;
  background: $color-paper-warm;
}
.modal-title {
  font-size: 32rpx;
  font-weight: 600;
  color: $color-ink;
  letter-spacing: 6rpx;
}
.modal-close {
  font-size: 36rpx;
  color: $color-ink-light;
  padding: 8rpx 16rpx;
  line-height: 1;
}
.modal-body {
  padding: 28rpx 32rpx;
  max-height: 65vh;
  box-sizing: border-box;
  overflow-x: hidden;
  width: 100%;
  background: $color-paper;
}

.section {
  margin-bottom: 32rpx;
}
.section-title-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 20rpx;
  padding-bottom: 12rpx;
  border-bottom: 1rpx solid $color-border;
}
.gong-info {
  font-size: 20rpx;
  color: $color-ink-light;
}
.section-title {
  display: block;
  font-size: 26rpx;
  color: $color-ink;
  letter-spacing: 6rpx;
  font-weight: 600;
  margin-bottom: 20rpx;
  padding-bottom: 12rpx;
  border-bottom: 1rpx solid $color-border;
  position: relative;
}
/* 标题左侧朱砂竖线 */
.section-title::before {
  content: '';
  position: absolute;
  left: 0;
  bottom: 12rpx;
  width: 6rpx;
  height: 24rpx;
  background: $color-vermilion;
  border-radius: 3rpx;
}

/* 四柱 */
.pillars-grid {
  display: flex;
  gap: 8rpx;
  box-sizing: border-box;
}
.pillar-card {
  flex: 1;
  min-width: 0;
  background: $color-bg-card;
  border-radius: 12rpx;
  padding: 20rpx 8rpx;
  text-align: center;
  border: 1rpx solid $color-border;
  box-sizing: border-box;
}
.pillar-card.day-master {
  background: $color-paper-warm;
  border-color: $color-vermilion;
  border-width: 2rpx;
  box-shadow: 0 2rpx 8rpx rgba(184, 72, 60, 0.12);
}
.pillar-name {
  display: block;
  font-size: 20rpx;
  color: $color-ink-light;
  margin-bottom: 12rpx;
  letter-spacing: 2rpx;
}
.pillar-gan {
  display: block;
  font-size: 40rpx;
  font-weight: bold;
  color: $color-ink;
  font-family: $font-family-display;
  letter-spacing: 4rpx;
  margin-bottom: 4rpx;
}
.pillar-card.day-master .pillar-gan { color: $color-vermilion; }
.pillar-zhi {
  display: block;
  font-size: 32rpx;
  color: $color-ink;
  font-family: $font-family-display;
  margin-bottom: 8rpx;
  letter-spacing: 4rpx;
}
.pillar-card.day-master .pillar-zhi { color: $color-vermilion; }
.pillar-nayin {
  display: block;
  font-size: 20rpx;
  color: $color-ink-lighter;
}

/* 五行 */
.wuxing-grid {
  display: flex;
  justify-content: space-around;
  align-items: flex-end;
  height: 220rpx;
}
.wuxing-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 18%;
}
.wuxing-bar-container {
  width: 100%;
  height: 140rpx;
  display: flex;
  align-items: flex-end;
  background: $color-paper-warm;
  border-radius: 8rpx 8rpx 0 0;
  overflow: hidden;
}
.wuxing-bar {
  width: 100%;
  border-radius: 8rpx 8rpx 0 0;
  min-height: 6rpx;
}
.wuxing-label {
  font-size: 26rpx;
  font-weight: bold;
  margin-top: 8rpx;
}
.wuxing-count {
  font-size: 22rpx;
  color: $color-ink-light;
}

/* 大运 */
.dayun-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  box-sizing: border-box;
}
.dayun-card {
  width: calc(25% - 9rpx);
  background: $color-bg-card;
  border-radius: 12rpx;
  padding: 16rpx 8rpx;
  text-align: center;
  border: 1rpx solid $color-border;
  box-sizing: border-box;
  min-width: 0;
}
.dayun-year {
  display: block;
  font-size: 30rpx;
  font-weight: bold;
  color: $color-ink;
  font-family: $font-family-display;
  margin-bottom: 6rpx;
  letter-spacing: 2rpx;
}
.dayun-range {
  display: block;
  font-size: 20rpx;
  color: $color-ink-light;
  margin-bottom: 2rpx;
}
.dayun-age {
  display: block;
  font-size: 20rpx;
  color: $color-ink-lighter;
}

.consult-grid {
  display: flex;
  gap: 12rpx;
  box-sizing: border-box;
}
.consult-card {
  flex: 1;
  min-width: 0;
  background: $color-bg-card;
  border-radius: 12rpx;
  padding: 16rpx 12rpx;
  border: 1rpx solid $color-border;
  box-sizing: border-box;
}
.consult-label {
  display: block;
  font-size: 20rpx;
  color: $color-ink-light;
  margin-bottom: 6rpx;
}
.consult-main {
  display: block;
  font-size: 28rpx;
  color: $color-vermilion;
  font-weight: 700;
  font-family: $font-family-display;
  margin-bottom: 4rpx;
}
.consult-sub {
  display: block;
  font-size: 20rpx;
  color: $color-ink-light;
}
.consult-note {
  margin-top: 12rpx;
  padding: 14rpx 16rpx;
  background: $color-paper-warm;
  border: 1rpx solid $color-border;
  border-left: 4rpx solid $color-vermilion;
  border-radius: 8rpx;
  color: $color-ink;
  font-size: 22rpx;
  line-height: 1.55;
}
.liunian-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10rpx;
  margin-top: 12rpx;
  box-sizing: border-box;
}
.liunian-pill {
  width: calc(33.33% - 7rpx);
  padding: 12rpx 10rpx;
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: 10rpx;
  box-sizing: border-box;
  min-width: 0;
}
.ln-year,
.ln-gz,
.ln-dy {
  display: block;
  text-align: center;
}
.ln-year { font-size: 20rpx; color: $color-ink-light; }
.ln-gz { font-size: 26rpx; color: $color-ink; font-family: $font-family-display; font-weight: 700; margin: 4rpx 0; }
.ln-dy { font-size: 20rpx; color: $color-ink-light; }
.warning-list {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  margin-top: 12rpx;
}
.warning-item {
  padding: 12rpx 14rpx;
  background: $color-paper-warm;
  border: 1rpx solid $color-border;
  border-left: 4rpx solid $state-warning;
  border-radius: 8rpx;
  color: $color-ink;
  font-size: 22rpx;
  line-height: 1.5;
}

/* 每柱神煞竖排 */
.pillar-shensha {
  display: flex;
  flex-wrap: wrap;
  gap: 6rpx;
  justify-content: center;
  margin-top: 12rpx;
  padding-top: 10rpx;
  border-top: 1rpx solid $color-border;
}
.ps-tag {
  font-size: 18rpx;
  padding: 3rpx 12rpx;
  border-radius: 8rpx;
  line-height: 1.6;
  /* 点击查看寓意反馈 */
  opacity: 0.85;
}
.ps-tag:active {
  opacity: 1;
  transform: scale(0.96);
}
.ps-good { color: #38a169; background: rgba(56,161,105,0.1); }
.ps-bad { color: #c53030; background: rgba(197,48,48,0.1); }
.ps-love { color: #b83280; background: rgba(184,50,128,0.1); }
.ps-career { color: #2b6cb0; background: rgba(43,108,176,0.1); }
.ps-other { color: #718096; background: rgba(113,128,150,0.1); }

/* 报告 */
.report-loading {
  padding: 32rpx;
  text-align: center;
  color: $color-ink-light;
  font-size: 26rpx;
  letter-spacing: 2rpx;
}
.report-placeholder {
  padding: 32rpx;
  text-align: center;
  color: $color-ink-lighter;
  font-size: 24rpx;
}
.report-content {
  background: $color-paper-warm;
  border: 1rpx solid $color-border;
  border-radius: 12rpx;
  padding: 24rpx;
}

/* 底部 */
.modal-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  padding: 20rpx 32rpx 24rpx;
  border-top: 1rpx solid $color-border;
  flex-shrink: 0;
  background: $color-paper-warm;
}
.btn {
  flex: 1 1 calc(50% - 6rpx);
  min-width: 0;
  text-align: center;
  padding: 16rpx 12rpx;
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: 16rpx;
  font-size: 24rpx;
  color: $color-ink;
  letter-spacing: 2rpx;
  box-sizing: border-box;
}
.btn-primary {
  background: $color-vermilion;
  color: $color-paper;
  border-color: $color-vermilion;
}
.btn.disabled { opacity: 0.4; }
</style>
