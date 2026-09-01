<template>
  <div class="huangli-page page-transition">
    <section class="huangli-card glass-card">
      <header>
        <span>DAILY ALMANAC</span>
        <h2>每日黄历</h2>
        <p>传统民俗文化参考，宜忌随日而变，理性看待。</p>
      </header>

      <!-- 日期切换 -->
      <div class="date-bar">
        <button class="nav-btn" :disabled="loading" @click="shiftDay(-1)">‹ 前一天</button>
        <input v-model="dateInput" type="date" class="date-picker" :min="minDate" :max="maxDate" :disabled="loading" @change="loadDay" />
        <button class="nav-btn" :disabled="loading" @click="shiftDay(1)">后一天 ›</button>
        <button class="nav-btn today-btn" :disabled="loading" @click="goToday">回今天</button>
      </div>

      <!-- 当日详情 -->
      <div v-if="day" class="day-detail">
        <div class="day-head">
          <div class="day-title">
            <h3>{{ day.date }}</h3>
            <div class="badges">
              <span class="badge lunar-badge">{{ day.lunar.text }}</span>
              <span class="badge gz-badge">{{ day.lunar.day_gz }}日</span>
              <span v-for="f in day.festivals" :key="'f-' + f" class="badge fest-badge">{{ f }}</span>
              <span v-if="day.jieqi" class="badge jieqi-badge">{{ day.jieqi }}</span>
              <span v-if="day.tian_shen.luck === '吉'" class="badge gold-badge">{{ day.tian_shen.name }} · {{ day.tian_shen.type }}</span>
            </div>
          </div>
        </div>

        <div class="yiji">
          <div class="yi-block">
            <b>宜</b>
            <div class="chips">
              <span v-for="item in day.yi" :key="'y-' + item" class="chip chip-yi">{{ item }}</span>
            </div>
          </div>
          <div class="ji-block">
            <b>忌</b>
            <div class="chips">
              <span v-for="item in day.ji" :key="'j-' + item" class="chip chip-ji">{{ item }}</span>
            </div>
          </div>
        </div>

        <div class="info-grid">
          <div class="info-item"><small>冲煞</small><p>{{ day.chong.desc }} 煞{{ day.chong.sha }}</p></div>
          <div class="info-item"><small>值神</small><p>{{ day.tian_shen.name }}（{{ day.tian_shen.type }}·{{ day.tian_shen.luck }}）</p></div>
          <div class="info-item"><small>建星</small><p>{{ day.zhixing }}</p></div>
          <div class="info-item"><small>九星</small><p>{{ day.nine_star }}</p></div>
          <div class="info-item"><small>二十八宿</small><p>{{ day.xiu.name }}（{{ day.xiu.luck }}）</p></div>
          <div class="info-item"><small>胎神占方</small><p>{{ day.taishen }}</p></div>
          <div class="info-item"><small>纳音五行</small><p>{{ day.nayin }}</p></div>
          <div class="info-item"><small>彭祖百忌</small><p class="pengzu">{{ day.pengzu.gan }}；{{ day.pengzu.zhi }}</p></div>
        </div>

        <div class="positions">
          <div v-for="pos in positionList" :key="pos.key" class="pos-item">
            <small>{{ pos.label }}</small><b>{{ pos.value }}</b>
          </div>
        </div>

        <button class="fold-btn" @click="shensFolded = !shensFolded">
          {{ shensFolded ? '展开吉神宜趋 / 凶煞宜忌 ▾' : '收起吉神宜趋 / 凶煞宜忌 ▴' }}
        </button>
        <div v-if="!shensFolded" class="shens">
          <p><b class="shen-good">吉神宜趋</b>{{ day.jishen.join(' · ') }}</p>
          <p><b class="shen-bad">凶煞宜忌</b>{{ day.xiongsha.join(' · ') }}</p>
        </div>
      </div>
      <p v-else-if="loading" class="placeholder">推演历书中…</p>

      <!-- 十二时辰吉凶 -->
      <div v-if="day" class="hours-section">
        <h4>十二时辰吉凶</h4>
        <div class="hours-strip">
          <button
            v-for="(h, i) in day.hours" :key="h.zhi + i"
            class="hour-cell" :class="{ luck: h.luck === '吉', active: activeHour === i }"
            @click="activeHour = activeHour === i ? -1 : i"
          >
            <b>{{ h.zhi }}</b>
            <small>{{ h.range }}</small>
            <em>{{ h.luck }}</em>
          </button>
        </div>
        <div v-if="activeHour >= 0 && day.hours[activeHour]" class="hour-detail">
          <p class="hour-title">{{ day.hours[activeHour].zhi }}时（{{ day.hours[activeHour].range }}）· {{ day.hours[activeHour].tian_shen }} · {{ day.hours[activeHour].luck }} · 冲{{ day.hours[activeHour].chong }}</p>
          <p><b class="shen-good">宜</b>{{ day.hours[activeHour].yi.join('、') || '无' }}</p>
          <p><b class="shen-bad">忌</b>{{ day.hours[activeHour].ji.join('、') || '无' }}</p>
        </div>
      </div>

      <!-- 本月概览 -->
      <div v-if="monthDays.length" class="month-section">
        <h4>本月概览（{{ monthLabel }}）</h4>
        <div class="month-grid">
          <button
            v-for="m in monthDays" :key="m.date"
            class="month-cell" :class="{ today: m.date === day?.date, tianshe: m.tianshe }"
            @click="jumpTo(m.date)"
          >
            <b>{{ Number(m.date.slice(8)) }}</b>
            <small>{{ m.lunar_day }}</small>
            <em v-if="m.festivals.length || m.jieqi">{{ m.festivals[0] || m.jieqi }}</em>
            <span v-if="m.yi_top5.length" class="month-yi">{{ m.yi_top5[0] }}</span>
            <i v-if="m.tianshe" class="tianshe-mark" title="天赦日">赦</i>
          </button>
        </div>
      </div>

      <!-- 择吉 -->
      <div class="zeji-section">
        <h4>择吉</h4>
        <div class="zeji-form">
          <select v-model="zejiItem" class="zeji-select">
            <option v-for="item in items" :key="item" :value="item">{{ item }}</option>
          </select>
          <input v-model="zejiStart" type="date" class="date-picker" :min="minDate" :max="maxDate" />
          <span class="range-sep">至</span>
          <input v-model="zejiEnd" type="date" class="date-picker" :min="minDate" :max="maxDate" />
          <select v-model="zejiAvoid" class="zeji-select narrow">
            <option value="">不限生肖</option>
            <option v-for="z in zodiacs" :key="z" :value="z">避冲{{ z }}</option>
          </select>
          <button class="zeji-btn" :disabled="zejiLoading" @click="runZeji">
            {{ zejiLoading ? '推算中…' : '查询吉日' }}
          </button>
        </div>
        <div v-if="zejiDays" class="zeji-result">
          <p v-if="!zejiDays.length" class="placeholder">该区间内没有宜「{{ zejiItem }}」的日子，试着放宽区间或去掉生肖限制。</p>
          <div v-for="d in zejiDays" :key="d.date" class="zeji-card" @click="jumpTo(d.date)">
            <div class="zeji-date">
              <b>{{ d.date }}</b>
              <small>{{ d.day_gz }}日 · {{ d.chong }} · 值神{{ d.tian_shen }}</small>
            </div>
            <span v-if="d.note" class="zeji-note">{{ '★'.repeat(Math.min(d.stars, 3)) }} {{ d.note }}</span>
          </div>
        </div>
      </div>

      <footer>黄历宜忌源自传统历法推演，仅供民俗文化参考，不构成任何决策建议。</footer>
    </section>
    <Transition name="toast-fade">
      <div v-if="error" class="toast">{{ error }}</div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import {
  getHuangLiDay, getHuangLiItems, getHuangLiRange, getHuangLiZeji,
  type HuangLiDay, type HuangLiRangeDay, type HuangLiZejiDay,
} from "@/api"

const MIN_YEAR = 1900
const MAX_YEAR = 2100
const minDate = `${MIN_YEAR}-01-01`
const maxDate = `${MAX_YEAR}-12-31`
const zodiacs = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

function fmtDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

const dateInput = ref(fmtDate(new Date()))
const day = ref<HuangLiDay | null>(null)
const loading = ref(false)
const error = ref("")
const shensFolded = ref(true)
const activeHour = ref(-1)

const monthDays = ref<HuangLiRangeDay[]>([])
const items = ref<string[]>([])
const zejiItem = ref("嫁娶")
const zejiStart = ref("")
const zejiEnd = ref("")
const zejiAvoid = ref("")
const zejiLoading = ref(false)
const zejiDays = ref<HuangLiZejiDay[] | null>(null)

const monthLabel = computed(() => dateInput.value.slice(0, 7))
const positionList = computed(() => {
  const p = day.value?.positions
  if (!p) return []
  return [
    { key: "cai", label: "财神", value: p.cai },
    { key: "xi", label: "喜神", value: p.xi },
    { key: "fu", label: "福神", value: p.fu },
    { key: "yang_gui", label: "阳贵", value: p.yang_gui },
    { key: "yin_gui", label: "阴贵", value: p.yin_gui },
    { key: "five_ghost", label: "五鬼·凶", value: p.five_ghost },
    { key: "sheng_men", label: "生门·吉", value: p.sheng_men },
    { key: "si_men", label: "死门·凶", value: p.si_men },
  ]
})

function shiftDate(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + days)
  return fmtDate(d)
}

function shiftDay(delta: number) {
  dateInput.value = shiftDate(dateInput.value, delta)
  loadDay()
}

function goToday() {
  dateInput.value = fmtDate(new Date())
  loadDay()
}

function jumpTo(iso: string) {
  dateInput.value = iso
  loadDay()
  window.scrollTo({ top: 0, behavior: "smooth" })
}

async function loadDay() {
  loading.value = true
  error.value = ""
  activeHour.value = -1
  try {
    day.value = await getHuangLiDay(dateInput.value)
    // 概览与择吉默认范围随当前日期联动（range 接口按整月取，超 31 天由后端 400 兜底）
    const [y, m] = dateInput.value.split("-").map(Number)
    const first = new Date(y, m - 1, 1)
    const last = new Date(y, m, 0)
    monthDays.value = await getHuangLiRange(fmtDate(first), fmtDate(last)).catch(() => [])
  } catch (e) {
    error.value = e instanceof Error ? e.message : "获取黄历失败"
  } finally {
    loading.value = false
  }
}

async function loadItems() {
  try {
    items.value = await getHuangLiItems()
    if (!items.value.includes(zejiItem.value)) zejiItem.value = items.value[0] ?? ""
  } catch {
    items.value = []
  }
}

async function runZeji() {
  if (!zejiStart.value || !zejiEnd.value) {
    error.value = "请选择择吉的起止日期"
    return
  }
  zejiLoading.value = true
  error.value = ""
  try {
    zejiDays.value = await getHuangLiZeji(zejiItem.value, zejiStart.value, zejiEnd.value, zejiAvoid.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : "择吉失败"
  } finally {
    zejiLoading.value = false
  }
}

onMounted(() => {
  loadDay()
  loadItems()
  const now = fmtDate(new Date())
  zejiStart.value = now
  zejiEnd.value = shiftDate(now, 29)
})
</script>

<style scoped>
.huangli-page { min-height: 100vh; padding: 22px; display: flex; justify-content: center; }
.huangli-card { width: min(100%, 900px); padding: 32px; text-align: center; }
.huangli-card header > span { font-size: 10px; letter-spacing: 4px; color: #cfad65; }
.huangli-card h2 { color: #e5c27c; letter-spacing: 8px; }
.huangli-card header p { color: var(--text-dim); font-size: 13px; }
.huangli-card h4 { color: #d9bd79; font-size: 14px; letter-spacing: 2px; margin: 26px 0 12px; }

/* 日期切换 */
.date-bar { display: flex; justify-content: center; align-items: center; gap: 8px; flex-wrap: wrap; margin: 24px 0 18px; }
.nav-btn { padding: 9px 14px; border: 1px solid var(--border); border-radius: 8px; background: rgba(20, 16, 26, .45); color: var(--text-dim); cursor: pointer; transition: all .2s; }
.nav-btn:hover:not(:disabled) { color: #f1d894; border-color: #caa95d; }
.nav-btn:disabled { opacity: .5; cursor: not-allowed; }
.today-btn { border-color: #caa95d; color: #f1d894; }
.date-picker { padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: #171221; color: #eee; color-scheme: dark; }

/* 当日详情 */
.day-head { margin-bottom: 16px; }
.day-title h3 { color: #f0d490; font-size: 22px; margin: 0 0 8px; }
.badges { display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; }
.badge { padding: 3px 10px; border-radius: 20px; font-size: 11px; border: 1px solid var(--border); color: var(--text-dim); }
.lunar-badge { color: #e5c27c; border-color: rgba(202, 169, 93, .5); background: rgba(202, 169, 93, .1); }
.gz-badge { color: #d9c9a3; }
.fest-badge, .jieqi-badge { color: #f1d894; border-color: rgba(212, 178, 107, .6); background: rgba(212, 178, 107, .12); }
.gold-badge { color: #ffe9b0; border-color: #caa95d; background: rgba(202, 169, 93, .18); }

.yiji { display: flex; gap: 14px; margin: 18px 0; text-align: left; }
.yi-block, .ji-block { flex: 1; padding: 16px; border-radius: 10px; border: 1px solid; }
.yi-block { border-color: rgba(90, 140, 105, .45); background: rgba(46, 80, 60, .16); }
.ji-block { border-color: rgba(150, 85, 95, .45); background: rgba(95, 50, 58, .16); }
.yi-block > b, .ji-block > b { display: block; text-align: center; font-size: 20px; margin-bottom: 10px; }
.yi-block > b { color: #9ed4b2; }
.ji-block > b { color: #e8a3ae; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; }
.chip { padding: 4px 10px; border-radius: 6px; font-size: 12px; }
.chip-yi { color: #bfe6cc; background: rgba(70, 120, 90, .3); }
.chip-ji { color: #f0c4cb; background: rgba(130, 70, 80, .3); }

.info-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 18px 0; }
.info-item { padding: 10px; border: 1px solid var(--border); border-radius: 8px; background: rgba(255, 255, 255, .03); }
.info-item small { display: block; color: #b99b61; font-size: 10px; letter-spacing: 2px; margin-bottom: 4px; }
.info-item p { margin: 0; color: #ddd2b8; font-size: 13px; }
.info-item .pengzu { font-size: 11px; }

.positions { display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; margin: 18px 0; }
.pos-item { width: 84px; padding: 10px 6px; border: 1px solid rgba(202, 169, 93, .35); border-radius: 10px; background: rgba(202, 169, 93, .07); }
.pos-item small { display: block; color: #b99b61; font-size: 10px; margin-bottom: 4px; }
.pos-item b { color: #f1d894; font-size: 15px; }

.fold-btn { padding: 7px 16px; border: none; border-radius: 6px; background: transparent; color: #b99b61; font-size: 12px; cursor: pointer; }
.fold-btn:hover { color: #f1d894; }
.shens { max-width: 640px; margin: 6px auto 0; padding: 14px; border-radius: 8px; background: rgba(255, 255, 255, .04); text-align: left; }
.shens p { margin: 6px 0; color: #d9c9a3; font-size: 12px; line-height: 1.8; }
.shens b { display: inline-block; margin-right: 10px; font-size: 11px; letter-spacing: 2px; }
.shen-good { color: #9ed4b2; }
.shen-bad { color: #e8a3ae; }

/* 时辰条 */
.hours-strip { display: grid; grid-template-columns: repeat(12, 1fr); gap: 6px; }
.hour-cell { padding: 10px 2px; border: 1px solid var(--border); border-radius: 8px; background: rgba(20, 16, 26, .45); color: var(--text-dim); cursor: pointer; transition: all .2s; }
.hour-cell b { display: block; font-size: 15px; }
.hour-cell small { display: block; font-size: 9px; margin-top: 3px; opacity: .8; }
.hour-cell em { display: block; font-style: normal; font-size: 10px; margin-top: 3px; }
.hour-cell.luck { border-color: rgba(202, 169, 93, .55); color: #f1d894; background: rgba(202, 169, 93, .1); }
.hour-cell.luck em { color: #ffe9b0; }
.hour-cell.active { transform: translateY(-2px); box-shadow: 0 4px 14px rgba(202, 169, 93, .3); }
.hour-detail { max-width: 640px; margin: 12px auto 0; padding: 14px; border-radius: 8px; background: rgba(255, 255, 255, .04); text-align: left; }
.hour-detail p { margin: 6px 0; color: #d9c9a3; font-size: 12px; line-height: 1.8; }
.hour-title { color: #f1d894 !important; }

/* 本月概览 */
.month-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; }
.month-cell { position: relative; padding: 8px 2px 6px; border: 1px solid var(--border); border-radius: 8px; background: rgba(20, 16, 26, .45); color: var(--text-dim); cursor: pointer; transition: all .2s; overflow: hidden; }
.month-cell:hover { border-color: #caa95d; }
.month-cell b { display: block; color: #ddd2b8; font-size: 14px; }
.month-cell small { display: block; font-size: 9px; margin-top: 2px; }
.month-cell em { display: block; font-style: normal; font-size: 9px; color: #f1d894; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.month-yi { display: block; font-size: 9px; color: #9ed4b2; margin-top: 2px; }
.month-cell.today { border-color: #caa95d; background: rgba(202, 169, 93, .14); box-shadow: 0 0 10px rgba(202, 169, 93, .25); }
.month-cell.tianshe { border-color: rgba(212, 178, 107, .5); }
.tianshe-mark { position: absolute; top: 3px; right: 5px; font-style: normal; font-size: 9px; color: #ffe9b0; border: 1px solid rgba(212, 178, 107, .6); border-radius: 4px; padding: 0 3px; }

/* 择吉 */
.zeji-form { display: flex; justify-content: center; align-items: center; gap: 8px; flex-wrap: wrap; }
.zeji-select { padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: #171221; color: #eee; }
.zeji-select.narrow { max-width: 110px; }
.range-sep { color: var(--text-dim); font-size: 12px; }
.zeji-btn { padding: 9px 22px; border: 1px solid #d1ae62; border-radius: 8px; background: linear-gradient(135deg, #694b1c, #a47b31); color: #fff; letter-spacing: 2px; cursor: pointer; transition: all .25s; }
.zeji-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(164, 123, 49, .45); }
.zeji-btn:disabled { opacity: .6; cursor: not-allowed; }
.zeji-result { max-width: 640px; margin: 16px auto 0; display: flex; flex-direction: column; gap: 8px; }
.zeji-card { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 16px; border: 1px solid var(--border); border-radius: 8px; background: rgba(255, 255, 255, .04); cursor: pointer; transition: border-color .2s; }
.zeji-card:hover { border-color: #caa95d; }
.zeji-date b { display: block; color: #f0d490; font-size: 14px; }
.zeji-date small { color: var(--text-dim); font-size: 11px; }
.zeji-note { color: #ffe9b0; font-size: 11px; white-space: nowrap; }

.placeholder { color: var(--text-dim); font-size: 13px; padding: 20px 0; }
.huangli-card footer { margin-top: 28px; color: #8d7a55; font-size: 11px; }

.toast { position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%); padding: 10px 20px; border-radius: 8px; background: #b54b62; color: #fff; }
.toast-fade-enter-active, .toast-fade-leave-active { transition: .25s; }
.toast-fade-enter-from, .toast-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(10px); }

@media (max-width: 700px) {
  .huangli-card { padding: 20px; }
  .yiji { flex-direction: column; }
  .info-grid { grid-template-columns: repeat(2, 1fr); }
  .hours-strip { grid-template-columns: repeat(6, 1fr); }
  .month-grid { grid-template-columns: repeat(4, 1fr); }
}
</style>
