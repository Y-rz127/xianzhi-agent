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
          <!-- 四柱命盘表格（11行×4列） -->
          <view class="bazi-table">
            <!-- 列头 -->
            <view class="bt-row bt-head">
              <text class="bt-cell bt-label"></text>
              <text v-for="p in pillars" :key="p.name" :class="['bt-cell bt-col-head', p.name === '日柱' && 'bt-day']">{{ p.name }}</text>
            </view>
            <!-- 主星（点击查看十神正反特性） -->
            <view class="bt-row">
              <text class="bt-cell bt-label">主星</text>
              <view v-for="p in pillars" :key="p.name" :class="['bt-cell', p.name === '日柱' && 'bt-day']">
                <text
                  v-if="p.shishenGan && isShishen(p.shishenGan)"
                  class="bt-shishen-tag"
                  @tap="showShishenInfo(p.shishenGan)"
                >{{ p.shishenGan }}</text>
                <text v-else class="bt-shishen">{{ p.shishenGan || '—' }}</text>
              </view>
            </view>
            <!-- 天干 -->
            <view class="bt-row">
              <text class="bt-cell bt-label">天干</text>
              <view v-for="p in pillars" :key="p.name" :class="['bt-cell', p.name === '日柱' && 'bt-day']">
                <text class="bt-gan" :style="{ color: ganColor(p.ganzhi[0]) }">{{ p.ganzhi[0] }}</text>
              </view>
            </view>
            <!-- 地支 -->
            <view class="bt-row">
              <text class="bt-cell bt-label">地支</text>
              <view v-for="p in pillars" :key="p.name" :class="['bt-cell', p.name === '日柱' && 'bt-day']">
                <text class="bt-zhi" :style="{ color: zhiColor(p.ganzhi[1]) }">{{ p.ganzhi[1] }}</text>
              </view>
            </view>
            <!-- 藏干 -->
            <view class="bt-row">
              <text class="bt-cell bt-label">藏干</text>
              <view v-for="p in pillars" :key="p.name" :class="['bt-cell bt-multi', p.name === '日柱' && 'bt-day']">
                <text v-for="(g, i) in (p.hiddenStems || [])" :key="i" class="bt-cang" :style="{ color: ganColor(g) }">{{ g }}</text>
              </view>
            </view>
            <!-- 副星（点击查看十神正反特性） -->
            <view class="bt-row">
              <text class="bt-cell bt-label">副星</text>
              <view v-for="p in pillars" :key="p.name" :class="['bt-cell bt-multi', p.name === '日柱' && 'bt-day']">
                <text
                  v-for="(s, i) in (p.shishenZhi || [])"
                  :key="i"
                  :class="['bt-fu', isShishen(s) && 'bt-fu-click']"
                  @tap="showShishenInfo(s)"
                >{{ s }}
                </text>
              </view>
            </view>
            <!-- 星运 -->
            <view class="bt-row">
              <text class="bt-cell bt-label">星运</text>
              <text v-for="p in pillars" :key="p.name" :class="['bt-cell', p.name === '日柱' && 'bt-day']">{{ p.changsheng || '—' }}</text>
            </view>
            <!-- 自坐 -->
            <view class="bt-row">
              <text class="bt-cell bt-label">自坐</text>
              <text v-for="p in pillars" :key="p.name" :class="['bt-cell', p.name === '日柱' && 'bt-day']">{{ p.zizuo || '—' }}</text>
            </view>
            <!-- 空亡 -->
            <view class="bt-row">
              <text class="bt-cell bt-label">空亡</text>
              <text v-for="p in pillars" :key="p.name" :class="['bt-cell', p.name === '日柱' && 'bt-day']">{{ p.xunkong || '—' }}</text>
            </view>
            <!-- 纳音 -->
            <view class="bt-row">
              <text class="bt-cell bt-label">纳音</text>
              <text v-for="p in pillars" :key="p.name" :class="['bt-cell', p.name === '日柱' && 'bt-day']">{{ p.nayin }}</text>
            </view>
            <!-- 神煞 -->
            <view class="bt-row">
              <text class="bt-cell bt-label">神煞</text>
              <view v-for="p in pillars" :key="p.name" :class="['bt-cell bt-multi', p.name === '日柱' && 'bt-day']">
                <text
                  v-for="(s, i) in (shenshaByPillar[p.name] || [])"
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
          <text class="section-title">大运 <text class="section-hint">点击查看详情</text></text>
          <view class="dayun-grid">
            <view v-for="(d, i) in dayun" :key="i" class="dayun-card dayun-card-clickable" @tap="openDetail(d)">
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
          <view v-if="relationText" class="consult-note">
            <text>{{ relationText }}</text>
          </view>
          <view v-if="liunian.length" class="liunian-strip">
            <view v-for="l in liunian.slice(0, 6)" :key="l.year" class="liunian-pill liunian-pill-clickable" @tap="openDetail(l)">
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
          <text
            v-if="!reportLoading"
            :class="['btn', 'btn-primary', 'section-cta', reportLoading && 'disabled']"
            @tap="generateReport"
          >{{ reportContent ? '重新生成报告' : '生成完整报告' }}</text>
        </view>
      </scroll-view>

      <!-- 大运/流年详情弹窗（小程序端：单独一个全屏浮层，避免嵌套在 scroll-view 内） -->
      <view v-if="selectedDetail" class="detail-mask" @tap="closeDetail">
        <view class="detail-card" @tap.stop>
          <view class="detail-header">
            <text class="detail-title">{{ selectedDetail.ganzhi }}</text>
            <text class="detail-close" @tap="closeDetail">✕</text>
          </view>
          <text class="detail-sub">{{ detailSubtitle }}</text>
          <view class="detail-grid">
            <view class="detail-row">
              <text class="detail-label">主星</text>
              <text class="detail-value">{{ selectedDetail.shishenGan || '—' }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">天干</text>
              <text class="detail-value">{{ selectedDetail.gan || '—' }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">地支</text>
              <text class="detail-value">{{ selectedDetail.zhi || '—' }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">藏干</text>
              <text class="detail-value">{{ (selectedDetail.hiddenStems || []).join('、') || '—' }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">副星</text>
              <text class="detail-value">{{ (selectedDetail.shishenZhi || []).join('、') || '—' }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">星运</text>
              <text class="detail-value">{{ selectedDetail.changsheng || '—' }}</text>
            </view>
          </view>
          <view v-if="selectedDetail.shensha && selectedDetail.shensha.length" class="detail-shensha-block">
            <text class="detail-shensha-title">神煞 <text class="detail-shensha-hint">点击查看详情</text></text>
            <view class="detail-shensha-tags">
              <view
                v-for="(s, i) in selectedDetail.shensha"
                :key="i"
                class="detail-shensha-tag"
                :class="{ active: activeShenshaName === s.name }"
                hover-class="detail-shensha-tag-hover"
                @tap="toggleShenshaDesc(s.name, s.description)"
              >
                <text>{{ s.name }}</text>
              </view>
            </view>
            <view v-if="activeShenshaName" class="detail-shensha-desc">
              <text class="detail-shensha-desc-name">{{ activeShenshaName }}</text>
              <text class="detail-shensha-desc-text">{{ activeShenshaDesc }}</text>
            </view>
          </view>
          <view class="detail-actions">
            <text class="detail-action-btn" @tap="closeDetail">关闭</text>
          </view>
        </view>
      </view>

      <!-- 底部操作栏 -->
      <view class="modal-footer">
        <text v-if="!reportContent" class="btn" @tap="handleDownloadPdf">下载 PDF</text>
        <text v-if="reportContent" class="btn" @tap="downloadFullPdf">导出完整 PDF</text>
        <text class="btn" @tap="close">关闭</text>
      </view>
    </view>

    <!-- 十神特性弹窗（自建浮层，绕开 uni.showModal 在小程序端不渲染 \n 的问题） -->
    <view v-if="shishenModal" class="shishen-mask" @tap="closeShishenModal">
      <view class="shishen-card" @tap.stop>
        <view class="shishen-header">
          <text class="shishen-title display-font">{{ shishenModal.name }}</text>
          <text class="shishen-close" @tap="closeShishenModal">✕</text>
        </view>
        <view class="shishen-body">
          <view class="shishen-section">
            <text class="shishen-label">【正面特性】</text>
            <text class="shishen-text">{{ shishenModal.positive }}</text>
          </view>
          <view class="shishen-section">
            <text class="shishen-label">【反面特性】</text>
            <text class="shishen-text">{{ shishenModal.negative }}</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
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

const reportContent = ref('')
const reportLoading = ref(false)

// 出生时间变化时清空报告，避免不同八字之间互相串台
watch(() => props.birthTime, () => {
  reportContent.value = ''
  reportLoading.value = false
  selectedDetail.value = null
})

const maxWuxing = computed(() => Math.max(...props.wuxing.map((w) => w.count), 1))
const liunian = computed(() => props.liunian || [])
const warnings = computed(() => props.warnings || [])
const currentYear = new Date().getFullYear()
const currentDayun = computed(() =>
  props.dayun.find((d) => d.startYear <= currentYear && (d.endYear || d.startYear + 9) >= currentYear) || props.dayun[0]
)

// === 大运/流年详情弹窗 ===
const selectedDetail = ref<DayunItem | LiuNianItem | null>(null)
const openDetail = (d: DayunItem | LiuNianItem) => {
  selectedDetail.value = d
  activeShenshaName.value = ''
  activeShenshaDesc.value = ''
}
const closeDetail = () => {
  selectedDetail.value = null
  activeShenshaName.value = ''
  activeShenshaDesc.value = ''
}
// 兜底：selectedDetail 任意方式被替换（比如父组件重置 liunian 流年数据）时清空展开中的神煞详情
watch(selectedDetail, (curr, prev) => {
  if (prev && curr !== prev) {
    activeShenshaName.value = ''
    activeShenshaDesc.value = ''
  }
})
// 详情弹窗内神煞标签点击：切换展开对应神煞的 description
const activeShenshaName = ref('')
const activeShenshaDesc = ref('')

// 主四柱十神标签点击：自建小浮层（uni.showModal 在某些端不渲染 \n，做不到正反面段落分隔）
const shishenModal = ref<{ name: string; positive: string; negative: string } | null>(null)
const toggleShenshaDesc = (name: string, desc: string) => {
  if (activeShenshaName.value === name) {
    activeShenshaName.value = ''
    activeShenshaDesc.value = ''
  } else {
    activeShenshaName.value = name
    activeShenshaDesc.value = desc
  }
}
const detailSubtitle = computed(() => {
  const d = selectedDetail.value
  if (!d) return ''
  // 大运：有 startYear
  if ('startYear' in d && d.startYear) {
    return `${d.startYear}-${d.endYear || d.startYear + 9} · ${d.startAge}-${d.endAge || d.startAge + 9}岁`
  }
  // 流年：有 age
  if ('age' in d && (d as any).age) {
    const l = d as LiuNianItem
    return `${l.year}年 · ${l.age}虚岁${l.dayun ? ' · 所在大运 ' + l.dayun : ''}`
  }
  return ''
})
// 关闭主弹窗时清空详情状态，避免下次打开不同八字时显示上一次的详情
watch(() => props.visible, (v) => {
  if (!v) {
    reportContent.value = ''
    reportLoading.value = false
    selectedDetail.value = null
  }
})
const relationText = computed(() => {
  const a = props.analysis
  if (!a) return ''
  const parts = [
    ...(a.combinations || []).map((v) => `合：${v}`),
    ...(a.clashes || []).map((v) => `冲：${v}`),
    ...(a.harms || []).map((v) => `害：${v}`),
    ...(a.punishments || []).map((v) => `刑：${v}`),
    ...(a.threeAssemblies || []).map((v) => {
      if (v.endsWith('破')) return `破：${v}`
      if (v.includes('会')) return `会：${v}`
      return `合：${v}`
    }),
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
  const seenByPillar: Record<string, Set<string>> = {}
  for (const s of props.shensha) {
    const pillarName = pillarNames.includes(s.pillar || '') ? s.pillar! : '日柱'
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

/**
 * 十神正反特性字典（标准命理口径）。
 * 键名严格对应引擎 bazi_engine.py 输出的十神：比肩/劫财/食神/伤官/偏财/正财/偏印/正印/七杀/正官。
 * alias 仅用于展示（如偏印又称枭神），不影响命中判断。
 */
const SHISHEN_INFO: Record<string, { alias?: string; positive: string; negative: string }> = {
  正官: {
    positive: '代表名誉、地位、规矩与责任感。利事业官运，为人正直守法、重视名誉、善于自我约束。',
    negative: '过旺无制则拘谨压抑、胆小怕事、依赖心重；太弱则缺乏担当、难担重任、易受人欺压。',
  },
  七杀: {
    alias: '偏官',
    positive: '代表权威、魄力、执行力与开拓精神。能掌权、闯劲足，逆境中爆发力强，宜武职、竞争与开创。',
    negative: '性烈易暴躁冲动、招惹是非官非；无制化则刑伤不断、压力过重、身心俱疲（"七杀无制祸来侵"）。',
  },
  正印: {
    positive: '代表学识、慈悲、庇护与贵人。利读书文凭、名誉声望，心地仁厚，多得长辈与母亲助力。',
    negative: '过旺则依赖惰性、行动力弱、易钻牛角尖；印重反克食伤，思想保守、不善变通表达。',
  },
  偏印: {
    alias: '枭神',
    positive: '代表领悟力、专长与冷门技艺。善钻研、有特殊才能与第六感，适技术、玄学、小众领域。',
    negative: '"枭神夺食"，易孤僻多疑、冷漠偏激；不善交际，遇食神则才华受抑、健康福泽受损。',
  },
  正财: {
    positive: '代表稳定收入、勤劳致富与务实节俭。利正业工薪、理财持家，为人踏实、重视家庭与积累。',
    negative: '太弱则财来财去、守财费力；太旺则斤斤计较、吝啬小气，反被财物所累、匮乏感强。',
  },
  偏财: {
    positive: '代表横财、机遇、社交与慷慨。利投资生意、意外之财，为人圆融、人缘佳、出手大方。',
    negative: '易投机好赌、挥霍无度；感情上多露水桃花，财来财去不稳定，重利轻义、因财生是非。',
  },
  食神: {
    positive: '代表才华、享受、口福与创造力。性温和、有艺术天赋，善表达、乐观随和，利技艺才艺。',
    negative: '过旺则贪图安逸、懒散纵欲、缺乏进取；遇枭神则"枭神夺食"，才华受抑、健康有损。',
  },
  伤官: {
    positive: '代表聪明、叛逆、创新与表达。才华外露、善辩敢突破，利艺术演艺、技术革新与自由职业。',
    negative: '"伤官见官"易傲气不服管、口舌是非；叛逆过激、轻视礼法，女命多不利夫星、感情波折。',
  },
  比肩: {
    positive: '代表同辈、朋友、合作与自立。重情义、有担当、能互助，利合伙团队，独立自主不依附。',
    negative: '"比劫夺财"易破财被分利；固执己见、争强好胜，朋友同辈反成拖累、合作生嫌隙。',
  },
  劫财: {
    positive: '代表行动力、义气与人际拓展。热情主动、善交际、乐于助人，利开拓人脉、江湖义气。',
    negative: '"劫财夺财"最甚，易破财被借被坑；冲动挥霍、争风吃醋，男命多不利财运与感情。',
  },
}

/** 判断一个字符串是否为引擎输出的十神（用于决定能否点击查看） */
function isShishen(name?: string): boolean {
  return !!name && name !== '—' && Object.prototype.hasOwnProperty.call(SHISHEN_INFO, name)
}

/** 点击十神查看其正面/反面特性（自建浮层，确保正反面段落换行生效） */
function showShishenInfo(name?: string) {
  if (!isShishen(name)) return
  const info = SHISHEN_INFO[name as string]
  const alias = info.alias ? `（又称${info.alias}）` : ''
  shishenModal.value = {
    name: `${name}${alias}`,
    positive: info.positive,
    negative: info.negative,
  }
}
function closeShishenModal() {
  shishenModal.value = null
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
  font-size: 36rpx;
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
  font-size: 24rpx;
  color: $color-ink-light;
}
.section-title {
  display: block;
  font-size: 30rpx;
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

/* 四柱命盘表格（11行×4列，CSS Grid 兼容小程序） */
.bazi-table {
  display: flex;
  flex-direction: column;
  border: 1rpx solid $color-border;
  border-radius: 12rpx;
  overflow: hidden;
  margin-bottom: 8rpx;
}
.bt-row {
  display: flex;
  flex-direction: row;
  border-bottom: 1rpx solid $color-border;
}
.bt-row:last-child { border-bottom: none; }
.bt-head { background: $color-paper-warm; }
.bt-cell {
  flex: 1; padding: 10rpx 4rpx; text-align: center; font-size: 26rpx; color: $color-ink;
  display: flex; align-items: center; justify-content: center;
  border-right: 1rpx solid $color-border; box-sizing: border-box; min-height: 0;
}
.bt-cell:last-child { border-right: none; }
.bt-label { flex: 0 0 80rpx; font-size: 26rpx; color: $color-ink-light; background: rgba(0,0,0,0.03); font-weight: 500; }
.bt-col-head { font-size: 26rpx; font-weight: 600; color: $color-ink; letter-spacing: 2px; }
.bt-day { background: rgba(184, 72, 60, 0.06); }
.bt-head .bt-day { background: rgba(184, 72, 60, 0.1); }
.bt-gan { font-size: 48rpx; font-weight: bold; font-family: $font-family-display; }
.bt-zhi { font-size: 48rpx; font-family: $font-family-display; }
.bt-multi { flex-direction: column; gap: 2rpx; padding: 8rpx 4rpx; }
.bt-cang { font-size: 26rpx; font-weight: 600; line-height: 1.5; }
.bt-fu { font-size: 26rpx; color: $color-ink-light; line-height: 1.5; }
/* 十神可点击（交互同神煞标签） */
.bt-shishen {
  font-size: 26rpx;
  color: $color-ink;
}
.bt-shishen-tag {
  font-size: 26rpx;
  color: $color-ink;
  padding: 2rpx 0;
  line-height: 1.5;
  transition: transform 0.15s, opacity 0.15s;
}
.bt-shishen-tag:active {
  transform: scale(0.95);
  opacity: 0.6;
}

/* === 十神自建浮层（绕开 uni.showModal 不渲染换行的限制） === */
.shishen-mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
}
.shishen-card {
  width: 78%;
  max-width: 620rpx;
  max-height: 78%;
  background: $color-paper;
  border-radius: 20rpx;
  box-shadow: 0 12rpx 40rpx rgba(0, 0, 0, 0.25);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.shishen-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28rpx 32rpx 16rpx;
  border-bottom: 1rpx solid rgba(184, 134, 11, 0.15);
}
.shishen-title {
  font-size: 40rpx;
  font-weight: 600;
  color: $color-ink;
  flex: 1;
  text-align: center;
}
.shishen-close {
  font-size: 36rpx;
  color: $color-ink-light;
  padding: 0 8rpx;
}
.shishen-body {
  padding: 24rpx 32rpx 32rpx;
  overflow-y: auto;
}
.shishen-section {
  margin-bottom: 20rpx;
}
.shishen-section:last-child {
  margin-bottom: 0;
}
.shishen-label {
  display: block;
  font-size: 32rpx;
  font-weight: 600;
  color: $color-ink;
  font-family: $font-family-display;
  margin-bottom: 12rpx;
  letter-spacing: 2rpx;
  text-align: center;
}
.shishen-text {
  display: block;
  font-size: 27rpx;
  color: $color-ink;
  line-height: 1.85;
  white-space: pre-wrap;
  word-break: break-all;
}

.bt-fu-click {
  color: $color-ink;
  transition: opacity 0.15s;
}
.bt-fu-click:active { opacity: 0.6; }

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
  font-size: 30rpx;
  font-weight: bold;
  margin-top: 8rpx;
}
.wuxing-count {
  font-size: 26rpx;
  color: $color-ink-light;
}

/* 大运 */
.dayun-grid {
  display: flex;
  flex-wrap: wrap;
  // 关键：让最后一行不满足 3 个时整体居中
  // flex-pack-justify 不能直接做"末行居中"，这里用 justify-content: center 配合固定列宽，
  // 每行 3 个会自动居中对齐，最后一行 1 个 / 2 个也会居中
  justify-content: center;
  gap: 12rpx;
  box-sizing: border-box;
}
.dayun-card {
  // 固定 3 列（小程序按屏幕宽度自动换行）
  // 列宽 = (父容器 - 2*gap) / 3 = calc((100% - 24rpx) / 3)
  flex: 0 0 calc((100% - 24rpx) / 3);
  width: calc((100% - 24rpx) / 3);
  background: $color-bg-card;
  border-radius: 12rpx;
  padding: 12rpx 6rpx;
  text-align: center;
  border: 1rpx solid $color-border;
  box-sizing: border-box;
  min-width: 0;
}
.dayun-card-clickable { transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s; }
.dayun-card-clickable:active { transform: scale(0.97); border-color: $color-primary; box-shadow: 0 4rpx 16rpx rgba(212, 175, 55, 0.2); }
.section-hint { font-size: 20rpx; color: $color-ink-light; font-weight: normal; margin-left: 8rpx; letter-spacing: 1rpx; }
.dayun-year {
  display: block;
  font-size: 32rpx;
  font-weight: bold;
  color: $color-ink;
  font-family: $font-family-display;
  margin-bottom: 4rpx;
  letter-spacing: 2rpx;
}
.dayun-range {
  display: block;
  font-size: 22rpx;
  color: $color-ink-light;
  margin-bottom: 2rpx;
}
.dayun-age {
  display: block;
  font-size: 22rpx;
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
  font-size: 24rpx;
  color: $color-ink-light;
  margin-bottom: 6rpx;
}
.consult-main {
  display: block;
  font-size: 32rpx;
  color: $color-vermilion;
  font-weight: 700;
  font-family: $font-family-display;
  margin-bottom: 4rpx;
}
.consult-sub {
  display: block;
  font-size: 24rpx;
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
  font-size: 26rpx;
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
.liunian-pill-clickable { transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s; }
.liunian-pill-clickable:active { transform: scale(0.97); border-color: $color-primary; box-shadow: 0 4rpx 16rpx rgba(212, 175, 55, 0.2); }
.ln-year,
.ln-gz,
.ln-dy {
  display: block;
  text-align: center;
}
.ln-year { font-size: 24rpx; color: $color-ink-light; }
.ln-gz { font-size: 30rpx; color: $color-ink; font-family: $font-family-display; font-weight: 700; margin: 4rpx 0; }
.ln-dy { font-size: 24rpx; color: $color-ink-light; }
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
  font-size: 26rpx;
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
  font-size: 22rpx;
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
  font-size: 30rpx;
  letter-spacing: 2rpx;
}
.report-placeholder {
  padding: 32rpx;
  text-align: center;
  color: $color-ink-lighter;
  font-size: 28rpx;
}
.report-content {
  background: $color-paper-warm;
  border: 1rpx solid $color-border;
  border-radius: 12rpx;
  padding: 24rpx;
}
.section-cta {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 80%;
  margin: 24rpx auto 0;
  padding: 22rpx 48rpx;
  font-size: 30rpx;
  font-weight: 600;
  letter-spacing: 4rpx;
  box-shadow: 0 4rpx 16rpx rgba(184, 72, 60, 0.25);
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
  flex: 1 1 0;
  min-width: 0;
  text-align: center;
  padding: 16rpx 12rpx;
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: 16rpx;
  font-size: 28rpx;
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

/* === 大运/流年详情弹窗（小程序端样式） === */
.detail-mask {
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40rpx;
  box-sizing: border-box;
}
.detail-card {
  width: 100%;
  max-width: 640rpx;
  max-height: 80vh;
  background: linear-gradient(135deg, $color-paper, $color-bg-card);
  border: 1rpx solid $color-border;
  border-radius: 20rpx;
  padding: 28rpx 28rpx 24rpx;
  box-shadow: 0 10rpx 40rpx rgba(0, 0, 0, 0.4);
  box-sizing: border-box;
  overflow-y: auto;
}
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6rpx;
}
.detail-title {
  font-size: 44rpx;
  font-weight: 700;
  color: $color-primary;
  letter-spacing: 6rpx;
  font-family: $font-family-display;
}
.detail-close {
  font-size: 32rpx;
  color: $color-ink-light;
  padding: 8rpx 16rpx;
}
.detail-sub {
  display: block;
  font-size: 22rpx;
  color: $color-ink-light;
  text-align: center;
  letter-spacing: 2rpx;
  margin-bottom: 20rpx;
}
.detail-grid {
  background: rgba(255, 255, 255, 0.04);
  border: 1rpx solid $color-border;
  border-radius: 12rpx;
  padding: 4rpx 16rpx;
  margin-bottom: 20rpx;
}
.detail-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16rpx 0;
  border-bottom: 1rpx solid rgba(255, 255, 255, 0.05);
}
.detail-row:last-child { border-bottom: none; }
.detail-label {
  font-size: 24rpx;
  color: $color-ink-light;
  letter-spacing: 2rpx;
}
.detail-value {
  font-size: 26rpx;
  color: $color-ink;
  font-weight: 600;
  font-family: $font-family-display;
  max-width: 60%;
  text-align: right;
}
.detail-shensha-block {
  margin-bottom: 20rpx;
}
.detail-shensha-title {
  display: block;
  font-size: 24rpx;
  color: $color-ink-light;
  letter-spacing: 2rpx;
  margin-bottom: 12rpx;
}
.detail-shensha-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10rpx;
}
.detail-shensha-tag {
  display: inline-block;
  font-size: 22rpx;
  padding: 6rpx 16rpx;
  background: rgba(212, 175, 55, 0.1);
  border: 1rpx solid rgba(212, 175, 55, 0.3);
  border-radius: 8rpx;
  color: $color-primary;
  letter-spacing: 1rpx;
}
.detail-shensha-tag.active {
  background: rgba(212, 175, 55, 0.25);
  border-color: $color-primary;
  font-weight: 600;
}
.detail-shensha-tag-hover {
  background: rgba(212, 175, 55, 0.2);
}
.detail-shensha-hint {
  font-size: 20rpx;
  color: $color-ink-light;
  font-weight: normal;
  margin-left: 8rpx;
  letter-spacing: 1rpx;
}
.detail-shensha-desc {
  margin-top: 14rpx;
  padding: 14rpx 18rpx;
  background: rgba(212, 175, 55, 0.06);
  border: 1rpx solid rgba(212, 175, 55, 0.2);
  border-left: 6rpx solid $color-primary;
  border-radius: 10rpx;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}
.detail-shensha-desc-name {
  font-size: 24rpx;
  color: $color-primary;
  font-weight: 600;
  letter-spacing: 2rpx;
}
.detail-shensha-desc-text {
  font-size: 24rpx;
  color: $color-ink;
  line-height: 1.6;
  letter-spacing: 1rpx;
}
.detail-actions {
  display: flex;
  justify-content: center;
  padding-top: 8rpx;
}
.detail-action-btn {
  padding: 14rpx 60rpx;
  font-size: 26rpx;
  color: $color-paper;
  background: $color-primary;
  border-radius: 30rpx;
  letter-spacing: 4rpx;
}
</style>