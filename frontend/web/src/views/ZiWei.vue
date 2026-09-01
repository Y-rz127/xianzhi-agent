<template>
  <div class="ziwei-page page-transition">
    <section class="ziwei-card glass-card">
      <header>
        <span>ZIWEI DOUSHU</span>
        <h2>紫微斗数</h2>
        <p>传统民俗文化参考 · 仅供自省与决策参考。</p>
      </header>

      <!-- 输入表单 -->
      <div v-if="phase === 'form'" class="form-panel">
        <div class="form-row">
          <label>历法</label>
          <div class="seg">
            <button :class="{ active: calendar === 'solar' }" :disabled="busy" @click="calendar = 'solar'">阳历</button>
            <button :class="{ active: calendar === 'lunar' }" :disabled="busy" @click="calendar = 'lunar'">农历</button>
          </div>
        </div>

        <div class="form-row">
          <label>出生日期</label>
          <input v-if="calendar === 'solar'" v-model="solarDate" type="date" min="1900-01-01" max="2099-12-31">
          <div v-else class="lunar-row">
            <select v-model.number="lunarYear">
              <option v-for="y in years" :key="y" :value="y">{{ y }}年</option>
            </select>
            <select v-model.number="lunarMonth">
              <option v-for="(m, i) in CN_MONTH" :key="m" :value="i + 1">{{ m }}月</option>
            </select>
            <select v-model.number="lunarDay">
              <option v-for="(d, i) in CN_DAY" :key="d" :value="i + 1">{{ d }}</option>
            </select>
          </div>
        </div>

        <div v-if="calendar === 'lunar'" class="form-row leap-row">
          <label>闰月（该年有闰此月时生效）</label>
          <input v-model="leap" type="checkbox">
        </div>

        <div class="form-row">
          <label>出生时辰</label>
          <select v-model.number="timeIndex">
            <option v-for="(t, i) in TIME_OPTIONS" :key="t" :value="i">{{ t }}</option>
          </select>
        </div>

        <div class="form-row">
          <label>性别</label>
          <div class="seg">
            <button :class="{ active: gender === '男' }" :disabled="busy" @click="gender = '男'">男</button>
            <button :class="{ active: gender === '女' }" :disabled="busy" @click="gender = '女'">女</button>
          </div>
        </div>

        <div class="btn-center">
          <button class="cast-btn" :disabled="loading" @click="cast">
            {{ loading ? '正在排盘…' : '排盘' }}
          </button>
        </div>
      </div>

      <!-- 命盘 -->
      <div v-if="chart && phase === 'chart'" class="result result-in">
        <div class="board">
          <template v-for="cell in boardCells" :key="cell.key">
            <div
              v-if="cell.palace"
              class="cell palace-cell"
              :class="{ soul: cell.palace.name === '命宫' }"
              :style="cell.style"
              @click="detail = cell.palace"
            >
              <i v-if="mutagenBadge(cell.palace)" class="mut-corner" :class="mutagenBadge(cell.palace)">{{ mutagenBadge(cell.palace) }}</i>
              <div class="p-head">
                <b>{{ cell.palace.name }}</b>
                <em v-if="cell.palace.is_body" class="p-body">身</em>
              </div>
              <small class="p-gz">{{ cell.palace.heavenly_stem }}{{ cell.palace.earthly_branch }}</small>
              <div class="p-majors">
                <div v-for="s in cell.palace.major_stars" :key="s.name" class="major-row">
                  <span class="major-name">{{ s.name }}</span>
                  <small v-if="s.brightness" class="major-bri">{{ s.brightness }}</small>
                  <i v-if="s.mutagen" class="major-mut" :class="'mut-' + s.mutagen">{{ s.mutagen }}</i>
                </div>
                <small v-if="!cell.palace.major_stars.length" class="major-empty">空宫</small>
              </div>
              <small class="p-minor">{{ minorNames(cell.palace) }}</small>
              <small v-if="cell.palace.decadal" class="p-dec">{{ cell.palace.decadal.range[0] }}~{{ cell.palace.decadal.range[1] }}</small>
            </div>
            <div v-else-if="cell.center" class="cell center-cell" :style="cell.style">
              <div class="center">
                <b class="c-title">{{ chart.gender }}命</b>
                <span>{{ chart.lunar_date }}</span>
                <span>{{ chart.time_name }}（{{ chart.time_range }}）</span>
                <small class="c-gz">四柱 {{ chart.four_pillars.yearly }} {{ chart.four_pillars.monthly }} {{ chart.four_pillars.daily }} {{ chart.four_pillars.hourly }}</small>
                <span>{{ chart.five_elements_class }} · 命宫{{ chart.earthly_branch_of_soul }} 身宫{{ chart.earthly_branch_of_body }}</span>
                <span>命主{{ chart.soul_star }} · 身主{{ chart.body_star }}</span>
                <small class="c-tip">点任意宫看详情</small>
              </div>
            </div>
          </template>
        </div>

        <div class="legend">
          <span><i class="lg lg-lu">禄</i>化禄</span>
          <span><i class="lg lg-quan">权</i>化权</span>
          <span><i class="lg lg-ke">科</i>化科</span>
          <span><i class="lg lg-ji">忌</i>化忌</span>
        </div>

        <div class="btn-center actions">
          <button class="ghost-btn" :disabled="busy" @click="resetForm">重新输入</button>
          <button class="cast-btn" :disabled="interpreting" @click="interpret">
            {{ interpreting ? '解读中…' : 'AI 简批' }}
          </button>
        </div>
        <p v-if="interpretation" class="ai-result">{{ interpretation }}</p>
      </div>
    </section>

    <!-- 点宫详情弹层 -->
    <Transition name="mask-fade">
      <div v-if="detail" class="mask" @click="detail = null">
        <div class="sheet" @click.stop>
          <header class="sheet-head">
            <h3>{{ detail.name }}宫（{{ detail.heavenly_stem }}{{ detail.earthly_branch }}）</h3>
            <button class="sheet-close" @click="detail = null">✕</button>
          </header>
          <div class="sheet-body">
            <section class="sec">
              <h4>主星</h4>
              <div v-for="s in detail.major_stars" :key="s.name" class="star-line">
                <b>{{ s.name }}</b>
                <small v-if="s.brightness">{{ s.brightness }}</small>
                <i v-if="s.mutagen" class="major-mut" :class="'mut-' + s.mutagen">化{{ s.mutagen }}</i>
              </div>
              <small v-if="!detail.major_stars.length" class="major-empty">空宫（借对宫主星论）</small>
            </section>
            <section v-if="detail.minor_stars.length" class="sec">
              <h4>辅星 · 煞星</h4>
              <div v-for="s in detail.minor_stars" :key="s.name" class="star-line">
                <b>{{ s.name }}</b>
                <small v-if="s.brightness">{{ s.brightness }}</small>
                <i v-if="s.mutagen" class="major-mut" :class="'mut-' + s.mutagen">化{{ s.mutagen }}</i>
              </div>
            </section>
            <section v-if="detail.adjective_stars.length" class="sec">
              <h4>杂曜</h4>
              <p class="misc">{{ detail.adjective_stars.map(s => s.name).join('、') }}</p>
            </section>
            <section class="sec">
              <h4>十二神</h4>
              <p class="misc">长生·{{ detail.changsheng12 }}　博士·{{ detail.boshi12 }}</p>
              <p class="misc">将前·{{ detail.jiangqian12 }}　岁前·{{ detail.suiqian12 }}</p>
            </section>
            <section class="sec">
              <h4>三方四正</h4>
              <p class="misc">{{ sanFangSiZheng }}</p>
            </section>
            <section v-if="detail.decadal" class="sec">
              <h4>大限</h4>
              <p class="misc">{{ detail.decadal.range[0] }}~{{ detail.decadal.range[1] }} 岁（{{ detail.decadal.heavenly_stem }}{{ detail.decadal.earthly_branch }}）</p>
            </section>
          </div>
        </div>
      </div>
    </Transition>

    <Transition name="toast-fade">
      <div v-if="error" class="toast">{{ error }}</div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
import { getZiWeiChart, interpretZiWei, type ZiWeiChart, type ZiWeiPalace } from "@/api"

const TIME_OPTIONS = [
  "早子时 00:00~01:00", "丑时 01:00~03:00", "寅时 03:00~05:00", "卯时 05:00~07:00",
  "辰时 07:00~09:00", "巳时 09:00~11:00", "午时 11:00~13:00", "未时 13:00~15:00",
  "申时 15:00~17:00", "酉时 17:00~19:00", "戌时 19:00~21:00", "亥时 21:00~23:00", "晚子时 23:00~00:00",
]
const CN_MONTH = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
const CN_DAY = ["初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
  "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
  "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"]

const phase = ref<"form" | "chart">("form")
const calendar = ref<"solar" | "lunar">("solar")
const solarDate = ref("2000-01-01")
const years = Array.from({ length: 200 }, (_, i) => 1900 + i)
const lunarYear = ref(2000)
const lunarMonth = ref(1)
const lunarDay = ref(1)
const leap = ref(false)
const timeIndex = ref(0)
const gender = ref<"男" | "女">("男")

const loading = ref(false)
const interpreting = ref(false)
const chart = ref<ZiWeiChart | null>(null)
const interpretation = ref("")
const detail = ref<ZiWeiPalace | null>(null)
const error = ref("")

const busy = computed(() => loading.value || interpreting.value)

// 地支 → 4×4 盘位（0~15，行优先）。中央 5/6/9/10 为信息区。
const BRANCH_CELL: Record<string, number> = {
  巳: 0, 午: 1, 未: 2, 申: 3, 辰: 4, 酉: 7, 卯: 8, 戌: 11, 寅: 12, 丑: 13, 子: 14, 亥: 15,
}
const CENTER_CELLS = new Set([5, 6, 9, 10])

const boardCells = computed(() => {
  const byCell: Record<number, ZiWeiPalace> = {}
  if (chart.value) for (const p of chart.value.palaces) byCell[BRANCH_CELL[p.earthly_branch]] = p
  const cells: { key: string; style: string; palace: ZiWeiPalace | null; center?: boolean }[] = []
  for (let c = 0; c < 16; c++) {
    const row = Math.floor(c / 4) + 1
    const col = (c % 4) + 1
    if (CENTER_CELLS.has(c)) {
      if (c === 5) cells.push({ key: "center", style: "grid-row:2 / span 2;grid-column:2 / span 2", palace: null, center: true })
      continue
    }
    cells.push({ key: "p" + c, style: `grid-row:${row};grid-column:${col}`, palace: byCell[c] || null })
  }
  return cells
})

function minorNames(p: ZiWeiPalace): string {
  const names = [...p.minor_stars.map(s => s.name), ...p.adjective_stars.filter(s => s.type === "flower" || s.type === "tough" || s.type === "soft").map(s => s.name)]
  return [...new Set(names)].slice(0, 8).join(" ")
}
function mutagenBadge(p: ZiWeiPalace): string {
  for (const m of ["禄", "权", "科", "忌"]) {
    if (p.major_stars.some(s => s.mutagen === m)) return m
  }
  return ""
}
const sanFangSiZheng = computed(() => {
  if (!detail.value || !chart.value) return ""
  const i = detail.value.index
  const at = (idx: number) => chart.value!.palaces[((idx % 12) + 12) % 12].name
  return `本宫${at(i)}、对宫${at(i + 6)}、三合${at(i + 4)}·${at(i + 8)}`
})

function castParams() {
  if (calendar.value === "solar") {
    return { date: solarDate.value, time_index: timeIndex.value, gender: gender.value, calendar: "solar" as const }
  }
  return { date: `${lunarYear.value}-${lunarMonth.value}-${lunarDay.value}`, time_index: timeIndex.value, gender: gender.value, calendar: "lunar" as const, leap: leap.value }
}

function resetForm() {
  phase.value = "form"
  chart.value = null
  interpretation.value = ""
}

async function cast() {
  loading.value = true
  error.value = ""
  try {
    chart.value = await getZiWeiChart(castParams())
    interpretation.value = ""
    phase.value = "chart"
  } catch (e) {
    error.value = e instanceof Error ? e.message : "排盘失败"
  } finally {
    loading.value = false
  }
}

async function interpret() {
  interpreting.value = true
  error.value = ""
  try {
    interpretation.value = await interpretZiWei(castParams())
  } catch (e) {
    error.value = e instanceof Error ? e.message : "解读失败"
  } finally {
    interpreting.value = false
  }
}
</script>

<style scoped>
.ziwei-page { min-height: 100vh; padding: 22px; display: flex; justify-content: center; }
.ziwei-card { width: min(100%, 860px); padding: 32px; text-align: center; }
.ziwei-card header > span { font-size: 10px; letter-spacing: 4px; color: #8fa1e8; }
.ziwei-card h2 { color: #a9b8f0; letter-spacing: 8px; }
.ziwei-card header p { color: var(--text-dim); font-size: 13px; }

/* ===== 表单 ===== */
.form-panel { max-width: 460px; margin: 26px auto 0; text-align: left; }
.form-row { margin-bottom: 16px; }
.form-row > label { display: block; margin-bottom: 8px; font-size: 12px; letter-spacing: 1px; color: #8fa1e8; font-weight: 600; }
.form-row input[type="date"], .form-row select {
  width: 100%; box-sizing: border-box; padding: 11px 12px; border: 1px solid var(--border);
  border-radius: 8px; background: #171221; color: #eee; font-size: 14px;
}
.lunar-row { display: flex; gap: 8px; }
.lunar-row select { flex: 1; min-width: 0; }
.leap-row { display: flex; align-items: center; justify-content: space-between; }
.leap-row input { width: 20px; height: 20px; accent-color: #8fa1e8; }
.seg { display: flex; gap: 8px; }
.seg button {
  flex: 1; padding: 11px; border: 1px solid var(--border); border-radius: 8px;
  background: rgba(20, 16, 26, .45); color: var(--text-dim); cursor: pointer; font-size: 14px;
}
.seg .active { color: #c4d0fa; border-color: #8fa1e8; background: rgba(143, 161, 232, .12); font-weight: 600; }

.btn-center { display: flex; justify-content: center; margin: 24px 0; }
.actions { gap: 12px; }
.cast-btn { margin: 0; padding: 14px 40px; border: 1px solid #8fa1e8; border-radius: 10px; background: linear-gradient(135deg, #33407e, #5566b8); color: #fff; letter-spacing: 2px; cursor: pointer; font-size: 15px; font-weight: 600; transition: all .25s; }
.cast-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(85, 102, 184, .45); }
.cast-btn:disabled { opacity: .6; cursor: not-allowed; }
.ghost-btn { padding: 14px 28px; border: 1px solid #8fa1e8; border-radius: 10px; background: transparent; color: #a9b8f0; cursor: pointer; font-size: 14px; }
.ghost-btn:disabled { opacity: .5; cursor: not-allowed; }

/* ===== 命盘 4×4 ===== */
.result { border-top: 1px solid rgba(143, 161, 232, .35); margin-top: 20px; padding-top: 22px; }
.result-in { animation: resultIn .6s ease both; }
@keyframes resultIn { 0% { opacity: 0; transform: translateY(18px); } 100% { opacity: 1; transform: translateY(0); } }

.board {
  display: grid; grid-template-columns: repeat(4, 1fr); grid-template-rows: repeat(4, 1fr);
  gap: 2px; width: 100%; max-width: 720px; aspect-ratio: 1 / 1; margin: 0 auto;
  background: var(--border); border: 2px solid #8fa1e8; border-radius: 10px; overflow: hidden;
}
.cell { position: relative; background: rgba(20, 16, 26, .72); padding: 7px 7px 22px; overflow: hidden; text-align: left; }
.palace-cell { cursor: pointer; transition: background .2s; }
.palace-cell:hover { background: rgba(143, 161, 232, .12); }
.palace-cell.soul { background: rgba(143, 161, 232, .10); }
.p-head { display: flex; align-items: center; gap: 4px; }
.p-head b { font-size: 12px; color: #a9b8f0; }
.p-body { font-style: normal; font-size: 9px; color: #fff; background: #5566b8; border-radius: 3px; padding: 0 3px; }
.p-gz { position: absolute; top: 7px; right: 7px; font-size: 9px; color: var(--text-dim); }
.p-majors { margin-top: 5px; }
.major-row { display: flex; align-items: baseline; gap: 2px; }
.major-name { font-size: 13px; font-weight: 600; color: #eee; }
.major-bri { font-size: 9px; color: var(--text-dim); }
.major-mut { font-style: normal; font-size: 9px; font-weight: 700; }
.major-empty { font-size: 11px; color: var(--text-dim); }
.p-minor { position: absolute; left: 7px; right: 7px; bottom: 15px; font-size: 9px; color: var(--text-dim); line-height: 1.3; }
.p-dec { position: absolute; left: 7px; bottom: 3px; font-size: 9px; color: var(--text-dim); }

/* 四化语义色（固定，徽章深底白字） */
.mut-lu { color: #e8c14a; } .mut-quan { color: #e07a6a; } .mut-ke { color: #5ec2c2; } .mut-ji { color: #9a9a9a; }
.mut-corner {
  position: absolute; top: 3px; right: 22px; width: 14px; height: 14px; line-height: 14px;
  text-align: center; font-style: normal; font-size: 9px; color: #fff; border-radius: 50%;
}
.mut-corner.mut-lu { background: #c9a227; } .mut-corner.mut-quan { background: #c0392b; }
.mut-corner.mut-ke { background: #2e8b8b; } .mut-corner.mut-ji { background: #555; }

.center-cell { padding: 0; }
.center {
  height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 4px; background: #171221; padding: 8px; text-align: center;
}
.center span { font-size: 11px; color: #ddd; }
.c-title { font-size: 16px; color: #a9b8f0; letter-spacing: 3px; }
.c-gz { font-size: 10px; color: var(--text-dim); }
.c-tip { margin-top: 4px; font-size: 9px; color: var(--text-dim); }

.legend { display: flex; justify-content: center; gap: 22px; margin: 16px 0 0; font-size: 12px; color: var(--text-dim); }
.legend span { display: flex; align-items: center; gap: 5px; }
.lg { width: 16px; height: 16px; line-height: 16px; text-align: center; border-radius: 50%; color: #fff; font-style: normal; font-size: 9px; }
.lg-lu { background: #c9a227; } .lg-quan { background: #c0392b; } .lg-ke { background: #2e8b8b; } .lg-ji { background: #555; }

.ai-result { max-width: 680px; margin: 20px auto; color: #d9d4c3; text-align: left; line-height: 1.8; white-space: pre-wrap; background: rgba(255, 255, 255, .04); padding: 16px; border-radius: 8px; }

/* ===== 点宫详情弹层 ===== */
.mask { position: fixed; inset: 0; z-index: 20; background: rgba(0, 0, 0, .55); display: flex; align-items: center; justify-content: center; padding: 20px; }
.sheet { width: min(100%, 480px); max-height: 80vh; display: flex; flex-direction: column; background: #1b1626; border: 1px solid #8fa1e8; border-radius: 14px; overflow: hidden; }
.sheet-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.sheet-head h3 { margin: 0; font-size: 16px; color: #a9b8f0; }
.sheet-close { border: none; background: transparent; color: var(--text-dim); font-size: 16px; cursor: pointer; padding: 4px 8px; }
.sheet-body { overflow-y: auto; padding: 6px 20px 22px; text-align: left; }
.sec { margin-top: 16px; }
.sec h4 { margin: 0 0 8px; font-size: 12px; font-weight: 600; color: var(--text-dim); letter-spacing: 1px; border-left: 3px solid #8fa1e8; padding-left: 8px; }
.star-line { display: flex; align-items: baseline; gap: 8px; padding: 4px 0; }
.star-line b { font-size: 14px; color: #eee; }
.star-line small { font-size: 11px; color: var(--text-dim); }
.star-line .major-mut { font-size: 11px; }
.misc { margin: 0; font-size: 13px; color: #ddd; line-height: 1.8; }

.toast { position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%); padding: 10px 20px; border-radius: 8px; background: #b54b62; color: #fff; z-index: 30; }
.toast-fade-enter-active, .toast-fade-leave-active { transition: .25s; }
.toast-fade-enter-from, .toast-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(10px); }
.mask-fade-enter-active, .mask-fade-leave-active { transition: opacity .2s; }
.mask-fade-enter-from, .mask-fade-leave-to { opacity: 0; }

@media (max-width: 640px) {
  .ziwei-card { padding: 20px; }
  .board { max-width: 100%; }
  .major-name { font-size: 11px; }
  .p-head b { font-size: 10px; }
  .p-minor, .p-dec { font-size: 8px; }
  .center span { font-size: 9px; }
}
</style>
