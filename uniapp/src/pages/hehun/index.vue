<template>
  <view class="page" :class="themeClass">
    <view class="meteor meteor-1" v-if="themeClass === 't-dark'"></view>
    <view class="meteor meteor-2" v-if="themeClass === 't-dark'"></view>
    <scroll-view class="scroll" scroll-y>
      <!-- 状态栏占位 -->
      <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

      <!-- 页面头 -->
      <view class="page-header">
        <view class="back-btn" @tap="goBack">
          <text class="back-arrow">‹</text>
        </view>
        <text class="page-title display-font">合婚分析</text>
        <text class="page-sub">输入双方出生信息，探寻命理姻缘</text>
      </view>

      <!-- 甲方卡片 -->
      <view class="person-card person-a">
        <view class="card-gradient-top gradient-a"></view>
        <view class="card-body">
          <view class="card-head">
            <view class="badge badge-a">甲</view>
            <text class="card-title display-font">甲方信息</text>
          </view>

          <view class="form-row">
            <text class="label">出生日期</text>
            <picker mode="date" :value="a.date" :end="today" @change="(e: any) => a.date = e.detail.value">
              <view class="picker">
                <text class="picker-text">{{ a.date || '选择日期' }}</text>
                <text class="picker-icon">▤</text>
              </view>
            </picker>
          </view>

          <view class="form-row">
            <text class="label">出生时辰</text>
            <picker mode="time" :value="a.time" @change="(e: any) => a.time = e.detail.value">
              <view class="picker">
                <text class="picker-text">{{ a.time || '选择时间' }}</text>
                <text class="picker-icon">◷</text>
              </view>
            </picker>
          </view>

          <view class="form-row">
            <text class="label">性别</text>
            <view class="seg-group">
              <text :class="['seg', a.gender === '男' && 'active']" @tap="a.gender = '男'">男</text>
              <text :class="['seg', a.gender === '女' && 'active']" @tap="a.gender = '女'">女</text>
            </view>
          </view>

          <view class="form-row">
            <text class="label">出生地</text>
            <view class="picker place-picker" @tap="openRegionPicker('a')">
              <text class="picker-text">{{ a.place || '选择地点（校正真太阳时）' }}</text>
              <text class="picker-icon">📍</text>
            </view>
            <text v-if="solarOffsetA !== 0" class="solar-hint">真太阳时{{ solarOffsetA > 0 ? '+' : '' }}{{ solarOffsetA }}分</text>
          </view>
        </view>
      </view>

      <!-- 能量连接器 -->
      <view class="connector">
        <view class="line line-left"></view>
        <view class="connector-icon">
          <text class="connector-glyph">⚡</text>
        </view>
        <view class="line line-right"></view>
      </view>

      <!-- 乙方卡片 -->
      <view class="person-card person-b">
        <view class="card-gradient-top gradient-b"></view>
        <view class="card-body">
          <view class="card-head">
            <view class="badge badge-b">乙</view>
            <text class="card-title display-font">乙方信息</text>
          </view>

          <view class="form-row">
            <text class="label">出生日期</text>
            <picker mode="date" :value="b.date" :end="today" @change="(e: any) => b.date = e.detail.value">
              <view class="picker">
                <text class="picker-text">{{ b.date || '选择日期' }}</text>
                <text class="picker-icon">▤</text>
              </view>
            </picker>
          </view>

          <view class="form-row">
            <text class="label">出生时辰</text>
            <picker mode="time" :value="b.time" @change="(e: any) => b.time = e.detail.value">
              <view class="picker">
                <text class="picker-text">{{ b.time || '选择时间' }}</text>
                <text class="picker-icon">◷</text>
              </view>
            </picker>
          </view>

          <view class="form-row">
            <text class="label">性别</text>
            <view class="seg-group">
              <text :class="['seg', b.gender === '男' && 'active']" @tap="b.gender = '男'">男</text>
              <text :class="['seg', b.gender === '女' && 'active']" @tap="b.gender = '女'">女</text>
            </view>
          </view>

          <view class="form-row">
            <text class="label">出生地</text>
            <view class="picker place-picker" @tap="openRegionPicker('b')">
              <text class="picker-text">{{ b.place || '选择地点（校正真太阳时）' }}</text>
              <text class="picker-icon">📍</text>
            </view>
            <text v-if="solarOffsetB !== 0" class="solar-hint">真太阳时{{ solarOffsetB > 0 ? '+' : '' }}{{ solarOffsetB }}分</text>
          </view>
        </view>
      </view>

      <!-- 子时流派：排盘引擎默认晚子时（子正换日），不再提供手动切换 -->
      <view class="sect-hint">
        排盘引擎默认为晚子时（子正换日，23:00~24:00 算次日）
      </view>

      <!-- 开始分析按钮 -->
      <view class="cta-wrap">
        <view
          :class="['cta-btn', (loading || !canSubmit) && 'disabled']"
          @tap="onAnalyze"
        >
          <text class="cta-glyph">✦</text>
          <text class="cta-text">{{ loading ? '分析中…' : '开始分析' }}</text>
        </view>
      </view>

      <!-- 结果卡片 -->
      <view v-if="result" class="result-card">
        <view class="card-gradient-top gradient-result"></view>
        <view class="card-body">
          <view class="card-head">
            <view class="badge badge-result">☰</view>
            <text class="card-title display-font">合婚报告</text>
          </view>
          <text class="result-text">{{ result }}</text>
        </view>
      </view>

      <!-- 省市区选择器弹窗 -->
      <view v-if="showRegionPicker" class="region-picker-mask" @tap="showRegionPicker = false">
        <view class="region-picker" @tap.stop>
          <view class="rp-header">
            <view class="rp-tabs">
              <text :class="['rp-tab', 'active']">国内</text>
            </view>
            <text class="rp-confirm" @tap="confirmRegionPicker">确定</text>
          </view>
          <view class="rp-search">
            <text class="rp-search-icon">🔍</text>
            <input
              class="rp-search-input"
              v-model="regionSearchText"
              placeholder="搜索全国城市及地区"
              placeholder-class="rp-search-ph"
            />
          </view>
          <view class="rp-col-labels">
            <text class="rp-col-label">省份</text>
            <text class="rp-col-label">城市</text>
            <text class="rp-col-label">区县</text>
          </view>
          <view class="rp-columns">
            <scroll-view scroll-y :style="{ height: scrollHeight + 'px' }" class="rp-col">
              <text
                v-for="(p, pi) in filteredProvinces"
                :key="p.name"
                :class="['rp-item', regionSelProvince === p.name && 'active']"
                @tap="onSelectProvince(p.name)"
              >{{ p.name }}</text>
            </scroll-view>
            <scroll-view scroll-y :style="{ height: scrollHeight + 'px' }" class="rp-col">
              <text
                v-for="c in filteredCities"
                :key="c.name"
                :class="['rp-item', regionSelCity === c.name && 'active']"
                @tap="onSelectCity(c)"
              >{{ c.name }}</text>
            </scroll-view>
            <scroll-view scroll-y :style="{ height: scrollHeight + 'px' }" class="rp-col">
              <text
                v-for="d in filteredDistricts"
                :key="d.name"
                :class="['rp-item', regionSelDistrict === d.name && 'active']"
                @tap="regionSelDistrict = d.name"
              >{{ d.name }}</text>
            </scroll-view>
          </view>
        </view>
      </view>

      <view class="bottom-spacer"></view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch } from 'vue'
import { hehun } from '@/api'
import { useTheme } from '@/composables/useTheme'
import { regionData, type City } from '@/utils/region-data'


const { themeClass } = useTheme()
const today = new Date().toISOString().slice(0, 10)
const a = reactive({ date: '', time: '', gender: '男' as '男' | '女', place: '', longitude: 0 })
const b = reactive({ date: '', time: '', gender: '女' as '男' | '女', place: '', longitude: 0 })
const loading = ref(false)
const result = ref('')

// 排盘引擎默认晚子时（子正换日，sect=2），不再提供用户手动切换
const sect = 2 as const

/** 真太阳时修正量（分钟）。基准经度 120°E（北京时间），每度差 4 分钟 */
const solarOffsetA = computed(() => (a.longitude ? Math.round((120 - a.longitude) * 4) : 0))
const solarOffsetB = computed(() => (b.longitude ? Math.round((120 - b.longitude) * 4) : 0))

// ---- 省市区选择器弹窗状态 ----
const showRegionPicker = ref(false)
/** 当前编辑的卡片：'a'=甲方，'b'=乙方 */
const editingSide = ref<'a' | 'b'>('a')
const regionSearchText = ref('')
const regionSelProvince = ref('')
const regionSelCity = ref('')
const regionSelDistrict = ref('')
const regionSelLongitude = ref(0)
/** scroll-view 固定高度（px），uni-app 要求具体数值才能滚动 */
const scrollHeight = ref(380)

// 搜索过滤
const filteredProvinces = computed(() => {
  if (!regionSearchText.value) return regionData
  const kw = regionSearchText.value.trim()
  return regionData.filter(p =>
    p.name.includes(kw) ||
    p.cities.some(c => c.name.includes(kw)) ||
    p.cities.some(c => c.districts.some(d => d.name.includes(kw)))
  )
})
const filteredCities = computed(() => {
  const prov = regionData.find(p => p.name === regionSelProvince.value)
  if (!prov) return []
  return prov.cities
})
const filteredDistricts = computed(() => {
  const prov = regionData.find(p => p.name === regionSelProvince.value)
  if (!prov) return []
  const city = prov.cities.find(c => c.name === regionSelCity.value)
  if (!city) return []
  return city.districts
})

/** 搜索命中时自动定位到对应省市（用于搜区县名的情况） */
function autoLocateBySearch(kw: string) {
  for (const p of regionData) {
    for (const c of p.cities) {
      const match = c.districts.find(d => d.name.includes(kw))
      if (match) {
        regionSelProvince.value = p.name
        regionSelCity.value = c.name
        regionSelDistrict.value = match.name
        regionSelLongitude.value = c.longitude
        return true
      }
    }
  }
  for (const p of regionData) {
    const c = p.cities.find(city => city.name.includes(kw))
    if (c) {
      regionSelProvince.value = p.name
      regionSelCity.value = c.name
      regionSelLongitude.value = c.longitude
      if (c.districts.length > 0) regionSelDistrict.value = c.districts[0].name
      return true
    }
  }
  return false
}

function onSelectProvince(name: string) {
  regionSelProvince.value = name
  regionSelCity.value = ''
  regionSelDistrict.value = ''
  regionSearchText.value = ''
}
function onSelectCity(c: City) {
  regionSelCity.value = c.name
  regionSelLongitude.value = c.longitude
  if (c.districts.length > 0 && !c.districts.some(d => d.name === regionSelDistrict.value)) {
    regionSelDistrict.value = c.districts[0].name
  }
  regionSearchText.value = ''
}
watch(regionSearchText, (kw) => {
  const t = (kw || '').trim()
  if (!t) return
  autoLocateBySearch(t)
})

function openRegionPicker(side: 'a' | 'b') {
  editingSide.value = side
  const target = side === 'a' ? a : b
  // 已有选择时预填
  regionSearchText.value = ''
  regionSelProvince.value = ''
  regionSelCity.value = ''
  regionSelDistrict.value = ''
  regionSelLongitude.value = 0
  if (target.place) {
    const parts = target.place.split(' ')
    if (parts.length >= 2) {
      const prov = regionData.find(x => x.name === parts[0])
      if (prov) {
        regionSelProvince.value = prov.name
        const city = prov.cities.find(c => c.name === parts[1])
        if (city) {
          regionSelCity.value = city.name
          regionSelLongitude.value = city.longitude
          if (parts[2] && city.districts.some(d => d.name === parts[2])) {
            regionSelDistrict.value = parts[2]
          } else if (city.districts.length > 0) {
            regionSelDistrict.value = city.districts[0].name
          }
        }
      }
    }
  }
  showRegionPicker.value = true
}

function confirmRegionPicker() {
  if (regionSelProvince.value && regionSelCity.value) {
    const parts = [regionSelProvince.value, regionSelCity.value]
    if (regionSelDistrict.value) parts.push(regionSelDistrict.value)
    const target = editingSide.value === 'a' ? a : b
    target.place = parts.join(' ')
    target.longitude = regionSelLongitude.value
  }
  showRegionPicker.value = false
}

// 状态栏高度
const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getWindowInfo()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}

function goBack() {
  uni.navigateBack()
}

const canSubmit = computed(() => a.date && a.time && b.date && b.time)

async function onAnalyze() {
  if (!canSubmit.value || loading.value) return
  loading.value = true
  result.value = ''
  try {
    const res = await hehun({
      birthTimeA: `${a.date} ${a.time}`,
      genderA: a.gender,
      birthTimeB: `${b.date} ${b.time}`,
      genderB: b.gender,
      sect,
      longitudeA: a.longitude || undefined,
      longitudeB: b.longitude || undefined,
    })
    result.value = res.result || '无结果'
  } catch (e: any) {
    uni.showToast({ title: e.message || '分析失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss">
.page {
  height: calc(100vh - var(--window-bottom));
  overflow: hidden;
  background: $color-bg;
  color: $color-ink;
}
.scroll { height: 100%; }

/* 状态栏占位 */
.status-bar { width: 100%; }

/* === 页面头 === */
.page-header {
  position: relative;
  padding: 88rpx 32rpx 48rpx;
  align-items: center;
  text-align: center;
}
.back-btn {
  position: absolute;
  left: 32rpx;
  top: 88rpx;
  width: 56rpx;
  height: 56rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}
.back-arrow {
  font-size: 48rpx;
  color: $color-primary;
  line-height: 1;
}
.page-title {
  display: block;
  font-family: $font-family-display;
  font-size: 44rpx;
  font-weight: 600;
  color: $color-primary;
  line-height: 1.3;
  margin-bottom: 16rpx;
  letter-spacing: 0.12em;
}
.page-sub {
  display: block;
  margin-top: 12rpx;
  font-size: 24rpx;
  color: $color-ink-light;
  line-height: 1.6;
  letter-spacing: 0.04em;
}

/* === 人物卡片 === */
.person-card {
  margin: 0 32rpx;
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: 24rpx;
  overflow: hidden;
  box-shadow: $shadow-sm;
}
.card-gradient-top {
  height: 4rpx;
}
.gradient-a {
  background: linear-gradient(90deg, transparent, $color-primary, $color-primary-lighter, transparent);
}
.gradient-b {
  background: linear-gradient(90deg, transparent, $color-vermilion, $color-vermilion-light, transparent);
}
.gradient-result {
  background: linear-gradient(90deg, transparent, $color-primary, $color-vermilion, transparent);
}
.card-body { padding: 36rpx; }
.person-card .card-body { padding: 36rpx 32rpx 38rpx; }
.card-head {
  display: flex;
  align-items: center;
  gap: 18rpx;
  margin-bottom: 32rpx;
}
.badge {
  width: 56rpx;
  height: 56rpx;
  line-height: 56rpx;
  text-align: center;
  border-radius: 50%;
  font-family: $font-family-display;
  font-size: 28rpx;
  font-weight: 600;
  border: 1rpx solid;
}
.badge-a {
  background: rgba(44, 44, 44, 0.06);
  border-color: $color-primary;
  color: $color-primary;
}
.badge-b {
  background: rgba(184, 72, 60, 0.06);
  border-color: $color-vermilion;
  color: $color-vermilion;
}
.badge-result {
  background: rgba(44, 44, 44, 0.04);
  border-color: $color-border;
  color: $color-primary;
}
.card-title {
  font-family: $font-family-display;
  font-size: 32rpx;
  font-weight: 600;
  color: $color-ink;
  letter-spacing: 0.06em;
}

/* 表单 */
.form-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 20rpx;
  margin-bottom: 28rpx;
}
.label {
  flex: 0 0 140rpx;
  font-size: 24rpx;
  color: $color-ink-light;
  letter-spacing: 0.04em;
}
.form-row picker,
.seg-group {
  flex: 1;
  min-width: 0;
}
.picker {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 76rpx;
  padding: 0 24rpx;
  background: $color-bg-warm;
  border: 1rpx solid $color-border-light;
  border-radius: 12rpx;
}
.person-b .picker {
  background: rgba(184, 72, 60, 0.03);
  border-color: rgba(184, 72, 60, 0.1);
}
.picker-text {
  font-size: 26rpx;
  color: $color-ink;
}
.picker-icon {
  color: $color-ink-lighter;
  font-size: 28rpx;
}
.seg-group {
  display: flex;
  height: 76rpx;
  border: 1rpx solid $color-border;
  border-radius: 12rpx;
  overflow: hidden;
}
.seg {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26rpx;
  color: $color-ink-light;
  background: $color-bg-warm;
}
.person-b .seg {
  background: rgba(184, 72, 60, 0.03);
}
.seg.active {
  background: rgba(44, 44, 44, 0.08);
  color: $color-primary;
}
.person-b .seg.active {
  background: rgba(184, 72, 60, 0.08);
  color: $color-vermilion;
}

/* === 能量连接器 === */
.connector {
  display: flex;
  align-items: center;
  padding: 32rpx 32rpx;
}
.line {
  flex: 1;
  height: 2rpx;
}
.line-left {
  background: linear-gradient(90deg, transparent, rgba(44, 44, 44, 0.2));
}
.line-right {
  background: linear-gradient(270deg, transparent, rgba(44, 44, 44, 0.2));
}
.connector-icon {
  margin: 0 24rpx;
  width: 60rpx;
  height: 60rpx;
  line-height: 60rpx;
  text-align: center;
  border-radius: 50%;
  border: 2rpx solid $color-primary;
  background: rgba(44, 44, 44, 0.04);
}
.connector-glyph {
  color: $color-primary;
  font-size: 30rpx;
}

/* === CTA 按钮 === */
.cta-wrap {
  padding: 40rpx 32rpx 48rpx;
}
.cta-btn {
  height: 92rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16rpx;
  background: $color-primary;
  border-radius: 16rpx;
}
.cta-btn.disabled { opacity: 0.5; }
.cta-glyph {
  color: $color-bg;
  font-size: 30rpx;
}
.cta-text {
  color: $color-bg;
  font-size: 30rpx;
  font-weight: 600;
  letter-spacing: 0.12em;
}

/* === 结果卡片 === */
.result-card {
  margin: 0 32rpx 48rpx;
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: 24rpx;
  overflow: hidden;
  box-shadow: $shadow-sm;
}
.result-text {
  font-size: 28rpx;
  line-height: 1.8;
  color: $color-ink;
  white-space: pre-wrap;
  letter-spacing: 0.02em;
}

/* 出生地 */
.place-picker { cursor: pointer; }
.solar-hint {
  font-size: 22rpx;
  color: $color-primary;
  flex-shrink: 0;
}

/* === 子时流派提示 === */
.sect-hint {
  margin: 28rpx 32rpx 0;
  font-size: 24rpx;
  color: $color-ink-light;
  text-align: center;
  line-height: 1.5;
}

/* === 省市区选择器弹窗 === */
.region-picker-mask {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  z-index: 999;
  display: flex;
  align-items: flex-end;
}
.region-picker {
  width: 100%;
  background: #fff;
  border-radius: 24rpx 24rpx 0 0;
  padding-bottom: env(safe-area-inset-bottom);
  max-height: 58vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.rp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 32rpx 12rpx;
  flex-shrink: 0;
}
.rp-tabs {
  display: flex;
  gap: 12rpx;
}
.rp-tab {
  padding: 10rpx 28rpx;
  font-size: 26rpx;
  border-radius: 30rpx;
  background: #f5f5f5;
  color: #888;
}
.rp-tab.active {
  background: #1a1a1a;
  color: #fff;
  font-weight: 600;
}
.rp-confirm {
  padding: 14rpx 36rpx;
  background: #1a1a1a;
  color: #fff;
  font-size: 26rpx;
  border-radius: 30rpx;
  font-weight: 600;
}
.rp-search {
  margin: 6rpx 32rpx 14rpx;
  display: flex;
  align-items: center;
  gap: 10rpx;
  padding: 16rpx 24rpx;
  background: #f7f7f7;
  border-radius: 12rpx;
  border: 1rpx solid #eee;
  flex-shrink: 0;
}
.rp-search-icon { font-size: 26rpx; }
.rp-search-input { flex: 1; font-size: 26rpx; }
.rp-search-ph { color: #bbb; }
.rp-col-labels {
  display: flex;
  padding: 10rpx 32rpx 6rpx;
  flex-shrink: 0;
}
.rp-col-label {
  flex: 1;
  text-align: center;
  font-size: 26rpx;
  color: #999;
  font-weight: 500;
}
.rp-columns {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}
.rp-col {
  flex: 1;
}
.rp-item {
  display: block;
  padding: 24rpx 16rpx;
  font-size: 30rpx;
  color: #333;
  text-align: center;
  line-height: 1.5;
}
.rp-item.active {
  color: #1a1a1a;
  font-weight: 700;
  background: rgba(212,175,55,0.08);
}

.bottom-spacer { height: 48rpx; }
</style>
