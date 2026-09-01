<template>
  <view class="page" :class="themeClass">
    <view class="meteor meteor-1" v-if="themeClass === 't-dark'"></view>
    <view class="meteor meteor-2" v-if="themeClass === 't-dark'"></view>
    <view class="meteor meteor-3" v-if="themeClass === 't-dark'"></view>
    <view class="nav" @tap="back">‹</view>
    <scroll-view scroll-y class="scroll">
      <view class="hero">
        <text>紫微斗数</text>
        <small class="hero-sub">传统民俗文化参考 · 仅供自省</small>
      </view>

      <!-- 输入表单 -->
      <view v-if="phase === 'form'" class="panel">
        <text class="label">历法</text>
        <view class="seg">
          <view :class="['seg-item', calendar === 'solar' && 'active']" @tap="calendar = 'solar'">阳历</view>
          <view :class="['seg-item', calendar === 'lunar' && 'active']" @tap="calendar = 'lunar'">农历</view>
        </view>

        <text class="label">出生日期</text>
        <picker v-if="calendar === 'solar'" mode="date" :value="solarDate" start="1900-01-01" end="2099-12-31" @change="e => solarDate = e.detail.value">
          <view class="field">{{ solarDate }}</view>
        </picker>
        <view v-else class="lunar-row">
          <picker class="lunar-cell" mode="selector" :range="yearOptions" :value="lunarYearIdx" @change="e => lunarYearIdx = +e.detail.value">
            <view class="field">{{ yearOptions[lunarYearIdx] }}</view>
          </picker>
          <picker class="lunar-cell" mode="selector" :range="monthOptions" :value="lunarMonthIdx" @change="e => lunarMonthIdx = +e.detail.value">
            <view class="field">{{ monthOptions[lunarMonthIdx] }}</view>
          </picker>
          <picker class="lunar-cell" mode="selector" :range="dayOptions" :value="lunarDayIdx" @change="e => lunarDayIdx = +e.detail.value">
            <view class="field">{{ dayOptions[lunarDayIdx] }}</view>
          </picker>
        </view>

        <view v-if="calendar === 'lunar'" class="leap-line">
          <text class="leap-text">闰月（该年有闰月时生效）</text>
          <switch :checked="leap" color="#5B6FC8" @change="e => leap = e.detail.value" />
        </view>

        <text class="label">出生时辰</text>
        <picker mode="selector" :range="timeOptions" :value="timeIndex" @change="e => timeIndex = +e.detail.value">
          <view class="field">{{ timeOptions[timeIndex] }}</view>
        </picker>

        <text class="label">性别</text>
        <view class="seg">
          <view :class="['seg-item', gender === '男' && 'active']" @tap="gender = '男'">男</view>
          <view :class="['seg-item', gender === '女' && 'active']" @tap="gender = '女'">女</view>
        </view>

        <button class="primary" :loading="loading" :disabled="loading" @tap="doCast">排盘</button>
      </view>

      <!-- 命盘 -->
      <view v-if="chart && phase === 'chart'" class="chart-wrap">
        <view class="board">
          <view
            v-for="cell in boardCells"
            :key="cell.key"
            :class="cell.cls"
            :style="cell.style"
            @tap="cell.palace && openDetail(cell.palace)"
          >
            <template v-if="cell.palace">
              <view class="mut-corner mut-lu" v-if="cell.palace.major_stars.some(s => s.mutagen === '禄')">禄</view>
              <view class="mut-corner mut-quan" v-if="cell.palace.major_stars.some(s => s.mutagen === '权')">权</view>
              <view class="mut-corner mut-ke" v-if="cell.palace.major_stars.some(s => s.mutagen === '科')">科</view>
              <view class="mut-corner mut-ji" v-if="cell.palace.major_stars.some(s => s.mutagen === '忌')">忌</view>
              <view class="p-head">
                <text class="p-name">{{ cell.palace.name }}</text>
                <text class="p-body" v-if="cell.palace.is_body">身</text>
              </view>
              <text class="p-gz">{{ cell.palace.heavenly_stem }}{{ cell.palace.earthly_branch }}</text>
              <view class="p-majors">
                <view v-for="s in cell.palace.major_stars" :key="s.name" class="major-row">
                  <text class="major-name">{{ s.name }}</text>
                  <text class="major-bri" v-if="s.brightness">{{ s.brightness }}</text>
                  <text :class="['major-mut', mutClass(s.mutagen)]" v-if="s.mutagen">{{ s.mutagen }}</text>
                </view>
                <text v-if="!cell.palace.major_stars.length" class="major-empty">空宫</text>
              </view>
              <text class="p-minor">{{ minorNames(cell.palace) }}</text>
              <text class="p-dec" v-if="cell.palace.decadal">{{ cell.palace.decadal.range[0] }}~{{ cell.palace.decadal.range[1] }}</text>
            </template>
            <template v-else>
              <view class="center">
                <text class="c-title">{{ chart.gender }}命</text>
                <text class="c-line">{{ chart.lunar_date }}</text>
                <text class="c-line">{{ chart.time_name }}（{{ chart.time_range }}）</text>
                <text class="c-gz">四柱 {{ chart.four_pillars.yearly }} {{ chart.four_pillars.monthly }} {{ chart.four_pillars.daily }} {{ chart.four_pillars.hourly }}</text>
                <text class="c-line">{{ chart.five_elements_class }} · 命宫{{ chart.earthly_branch_of_soul }} 身宫{{ chart.earthly_branch_of_body }}</text>
                <text class="c-line">命主{{ chart.soul_star }} · 身主{{ chart.body_star }}</text>
                <text class="c-tip">点任意宫看详情</text>
              </view>
            </template>
          </view>
        </view>

        <view class="legend">
          <text><text class="lg lg-lu">禄</text>化禄</text>
          <text><text class="lg lg-quan">权</text>化权</text>
          <text><text class="lg lg-ke">科</text>化科</text>
          <text><text class="lg lg-ji">忌</text>化忌</text>
        </view>

        <view class="actions">
          <button class="ghost" @tap="resetForm">重新输入</button>
          <button class="primary" :loading="interpreting" :disabled="interpreting" @tap="doInterpret">AI 简批</button>
        </view>
        <view v-if="interpretation" class="answer">
          <text class="a-title">命盘简批</text>
          <text class="a-body">{{ interpretation }}</text>
        </view>
        <view class="foot-space"></view>
      </view>
    </scroll-view>

    <!-- 点宫详情弹层 -->
    <view v-if="detail" class="mask" @tap="detail = null">
      <view class="sheet" @tap.stop>
        <view class="sheet-head">
          <text class="sheet-title">{{ detail.name }}宫（{{ detail.heavenly_stem }}{{ detail.earthly_branch }}）</text>
          <text class="sheet-close" @tap="detail = null">✕</text>
        </view>
        <scroll-view scroll-y class="sheet-body">
          <view class="sec"><text class="sec-t">主星</text>
            <view v-for="s in detail.major_stars" :key="s.name" class="star-line">
              <text class="sl-name">{{ s.name }}</text>
              <text class="sl-bri" v-if="s.brightness">{{ s.brightness }}</text>
              <text :class="['sl-mut', mutClass(s.mutagen)]" v-if="s.mutagen">化{{ s.mutagen }}</text>
            </view>
            <text v-if="!detail.major_stars.length" class="sl-empty">空宫（借对宫主星论）</text>
          </view>
          <view class="sec" v-if="detail.minor_stars.length"><text class="sec-t">辅星·煞星</text>
            <view v-for="s in detail.minor_stars" :key="s.name" class="star-line">
              <text class="sl-name">{{ s.name }}</text>
              <text class="sl-bri" v-if="s.brightness">{{ s.brightness }}</text>
              <text :class="['sl-mut', mutClass(s.mutagen)]" v-if="s.mutagen">化{{ s.mutagen }}</text>
            </view>
          </view>
          <view class="sec" v-if="detail.adjective_stars.length"><text class="sec-t">杂曜</text>
            <text class="misc">{{ detail.adjective_stars.map(s => s.name).join('、') }}</text>
          </view>
          <view class="sec"><text class="sec-t">十二神</text>
            <text class="misc">长生·{{ detail.changsheng12 }}　博士·{{ detail.boshi12 }}</text>
            <text class="misc">将前·{{ detail.jiangqian12 }}　岁前·{{ detail.suiqian12 }}</text>
          </view>
          <view class="sec"><text class="sec-t">三方四正</text>
            <text class="misc">{{ sanFangSiZheng }}</text>
          </view>
          <view class="sec" v-if="detail.decadal"><text class="sec-t">大限</text>
            <text class="misc">{{ detail.decadal.range[0] }}~{{ detail.decadal.range[1] }} 岁（{{ detail.decadal.heavenly_stem }}{{ detail.decadal.earthly_branch }}）</text>
          </view>
        </scroll-view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { getZiWeiChart, interpretZiWei, type ZiWeiChart, type ZiWeiPalace } from '@/api'
import { useTheme } from '@/composables/useTheme'

const { themeClass } = useTheme()

const TIME_OPTIONS = [
  '早子时 00:00~01:00', '丑时 01:00~03:00', '寅时 03:00~05:00', '卯时 05:00~07:00',
  '辰时 07:00~09:00', '巳时 09:00~11:00', '午时 11:00~13:00', '未时 13:00~15:00',
  '申时 15:00~17:00', '酉时 17:00~19:00', '戌时 19:00~21:00', '亥时 21:00~23:00', '晚子时 23:00~00:00',
]
const CN_MONTH = ['正', '二', '三', '四', '五', '六', '七', '八', '九', '十', '冬', '腊']
const CN_DAY = ['初一', '初二', '初三', '初四', '初五', '初六', '初七', '初八', '初九', '初十',
  '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
  '廿一', '廿二', '廿三', '廿四', '廿五', '廿六', '廿七', '廿八', '廿九', '三十']

const phase = ref<'form' | 'chart'>('form')
const calendar = ref<'solar' | 'lunar'>('solar')
const solarDate = ref('2000-01-01')
const yearOptions = Array.from({ length: 200 }, (_, i) => `${1900 + i}年`)
const lunarYearIdx = ref(100) // 2000
const monthOptions = CN_MONTH.map(m => `${m}月`)
const lunarMonthIdx = ref(0)
const dayOptions = CN_DAY
const lunarDayIdx = ref(0)
const leap = ref(false)
const timeOptions = TIME_OPTIONS
const timeIndex = ref(0)
const gender = ref<'男' | '女'>('男')

const loading = ref(false)
const interpreting = ref(false)
const chart = ref<ZiWeiChart | null>(null)
const interpretation = ref('')
const detail = ref<ZiWeiPalace | null>(null)

// 地支 → 4×4 盘位（0~15，行优先）。中央 5/6/9/10 为信息区。
const BRANCH_CELL: Record<string, number> = {
  巳: 0, 午: 1, 未: 2, 申: 3, 辰: 4, 酉: 7, 卯: 8, 戌: 11, 寅: 12, 丑: 13, 子: 14, 亥: 15,
}
const CENTER_CELLS = new Set([5, 6, 9, 10])

const boardCells = computed(() => {
  const byCell: Record<number, ZiWeiPalace> = {}
  if (chart.value) for (const p of chart.value.palaces) byCell[BRANCH_CELL[p.earthly_branch]] = p
  const cells: any[] = []
  for (let c = 0; c < 16; c++) {
    const row = Math.floor(c / 4) + 1
    const col = (c % 4) + 1
    if (CENTER_CELLS.has(c)) {
      if (c === 5) cells.push({ key: 'center', cls: 'cell center-cell', style: 'grid-row:2 / span 2;grid-column:2 / span 2', palace: null })
      continue
    }
    const p = byCell[c] || null
    cells.push({ key: 'p' + c, cls: 'cell palace-cell' + (p && p.name === '命宫' ? ' soul' : ''), style: `grid-row:${row};grid-column:${col}`, palace: p })
  }
  return cells
})

function minorNames(p: ZiWeiPalace): string {
  const names = [...p.minor_stars.map(s => s.name), ...p.adjective_stars.filter(s => s.type === 'flower' || s.type === 'tough' || s.type === 'soft').map(s => s.name)]
  return [...new Set(names)].slice(0, 8).join(' ')
}
function mutClass(m: string): string {
  return m === '禄' ? 'mut-lu' : m === '权' ? 'mut-quan' : m === '科' ? 'mut-ke' : m === '忌' ? 'mut-ji' : ''
}
const sanFangSiZheng = computed(() => {
  if (!detail.value || !chart.value) return ''
  const i = detail.value.index
  const at = (idx: number) => chart.value!.palaces[((idx % 12) + 12) % 12].name
  return `本宫${at(i)}、对宫${at(i + 6)}、三合${at(i + 4)}·${at(i + 8)}`
})

function back() { uni.navigateBack() }
function resetForm() { phase.value = 'form'; chart.value = null; interpretation.value = '' }
function openDetail(p: ZiWeiPalace) { detail.value = p }

function castParams() {
  if (calendar.value === 'solar') {
    return { date: solarDate.value, time_index: timeIndex.value, gender: gender.value, calendar: 'solar' as const }
  }
  const date = `${1900 + lunarYearIdx.value}-${lunarMonthIdx.value + 1}-${lunarDayIdx.value + 1}`
  return { date, time_index: timeIndex.value, gender: gender.value, calendar: 'lunar' as const, leap: leap.value }
}

async function doCast() {
  loading.value = true
  try {
    chart.value = await getZiWeiChart(castParams())
    interpretation.value = ''
    phase.value = 'chart'
  } catch (e: any) {
    uni.showToast({ title: e.message || '排盘失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function doInterpret() {
  interpreting.value = true
  try {
    interpretation.value = await interpretZiWei(castParams())
  } catch (e: any) {
    uni.showToast({ title: e.message || '解读失败', icon: 'none' })
  } finally {
    interpreting.value = false
  }
}
</script>

<style lang="scss">
/* 四化语义色（固定，两套主题均成立） */
$mut-lu: #C9A227;
$mut-quan: #C0392B;
$mut-ke: #2E8B8B;
$mut-ji: #2C2C2C;

.page { min-height: 100vh; background: linear-gradient(180deg, $nx-bg, $nx-bg-2 55%, $nx-bg-3); color: $nx-text; }
.scroll { height: 100vh; }
.nav { position: fixed; z-index: 2; top: 50rpx; left: 28rpx; font-size: 60rpx; color: $nx-text; }
.hero { text-align: center; padding: 140rpx 0 48rpx; }
.hero text, .hero .hero-sub { display: block; }
.hero text { font-size: 62rpx; letter-spacing: 14rpx; color: $nx-accent-ziwei; }
.hero .hero-sub { margin-top: 20rpx; color: $nx-text-dim; font-size: 26rpx; }

.panel { margin: 24rpx 36rpx 60rpx; padding: 40rpx 36rpx; border: 1rpx solid $nx-border; border-radius: 24rpx; background: $nx-card; }
.label { display: block; color: $nx-accent-ziwei; margin: 24rpx 0 14rpx; font-size: 28rpx; font-weight: 600; letter-spacing: 2rpx; }
.field { padding: 26rpx 28rpx; background: $nx-bg-3; color: $nx-text; border: 1rpx solid $nx-border; border-radius: 14rpx; font-size: 30rpx; }
.seg { display: flex; gap: 18rpx; }
.seg-item { flex: 1; text-align: center; padding: 24rpx 12rpx; border: 1rpx solid $nx-border; border-radius: 14rpx; color: $nx-text-dim; font-size: 30rpx; }
.seg-item.active { background: rgba(91, 111, 200, .16); color: $nx-accent-ziwei; border-color: $nx-accent-ziwei; font-weight: 600; }
.lunar-row { display: flex; gap: 16rpx; }
.lunar-cell { flex: 1; min-width: 0; }
.leap-line { display: flex; align-items: center; justify-content: space-between; margin-top: 24rpx; }
.leap-text { color: $nx-text-dim; font-size: 28rpx; }
.primary { margin-top: 44rpx; padding: 28rpx; background: linear-gradient(135deg, #4a5bb0, #7488dd); color: #fff; font-size: 32rpx; font-weight: 600; border-radius: 16rpx; letter-spacing: 4rpx; }
.primary[disabled] { opacity: .6; }
.ghost { padding: 28rpx; background: transparent; color: $nx-accent-ziwei; border: 1rpx solid $nx-accent-ziwei; font-size: 30rpx; border-radius: 16rpx; }

/* ===== 命盘 4×4 ===== */
.chart-wrap { margin: 12rpx 20rpx; }
.board { display: grid; grid-template-columns: repeat(4, 1fr); grid-template-rows: repeat(4, 1fr); gap: 2rpx; width: 100%; aspect-ratio: 1 / 1; background: $nx-border; border: 2rpx solid $nx-accent-ziwei; border-radius: 12rpx; overflow: hidden; }
.cell { position: relative; background: $nx-card; padding: 8rpx 8rpx 26rpx; overflow: hidden; }
.palace-cell:active { background: $nx-bg-3; }
.palace-cell.soul { background: rgba(91, 111, 200, .10); }
.p-head { display: flex; align-items: center; gap: 4rpx; }
.p-name { font-size: 22rpx; color: $nx-accent-ziwei; font-weight: 700; }
.p-body { font-size: 16rpx; color: #fff; background: $nx-accent-ziwei; border-radius: 4rpx; padding: 0 4rpx; }
.p-gz { position: absolute; top: 8rpx; right: 8rpx; font-size: 16rpx; color: $nx-text-muted; }
.p-majors { margin-top: 10rpx; }
.major-row { display: flex; align-items: baseline; gap: 2rpx; }
.major-name { font-size: 24rpx; color: $nx-text; font-weight: 600; }
.major-bri { font-size: 16rpx; color: $nx-text-dim; }
.major-mut { font-size: 16rpx; font-weight: 700; }
.major-empty { font-size: 20rpx; color: $nx-text-muted; }
.p-minor { position: absolute; left: 8rpx; right: 8rpx; bottom: 26rpx; font-size: 15rpx; color: $nx-text-muted; line-height: 1.3; }
.p-dec { position: absolute; left: 8rpx; bottom: 6rpx; font-size: 15rpx; color: $nx-text-dim; }
.mut-lu { color: $mut-lu; } .mut-quan { color: $mut-quan; } .mut-ke { color: $mut-ke; } .mut-ji { color: $mut-ji; }
.mut-corner { position: absolute; width: 22rpx; height: 22rpx; line-height: 22rpx; text-align: center; font-size: 14rpx; color: #fff; border-radius: 50%; }
.mut-corner.mut-lu { top: 4rpx; right: 4rpx; background: $mut-lu; }
.mut-corner.mut-quan { top: 4rpx; left: 4rpx; background: $mut-quan; }
.mut-corner.mut-ke { bottom: 4rpx; right: 4rpx; background: $mut-ke; }
.mut-corner.mut-ji { bottom: 4rpx; left: 4rpx; background: $mut-ji; }

.center-cell { padding: 0; }
.center { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6rpx; background: $nx-bg-3; }
.c-title { font-size: 30rpx; color: $nx-accent-ziwei; font-weight: 700; letter-spacing: 4rpx; }
.c-line { font-size: 20rpx; color: $nx-text; }
.c-gz { font-size: 18rpx; color: $nx-text-dim; }
.c-tip { margin-top: 8rpx; font-size: 16rpx; color: $nx-text-muted; }

.legend { display: flex; justify-content: center; gap: 28rpx; margin: 18rpx 0 6rpx; font-size: 22rpx; color: $nx-text-dim; }
.legend text { display: flex; align-items: center; gap: 6rpx; }
.lg { width: 28rpx; height: 28rpx; line-height: 28rpx; text-align: center; border-radius: 50%; color: #fff; font-size: 16rpx; }
.lg-lu { background: $mut-lu; } .lg-quan { background: $mut-quan; } .lg-ke { background: $mut-ke; } .lg-ji { background: $mut-ji; }

.actions { display: flex; gap: 24rpx; margin: 24rpx 8rpx 0; }
.actions button { flex: 1; }
.answer { margin: 28rpx 8rpx 0; padding: 32rpx; background: $nx-card; border: 1rpx solid $nx-border; border-radius: 16rpx; }
.a-title { display: block; color: $nx-accent-ziwei; font-size: 32rpx; font-weight: 600; margin-bottom: 16rpx; letter-spacing: 2rpx; }
.a-body { display: block; line-height: 2; font-size: 29rpx; color: $nx-text; }
.foot-space { height: 80rpx; }

/* ===== 点宫详情弹层 ===== */
.mask { position: fixed; inset: 0; z-index: 10; background: rgba(0, 0, 0, .55); display: flex; align-items: flex-end; }
.sheet { width: 100%; max-height: 76vh; background: $nx-bg-3; border-top-left-radius: 28rpx; border-top-right-radius: 28rpx; border-top: 4rpx solid $nx-accent-ziwei; }
.sheet-head { display: flex; align-items: center; justify-content: space-between; padding: 30rpx 36rpx; border-bottom: 1rpx solid $nx-border; }
.sheet-title { font-size: 34rpx; color: $nx-accent-ziwei; font-weight: 700; }
.sheet-close { font-size: 34rpx; color: $nx-text-dim; padding: 0 12rpx; }
.sheet-body { padding: 20rpx 36rpx 60rpx; }
.sec { margin-top: 28rpx; }
.sec-t { display: block; font-size: 26rpx; color: $nx-text-dim; letter-spacing: 2rpx; margin-bottom: 12rpx; border-left: 6rpx solid $nx-accent-ziwei; padding-left: 14rpx; }
.star-line { display: flex; align-items: baseline; gap: 12rpx; padding: 8rpx 0; }
.sl-name { font-size: 30rpx; color: $nx-text; font-weight: 600; }
.sl-bri { font-size: 22rpx; color: $nx-text-dim; }
.sl-mut { font-size: 22rpx; font-weight: 700; }
.sl-empty { font-size: 26rpx; color: $nx-text-muted; }
.misc { display: block; font-size: 26rpx; color: $nx-text; line-height: 1.8; }
</style>
