<template>
  <div class="dayun-timeline" v-if="dayun.length">
    <div class="timeline-header">
      <div class="header-title">大运流年</div>
      <div class="header-sub">每十年一步大运，逐年推演</div>
    </div>
    <div class="timeline-container">
      <div class="timeline-line"></div>
      <div class="timeline-glow"></div>
      <div v-for="(d, idx) in dayun" :key="idx" class="dayun-node" :style="{ animationDelay: `${idx * 0.15}s` }">
        <div class="node-glow"></div>
        <div class="node-dot">
          <span class="dot-inner"></span>
        </div>
        <div class="node-content">
          <div class="node-year">{{ d.year }}</div>
          <div class="node-age">{{ d.startAge }}-{{ d.startAge + 9 }}岁</div>
          <div class="node-range">{{ d.startYear }}-{{ d.startYear + 9 }}</div>
          <div v-if="d.liunian && d.liunian.length" class="liunian-list">
            <div v-for="(l, i) in d.liunian.slice(0, 5)" :key="i" class="liunian-item">
              {{ l.year }}年 {{ l.ganzhi }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface LiuNian { year: string; ganzhi: string }
interface Dayun { year: string; ganzhi: string; startAge: number; startYear: number; liunian?: LiuNian[] }
defineProps<{ dayun: Dayun[] }>()
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

.timeline-container { position: relative; padding-left: 28px; position: relative; z-index: 1; }

.timeline-line { position: absolute; left: 11px; top: 0; bottom: 0; width: 2px;
  background: linear-gradient(180deg, rgba(212,175,55,0.5), rgba(139,92,246,0.2)); }

.timeline-glow { position: absolute; left: 7px; top: 0; bottom: 0; width: 10px;
  background: linear-gradient(180deg, rgba(212,175,55,0.1), transparent); filter: blur(4px); }

.dayun-node { position: relative; padding-left: 20px; margin-bottom: 20px; animation: fadeInUp 0.4s ease-out backwards; }
.dayun-node:last-child { margin-bottom: 0; }

.node-glow { position: absolute; left: -3px; top: 5px; width: 18px; height: 18px;
  background: radial-gradient(circle, rgba(212,175,55,0.3), transparent); border-radius: 50%; }

.node-dot { position: absolute; left: -3px; top: 5px; width: 12px; height: 12px;
  border-radius: 50%; background: var(--accent); box-shadow: 0 0 10px rgba(212,175,55,0.4);
  display: flex; align-items: center; justify-content: center; }
.dot-inner { width: 4px; height: 4px; background: #0a0f1a; border-radius: 50%; }

.node-content { background: rgba(255,255,255,0.02); border-radius: 10px; padding: 12px;
  border: 1px solid var(--border); transition: all 0.25s; }
.node-content:hover { background: rgba(212,175,55,0.04); border-color: rgba(212,175,55,0.15); }

.node-year { font-size: 16px; font-weight: bold; color: var(--accent-light); letter-spacing: 2px; margin-bottom: 4px; }
.node-age { font-size: 12px; color: var(--text-dim); margin-bottom: 2px; }
.node-range { font-size: 11px; color: var(--text-muted); margin-bottom: 8px; }

.liunian-list { display: flex; flex-wrap: wrap; gap: 6px; }
.liunian-item { font-size: 11px; padding: 3px 8px; background: rgba(255,255,255,0.02);
  border-radius: 6px; color: var(--text-dim); border: 1px solid var(--border); }

@media (max-width: 600px) {
  .timeline-container { padding-left: 22px; }
  .node-content { padding: 10px; }
  .node-year { font-size: 14px; }
}
</style>
