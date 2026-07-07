<template>
  <div class="huangli-page" ref="pageEl">
    <div class="hl-container">
      <!-- Date selector -->
      <div class="hl-date-bar">
        <button class="hl-nav-btn" @click="prevDay" aria-label="前一天">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
        </button>
        <div class="hl-date-display" @click="togglePicker">
          <span class="hl-date-text">{{ displayDate }}</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        </div>
        <button class="hl-nav-btn" @click="nextDay" aria-label="后一天">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
        </button>
      </div>

      <!-- Hidden date picker -->
      <div v-if="showPicker" class="hl-picker-overlay" @click.self="showPicker = false">
        <div class="hl-picker-panel">
          <input type="date" v-model="dateStr" @change="onDateChange" class="hl-picker-input" />
          <button class="hl-picker-today" @click="goToday">今天</button>
        </div>
      </div>

      <!-- Lunar date header -->
      <div class="hl-lunar-header">
        <div class="hl-lunar-big">{{ data?.lunar || '加载中...' }}</div>
      </div>

      <!-- GanZhi + week row -->
      <div class="hl-ganzhi-sub" v-if="data">
        <span>{{ data.yearGanZhi }}年</span>
        <span>{{ data.shengXiao }}年</span>
        <span>{{ data.monthGanZhi }}月</span>
        <span>{{ data.dayGanZhi }}日</span>
        <span>星期{{ data.week }}</span>
      </div>

      <!-- Action buttons -->
      <div class="hl-actions" v-if="data">
        <div class="hl-action-btn" @click="openFortune">
          <span class="hl-action-icon hl-action-icon-qiu"></span>
          <span>每日一签</span>
        </div>
        <div class="hl-action-btn">
          <span class="hl-action-icon">吉</span>
          <span>吉日查询</span>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="hl-skeleton-wrap">
        <div class="skeleton" style="height:100px;margin-bottom:16px"></div>
        <div class="hl-skeleton-grid">
          <div class="skeleton" style="height:120px"></div>
          <div class="skeleton" style="height:120px"></div>
        </div>
        <div class="skeleton" style="height:80px;margin-top:16px"></div>
        <div class="skeleton" style="height:60px;margin-top:16px"></div>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="hl-error">{{ error }}</div>

      <!-- Content -->
      <div v-else-if="data" class="hl-content">
        <!-- Yi / Ji -->
        <div class="hl-yiji-row">
          <div class="hl-yiji-box hl-yi-box">
            <div class="hl-yiji-title hl-yi-title">宜</div>
            <div class="hl-yiji-items hl-yi-items">
              <span v-for="y in data.yi" :key="y">{{ y }}</span>
            </div>
          </div>
          <div class="hl-yiji-box hl-ji-box">
            <div class="hl-yiji-title hl-ji-title">忌</div>
            <div class="hl-yiji-items hl-ji-items">
              <span v-for="j in data.ji" :key="j">{{ j }}</span>
            </div>
          </div>
        </div>

        <!-- Info grid: 五行/彭祖/冲煞/胎神/星宿 -->
        <div class="hl-info-grid">
          <div class="hl-info-cell">
            <div class="hl-info-cell-title">五行</div>
            <div class="hl-info-cell-value">{{ data.naYin || '-' }} <span v-if="data.xiuLuck" class="hl-info-cell-sub">{{ data.xiuLuck }}位</span></div>
          </div>
          <div class="hl-info-cell hl-info-cell-tall">
            <div class="hl-info-cell-title">彭祖</div>
            <div class="hl-info-cell-value hl-pengzu">{{ data.pengZu || '-' }}</div>
          </div>
          <div class="hl-info-cell">
            <div class="hl-info-cell-title">冲煞</div>
            <div class="hl-info-cell-value">冲{{ data.chong || '-' }}煞{{ data.sha || '-' }}</div>
          </div>
          <div class="hl-info-cell">
            <div class="hl-info-cell-title">胎神</div>
            <div class="hl-info-cell-value">{{ data.taiShen || '-' }}</div>
          </div>
          <div class="hl-info-cell hl-info-cell-tall" style="display:none"></div>
          <div class="hl-info-cell">
            <div class="hl-info-cell-title">星宿</div>
            <div class="hl-info-cell-value">{{ data.xiu || '-' }}{{ data.xiuLuck ? ' · ' + data.xiuLuck : '' }}</div>
          </div>
        </div>

        <!-- Direction row: 财神 喜神 福神 阳贵 阴贵 五鬼 生门 死门 -->
        <div class="hl-dir-row">
          <div class="hl-dir-item" v-for="d in dirItems" :key="d.label">
            <div class="hl-dir-label">{{ d.label }}</div>
            <div class="hl-dir-icon">{{ d.icon }}</div>
            <div class="hl-dir-value">{{ d.value }}</div>
          </div>
        </div>

        <!-- 12 地支吉凶 -->
        <div class="hl-branch-row">
          <div
            v-for="b in branchItems"
            :key="b.name"
            class="hl-branch-item"
            :class="{ 'hl-branch-active': b.isCurrent }"
          >
            <div class="hl-branch-name">{{ b.name }}</div>
            <div class="hl-branch-dot" :class="b.luck === '吉' ? 'good' : 'bad'"></div>
            <div class="hl-branch-luck" :class="b.luck === '吉' ? 'good' : 'bad'">{{ b.luck }}</div>
          </div>
        </div>

        <!-- Expandable calendar table -->
        <div class="hl-expand-bar" @click="showTable = !showTable">
          <span>查看历法表</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :style="{ transform: showTable ? 'rotate(180deg)' : '' }"><path d="M6 9l6 6 6-6"/></svg>
        </div>

        <div v-if="showTable" class="hl-table-wrap">
          <table class="hl-table">
            <thead>
              <tr><th>时辰</th><th>干支</th><th>天神</th><th>吉凶</th><th>煞方</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in allTimes" :key="t.ganzhi">
                <td>{{ t.time }}</td>
                <td>{{ t.ganzhi }}</td>
                <td>{{ t.tianShen }}</td>
                <td :class="t.isJi ? 'good' : 'bad'">{{ t.isJi ? '吉' : '凶' }}</td>
                <td>{{ t.sha }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 每日一签弹窗 -->
      <div v-if="showFortune" class="hl-fortune-overlay" @click.self="showFortune = false">
        <div class="hl-fortune-card">
          <button class="hl-fortune-close" @click="showFortune = false" aria-label="关闭">×</button>
          <div class="hl-fortune-inner">
            <div class="hl-fortune-border">
              <div class="hl-fortune-header">每日一签</div>
              <div class="hl-fortune-body">
                <div class="hl-fortune-palace">{{ fortune.palace }}</div>
                <div class="hl-fortune-level" :class="fortune.levelClass">{{ fortune.level }}</div>
                <div class="hl-fortune-poem">
                  <div v-for="(line, idx) in fortune.poem" :key="idx" class="hl-fortune-line">{{ line }}</div>
                </div>
              </div>
              <button class="hl-fortune-explain-btn" @click="showFortuneExplain = !showFortuneExplain">
                {{ showFortuneExplain ? '收起解签' : '大师解签' }}
              </button>
              <div v-if="showFortuneExplain" class="hl-fortune-explain">{{ fortune.explain }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"

const API_BASE = import.meta.env.DEV ? "http://localhost:8123/api" : "/api"
const dateStr = ref("")
const loading = ref(false)
const error = ref("")
const data = ref<any>(null)
const showPicker = ref(false)
const showTable = ref(false)
const showFortune = ref(false)
const showFortuneExplain = ref(false)

const displayDate = computed(() => {
  if (!dateStr.value) return "选择日期"
  const [y, m, d] = dateStr.value.split("-")
  return `${y}年${parseInt(m)}月${parseInt(d)}日`
})

const goToday = () => {
  const today = new Date()
  dateStr.value = today.toISOString().split("T")[0]
  showPicker.value = false
  loadHuangli()
}

const onDateChange = () => {
  showPicker.value = false
  loadHuangli()
}

const togglePicker = () => { showPicker.value = !showPicker.value }

const shiftDay = (delta: number) => {
  if (!dateStr.value) return
  const [y, m, d] = dateStr.value.split("-").map(Number)
  const dt = new Date(y, m - 1, d)
  dt.setDate(dt.getDate() + delta)
  const yy = dt.getFullYear()
  const mm = String(dt.getMonth() + 1).padStart(2, "0")
  const dd = String(dt.getDate()).padStart(2, "0")
  dateStr.value = `${yy}-${mm}-${dd}`
  loadHuangli()
}
const prevDay = () => shiftDay(-1)
const nextDay = () => shiftDay(1)

const loadHuangli = async () => {
  if (!dateStr.value) return
  loading.value = true
  error.value = ""
  showTable.value = false
  try {
    const [y, m, d] = dateStr.value.split("-")
    const res = await fetch(`${API_BASE}/ai/xianzhi/huangli?year=${y}&month=${m}&day=${d}`)
    const json = await res.json()
    if (json.error) { error.value = json.error; data.value = null }
    else data.value = json
  } catch { error.value = "加载失败" }
  finally { loading.value = false }
}

onMounted(() => {
  const today = new Date()
  dateStr.value = today.toISOString().split("T")[0]
  loadHuangli()
})

// Direction items
const dirItems = computed(() => {
  if (!data.value) return []
  return [
    { label: "财神", icon: "—", value: data.value.caiShen || "-" },
    { label: "喜神", icon: "↗", value: data.value.xiShen || "-" },
    { label: "福神", icon: "↘", value: data.value.fuShen || "-" },
    { label: "阳贵", icon: "↗", value: data.value.yangGui || "-" },
    { label: "阴贵", icon: "↓", value: data.value.yinGui || "-" },
    { label: "五鬼", icon: "↗", value: data.value.wuGui || "-" },
    { label: "生门", icon: "↘", value: data.value.shengMen || "-" },
    { label: "死门", icon: "↘", value: data.value.siMen || "-" },
  ]
})

// 12 branch items
const branchMap: { name: string; hour: number }[] = [
  { name: "子", hour: 0 }, { name: "丑", hour: 1 }, { name: "寅", hour: 3 },
  { name: "卯", hour: 5 }, { name: "辰", hour: 7 }, { name: "巳", hour: 9 },
  { name: "午", hour: 11 }, { name: "未", hour: 13 }, { name: "申", hour: 15 },
  { name: "酉", hour: 17 }, { name: "戌", hour: 19 }, { name: "亥", hour: 21 },
]

const hourGood = computed(() => {
  const arr = Array(24).fill(false)
  for (const item of data.value?.jiShi || []) {
    const m = (item.time || "").match(/(\d{1,2}):/)
    if (m) { const h = parseInt(m[1]); if (h >= 0 && h < 24) arr[h] = true }
  }
  return arr
})
const hourBad = computed(() => {
  const arr = Array(24).fill(false)
  for (const item of data.value?.xiongShi || []) {
    const m = (item.time || "").match(/(\d{1,2}):/)
    if (m) { const h = parseInt(m[1]); if (h >= 0 && h < 24) arr[h] = true }
  }
  return arr
})

const branchItems = computed(() => {
  if (!data.value) return []
  const now = new Date()
  const currentHour = now.getHours()
  const todayStr = new Date().toISOString().split("T")[0]
  const isToday = dateStr.value === todayStr
  return branchMap.map(b => {
    const luck = hourGood.value[b.hour] ? "吉" : hourBad.value[b.hour] ? "凶" : "吉"
    return {
      name: b.name,
      luck,
      isCurrent: isToday && currentHour >= b.hour && currentHour < b.hour + 2,
    }
  })
})

// Seeded random
function seededRandom(seed: string) {
  let h = 0
  for (let i = 0; i < seed.length; i++) {
    h = (h << 5) - h + seed.charCodeAt(i)
    h |= 0
  }
  return () => {
    h = (h * 9301 + 49297) % 233280
    return h / 233280
  }
}

const openFortune = () => {
  showFortuneExplain.value = false
  showFortune.value = true
}

const fortune = computed(() => {
  const seed = `${dateStr.value}-${data.value?.dayGanZhi || ""}-${data.value?.lunar || ""}`
  const rng = seededRandom(seed)
  const levels = ["上上签", "上签", "中签", "下签"]
  const level = levels[Math.floor(rng() * levels.length)]
  const levelClass = level.includes("上上") ? "best" : level.includes("上") ? "good" : level === "中签" ? "mid" : "bad"
  const palaces = ["东宫", "西宫", "南宫", "北宫", "中宫"]
  const palace = palaces[Math.floor(rng() * palaces.length)]
  const phrasePool = [
    "云开见月明", "风正好扬帆", "贵人暗相助", "步步踏青云",
    "莫急且徐行", "静观待时机", "小人须提防", "守旧最为先",
    "春风吹又生", "花开正当时", "水到渠自成", "天降及时雨",
    "行船遇顺风", "登高望远山", "宝剑露锋芒", "明珠卧蚌中",
  ]
  const shuffle = (arr: string[]) => {
    const a = [...arr]
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]]
    }
    return a
  }
  const picks = shuffle(phrasePool).slice(0, 4)
  const poem = [
    `今日求签问前程，${picks[0]}。`,
    `${picks[1]}心自定，`,
    `${picks[2]}莫迟疑，`,
    `${picks[3]}万事宁。`,
  ]
  const explainMap: Record<string, string> = {
    best: "此签为上上之兆，天时地利人和俱备，所求之事多能如愿，宜积极进取。",
    good: "此签主吉，虽有微澜，终能化险为夷，贵人暗藏，凡事顺势而为即可。",
    mid: "此签平平，吉凶参半，宜守不宜攻，凡事三思而后行，静待时机。",
    bad: "此签示警，近期宜低调谨慎，避免重大决策，待时运好转再图进取。",
  }
  return { palace, level, levelClass, poem, explain: explainMap[levelClass] }
})

// All times for table
const allTimes = computed(() => {
  const ji = (data.value?.jiShi || []).map((t: any) => ({ ...t, isJi: true }))
  const xiong = (data.value?.xiongShi || []).map((t: any) => ({ ...t, isJi: false }))
  return [...ji, ...xiong].sort((a, b) => {
    const ah = parseInt((a.time || "00:00").split(":")[0])
    const bh = parseInt((b.time || "00:00").split(":")[0])
    return ah - bh
  })
})
</script>

<style scoped>
.huangli-page {
  min-height: 100%;
  display: flex;
  justify-content: center;
  padding: 16px;
  padding-bottom: 60px;
}
.hl-container {
  width: 100%;
  max-width: 480px;
  color: #c9a87c;
}

/* Date bar */
.hl-date-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 8px;
}
.hl-nav-btn {
  width: 36px; height: 36px;
  border-radius: 50%;
  background: rgba(201,168,124,0.08);
  border: 1px solid rgba(201,168,124,0.15);
  color: #c9a87c;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: background 0.2s;
}
.hl-nav-btn:hover { background: rgba(201,168,124,0.18); }
.hl-date-display {
  display: flex; align-items: center; gap: 6px;
  font-size: 18px; color: #c9a87c;
  cursor: pointer;
  padding: 4px 12px;
  border-radius: 8px;
  transition: background 0.2s;
}
.hl-date-display:hover { background: rgba(201,168,124,0.08); }

/* Picker overlay */
.hl-picker-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 200;
  display: flex; align-items: flex-start; justify-content: center;
  padding-top: 80px;
}
.hl-picker-panel {
  background: #1a1410;
  border: 1px solid rgba(201,168,124,0.2);
  border-radius: 12px;
  padding: 16px;
  display: flex; gap: 10px; align-items: center;
}
.hl-picker-input {
  background: rgba(201,168,124,0.06);
  border: 1px solid rgba(201,168,124,0.2);
  border-radius: 8px;
  padding: 8px 12px;
  color: #c9a87c;
  font-size: 14px;
  outline: none;
}
.hl-picker-today {
  background: rgba(201,168,124,0.15);
  border: 1px solid rgba(201,168,124,0.3);
  color: #c9a87c;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
}

/* Lunar header */
.hl-lunar-header {
  text-align: center;
  margin: 16px 0 8px;
}
.hl-lunar-big {
  font-size: 42px;
  font-weight: 700;
  color: #c9a87c;
  letter-spacing: 4px;
}

/* GanZhi sub row */
.hl-ganzhi-sub {
  text-align: center;
  font-size: 13px;
  color: #a08060;
  display: flex;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

/* Action buttons */
.hl-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 20px;
}
.hl-action-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 12px;
  background: rgba(201,168,124,0.08);
  border: 1px solid rgba(201,168,124,0.12);
  font-size: 14px;
  color: #c9a87c;
  cursor: pointer;
  transition: background 0.2s;
}
.hl-action-btn:hover { background: rgba(201,168,124,0.14); }
.hl-action-icon {
  font-size: 20px;
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 8px;
  background: rgba(201,168,124,0.1);
}
.hl-action-icon-qiu {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23c9a87c' stroke-width='1.5'%3E%3Cpath d='M12 2a10 10 0 0 0-7.35 16.83'/%3E%3Cpath d='M12 22a10 10 0 0 0 7.35-16.83'/%3E%3Cpath d='M9 10h6v4H9z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: center;
  background-size: 20px;
}

/* Yi / Ji boxes */
.hl-yiji-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 20px;
}
.hl-yiji-box {
  border-radius: 12px;
  padding: 14px;
  border: 1px solid;
}
.hl-yi-box {
  background: rgba(74,100,50,0.12);
  border-color: rgba(74,124,58,0.3);
}
.hl-ji-box {
  background: rgba(160,60,40,0.1);
  border-color: rgba(180,80,60,0.25);
}
.hl-yiji-title {
  text-align: center;
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 10px;
  letter-spacing: 4px;
}
.hl-yi-title { color: #7aaa5a; }
.hl-ji-title { color: #c07060; }
.hl-yiji-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 13px;
  line-height: 1.8;
}
.hl-yi-items span { color: #9abf7a; }
.hl-ji-items span { color: #d09080; }

/* Info grid */
.hl-info-grid {
  display: grid;
  grid-template-columns: 1fr 1.2fr 1fr;
  gap: 1px;
  background: rgba(201,168,124,0.12);
  border: 1px solid rgba(201,168,124,0.15);
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 20px;
}
.hl-info-cell {
  background: #141010;
  padding: 14px 10px;
  text-align: center;
}
.hl-info-cell-tall {
  grid-row: span 2;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.hl-info-cell-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9a87c;
  margin-bottom: 6px;
}
.hl-info-cell-value {
  font-size: 12px;
  color: #a08060;
  line-height: 1.5;
}
.hl-info-cell-sub {
  font-size: 11px;
  color: #806040;
}
.hl-pengzu {
  white-space: pre-line;
  font-size: 11px;
}

/* Direction row */
.hl-dir-row {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 1px;
  background: rgba(201,168,124,0.12);
  border: 1px solid rgba(201,168,124,0.15);
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 20px;
}
.hl-dir-item {
  background: #141010;
  padding: 10px 4px;
  text-align: center;
}
.hl-dir-label {
  font-size: 12px;
  font-weight: 600;
  color: #c9a87c;
  margin-bottom: 4px;
}
.hl-dir-icon {
  font-size: 14px;
  color: #a08060;
  margin-bottom: 4px;
}
.hl-dir-value {
  font-size: 10px;
  color: #806040;
}

/* Branch row */
.hl-branch-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
  padding: 0 4px;
}
.hl-branch-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 6px 2px;
  border-radius: 8px;
  transition: background 0.2s;
  min-width: 28px;
}
.hl-branch-active {
  background: rgba(201,168,124,0.15);
}
.hl-branch-name {
  font-size: 13px;
  font-weight: 600;
  color: #c9a87c;
}
.hl-branch-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
}
.hl-branch-dot.good { background: #6a9c5a; }
.hl-branch-dot.bad { background: #c0392b; }
.hl-branch-luck {
  font-size: 10px;
}
.hl-branch-luck.good { color: #6a9c5a; }
.hl-branch-luck.bad { color: #c0392b; }

/* Expand bar */
.hl-expand-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  background: rgba(201,168,124,0.08);
  border: 1px solid rgba(201,168,124,0.12);
  border-radius: 10px;
  color: #c9a87c;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
  margin-bottom: 12px;
}
.hl-expand-bar:hover { background: rgba(201,168,124,0.14); }
.hl-expand-bar svg { transition: transform 0.3s; }

/* Table */
.hl-table-wrap {
  overflow-x: auto;
  margin-bottom: 20px;
}
.hl-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.hl-table th {
  background: rgba(201,168,124,0.08);
  color: #c9a87c;
  padding: 8px 6px;
  text-align: left;
  font-weight: 600;
  border-bottom: 1px solid rgba(201,168,124,0.15);
}
.hl-table td {
  padding: 8px 6px;
  color: #a08060;
  border-bottom: 1px solid rgba(201,168,124,0.06);
}
.hl-table td.good { color: #6a9c5a; }
.hl-table td.bad { color: #c0392b; }

/* Skeleton */
.hl-skeleton-wrap { padding: 8px 0; }
.hl-skeleton-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

/* Error */
.hl-error {
  text-align: center;
  padding: 40px;
  color: #c0392b;
}

/* Responsive */
/* Fortune sign */
.hl-fortune-overlay {
  position: fixed; inset: 0;
  background: rgba(80, 60, 40, 0.75);
  z-index: 300;
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
  backdrop-filter: blur(4px);
}
.hl-fortune-card {
  position: relative;
  width: 100%; max-width: 360px;
  background: #f7f0e3;
  border-radius: 16px;
  padding: 28px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.35);
}
.hl-fortune-close {
  position: absolute; top: 10px; right: 14px;
  background: none; border: none;
  font-size: 24px; color: #8a6e4b;
  cursor: pointer;
}
.hl-fortune-inner {
  background: #fffbf2;
  border-radius: 12px;
  padding: 20px;
}
.hl-fortune-border {
  border: 2px solid #c9a87c;
  border-radius: 10px;
  padding: 20px 14px;
  position: relative;
  text-align: center;
}
.hl-fortune-border::before, .hl-fortune-border::after {
  content: ""; position: absolute;
  width: 12px; height: 12px;
  border: 2px solid #c9a87c;
}
.hl-fortune-border::before { top: -2px; left: -2px; border-right: none; border-bottom: none; }
.hl-fortune-border::after { bottom: -2px; right: -2px; border-left: none; border-top: none; }
.hl-fortune-header {
  font-size: 20px; font-weight: 700;
  color: #8a6e4b;
  margin-bottom: 16px;
  letter-spacing: 4px;
}
.hl-fortune-palace {
  font-size: 14px; color: #a08060;
  margin-bottom: 6px;
}
.hl-fortune-level {
  font-size: 42px; font-weight: 700;
  margin-bottom: 16px;
  letter-spacing: 2px;
}
.hl-fortune-level.best { color: #c0392b; }
.hl-fortune-level.good { color: #d48c38; }
.hl-fortune-level.mid { color: #8a6e4b; }
.hl-fortune-level.bad { color: #555; }
.hl-fortune-poem {
  writing-mode: vertical-rl;
  text-orientation: upright;
  display: inline-flex;
  gap: 16px;
  margin: 0 auto 20px;
  font-size: 16px;
  color: #5a4630;
  line-height: 1.8;
  height: 180px;
}
.hl-fortune-line { border-right: 1px dashed rgba(201,168,124,0.4); padding-right: 8px; }
.hl-fortune-explain-btn {
  background: #c85a54;
  color: #fff;
  border: none;
  border-radius: 50%;
  width: 76px; height: 76px;
  font-size: 15px;
  letter-spacing: 1px;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(200,90,84,0.35);
  transition: transform 0.2s;
}
.hl-fortune-explain-btn:hover { transform: scale(1.05); }
.hl-fortune-explain {
  margin-top: 16px;
  padding: 12px;
  background: rgba(201,168,124,0.12);
  border-radius: 8px;
  font-size: 13px;
  color: #6a5038;
  line-height: 1.6;
  text-align: left;
}

@media (max-width: 500px) {
  .hl-dir-row { grid-template-columns: repeat(4, 1fr); }
  .hl-lunar-big { font-size: 34px; }
  .hl-info-grid { grid-template-columns: 1fr 1fr; }
  .hl-info-cell-tall { grid-row: span 1; }
}
</style>
