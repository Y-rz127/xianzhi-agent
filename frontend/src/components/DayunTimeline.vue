<template>
  <div class="dayun-timeline" v-if="dayun.length" :class="{ ready: mounted }">
    <div class="timeline-header">
      <div class="header-title">大运流年</div>
      <div class="header-sub">每十年一步大运，逐年推演</div>
    </div>
    <div class="timeline-container">
      <div class="timeline-line"></div>
      <div class="timeline-progress" v-if="highlightIndex >= 0" :style="progressStyle"></div>
      <div class="timeline-glow"></div>
      <div
        v-for="(d, idx) in dayun"
        :key="idx"
        class="dayun-node"
        :class="{ highlighted: idx === highlightIndex, expanded: expanded.has(idx) }"
        :style="{ '--stagger': idx }"
        :ref="el => setNodeRef(el, idx)"
      >
        <div class="node-glow"></div>
        <div class="node-dot">
          <span class="dot-inner"></span>
        </div>
        <div class="node-content" @click="toggle(idx)" role="button" :aria-expanded="expanded.has(idx)" tabindex="0" @keydown.enter.space.prevent="toggle(idx)">
          <div class="node-main">
            <div class="node-year">{{ d.year }}</div>
            <div class="node-meta">
              <span class="node-age">{{ d.startAge }}-{{ d.startAge + 9 }}岁</span>
              <span class="node-range">{{ d.startYear }}-{{ d.startYear + 9 }}</span>
            </div>
            <div class="node-chevron">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </div>
          </div>
          <div v-if="expanded.has(idx)" class="node-details">
            <div v-if="d.liunian && d.liunian.length" class="liunian-list">
              <div v-for="(l, i) in d.liunian" :key="i" class="liunian-item">
                <span class="liunian-year">{{ l.year }}年</span>
                <span class="liunian-ganzhi">{{ l.ganzhi }}</span>
              </div>
            </div>
            <div v-else class="liunian-placeholder">此大运暂无流年数据</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from "vue"

interface LiuNian { year: string; ganzhi: string }
interface Dayun { year: string; ganzhi: string; startAge: number; startYear: number; endAge?: number; endYear?: number; liunian?: LiuNian[] }

const props = withDefaults(defineProps<{
  dayun: Dayun[]
  highlightYear?: number
}>(), {
  highlightYear: undefined
})

const expanded = ref<Set<number>>(new Set())
const mounted = ref(false)
const nodeRefs = ref<Record<number, HTMLElement>>({})
const progressStyle = ref<Record<string, string>>({})

const highlightIndex = computed(() => {
  const year = props.highlightYear
  if (year === undefined) return -1
  return props.dayun.findIndex(d => d.startYear <= year && (d.endYear ?? d.startYear + 9) >= year)
})

function toggle(idx: number) {
  const next = new Set(expanded.value)
  if (next.has(idx)) next.delete(idx)
  else next.add(idx)
  expanded.value = next
}

function setNodeRef(el: any, idx: number) {
  if (el && el instanceof HTMLElement) nodeRefs.value[idx] = el
}

function updateProgress() {
  nextTick(() => {
    const idx = highlightIndex.value
    if (idx < 0) return
    const el = nodeRefs.value[idx]
    const container = el?.parentElement
    if (!el || !container) return
    const top = el.offsetTop + el.offsetHeight / 2
    progressStyle.value = { height: `${top}px` }
  })
}

onMounted(() => {
  mounted.value = true
  updateProgress()
})

watch(highlightIndex, updateProgress)
watch(expanded, updateProgress, { deep: true })
watch(() => props.dayun, updateProgress, { deep: true })
</script>

<style scoped>
.dayun-timeline { position: relative; padding: 20px; border-radius: var(--radius);
  background: rgba(15,21,32,0.92); border: 1px solid var(--border-bright); overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,0.35), inset 0 0 40px rgba(212,175,55,0.02); }
.dayun-timeline::before { content: ""; position: absolute; inset: 0;
  background: url("data:image/svg+xml,%3Csvg width='40' height='40' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='20' cy='20' r='18' fill='none' stroke='%23d4af37' stroke-opacity='0.02'/%3E%3C/svg%3E"); opacity: 0.5; pointer-events: none; }

.timeline-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 20px; position: relative; z-index: 1; }
.header-title { font-size: 14px; color: var(--accent-light); letter-spacing: 4px; font-weight: 600; text-shadow: 0 0 10px rgba(212,175,55,0.3); }
.header-sub { font-size: 11px; color: var(--text-muted); letter-spacing: 2px; }

.timeline-container { position: relative; padding-left: 28px; z-index: 1; }

.timeline-line { position: absolute; left: 11px; top: 0; bottom: 0; width: 2px;
  background: linear-gradient(180deg, rgba(212,175,55,0.5), rgba(139,92,246,0.2)); }

.timeline-progress { position: absolute; left: 11px; top: 0; width: 2px;
  background: linear-gradient(180deg, rgba(212,175,55,0.95), rgba(212,175,55,0.2));
  box-shadow: 0 0 12px rgba(212,175,55,0.45); transition: height 0.5s ease; z-index: 2; }

.timeline-glow { position: absolute; left: 7px; top: 0; bottom: 0; width: 10px;
  background: linear-gradient(180deg, rgba(212,175,55,0.1), transparent); filter: blur(4px); }

.dayun-node { position: relative; padding-left: 20px; margin-bottom: 20px;
  opacity: 0; transform: translateY(16px); }
.dayun-timeline.ready .dayun-node { animation: nodeEnter 0.5s ease-out both; animation-delay: calc(var(--stagger) * 0.1s); }
.dayun-node:last-child { margin-bottom: 0; }

@keyframes nodeEnter { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }

.dayun-node.highlighted .node-content { background: linear-gradient(135deg, rgba(212,175,55,0.08), rgba(139,92,246,0.05)); border-color: rgba(212,175,55,0.35); box-shadow: 0 0 18px rgba(212,175,55,0.12); }
.dayun-node.highlighted .node-dot { background: var(--accent-light); box-shadow: 0 0 14px rgba(212,175,55,0.7); transform: scale(1.15); }
.dayun-node.highlighted .node-year { color: var(--accent-light); text-shadow: 0 0 10px rgba(212,175,55,0.35); }

.node-glow { position: absolute; left: -3px; top: 5px; width: 18px; height: 18px;
  background: radial-gradient(circle, rgba(212,175,55,0.3), transparent); border-radius: 50%; }

.node-dot { position: absolute; left: -3px; top: 5px; width: 12px; height: 12px;
  border-radius: 50%; background: var(--accent); box-shadow: 0 0 10px rgba(212,175,55,0.4);
  display: flex; align-items: center; justify-content: center; transition: all 0.25s; }
.dot-inner { width: 4px; height: 4px; background: #0a0f1a; border-radius: 50%; }

.node-content { background: rgba(255,255,255,0.02); border-radius: 10px; padding: 12px;
  border: 1px solid var(--border); transition: all 0.25s; cursor: pointer; outline: none; }
.node-content:hover { background: rgba(212,175,55,0.04); border-color: rgba(212,175,55,0.15); }
.node-content:focus-visible { box-shadow: 0 0 0 2px rgba(212,175,55,0.25); }

.node-main { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.node-year { font-size: 16px; font-weight: bold; color: var(--accent-light); letter-spacing: 2px; }
.node-meta { display: flex; flex-direction: column; gap: 2px; margin-right: auto; }
.node-age { font-size: 12px; color: var(--text-dim); }
.node-range { font-size: 11px; color: var(--text-muted); }
.node-chevron { color: var(--text-muted); transition: transform 0.25s; }
.dayun-node.expanded .node-chevron { transform: rotate(180deg); color: var(--accent); }

.node-details { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border);
  animation: detailsIn 0.25s ease; }
@keyframes detailsIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: translateY(0); } }

.liunian-list { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }
.liunian-item { display: flex; flex-direction: column; align-items: center; gap: 2px; font-size: 11px;
  padding: 6px 4px; background: rgba(255,255,255,0.02); border-radius: 6px; color: var(--text-dim);
  border: 1px solid var(--border); }
.liunian-year { font-size: 10px; color: var(--text-muted); }
.liunian-ganzhi { font-size: 12px; color: var(--text); font-weight: 600; }
.liunian-placeholder { font-size: 12px; color: var(--text-muted); padding: 8px; text-align: center; }

@media (max-width: 600px) {
  .timeline-container { padding-left: 22px; }
  .node-content { padding: 10px; }
  .node-year { font-size: 14px; }
  .node-main { flex-wrap: wrap; }
  .liunian-list { grid-template-columns: repeat(3, 1fr); }
}
</style>
