<template>
  <view class="page" :class="themeClass">
    <view class="meteor meteor-1" v-if="themeClass === 't-dark'"></view>
    <view class="meteor meteor-2" v-if="themeClass === 't-dark'"></view>
    <view class="meteor meteor-3" v-if="themeClass === 't-dark'"></view>
    <view class="nav" @tap="back">‹</view>
    <scroll-view scroll-y class="scroll">
      <view class="hero">
        <text>每日黄历</text>
        <small class="sub">传统民俗文化参考，宜忌随日而变，理性看待</small>
      </view>

      <!-- 日期切换 -->
      <view class="date-bar">
        <view class="dbtn" @tap="shiftDay(-1)">‹ 前一天</view>
        <view class="dbtn current" @tap="openDateSheet('main')">{{ dateInput }}</view>
        <view class="dbtn" @tap="shiftDay(1)">后一天 ›</view>
        <view class="dbtn today" @tap="goToday">回今天</view>
      </view>

      <!-- 当日黄历 -->
      <view v-if="day" class="panel">
        <view class="day-head">
          <text class="day-solar">{{ day.date }} {{ day.solar.slice(-3) }}</text>
          <view class="badges">
            <text class="badge gold">{{ day.lunar.text }}</text>
            <text class="badge">{{ day.lunar.month_gz }}月{{ day.lunar.day_gz }}日</text>
            <text v-for="f in day.festivals" :key="'f' + f" class="badge red">{{ f }}</text>
            <text v-if="day.jieqi" class="badge green">{{ day.jieqi }}</text>
            <text v-if="day.tian_shen.luck === '吉'" class="badge gold">{{ day.tian_shen.name }}·{{ day.tian_shen.type }}</text>
          </view>
        </view>

        <view class="yiji">
          <view class="yi-block">
            <text class="yj-title yi">宜</text>
            <view class="chips">
              <text v-for="it in day.yi" :key="'y' + it" class="chip yi">{{ it }}</text>
            </view>
          </view>
          <view class="ji-block">
            <text class="yj-title ji">忌</text>
            <view class="chips">
              <text v-for="it in day.ji" :key="'j' + it" class="chip ji">{{ it }}</text>
            </view>
          </view>
        </view>

        <view class="infos">
          <view class="info"><text class="k">冲煞</text><text class="v">{{ day.chong.desc }} 煞{{ day.chong.sha }}</text></view>
          <view class="info"><text class="k">值神</text><text class="v">{{ day.tian_shen.name }}（{{ day.tian_shen.type }}·{{ day.tian_shen.luck }}）</text></view>
          <view class="info"><text class="k">建星</text><text class="v">{{ day.zhixing }}</text></view>
          <view class="info"><text class="k">九星</text><text class="v">{{ day.nine_star }}</text></view>
          <view class="info"><text class="k">二十八宿</text><text class="v">{{ day.xiu.name }}（{{ day.xiu.luck }}）</text></view>
          <view class="info"><text class="k">胎神占方</text><text class="v">{{ day.taishen }}</text></view>
          <view class="info"><text class="k">纳音五行</text><text class="v">{{ day.nayin }}</text></view>
          <view class="info"><text class="k">彭祖百忌</text><text class="v small">{{ day.pengzu.gan }}；{{ day.pengzu.zhi }}</text></view>
        </view>

        <view class="positions">
          <view v-for="p in positionList" :key="p.key" class="pos">
            <text class="k">{{ p.label }}</text><text class="v">{{ p.value }}</text>
          </view>
        </view>

        <view class="fold" @tap="shensFolded = !shensFolded">
          {{ shensFolded ? '吉神宜趋 / 凶煞宜忌 ▾' : '收起 ▴' }}
        </view>
        <view v-if="!shensFolded" class="shens">
          <text class="shen-line"><text class="good">吉神宜趋　</text>{{ day.jishen.join(' · ') }}</text>
          <text class="shen-line"><text class="bad">凶煞宜忌　</text>{{ day.xiongsha.join(' · ') }}</text>
        </view>
      </view>
      <view v-else class="panel placeholder">{{ loading ? '推演历书中…' : '加载失败，下拉重试' }}</view>

      <!-- 十二时辰吉凶 -->
      <view v-if="day" class="panel">
        <text class="sec-title">十二时辰吉凶</text>
        <view class="hours">
          <view
            v-for="(h, i) in day.hours" :key="h.zhi"
            :class="['hour', h.luck === '吉' && 'lucky', activeHour === i && 'active']"
            @tap="activeHour = activeHour === i ? -1 : i"
          >
            <text class="hz">{{ h.zhi }}时</text>
            <text class="hr">{{ h.range }}</text>
            <text class="hl">{{ h.luck }}</text>
          </view>
        </view>
        <view v-if="activeHour >= 0 && day.hours[activeHour]" class="hour-detail">
          <text class="hd-title">{{ day.hours[activeHour].zhi }}时（{{ day.hours[activeHour].range }}）· {{ day.hours[activeHour].tian_shen }} · {{ day.hours[activeHour].luck }} · 冲{{ day.hours[activeHour].chong }}</text>
          <text class="hd-line"><text class="good">宜　　</text>{{ day.hours[activeHour].yi.join('、') || '无' }}</text>
          <text class="hd-line"><text class="bad">忌　　</text>{{ day.hours[activeHour].ji.join('、') || '无' }}</text>
        </view>
      </view>

      <!-- 本月概览 -->
      <view v-if="monthDays.length" class="panel">
        <text class="sec-title">本月概览（{{ monthLabel }}）</text>
        <view class="month">
          <view
            v-for="m in monthDays" :key="m.date"
            :class="['mcell', m.date === (day && day.date) && 'cur']"
            @tap="jumpTo(m.date)"
          >
            <text class="md">{{ Number(m.date.slice(8)) }}</text>
            <text class="ml">{{ m.lunar_day }}</text>
            <text v-if="m.festivals.length || m.jieqi" class="mf">{{ m.festivals[0] || m.jieqi }}</text>
            <text v-if="m.tianshe" class="ms">赦</text>
          </view>
        </view>
      </view>

      <!-- 择吉 -->
      <view class="panel">
        <text class="sec-title">择吉</text>
        <view class="zrow">
          <view class="zpick wide" @tap="openSheet('item')">{{ zejiItem || '选择事项' }}</view>
          <view class="zpick" @tap="openSheet('avoid')">{{ avoidRange[avoidIndex] }}</view>
        </view>
        <view class="zrow">
          <view class="zpick" @tap="openDateSheet('start')">{{ zejiStart || '起始日期' }}</view>
          <text class="zsep">至</text>
          <view class="zpick" @tap="openDateSheet('end')">{{ zejiEnd || '截止日期' }}</view>
        </view>
        <button class="zeji-btn" :loading="zejiLoading" :disabled="zejiLoading" @tap="runZeji">
          {{ zejiLoading ? '推算中…' : '查询吉日' }}
        </button>

        <view v-if="zejiDays" class="zresults">
          <view v-if="!zejiDays.length" class="placeholder">该区间内没有宜「{{ zejiItem }}」的日子，试着放宽区间或去掉生肖限制。</view>
          <view v-for="z in zejiDays" :key="z.date" class="zcard" @tap="jumpTo(z.date)">
            <view class="zl">
              <text class="zd">{{ z.date }}</text>
              <text class="zsub">{{ z.day_gz }}日 · {{ z.chong }} · 值神{{ z.tian_shen }}</text>
            </view>
            <text v-if="z.note" class="zstar">{{ starText(z.stars) }} {{ z.note }}</text>
          </view>
        </view>
      </view>

      <view class="footer">黄历宜忌源自传统历法推演，仅供民俗文化参考，不构成任何决策建议。</view>
    </scroll-view>

    <!-- 事项/生肖选择弹层（自定义底部弹层，字号可控并随主题配色） -->
    <view v-if="showSheet" class="sheet-mask" @tap="showSheet = false">
      <view class="sheet" @tap.stop>
        <view class="sheet-head">
          <text class="sheet-title">{{ sheetTitle }}</text>
          <text class="sheet-close" @tap="showSheet = false">✕</text>
        </view>
        <scroll-view scroll-y class="sheet-body">
          <text
            v-for="(opt, i) in sheetOptions" :key="i"
            :class="['sheet-item', sheetIndex === i && 'active']"
            @tap="pickOption(i)"
          >{{ opt }}</text>
        </scroll-view>
      </view>
    </view>
    <!-- 日期选择弹层（年/月/日三列，字号可控并随主题配色） -->
    <view v-if="showDateSheet" class="sheet-mask" @tap="showDateSheet = false">
      <view class="sheet" @tap.stop>
        <view class="sheet-head">
          <text class="sheet-cancel" @tap="showDateSheet = false">取消</text>
          <text class="sheet-title">{{ datePreview }}</text>
          <text class="sheet-ok" @tap="commitDate">确定</text>
        </view>
        <view class="date-cols">
          <scroll-view scroll-y class="date-col">
            <text
              v-for="y in dpYears" :key="y"
              :class="['date-item', dpY === y && 'active']"
              @tap="dpY = y"
            >{{ y }}年</text>
          </scroll-view>
          <scroll-view scroll-y class="date-col">
            <text
              v-for="m in 12" :key="m"
              :class="['date-item', dpM === m && 'active']"
              @tap="dpM = m"
            >{{ m }}月</text>
          </scroll-view>
          <scroll-view scroll-y class="date-col">
            <text
              v-for="d in dpDays" :key="d"
              :class="['date-item', dpD === d && 'active']"
              @tap="dpD = d"
            >{{ d }}日</text>
          </scroll-view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useTheme } from '@/composables/useTheme'
import { onMounted } from 'vue'
import {
  getHuangLiDay, getHuangLiItems, getHuangLiRange, getHuangLiZeji,
  type HuangLiDay, type HuangLiRangeDay, type HuangLiZejiDay,
} from '@/api'

const { themeClass } = useTheme()

const zodiacs = ['鼠', '牛', '虎', '兔', '龙', '蛇', '马', '羊', '猴', '鸡', '狗', '猪']
const avoidRange = ['不限生肖', ...zodiacs]

function fmt(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
/** iOS 微信对带 '-' 的 Date 字符串解析不稳，手动拆解后平移天数 */
function shiftIso(iso: string, days: number): string {
  const [y, m, dd] = iso.split('-').map(Number)
  return fmt(new Date(y, m - 1, dd + days))
}

const dateInput = ref(fmt(new Date()))
const day = ref<HuangLiDay | null>(null)
const loading = ref(true)
const shensFolded = ref(true)
const activeHour = ref(-1)
const monthDays = ref<HuangLiRangeDay[]>([])

const items = ref<string[]>([])
const itemIndex = ref(0)
const avoidIndex = ref(0)
const zejiItem = computed(() => items.value[itemIndex.value] || '')
const zejiStart = ref(fmt(new Date()))
const zejiEnd = ref(shiftIso(fmt(new Date()), 29))
const zejiLoading = ref(false)
const zejiDays = ref<HuangLiZejiDay[] | null>(null)

const monthLabel = computed(() => dateInput.value.slice(0, 7))
const positionList = computed(() => {
  const p = day.value?.positions
  if (!p) return []
  return [
    { key: 'cai', label: '财神', value: p.cai },
    { key: 'xi', label: '喜神', value: p.xi },
    { key: 'fu', label: '福神', value: p.fu },
    { key: 'yang_gui', label: '阳贵', value: p.yang_gui },
    { key: 'yin_gui', label: '阴贵', value: p.yin_gui },
    { key: 'five_ghost', label: '五鬼凶', value: p.five_ghost },
    { key: 'sheng_men', label: '生门吉', value: p.sheng_men },
    { key: 'si_men', label: '死门凶', value: p.si_men },
  ]
})

function toast(msg: string) {
  uni.showToast({ title: msg, icon: 'none', duration: 2200 })
}

function starText(n: number) {
  return '★'.repeat(Math.min(n, 3))
}

async function loadDay() {
  loading.value = true
  activeHour.value = -1
  try {
    day.value = await getHuangLiDay(dateInput.value)
    // 整月简报（range 上限 31 天，正好覆盖最长公历月）
    const [y, m] = dateInput.value.split('-').map(Number)
    const first = fmt(new Date(y, m - 1, 1))
    const last = fmt(new Date(y, m, 0))
    try {
      monthDays.value = await getHuangLiRange(first, last)
    } catch {
      monthDays.value = []
    }
  } catch (e) {
    toast(e instanceof Error ? e.message : '获取黄历失败')
  } finally {
    loading.value = false
  }
}

function shiftDay(delta: number) {
  dateInput.value = shiftIso(dateInput.value, delta)
  loadDay()
}
function goToday() {
  dateInput.value = fmt(new Date())
  loadDay()
}
function jumpTo(iso: string) {
  dateInput.value = iso
  loadDay()
  uni.pageScrollTo({ scrollTop: 0, duration: 250 })
}

/* 自定义日期选择弹层（原生 date picker 弹层字号偏小且不受主题控制，故改用自绘三列） */
const showDateSheet = ref(false)
const dateTarget = ref<'main' | 'start' | 'end'>('main')
const dpY = ref(2026)
const dpM = ref(1)
const dpD = ref(1)
const dpYears = Array.from({ length: 2100 - 1900 + 1 }, (_, i) => 1900 + i)
const dpDays = computed(() => {
  const max = new Date(dpY.value, dpM.value, 0).getDate()
  return Array.from({ length: max }, (_, i) => i + 1)
})
const datePreview = computed(() => {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${dpY.value}-${pad(dpM.value)}-${pad(dpD.value)}`
})

function openDateSheet(target: 'main' | 'start' | 'end') {
  const v = target === 'main' ? dateInput.value : target === 'start' ? zejiStart.value : zejiEnd.value
  const [y, m, d] = (v || fmt(new Date())).split('-').map(Number)
  dpY.value = y
  dpM.value = m
  dpD.value = d
  dateTarget.value = target
  showDateSheet.value = true
}
function commitDate() {
  const iso = datePreview.value
  const maxD = new Date(dpY.value, dpM.value, 0).getDate()
  if (dpD.value > maxD) dpD.value = maxD
  if (dateTarget.value === 'main') {
    dateInput.value = iso
    loadDay()
  } else if (dateTarget.value === 'start') {
    zejiStart.value = iso
    if (zejiEnd.value && iso > zejiEnd.value) zejiEnd.value = iso
  } else {
    zejiEnd.value = iso
    if (zejiStart.value && iso < zejiStart.value) zejiStart.value = iso
  }
  showDateSheet.value = false
}

/* 自定义事项/生肖选择弹层（原生 picker 弹层字号偏小且不受主题控制，故改用自绘底部弹层） */
const showSheet = ref(false)
const sheetKind = ref<'item' | 'avoid'>('item')
const sheetIndex = ref(0)
const sheetOptions = computed(() => (sheetKind.value === 'item' ? items.value : avoidRange))
const sheetTitle = computed(() => (sheetKind.value === 'item' ? '择吉事项' : '冲煞生肖'))

function openSheet(kind: 'item' | 'avoid') {
  sheetKind.value = kind
  sheetIndex.value = kind === 'item' ? itemIndex.value : avoidIndex.value
  showSheet.value = true
}
function pickOption(i: number) {
  if (sheetKind.value === 'item') itemIndex.value = i
  else avoidIndex.value = i
  showSheet.value = false
}

async function runZeji() {
  if (!zejiItem.value) return toast('请先选择择吉事项')
  if (!zejiStart.value || !zejiEnd.value) return toast('请选择起止日期')
  zejiLoading.value = true
  try {
    zejiDays.value = await getHuangLiZeji(zejiItem.value, zejiStart.value, zejiEnd.value, avoidRange[avoidIndex.value] === '不限生肖' ? '' : avoidRange[avoidIndex.value])
    if (!zejiDays.value.length) toast('该区间无合适吉日')
  } catch (e) {
    toast(e instanceof Error ? e.message : '择吉失败')
  } finally {
    zejiLoading.value = false
  }
}

async function loadItems() {
  try {
    items.value = await getHuangLiItems()
    const i = items.value.indexOf('嫁娶')
    itemIndex.value = i >= 0 ? i : 0
  } catch {
    items.value = []
  }
}

function back() {
  uni.navigateBack()
}

onMounted(() => {
  loadDay()
  loadItems()
})
</script>

<style lang="scss">
.page { min-height: 100vh; background: linear-gradient(180deg, $nx-bg, $nx-bg-2 55%, $nx-bg-3); color: $nx-text; }
.scroll { height: 100vh; }
.nav { position: fixed; z-index: 2; top: 50rpx; left: 28rpx; font-size: 60rpx; }
.hero { text-align: center; padding: 140rpx 0 48rpx; }
.hero text, .hero .sub { display: block; }
.hero text { font-size: 60rpx; letter-spacing: 14rpx; color: $nx-accent-huangli; }
.hero .sub { margin-top: 20rpx; color: $nx-text-dim; font-size: 26rpx; }

.panel { margin: 28rpx 36rpx; padding: 36rpx 32rpx; border: 1rpx solid $nx-border; border-radius: 24rpx; background: $nx-card; }
.sec-title { display: block; color: $nx-gold-light; font-size: 30rpx; font-weight: 600; letter-spacing: 2rpx; margin-bottom: 24rpx; }
.placeholder { color: $nx-text-muted; font-size: 26rpx; text-align: center; padding: 24rpx 0; }

/* 日期切换 */
.date-bar { display: flex; justify-content: center; align-items: center; gap: 14rpx; margin: 0 36rpx; flex-wrap: wrap; }
.dbtn { padding: 16rpx 24rpx; border: 1rpx solid $nx-border; border-radius: 14rpx; color: $nx-text-dim; font-size: 26rpx; background: rgba(255,255,255,.03); }
.dbtn:active { color: $nx-gold-light; border-color: $nx-border-strong; }
.dbtn.current { color: $nx-gold-light; border-color: $nx-border-strong; font-weight: 600; }
.dbtn.today { color: $nx-gold-light; border-color: $nx-border-strong; }

/* 当日 */
.day-head { text-align: center; margin-bottom: 24rpx; }
.day-solar { display: block; font-size: 44rpx; font-weight: 700; color: $nx-gold-light; letter-spacing: 2rpx; }
.badges { display: flex; flex-wrap: wrap; justify-content: center; gap: 12rpx; margin-top: 16rpx; }
.badge { padding: 6rpx 18rpx; border-radius: 999rpx; font-size: 24rpx; border: 1rpx solid $nx-border; color: $nx-text-dim; }
.badge.gold { color: $nx-gold-light; border-color: $nx-border-strong; background: rgba(212, 175, 55, .1); }
.badge.red { color: $nx-ji; border-color: rgba(231, 155, 161, .45); }
.badge.green { color: $nx-yi; border-color: rgba(143, 206, 159, .45); }

.yiji { display: flex; flex-direction: column; gap: 22rpx; }
.yj-title { display: inline-block; width: 64rpx; height: 64rpx; line-height: 64rpx; text-align: center; border-radius: 14rpx; font-size: 34rpx; font-weight: 700; }
.yj-title.yi { background: rgba(96, 158, 110, .18); color: $nx-yi; border: 1rpx solid rgba(143, 206, 159, .45); }
.yj-title.ji { background: rgba(181, 75, 98, .16); color: $nx-ji; border: 1rpx solid rgba(231, 155, 161, .45); }
.yi-block, .ji-block { display: flex; align-items: flex-start; gap: 20rpx; }
.chips { display: flex; flex-wrap: wrap; gap: 12rpx; flex: 1; padding-top: 8rpx; }
.chip { padding: 8rpx 18rpx; border-radius: 10rpx; font-size: 26rpx; }
.chip.yi { color: $nx-yi; background: rgba(96, 158, 110, .12); border: 1rpx solid rgba(143, 206, 159, .3); }
.chip.ji { color: $nx-ji; background: rgba(181, 75, 98, .1); border: 1rpx solid rgba(231, 155, 161, .3); }

.infos { display: flex; flex-wrap: wrap; margin-top: 28rpx; border-top: 1rpx solid $nx-border; padding-top: 24rpx; }
.info { width: 50%; box-sizing: border-box; padding: 12rpx 8rpx; display: flex; gap: 12rpx; }
.info .k { color: $nx-text-muted; font-size: 26rpx; flex-shrink: 0; }
.info .v { color: $nx-text; font-size: 28rpx; line-height: 1.4; }
.info .v.small { font-size: 26rpx; line-height: 1.5; }
.info:nth-child(8) { width: 100%; }

.positions { display: flex; flex-wrap: wrap; margin-top: 18rpx; padding-top: 20rpx; border-top: 1rpx solid $nx-border; }
.pos { width: 25%; box-sizing: border-box; text-align: center; padding: 8rpx 0; }
.pos:nth-child(n+5) { padding-top: 18rpx; }
.pos .k { display: block; color: $nx-text-muted; font-size: 24rpx; }
.pos .v { display: block; color: $nx-gold-light; font-size: 32rpx; font-weight: 600; margin-top: 6rpx; }

.fold { margin-top: 24rpx; text-align: center; color: $nx-text-dim; font-size: 25rpx; padding: 14rpx; border: 1rpx dashed rgba(212, 175, 55, .25); border-radius: 12rpx; }
.shens { margin-top: 18rpx; }
.shen-line { display: block; font-size: 27rpx; color: $nx-text; line-height: 1.8; }
.good { color: $nx-yi; font-weight: 600; }
.bad { color: $nx-ji; font-weight: 600; }

/* 时辰：4 列 × 3 行 */
.hours { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12rpx; }
.hour { box-sizing: border-box; text-align: center; padding: 16rpx 4rpx; border: 1rpx solid $nx-border; border-radius: 14rpx; opacity: .68; }
.hour.lucky { opacity: 1; border-color: $nx-border-strong; background: rgba(212, 175, 55, .08); }
.hour.active { border-color: $nx-gold; background: rgba(212, 175, 55, .16); }
.hour .hz { display: block; font-size: 28rpx; font-weight: 600; color: $nx-gold-light; }
.hour .hr { display: block; font-size: 18rpx; color: $nx-text-muted; margin-top: 4rpx; }
.hour .hl { display: block; font-size: 22rpx; margin-top: 4rpx; }
.hour.lucky .hl { color: $nx-yi; }
.hour:not(.lucky) .hl { color: $nx-ji; }
.hour-detail { margin-top: 20rpx; padding: 20rpx; background: $nx-bg-3; border: 1rpx solid $nx-border; border-radius: 14rpx; }
.hd-title { display: block; font-size: 25rpx; color: $nx-gold-light; margin-bottom: 10rpx; }
.hd-line { display: block; font-size: 24rpx; color: $nx-text; line-height: 1.8; }

/* 月概览 */
.month { display: grid; grid-template-columns: repeat(6, 1fr); }
.mcell { box-sizing: border-box; min-height: 140rpx; padding: 10rpx 4rpx 8rpx; text-align: center; border: 1rpx solid $nx-border; position: relative; }
.mcell.cur { background: rgba(212, 175, 55, .15); border-color: $nx-border-strong; }
.mcell .md { display: block; font-size: 30rpx; color: $nx-text; line-height: 1.2; }
.mcell .ml { display: block; font-size: 21rpx; color: $nx-text-dim; margin-top: 4rpx; line-height: 1.3; }
.mcell .mf { display: block; font-size: 21rpx; color: $nx-ji; margin-top: 4rpx; line-height: 1.3; }
.mcell .ms { position: absolute; top: 4rpx; right: 6rpx; font-size: 20rpx; color: $nx-gold-light; }

/* 择吉 */
.zrow { display: flex; align-items: center; gap: 14rpx; margin-bottom: 18rpx; }
.zrow .zpick { flex: 1; min-width: 0; }
.zpick { padding: 18rpx 20rpx; background: $nx-bg-3; border: 1rpx solid $nx-border; border-radius: 12rpx; color: $nx-text; font-size: 26rpx; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.zpick.wide { font-weight: 600; color: $nx-gold-light; }
.zsep { color: $nx-text-muted; font-size: 24rpx; flex-shrink: 0; }
.zeji-btn { margin-top: 12rpx; padding: 24rpx; background: linear-gradient(135deg, #b58b35, #e7bd67); color: #271b08; font-size: 30rpx; font-weight: 600; border-radius: 16rpx; letter-spacing: 4rpx; }
.zeji-btn[disabled] { opacity: .6; }
.zresults { margin-top: 24rpx; }
.zcard { display: flex; justify-content: space-between; align-items: center; gap: 16rpx; padding: 20rpx 22rpx; margin-bottom: 14rpx; border: 1rpx solid $nx-border; border-radius: 14rpx; background: rgba(255, 255, 255, .03); }
.zcard:active { border-color: $nx-border-strong; }
.zl { flex: 1; min-width: 0; }
.zd { display: block; font-size: 28rpx; color: $nx-gold-light; font-weight: 600; }
.zsub { display: block; font-size: 22rpx; color: $nx-text-dim; margin-top: 6rpx; }
.zstar { flex-shrink: 0; font-size: 22rpx; color: $nx-gold-light; text-align: right; max-width: 40%; }

/* 事项/生肖选择弹层 */
.sheet-mask { position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 999; background: rgba(0, 0, 0, .55); display: flex; align-items: flex-end; }
.sheet { width: 100%; max-height: 72vh; background: $nx-bg-3; border-top-left-radius: 28rpx; border-top-right-radius: 28rpx; border-top: 4rpx solid $nx-accent-huangli; display: flex; flex-direction: column; overflow: hidden; padding-bottom: env(safe-area-inset-bottom); }
.sheet-head { display: flex; align-items: center; justify-content: space-between; padding: 30rpx 36rpx; border-bottom: 1rpx solid $nx-border; flex-shrink: 0; }
.sheet-title { font-size: 34rpx; color: $nx-gold-light; font-weight: 700; letter-spacing: 2rpx; }
.sheet-close { font-size: 36rpx; color: $nx-text-dim; padding: 0 12rpx; }
.sheet-body { height: 56vh; max-height: 56vh; padding: 10rpx 0 30rpx; }
.sheet-item { display: block; padding: 26rpx 40rpx; font-size: 34rpx; color: $nx-text; text-align: center; line-height: 1.5; }
.sheet-item.active { color: $nx-gold-light; font-weight: 700; background: rgba(212, 175, 55, .12); }
.sheet-item:active { background: rgba(212, 175, 55, .08); }

/* 日期选择弹层（年/月/日三列） */
.sheet-cancel { font-size: 32rpx; color: $nx-text-dim; padding: 0 12rpx; }
.sheet-ok { font-size: 32rpx; color: $nx-gold-light; font-weight: 600; padding: 0 12rpx; }
.date-cols { display: flex; height: 52vh; }
.date-col { flex: 1; }
.date-item { display: block; padding: 26rpx 6rpx; font-size: 34rpx; color: $nx-text; text-align: center; line-height: 1.5; }
.date-item.active { color: $nx-gold-light; font-weight: 700; background: rgba(212, 175, 55, .12); }
.date-item:active { background: rgba(212, 175, 55, .08); }

.footer { text-align: center; color: $nx-text-muted; font-size: 21rpx; padding: 24rpx 60rpx 60rpx; line-height: 1.7; }
</style>
