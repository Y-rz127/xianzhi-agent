<template>
  <view class="page" :class="themeClass">
    <view class="nav" @tap="back">‹</view>
    <scroll-view scroll-y class="scroll">
      <view class="hero">
        <text>每日黄历</text>
        <small class="sub">传统民俗文化参考，宜忌随日而变，理性看待</small>
      </view>

      <!-- 日期切换 -->
      <view class="date-bar">
        <view class="dbtn" @tap="shiftDay(-1)">‹ 前一天</view>
        <picker mode="date" :value="dateInput" start="1900-01-01" end="2100-12-31" @change="onDatePick">
          <view class="dbtn current">{{ dateInput }}</view>
        </picker>
        <view class="dbtn" @tap="shiftDay(1)">后一天 ›</view>
        <view class="dbtn today" @tap="goToday">回今天</view>
      </view>

      <!-- 当日黄历 -->
      <view v-if="day" class="panel">
        <view class="day-head">
          <text class="day-solar">{{ day.date }} {{ day.solar.slice(-3) }}</text>
          <view class="badges">
            <text class="badge gold">{{ day.lunar.text }}</text>
            <text class="badge">{{ day.lunar.day_gz }}日</text>
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
          <picker mode="selector" :range="items" :value="itemIndex" @change="onItemPick">
            <view class="zpick wide">{{ zejiItem || '选择事项' }}</view>
          </picker>
          <picker mode="selector" :range="avoidRange" :value="avoidIndex" @change="onAvoidPick">
            <view class="zpick">{{ avoidRange[avoidIndex] }}</view>
          </picker>
        </view>
        <view class="zrow">
          <picker mode="date" :value="zejiStart" start="1900-01-01" end="2100-12-31" @change="onZejiStartPick">
            <view class="zpick">{{ zejiStart || '起始日期' }}</view>
          </picker>
          <text class="zsep">至</text>
          <picker mode="date" :value="zejiEnd" :start="zejiStart" end="2100-12-31" @change="onZejiEndPick">
            <view class="zpick">{{ zejiEnd || '截止日期' }}</view>
          </picker>
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
function onDatePick(e: any) {
  dateInput.value = e.detail.value
  loadDay()
}
function jumpTo(iso: string) {
  dateInput.value = iso
  loadDay()
  uni.pageScrollTo({ scrollTop: 0, duration: 250 })
}

function onItemPick(e: any) {
  itemIndex.value = Number(e.detail.value)
}
function onAvoidPick(e: any) {
  avoidIndex.value = Number(e.detail.value)
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
.badge { padding: 6rpx 18rpx; border-radius: 999rpx; font-size: 22rpx; border: 1rpx solid $nx-border; color: $nx-text-dim; }
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
.info { width: 50%; box-sizing: border-box; padding: 10rpx 8rpx; display: flex; gap: 12rpx; }
.info .k { color: $nx-text-muted; font-size: 24rpx; flex-shrink: 0; }
.info .v { color: $nx-text; font-size: 24rpx; }
.info .v.small { font-size: 22rpx; line-height: 1.5; }
.info:nth-child(8) { width: 100%; }

.positions { display: flex; flex-wrap: wrap; margin-top: 18rpx; padding-top: 20rpx; border-top: 1rpx solid $nx-border; }
.pos { width: 25%; box-sizing: border-box; text-align: center; padding: 8rpx 0; }
.pos:nth-child(n+5) { padding-top: 18rpx; }
.pos .k { display: block; color: $nx-text-muted; font-size: 22rpx; }
.pos .v { display: block; color: $nx-gold-light; font-size: 28rpx; font-weight: 600; margin-top: 6rpx; }

.fold { margin-top: 24rpx; text-align: center; color: $nx-text-dim; font-size: 25rpx; padding: 14rpx; border: 1rpx dashed rgba(212, 175, 55, .25); border-radius: 12rpx; }
.shens { margin-top: 18rpx; }
.shen-line { display: block; font-size: 24rpx; color: $nx-text; line-height: 1.8; }
.good { color: $nx-yi; font-weight: 600; }
.bad { color: $nx-ji; font-weight: 600; }

/* 时辰 */
.hours { display: flex; flex-wrap: wrap; gap: 12rpx; }
.hour { width: calc(25% - 9rpx); box-sizing: border-box; text-align: center; padding: 16rpx 4rpx; border: 1rpx solid $nx-border; border-radius: 14rpx; opacity: .68; }
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
.month { display: flex; flex-wrap: wrap; }
.mcell { width: 14.28%; box-sizing: border-box; height: 128rpx; padding: 8rpx 2rpx; text-align: center; border: 1rpx solid $nx-border; position: relative; }
.mcell.cur { background: rgba(212, 175, 55, .15); border-color: $nx-border-strong; }
.mcell .md { display: block; font-size: 26rpx; color: $nx-text; }
.mcell .ml { display: block; font-size: 17rpx; color: $nx-text-muted; margin-top: 2rpx; overflow: hidden; }
.mcell .mf { display: block; font-size: 17rpx; color: $nx-ji; margin-top: 2rpx; overflow: hidden; }
.mcell .ms { position: absolute; top: 2rpx; right: 4rpx; font-size: 16rpx; color: $nx-gold-light; }

/* 择吉 */
.zrow { display: flex; align-items: center; gap: 14rpx; margin-bottom: 18rpx; }
.zrow picker { flex: 1; min-width: 0; }
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

.footer { text-align: center; color: $nx-text-muted; font-size: 21rpx; padding: 24rpx 60rpx 60rpx; line-height: 1.7; }
</style>
