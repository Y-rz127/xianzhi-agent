<template>
  <div class="chart-detail-page">
    <header class="page-header">
      <button class="back-btn" @click="goBack" aria-label="返回">← 返回</button>
      <div class="page-title display-font">命盘详情</div>
      <button class="copy-btn" @click="copyChartText" aria-label="复制命盘">{{ copied ? '已复制' : '复制命盘' }}</button>
    </header>

    <div v-if="loading" class="page-state">正在排盘...</div>
    <div v-else-if="!chart" class="page-state">
      缺少出生信息，无法排盘。请从先知对话或命例库进入。
    </div>

    <template v-else>
      <nav class="tab-bar" role="tablist" aria-label="命盘分节">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-btn"
          :class="{ active: activeTab === tab.key }"
          role="tab"
          :aria-selected="activeTab === tab.key"
          @click="activeTab = tab.key"
        >{{ tab.label }}</button>
      </nav>

      <main class="page-body">
        <!-- 四柱 -->
        <div v-if="activeTab === 'pillars'" class="tab-panel" role="tabpanel">
          <div class="section-title-row">
            <span class="section-title">四柱命盘</span>
            <span v-if="chart.mingGong || chart.shenGong" class="gong-info">
              <template v-if="chart.mingGong">命宫 {{ chart.mingGong }}</template>
              <template v-if="chart.mingGong && chart.shenGong"> · </template>
              <template v-if="chart.shenGong">身宫 {{ chart.shenGong }}</template>
            </span>
          </div>
          <div class="chart-grid">
            <div class="cg-row cg-head">
              <div class="cg-label"></div>
              <div v-for="p in pillars" :key="'h-' + p.name" :class="['cg-cell cg-col-head', p.name === '日柱' ? 'day-master' : '']">{{ p.name }}</div>
            </div>
            <div class="cg-row">
              <div class="cg-label">主星</div>
              <div v-for="p in pillars" :key="'m-' + p.name" :class="['cg-cell', p.name === '日柱' ? 'day-master' : '']">{{ p.shishenGan || '—' }}</div>
            </div>
            <div class="cg-row">
              <div class="cg-label">天干</div>
              <div v-for="p in pillars" :key="'g-' + p.name" :class="['cg-cell', p.name === '日柱' ? 'day-master' : '']">
                <span class="big-gan" :style="{ color: ganColor(p.ganzhi[0]) }">{{ p.ganzhi[0] }}</span>
              </div>
            </div>
            <div class="cg-row">
              <div class="cg-label">地支</div>
              <div v-for="p in pillars" :key="'z-' + p.name" :class="['cg-cell', p.name === '日柱' ? 'day-master' : '']">
                <span class="big-zhi" :style="{ color: zhiColor(p.ganzhi[1]) }">{{ p.ganzhi[1] }}</span>
              </div>
            </div>
            <div class="cg-row">
              <div class="cg-label">藏干</div>
              <div v-for="p in pillars" :key="'c-' + p.name" :class="['cg-cell cg-multi', p.name === '日柱' ? 'day-master' : '']">
                <span v-for="(g, i) in p.hiddenStems" :key="'c-' + p.name + '-' + i" class="cang-item" :style="{ color: ganColor(g) }">{{ g }}</span>
              </div>
            </div>
            <div class="cg-row">
              <div class="cg-label">副星</div>
              <div v-for="p in pillars" :key="'f-' + p.name" :class="['cg-cell cg-multi', p.name === '日柱' ? 'day-master' : '']">
                <span v-for="(s, i) in p.shishenZhi" :key="'f-' + p.name + '-' + i" class="fu-item">{{ s }}</span>
              </div>
            </div>
            <div class="cg-row">
              <div class="cg-label">星运</div>
              <div v-for="p in pillars" :key="'cs-' + p.name" :class="['cg-cell', p.name === '日柱' ? 'day-master' : '']">{{ p.changsheng || '—' }}</div>
            </div>
            <div class="cg-row">
              <div class="cg-label">自坐</div>
              <div v-for="p in pillars" :key="'zz-' + p.name" :class="['cg-cell', p.name === '日柱' ? 'day-master' : '']">{{ p.zizuo || '—' }}</div>
            </div>
            <div class="cg-row">
              <div class="cg-label">空亡</div>
              <div v-for="p in pillars" :key="'xk-' + p.name" :class="['cg-cell', p.name === '日柱' ? 'day-master' : '']">{{ p.xunkong || '—' }}</div>
            </div>
            <div class="cg-row">
              <div class="cg-label">纳音</div>
              <div v-for="p in pillars" :key="'ny-' + p.name" :class="['cg-cell', p.name === '日柱' ? 'day-master' : '']">{{ p.nayin }}</div>
            </div>
            <div class="cg-row">
              <div class="cg-label">神煞</div>
              <div v-for="p in pillars" :key="'ss-' + p.name" :class="['cg-cell cg-multi cg-tags', p.name === '日柱' ? 'day-master' : '']">
                <span
                  v-for="(s, i) in (shenshaByPillar[p.name] || [])"
                  :key="'ss-' + p.name + '-' + i"
                  class="ps-tag"
                  :class="['ps-' + s._cat, { 'ps-active': activeShensha === s }]"
                  @click.stop="toggleShensha(s)"
                >{{ s.name }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 五行 -->
        <div v-if="activeTab === 'wuxing'" class="tab-panel" role="tabpanel">
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

        <!-- 大运 -->
        <div v-if="activeTab === 'dayun'" class="tab-panel" role="tabpanel">
          <div v-if="dayun.length" class="section-block">
            <div class="section-title">大运 <span class="section-hint">点击查看详情</span></div>
            <div class="dayun-grid">
              <div v-for="(d, i) in dayun" :key="i" class="dayun-card clickable" @click="openDetail(d)">
                <div class="dayun-year">{{ d.ganzhi }}</div>
                <div class="dayun-range">{{ d.startYear }}-{{ d.endYear || d.startYear + 9 }}</div>
                <div class="dayun-age">{{ d.startAge }}-{{ d.endAge || d.startAge + 9 }}岁</div>
              </div>
            </div>
          </div>
          <div v-if="hasConsultationContext" class="section-block">
            <div class="section-title">咨询依据</div>
            <div class="consult-grid">
              <div v-if="currentDayun" class="consult-card">
                <div class="consult-label">当前大运</div>
                <div class="consult-main">{{ currentDayun.ganzhi || currentDayun.year }}</div>
                <div class="consult-sub">{{ currentDayun.startYear }}-{{ currentDayun.endYear || currentDayun.startYear + 9 }} · {{ currentDayun.startAge }}-{{ currentDayun.endAge || currentDayun.startAge + 9 }}岁</div>
              </div>
              <div v-if="chart.startYun" class="consult-card">
                <div class="consult-label">起运口径</div>
                <div class="consult-main">{{ chart.startYun.direction || '-' }}</div>
                <div class="consult-sub">{{ chart.startYun.startDate || '-' }}</div>
              </div>
              <div v-if="chart.analysis?.strength" class="consult-card">
                <div class="consult-label">日主强弱</div>
                <div class="consult-main">{{ chart.analysis.day_master }}{{ chart.analysis.strength }}</div>
                <div class="consult-sub">置信度 {{ chart.analysis.confidence || '-' }}</div>
              </div>
              <div v-if="chart.analysis?.season" class="consult-card wide">
                <div class="consult-label">调候提示</div>
                <div class="consult-text">{{ chart.analysis.adjustment }}</div>
              </div>
            </div>
            <div v-if="chart.analysis?.patternHint" class="consult-note">{{ chart.analysis.patternHint }}</div>
            <div v-if="relationText" class="consult-note">{{ relationText }}</div>
            <div v-if="warnings.length" class="warning-list">
              <div v-for="w in warnings" :key="w" class="warning-item">{{ w }}</div>
            </div>
          </div>
        </div>

        <!-- 流年 -->
        <div v-if="activeTab === 'liunian'" class="tab-panel" role="tabpanel">
          <div class="section-title">流年 <span class="section-hint">点击查看详情</span></div>
          <div v-if="liunian.length" class="liunian-strip">
            <div v-for="l in liunian" :key="l.year" class="liunian-pill clickable" @click="openDetail(l)">
              <span>{{ l.year }}</span><b>{{ l.ganzhi }}</b><em>{{ l.dayun || '-' }}</em>
            </div>
          </div>
          <div v-else class="tab-empty">暂无流年数据</div>
        </div>

        <!-- 细盘：时间层级 -->
        <div v-if="activeTab === 'xipan'" class="tab-panel" role="tabpanel">
          <div v-if="xipan" class="xipan-section">
            <!-- 起运 -->
            <div class="xp-qiyun">
              <div class="xp-qiyun-main">
                <span class="xp-qiyun-tag">起运</span>
                <span class="xp-qiyun-after">{{ xipan.qiyun.after }}</span>
                <span class="xp-qiyun-dir">{{ xipan.qiyun.direction }}</span>
              </div>
              <div class="xp-qiyun-sub">
                交运 {{ xipan.qiyun.startDate }} · {{ xipan.qiyun.jieqi }}后{{ xipan.qiyun.daysAfterJieqi }}天 · 逢{{ xipan.qiyun.gan }}年交运
              </div>
            </div>

            <!-- 当前快照：流年+大运叠加四柱 -->
            <div class="section-block">
              <div class="section-title-row">
                <span class="section-title">当前快照</span>
                <span class="gong-info">{{ xipan.snapshot.label }} · {{ xipan.current.year }}年 {{ xipan.current.age }}虚岁</span>
              </div>
              <div class="chart-grid xp-snapshot">
                <div class="cg-row cg-head">
                  <div class="cg-label"></div>
                  <div v-for="c in xipan.snapshot.columns" :key="'sh-' + c.name" :class="['cg-cell cg-col-head', c.name === '日柱' ? 'day-master' : '']">{{ c.name }}</div>
                </div>
                <div class="cg-row">
                  <div class="cg-label">主星</div>
                  <div v-for="c in xipan.snapshot.columns" :key="'sm-' + c.name" :class="['cg-cell', c.name === '日柱' ? 'day-master' : '']">{{ c.shishen || '—' }}</div>
                </div>
                <div class="cg-row">
                  <div class="cg-label">天干</div>
                  <div v-for="c in xipan.snapshot.columns" :key="'sg-' + c.name" :class="['cg-cell', c.name === '日柱' ? 'day-master' : '']">
                    <span class="xp-gan" :style="{ color: ganColor(c.gan) }">{{ c.gan || '—' }}</span>
                  </div>
                </div>
                <div class="cg-row">
                  <div class="cg-label">地支</div>
                  <div v-for="c in xipan.snapshot.columns" :key="'sz-' + c.name" :class="['cg-cell', c.name === '日柱' ? 'day-master' : '']">
                    <span class="xp-gan" :style="{ color: zhiColor(c.zhi) }">{{ c.zhi || '—' }}</span>
                  </div>
                </div>
                <div class="cg-row">
                  <div class="cg-label">藏干</div>
                  <div v-for="c in xipan.snapshot.columns" :key="'sc-' + c.name" :class="['cg-cell cg-multi', c.name === '日柱' ? 'day-master' : '']">
                    <span v-for="(g, i) in c.hiddenStems" :key="'sc-' + c.name + '-' + i" class="cang-item" :style="{ color: ganColor(g) }">{{ g }}</span>
                  </div>
                </div>
                <div class="cg-row">
                  <div class="cg-label">副星</div>
                  <div v-for="c in xipan.snapshot.columns" :key="'sf-' + c.name" :class="['cg-cell cg-multi', c.name === '日柱' ? 'day-master' : '']">
                    <span v-for="(s, i) in c.shishenZhi" :key="'sf-' + c.name + '-' + i" class="fu-item">{{ s }}</span>
                  </div>
                </div>
                <div class="cg-row">
                  <div class="cg-label">星运</div>
                  <div v-for="c in xipan.snapshot.columns" :key="'scs-' + c.name" :class="['cg-cell', c.name === '日柱' ? 'day-master' : '']">{{ c.changsheng || '—' }}</div>
                </div>
                <div class="cg-row">
                  <div class="cg-label">自坐</div>
                  <div v-for="c in xipan.snapshot.columns" :key="'szz-' + c.name" :class="['cg-cell', c.name === '日柱' ? 'day-master' : '']">{{ c.zizuo || '—' }}</div>
                </div>
                <div class="cg-row">
                  <div class="cg-label">空亡</div>
                  <div v-for="c in xipan.snapshot.columns" :key="'sxk-' + c.name" :class="['cg-cell', c.name === '日柱' ? 'day-master' : '']">{{ c.xunkong || '—' }}</div>
                </div>
                <div class="cg-row">
                  <div class="cg-label">纳音</div>
                  <div v-for="c in xipan.snapshot.columns" :key="'sny-' + c.name" :class="['cg-cell', c.name === '日柱' ? 'day-master' : '']">{{ c.nayin || '—' }}</div>
                </div>
              </div>
            </div>

            <!-- 月令旺衰 + 人元司令 -->
            <div class="xp-state-row">
              <div class="xp-state-block">
                <div class="xp-state-title">月令旺衰</div>
                <div class="xp-state-items">
                  <span v-for="w in xipan.wuxingState" :key="w.name" class="xp-state-item" :class="'xs-' + w.state">{{ w.name }}{{ w.state }}</span>
                </div>
              </div>
              <div v-if="xipan.siling?.stem" class="xp-state-block">
                <div class="xp-state-title">人元司令</div>
                <div class="xp-state-items"><span class="xp-siling">{{ xipan.siling.stem }} 司令</span></div>
                <div class="xp-siling-detail">{{ xipan.siling.detail }}</div>
              </div>
            </div>

            <!-- 大运横条 -->
            <div class="section-block">
              <div class="section-title">大运 <span class="section-hint">点击切换</span></div>
              <div class="xp-dayun-strip">
                <button
                  v-for="d in xipan.dayun"
                  :key="d.index"
                  class="xp-dayun-chip"
                  :class="{ active: d.index === selectedDayunIndex, now: d.index === xipan.current.dayunIndex }"
                  @click="selectDayun(d.index)"
                >
                  <span class="xp-dy-gz">{{ d.ganzhi }}</span>
                  <span v-if="d.shishen" class="xp-dy-shishen">{{ d.shishen }}</span>
                  <span class="xp-dy-meta">{{ d.startAge }}-{{ d.endAge }}岁</span>
                  <span class="xp-dy-meta">{{ d.startYear }}-{{ d.endYear }}</span>
                </button>
              </div>
            </div>

            <!-- 流年条（选中大运下） -->
            <div class="section-block">
              <div class="section-title-row">
                <span class="section-title">流年</span>
                <span class="gong-info">{{ selectedDayunLabel }}</span>
              </div>
              <div class="xp-liunian-strip">
                <button
                  v-for="l in liunianOfDayun"
                  :key="l.year"
                  class="xp-ln-chip"
                  :class="{ active: l.year === selectedYear, now: l.year === xipan.current.year }"
                  @click="selectYear(l.year)"
                >
                  <span class="xp-ln-year">{{ l.year }}</span>
                  <span class="xp-ln-gz">{{ l.ganzhi }}</span>
                  <span class="xp-ln-shishen">{{ l.shishen }}</span>
                  <span class="xp-ln-meta">{{ l.age }}岁{{ l.xiaoyun ? ' · 小运' + l.xiaoyun : '' }}</span>
                </button>
              </div>
            </div>

            <!-- 流月表（选中流年下，按节气切分） -->
            <div class="section-block">
              <div class="section-title">流月 <span class="section-hint">{{ selectedYear }}年 · 按节气换月</span></div>
              <div class="xp-liuyue-grid">
                <div
                  v-for="m in liuyueOfYear"
                  :key="m.zhi"
                  class="xp-ly-cell"
                  :class="{ now: isCurrentLiuyue(m) }"
                >
                  <div class="xp-ly-jie">{{ m.jieqi }}</div>
                  <div class="xp-ly-date">{{ m.date }}</div>
                  <div class="xp-ly-gz">{{ m.ganzhi }}</div>
                  <div class="xp-ly-shishen">{{ m.shishen }}</div>
                </div>
              </div>
            </div>

            <div v-if="xipan.note" class="xipan-note">{{ xipan.note }}</div>
          </div>
          <div v-else class="tab-empty">暂无细盘数据</div>
        </div>

        <!-- 报告 -->
        <div v-if="activeTab === 'report'" class="tab-panel" role="tabpanel">
          <div class="section-block">
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
      </main>

      <footer class="page-footer">
        <button v-if="!reportContent" class="btn" @click="handleDownload" aria-label="下载PDF报告">下载 PDF 报告</button>
        <button class="btn" @click="generateReport" :disabled="reportLoading" aria-label="生成完整命理报告">
          {{ reportLoading ? "生成中..." : "生成完整命理报告" }}
        </button>
        <button v-if="reportContent" class="btn" @click="downloadMarkdown" aria-label="导出Markdown">导出 Markdown</button>
        <button v-if="reportContent" class="btn" @click="downloadFullPDF" aria-label="导出完整PDF">导出完整 PDF</button>
      </footer>
    </template>

    <!-- 神煞寓意浮层 -->
    <div v-if="activeShensha" class="ps-popover" @click="activeShensha = null">
      <div class="ps-popover-card" @click.stop>
        <div class="ps-popover-title" :class="'ps-' + activeShensha._cat">{{ activeShensha.name }}</div>
        <div class="ps-popover-desc">{{ activeShensha.description }}</div>
        <button class="ps-popover-close" @click="activeShensha = null" aria-label="关闭">关闭</button>
      </div>
    </div>
    <!-- 大运/流年详情浮层 -->
    <div v-if="selectedDetail" class="ps-popover" @click="closeDetail">
      <div class="detail-popover-card" @click.stop>
        <div class="detail-popover-title">{{ selectedDetail.ganzhi }}</div>
        <div class="detail-popover-sub">{{ detailSubtitle }}</div>
        <div class="detail-grid">
          <div class="detail-row"><span class="detail-label">主星</span><span class="detail-value">{{ selectedDetail.shishenGan || '—' }}</span></div>
          <div class="detail-row"><span class="detail-label">天干</span><span class="detail-value">{{ selectedDetail.gan || '—' }}</span></div>
          <div class="detail-row"><span class="detail-label">地支</span><span class="detail-value">{{ selectedDetail.zhi || '—' }}</span></div>
          <div class="detail-row"><span class="detail-label">藏干</span><span class="detail-value">{{ selectedDetail.hiddenStems?.join('、') || '—' }}</span></div>
          <div class="detail-row"><span class="detail-label">副星</span><span class="detail-value">{{ selectedDetail.shishenZhi?.join('、') || '—' }}</span></div>
          <div class="detail-row"><span class="detail-label">星运</span><span class="detail-value">{{ selectedDetail.changsheng || '—' }}</span></div>
        </div>
        <div v-if="selectedDetail.shensha?.length" class="detail-shensha-section">
          <div class="detail-label">神煞 <span class="section-hint">点击查看详情</span></div>
          <div class="detail-shensha-tags">
            <span
              v-for="(s, i) in selectedDetail.shensha"
              :key="i"
              class="detail-shensha-tag"
              :class="{ active: activeDetailShenshaName === s.name }"
              @click="toggleDetailShensha(s.name, s.description)"
            >{{ s.name }}</span>
          </div>
          <div v-if="activeDetailShenshaName" class="detail-shensha-desc">
            <div class="detail-shensha-desc-name">{{ activeDetailShenshaName }}</div>
            <div class="detail-shensha-desc-text">{{ activeDetailShenshaDesc }}</div>
          </div>
        </div>
        <button class="ps-popover-close" @click="closeDetail" aria-label="关闭">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import type { Pillar, WuxingItem, DayunItem, ShenshaItem, LiuNianItem, ChartAnalysis, ChartData, XiPanData, XiPanLiuYue } from "../api/index.ts"
import { getChart, downloadReport, generateFullReport, downloadFullReportPDF } from "../api/index.ts"
import MarkdownRender from "../components/MarkdownRender.vue"

type TabKey = 'pillars' | 'wuxing' | 'dayun' | 'liunian' | 'xipan' | 'report'

const route = useRoute()
const router = useRouter()

const tabs = [
  { key: 'pillars' as TabKey, label: '四柱' },
  { key: 'wuxing' as TabKey, label: '五行' },
  { key: 'dayun' as TabKey, label: '大运' },
  { key: 'liunian' as TabKey, label: '流年' },
  { key: 'xipan' as TabKey, label: '细盘' },
  { key: 'report' as TabKey, label: '报告' },
]
const activeTab = ref<TabKey>('pillars')

const chart = ref<ChartData | null>(null)
const loading = ref(true)
const birthTime = computed(() => String(route.query.birth_time || ""))
const gender = computed(() => String(route.query.gender || ""))

const ganWx: Record<string, string> = {
  '甲': '#4ade80', '乙': '#4ade80',
  '丙': '#f87171', '丁': '#f87171',
  '戊': '#d4a574', '己': '#d4a574',
  '庚': '#fbbf24', '辛': '#fbbf24',
  '壬': '#60a5fa', '癸': '#60a5fa',
}
const zhiWx: Record<string, string> = {
  '寅': '#4ade80', '卯': '#4ade80',
  '巳': '#f87171', '午': '#f87171',
  '辰': '#d4a574', '戌': '#d4a574', '丑': '#d4a574', '未': '#d4a574',
  '申': '#fbbf24', '酉': '#fbbf24',
  '亥': '#60a5fa', '子': '#60a5fa',
}
const ganColor = (c: string) => ganWx[c] || '#e5e7eb'
const zhiColor = (c: string) => zhiWx[c] || '#e5e7eb'

const pillars = computed<Pillar[]>(() => chart.value?.pillars || [])
const wuxing = computed<WuxingItem[]>(() => chart.value?.wuxing || [])
const dayun = computed<DayunItem[]>(() => chart.value?.dayun || [])
const liunian = computed<LiuNianItem[]>(() => chart.value?.liunian || [])
const warnings = computed(() => chart.value?.warnings || [])
const xipan = computed<XiPanData | null>(() => chart.value?.xipan || null)
const maxWuxing = computed(() => Math.max(...wuxing.value.map(w => w.count), 1))

const currentYear = new Date().getFullYear()
const currentDayun = computed(() =>
  dayun.value.find(d => d.startYear <= currentYear && (d.endYear || d.startYear + 9) >= currentYear) || dayun.value[0]
)
const relationText = computed(() => {
  const a = chart.value?.analysis as ChartAnalysis | undefined
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
  !!(chart.value?.analysis || chart.value?.startYun || liunian.value.length > 0 || warnings.value.length > 0)
)

// === 细盘选中联动 ===
const selectedDayunIndex = ref(-1)
const selectedYear = ref(0)

watch(xipan, (xp) => {
  if (xp) {
    selectedDayunIndex.value = xp.current.dayunIndex
    selectedYear.value = xp.current.year
  }
})

const liunianOfDayun = computed(() => {
  const xp = xipan.value
  return xp ? xp.liunian.filter(l => l.dayunIndex === selectedDayunIndex.value) : []
})
const liuyueOfYear = computed(() => {
  const xp = xipan.value
  return xp ? xp.liuyue.filter(m => m.year === selectedYear.value) : []
})
const selectedDayunLabel = computed(() => {
  const xp = xipan.value
  if (!xp) return ''
  const d = xp.dayun.find(x => x.index === selectedDayunIndex.value)
  return d ? `${d.index === 0 ? "童限" : d.ganzhi + " 大运"} · ${d.startYear}-${d.endYear}` : ""
})

function selectDayun(index: number) {
  selectedDayunIndex.value = index
  const first = xipan.value?.liunian.find(l => l.dayunIndex === index)
  if (first) selectedYear.value = first.year
}
function selectYear(year: number) {
  selectedYear.value = year
}
function isCurrentLiuyue(m: XiPanLiuYue): boolean {
  const xp = xipan.value
  return !!xp && selectedYear.value === xp.current.year && m.ganzhi === xp.current.liuyue
}

// 五行旺相休囚死的取色 class：用 ASCII 数字避免中文 class 被转义
const XS_STATE_KEY: Record<string, number> = { 旺: 0, 相: 1, 休: 2, 囚: 3, 死: 4 }
function xsStateKey(state: string): number {
  return XS_STATE_KEY[state] ?? 0
}

// === 神煞 ===
type TaggedShensha = ShenshaItem & { _cat: string }
const activeShensha = ref<TaggedShensha | null>(null)
const toggleShensha = (s: TaggedShensha) => {
  activeShensha.value = activeShensha.value === s ? null : s
}

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
  const seenByPillar: Record<string, Set<string>> = {}
  for (const s of (chart.value?.shensha || [])) {
    const pillarName = pillarNames.includes(s.pillar || '') ? s.pillar! : '日柱'
    const seen = seenByPillar[pillarName] ??= new Set<string>()
    if (seen.has(s.name)) continue
    seen.add(s.name)
    const tagged = { ...s, _cat: classifyShensha(s) }
    ;(groups[pillarName] ||= []).push(tagged)
  }
  return groups
})

// === 大运/流年详情浮层 ===
const selectedDetail = ref<DayunItem | LiuNianItem | null>(null)
const activeDetailShenshaName = ref('')
const activeDetailShenshaDesc = ref('')
const toggleDetailShensha = (name: string, desc: string) => {
  if (activeDetailShenshaName.value === name) {
    activeDetailShenshaName.value = ''
    activeDetailShenshaDesc.value = ''
  } else {
    activeDetailShenshaName.value = name
    activeDetailShenshaDesc.value = desc
  }
}
const openDetail = (d: DayunItem | LiuNianItem) => {
  selectedDetail.value = d
  activeDetailShenshaName.value = ''
  activeDetailShenshaDesc.value = ''
}
const closeDetail = () => {
  selectedDetail.value = null
  activeDetailShenshaName.value = ''
  activeDetailShenshaDesc.value = ''
}
const detailSubtitle = computed(() => {
  const d = selectedDetail.value
  if (!d) return ''
  if ('startYear' in d && d.startYear) {
    return `${d.startYear}-${d.endYear || d.startYear + 9} · ${d.startAge}-${d.endAge || d.startAge + 9}岁`
  }
  if ('age' in d && d.age) {
    return `${d.year}年 · ${d.age}虚岁${d.dayun ? ' · 所在大运 ' + d.dayun : ''}`
  }
  return ''
})

// === 复制命盘文本 ===
const copied = ref(false)
let copyTimer: ReturnType<typeof setTimeout> | null = null

const formattedChartText = computed(() => {
  const lines: string[] = ['命盘详情']
  if (birthTime.value) lines.push(`出生：${birthTime.value} ${gender.value}`)
  if (pillars.value.length) {
    lines.push('', '【四柱命盘】')
    pillars.value.forEach(p => {
      lines.push(`${p.name}: ${p.ganzhi} (${p.nayin})`)
      const parts: string[] = []
      if (p.shishenGan) parts.push(`主星=${p.shishenGan}`)
      if (p.changsheng) parts.push(`星运=${p.changsheng}`)
      if (p.zizuo) parts.push(`自坐=${p.zizuo}`)
      if (p.xunkong) parts.push(`空亡=${p.xunkong}`)
      if (p.hiddenStems?.length) parts.push(`藏干=${p.hiddenStems.join('')}`)
      if (p.shishenZhi?.length) parts.push(`副星=${p.shishenZhi.join('')}`)
      if (parts.length) lines.push('  ' + parts.join('，'))
    })
  }
  const xp = xipan.value
  if (xp) {
    lines.push('', '【起运】')
    lines.push(`${xp.qiyun.after} · ${xp.qiyun.direction}`)
    lines.push(`交运 ${xp.qiyun.startDate} · ${xp.qiyun.jieqi}后${xp.qiyun.daysAfterJieqi}天 · 逢${xp.qiyun.gan}年交运`)
    lines.push('', '【大运】')
    xp.dayun.forEach(d => lines.push(`${d.startYear}-${d.endYear}（${d.startAge}-${d.endAge}岁） ${d.ganzhi}${d.shishen ? ' ' + d.shishen : ''}`))
    lines.push('', '【流年】')
    xp.liunian.forEach(l => lines.push(`${l.year} ${l.ganzhi} ${l.shishen}（${l.age}岁${l.xiaoyun ? ' 小运' + l.xiaoyun : ''}）`))
    lines.push('', '【流月】')
    xp.liuyue.filter(m => m.year === selectedYear.value).forEach(m => lines.push(`${m.jieqi} ${m.date} ${m.ganzhi} ${m.shishen}`))
  }
  return lines.join('\n')
})

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

// === 报告 ===
const reportContent = ref("")
const reportLoading = ref(false)

const handleDownload = () => {
  if (birthTime.value && gender.value) downloadReport(birthTime.value, gender.value)
}

const generateReport = async () => {
  if (!birthTime.value || !gender.value || reportLoading.value) return
  reportLoading.value = true
  try {
    reportContent.value = await generateFullReport(birthTime.value, gender.value)
  } catch {
    reportContent.value = "报告生成失败，请稍后重试。"
  } finally {
    reportLoading.value = false
  }
}

const downloadMarkdown = () => {
  if (!reportContent.value || !birthTime.value) return
  const blob = new Blob([reportContent.value], { type: "text/markdown;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `先知命理报告_${birthTime.value.replace(/[ :]/g, "_")}.md`
  a.click()
  URL.revokeObjectURL(url)
}

const downloadFullPDF = () => {
  if (birthTime.value && gender.value) downloadFullReportPDF(birthTime.value, gender.value)
}

const goBack = () => {
  if (window.history.length > 1) router.back()
  else router.push("/xianzhi")
}

onMounted(async () => {
  if (!birthTime.value || !gender.value) {
    loading.value = false
    return
  }
  try {
    const sect = Number(route.query.sect || 2) || 2
    const yunSect = Number(route.query.yun_sect || 1) || 1
    const longitude = Number(route.query.longitude || 0) || undefined
    chart.value = await getChart(birthTime.value, gender.value, sect, yunSect, longitude)
  } catch {
    chart.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.chart-detail-page {
  min-height: 100vh;
  background: linear-gradient(135deg, rgba(18,26,42,0.98), rgba(12,18,32,0.98));
  display: flex;
  flex-direction: column;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.02);
  position: sticky;
  top: 0;
  z-index: 10;
}
.back-btn { padding: 8px 14px; background: transparent; border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-dim); cursor: pointer; font-size: 13px; transition: all 0.2s; }
.back-btn:hover { border-color: var(--accent); color: var(--accent); }
.page-title { font-size: 17px; color: var(--accent-light); letter-spacing: 4px; font-weight: 600; }
.copy-btn { padding: 8px 14px; background: transparent; border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-dim); cursor: pointer; font-size: 12px; transition: all 0.2s; }
.copy-btn:hover { border-color: var(--accent); color: var(--accent); }
.page-state { padding: 80px 20px; text-align: center; color: var(--text-dim); font-size: 14px; }

.tab-bar { display: flex; gap: 4px; padding: 10px 24px 0; border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.02); position: sticky; top: 57px; z-index: 9; overflow-x: auto; }
.tab-btn { padding: 10px 18px; background: transparent; border: none; border-bottom: 2px solid transparent;
  color: var(--text-dim); font-size: 14px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--accent-light); border-bottom-color: var(--accent); }

.page-body { flex: 1; width: 100%; max-width: 1080px; margin: 0 auto; padding: 28px 24px 40px; box-sizing: border-box; }
.tab-panel { animation: fadeIn 0.25s ease; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.tab-empty { color: var(--text-dim); font-size: 13px; text-align: center; padding: 30px 20px; }
.section-block { margin-bottom: 26px; }
.section-title { font-size: 14px; color: var(--accent); letter-spacing: 3px; margin-bottom: 14px;
  padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.section-title-row { display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 14px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.section-hint { font-size: 11px; color: var(--text-muted); letter-spacing: normal; font-weight: normal; }
.gong-info { font-size: 11px; color: var(--text-dim); letter-spacing: normal; }

/* 四柱表格（复用 modal 版网格） */
.chart-grid { display: block; border: 1px solid var(--border); border-radius: 10px; overflow: hidden;
  margin-bottom: 10px; font-size: 13px; }
.cg-row { display: grid; grid-template-columns: 64px repeat(4, 1fr); border-bottom: 1px solid var(--border); }
.xp-snapshot .cg-row { grid-template-columns: 64px repeat(6, 1fr); }
.cg-row:last-child { border-bottom: none; }
.cg-head { background: rgba(255,255,255,0.04); }
.cg-label { font-size: 11px; color: var(--text-dim); background: rgba(255,255,255,0.02); padding: 8px 4px;
  text-align: center; display: flex; align-items: center; justify-content: center; border-right: 1px solid var(--border); white-space: nowrap; }
.cg-cell { padding: 6px 4px; text-align: center; color: var(--text); line-height: 1.5;
  border-right: 1px solid var(--border); display: flex; align-items: center; justify-content: center;
  word-break: break-all; min-height: 28px; }
.cg-cell:last-child { border-right: none; }
.cg-head .cg-cell { font-size: 12px; color: var(--accent-light); letter-spacing: 1px; padding: 8px 4px; }
.cg-cell.day-master { background: linear-gradient(135deg, rgba(212,175,55,0.1), rgba(139,92,246,0.06)); }
.cg-head .cg-cell.day-master { background: linear-gradient(135deg, rgba(212,175,55,0.16), rgba(139,92,246,0.08)); }
.big-gan, .big-zhi { font-size: 30px; font-weight: bold; line-height: 1.1; }
.xp-gan { font-size: 24px; font-weight: bold; line-height: 1.2; }
.cg-multi { flex-direction: row; flex-wrap: wrap; gap: 2px 5px; justify-content: center; align-items: center; padding: 4px 2px; }
.cang-item { font-size: 11px; font-weight: 600; padding: 1px 2px; }
.fu-item { font-size: 10px; color: var(--text-dim); padding: 1px 2px; }
.cg-tags { padding: 4px 2px; }

/* 五行 */
.wuxing-grid { display: flex; justify-content: space-around; align-items: flex-end; height: 160px; margin-bottom: 10px; max-width: 560px; }
.wuxing-item { display: flex; flex-direction: column; align-items: center; gap: 6px; width: 16%; }
.wuxing-bar-container { width: 100%; height: 100px; background: rgba(255,255,255,0.03); border-radius: 6px 6px 0 0;
  display: flex; align-items: flex-end; overflow: hidden; }
.wuxing-bar { width: 100%; border-radius: 6px 6px 0 0; min-height: 4px; transition: height 0.5s ease; }
.wuxing-label { font-size: 14px; font-weight: bold; }
.wuxing-count { font-size: 12px; color: var(--text-dim); }

/* 大运 */
.dayun-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 24px; }
.dayun-card { background: rgba(255,255,255,0.03); border-radius: 10px; padding: 10px; text-align: center;
  border: 1px solid var(--border); }
.dayun-year { font-size: 16px; font-weight: bold; color: var(--accent-light); margin-bottom: 4px; }
.dayun-range { font-size: 10px; color: var(--text-dim); margin-bottom: 2px; }
.dayun-age { font-size: 10px; color: rgba(138,155,176,0.6); }
.consult-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 10px; }
.consult-card { background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 10px; padding: 10px; min-width: 0; }
.consult-card.wide { grid-column: span 3; }
.consult-label { font-size: 10px; color: var(--text-muted); margin-bottom: 4px; }
.consult-main { font-size: 15px; color: var(--accent-light); font-weight: 700; margin-bottom: 3px; }
.consult-sub, .consult-text { font-size: 11px; color: var(--text-dim); line-height: 1.5; }
.consult-note { font-size: 12px; line-height: 1.6; color: var(--text-dim); background: rgba(212,175,55,0.05);
  border: 1px solid rgba(212,175,55,0.12); border-radius: 10px; padding: 9px 10px; margin-top: 8px; }
.warning-list { margin-top: 10px; display: grid; gap: 6px; }
.warning-item { font-size: 11px; color: #d8bf7a; line-height: 1.5; padding: 8px 10px; border-radius: 9px;
  background: rgba(212,175,55,0.06); border: 1px solid rgba(212,175,55,0.12); }
.liunian-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.liunian-pill { display: grid; grid-template-columns: auto auto 1fr; gap: 6px; align-items: center; padding: 8px 9px;
  border-radius: 9px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); font-size: 11px; color: var(--text-dim); }
.liunian-pill b { color: var(--text); font-size: 13px; }
.liunian-pill em { font-style: normal; color: var(--accent); text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 神煞 */
.ps-tag { font-size: 9px; padding: 1px 5px; border-radius: 4px; line-height: 1.6; cursor: pointer;
  transition: all 0.2s; white-space: nowrap; user-select: none; display: inline-block; }
.ps-tag:hover { filter: brightness(1.2); }
.ps-active { outline: 1px solid currentColor; }
.ps-good { color: #4ade80; }
.ps-bad { color: #f87171; }
.ps-love { color: #f472b6; }
.ps-career { color: #60a5fa; }
.ps-other { color: #94a3b8; }
.ps-popover-title.ps-good, .ps-popover-title.ps-bad, .ps-popover-title.ps-love,
.ps-popover-title.ps-career, .ps-popover-title.ps-other { background: none; }
.ps-popover { position: fixed; inset: 0; background: rgba(0,0,0,0.55); display: flex; align-items: center;
  justify-content: center; z-index: 1100; padding: 20px; box-sizing: border-box; cursor: pointer; animation: fadeIn 0.15s ease; }
.ps-popover-card { background: linear-gradient(135deg, rgba(28,36,56,0.98), rgba(18,24,40,0.98));
  border: 1px solid var(--border-bright); border-radius: 12px; padding: 20px 24px; max-width: 340px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.5); cursor: default; animation: slideUp 0.2s ease-out; }
@keyframes slideUp { from { opacity: 0; transform: translateY(20px) scale(0.96); } to { opacity: 1; transform: translateY(0) scale(1); } }
.ps-popover-title { font-size: 16px; font-weight: 600; margin-bottom: 12px; letter-spacing: 2px; text-align: center; }
.ps-popover-desc { font-size: 13px; color: var(--text-dim); line-height: 1.8; margin-bottom: 16px; text-align: center; }
.ps-popover-close { display: block; margin: 0 auto; padding: 7px 28px; background: rgba(255,255,255,0.06);
  border: 1px solid var(--border); border-radius: 6px; color: var(--text-dim); font-size: 12px; cursor: pointer; transition: all 0.2s; }
.ps-popover-close:hover { border-color: var(--accent); color: var(--accent); }

/* 大运/流年详情浮层 */
.clickable { cursor: pointer; transition: all 0.2s; }
.clickable:hover { border-color: var(--accent) !important; box-shadow: 0 4px 16px rgba(212,175,55,0.15); transform: translateY(-2px); }
.detail-popover-card { background: linear-gradient(135deg, rgba(28,36,56,0.98), rgba(18,24,40,0.98));
  border: 1px solid var(--border-bright); border-radius: 12px; padding: 20px 24px; max-width: 360px; width: 90%;
  box-shadow: 0 10px 30px rgba(0,0,0,0.5); cursor: default; animation: slideUp 0.2s ease-out; }
.detail-popover-title { font-size: 22px; font-weight: bold; color: var(--accent-light); text-align: center; letter-spacing: 4px; margin-bottom: 4px; }
.detail-popover-sub { font-size: 12px; color: var(--text-dim); text-align: center; margin-bottom: 16px; }
.detail-grid { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.detail-row { display: flex; align-items: center; gap: 12px; padding: 6px 10px; border-radius: 8px; background: rgba(255,255,255,0.03); }
.detail-label { font-size: 12px; color: var(--text-muted); min-width: 40px; text-align: right; }
.detail-value { font-size: 14px; color: var(--text); font-weight: 500; }
.detail-shensha-section { margin-bottom: 14px; }
.detail-shensha-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.detail-shensha-tag { font-size: 11px; padding: 3px 10px; border-radius: 4px; background: rgba(212,175,55,0.1);
  border: 1px solid rgba(212,175,55,0.2); color: var(--accent-light); cursor: pointer; transition: all 0.2s; }
.detail-shensha-tag:hover { background: rgba(212,175,55,0.2); border-color: var(--accent); }
.detail-shensha-tag.active { background: rgba(212,175,55,0.3); border-color: var(--accent); color: var(--accent-light); font-weight: 600; }
.detail-shensha-desc { margin-top: 10px; padding: 10px 14px; background: rgba(212,175,55,0.05);
  border: 1px solid rgba(212,175,55,0.2); border-left: 3px solid var(--accent); border-radius: 6px; }
.detail-shensha-desc-name { font-size: 12px; color: var(--accent-light); font-weight: 600; margin-bottom: 4px; letter-spacing: 1px; }
.detail-shensha-desc-text { font-size: 12px; color: var(--text); line-height: 1.6; }

/* === 细盘（时间层级） === */
.xipan-section { display: flex; flex-direction: column; gap: 4px; }
.xp-qiyun { background: linear-gradient(135deg, rgba(212,175,55,0.08), rgba(139,92,246,0.05));
  border: 1px solid rgba(212,175,55,0.22); border-radius: 12px; padding: 14px 16px; margin-bottom: 26px; }
.xp-qiyun-main { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 6px; }
.xp-qiyun-tag { font-size: 12px; color: var(--accent-light); font-weight: 600; letter-spacing: 2px;
  padding: 2px 10px; border: 1px solid rgba(212,175,55,0.35); border-radius: 4px; }
.xp-qiyun-after { font-size: 15px; color: var(--text); font-weight: 600; }
.xp-qiyun-dir { font-size: 12px; color: var(--accent); }
.xp-qiyun-sub { font-size: 12px; color: var(--text-dim); line-height: 1.6; }

.xp-state-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 26px; }
.xp-state-block { background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; }
.xp-state-title { font-size: 12px; color: var(--text-muted); letter-spacing: 2px; margin-bottom: 10px; }
.xp-state-items { display: flex; flex-wrap: wrap; gap: 8px; }
.xp-state-item { font-size: 13px; padding: 3px 12px; border-radius: 6px; border: 1px solid var(--border); color: var(--text); }
.xs-旺 { color: #f87171; border-color: rgba(248,113,113,0.35); }
.xs-相 { color: #fbbf24; border-color: rgba(251,191,36,0.35); }
.xs-休 { color: #60a5fa; border-color: rgba(96,165,250,0.35); }
.xs-囚 { color: #a78bfa; border-color: rgba(167,139,250,0.35); }
.xs-死 { color: #94a3b8; border-color: rgba(148,163,184,0.35); }
.xp-siling { font-size: 15px; color: var(--accent-light); font-weight: 700; }
.xp-siling-detail { font-size: 11px; color: var(--text-dim); margin-top: 8px; line-height: 1.6; }

.xp-dayun-strip { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 8px; }
.xp-dayun-chip { flex: 0 0 auto; display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 10px 16px; border-radius: 10px; background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  cursor: pointer; transition: all 0.2s; min-width: 88px; }
.xp-dayun-chip:hover { border-color: var(--accent); }
.xp-dayun-chip.active { background: linear-gradient(135deg, rgba(212,175,55,0.18), rgba(139,92,246,0.1)); border-color: var(--accent); }
.xp-dayun-chip.now::after { content: '当前'; font-size: 9px; color: var(--accent); letter-spacing: 1px; }
.xp-dy-gz { font-size: 17px; font-weight: 700; color: var(--text); letter-spacing: 2px; }
.xp-dayun-chip.active .xp-dy-gz { color: var(--accent-light); }
.xp-dy-shishen { font-size: 11px; color: var(--accent); }
.xp-dy-meta { font-size: 10px; color: var(--text-dim); }

.xp-liunian-strip { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
.xp-ln-chip { display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 10px 8px;
  border-radius: 10px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); cursor: pointer; transition: all 0.2s; }
.xp-ln-chip:hover { border-color: var(--accent); }
.xp-ln-chip.active { background: linear-gradient(135deg, rgba(212,175,55,0.18), rgba(139,92,246,0.1)); border-color: var(--accent); }
.xp-ln-chip.now { border-color: rgba(212,175,55,0.5); }
.xp-ln-year { font-size: 14px; color: var(--text-dim); }
.xp-ln-gz { font-size: 17px; font-weight: 700; color: var(--text); letter-spacing: 2px; }
.xp-ln-chip.active .xp-ln-gz { color: var(--accent-light); }
.xp-ln-shishen { font-size: 11px; color: var(--accent); }
.xp-ln-meta { font-size: 10px; color: var(--text-dim); }

.xp-liuyue-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
.xp-ly-cell { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 8px;
  border-radius: 10px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); }
.xp-ly-cell.now { background: linear-gradient(135deg, rgba(212,175,55,0.18), rgba(139,92,246,0.1)); border-color: var(--accent); }
.xp-ly-jie { font-size: 12px; color: var(--text); font-weight: 600; }
.xp-ly-date { font-size: 10px; color: var(--text-dim); }
.xp-ly-gz { font-size: 18px; font-weight: 700; color: var(--accent-light); letter-spacing: 2px; }
.xp-ly-cell.now .xp-ly-gz { color: var(--accent); }
.xp-ly-shishen { font-size: 10px; color: var(--text-muted); }
.xipan-note { font-size: 11px; color: var(--text-dim); line-height: 1.6; padding: 9px 10px; border-radius: 9px;
  background: rgba(255,255,255,0.02); border: 1px dashed var(--border); }

/* 报告 */
.report-loading { display: flex; align-items: center; gap: 10px; color: var(--accent); font-size: 13px; padding: 20px; }
.report-placeholder { color: var(--text-dim); font-size: 13px; text-align: center; padding: 20px; }
.report-content { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.loading-dots { display: inline-flex; gap: 4px; }
.loading-dots span { width: 6px; height: 6px; background: var(--accent); border-radius: 50%; animation: dot 1.4s infinite both; }
.loading-dots span:nth-child(1) { animation-delay: 0s; }
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot { 0%, 80%, 100% { transform: scale(0); opacity: 0.5; } 40% { transform: scale(1); opacity: 1; } }

.page-footer { display: flex; justify-content: center; gap: 10px; padding: 16px 24px;
  border-top: 1px solid var(--border); background: rgba(255,255,255,0.02); flex-wrap: wrap; }
.page-footer .btn { display: inline-flex; align-items: center; gap: 6px; min-width: 140px; justify-content: center; }

@media (max-width: 768px) {
  .dayun-grid { grid-template-columns: repeat(2, 1fr); }
  .consult-grid { grid-template-columns: repeat(2, 1fr); }
  .consult-card.wide { grid-column: span 2; }
  .liunian-strip { grid-template-columns: repeat(2, 1fr); }
  .xp-liunian-strip { grid-template-columns: repeat(3, 1fr); }
  .xp-liuyue-grid { grid-template-columns: repeat(3, 1fr); }
  .xp-state-row { grid-template-columns: 1fr; }
  .tab-bar { top: 53px; }
  .page-body { padding: 20px 14px 30px; }
}
</style>
