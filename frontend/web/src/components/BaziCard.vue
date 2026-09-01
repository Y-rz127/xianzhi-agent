<template>
  <div class="bazi-card" v-if="pillars.length">
    <div class="card-header">
      <div class="card-title">四柱命盘</div>
      <div class="card-sub">年 · 月 · 日 · 时</div>
    </div>
    <div class="pillars">
      <div v-for="(p, idx) in pillars" :key="p.name" class="pillar" :class="{ 'day-master': p.name === '日柱' }" :style="{ animationDelay: `${idx * 0.1}s` }">
        <div class="pillar-glow"></div>
        <div class="pillar-name">{{ p.name }}</div>
        <div class="pillar-gan" :style="{ color: ganColor(p.ganzhi[0]) }">{{ p.ganzhi[0] }}</div>
        <div class="pillar-zhi" :style="{ color: zhiColor(p.ganzhi[1]) }">{{ p.ganzhi[1] }}</div>
        <div class="pillar-nayin">{{ p.nayin }}</div>
        <div v-if="p.name === '日柱'" class="day-badge">日主</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Pillar } from "../api"
defineProps<{ pillars: Pillar[] }>()

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
</script>

<style scoped>
.bazi-card {
  position: relative; border-radius: var(--radius); padding: 20px; margin-bottom: 16px;
  background: rgba(15,21,32,0.92); border: 1px solid var(--border-bright);
  box-shadow: 0 8px 32px rgba(0,0,0,0.35), inset 0 0 40px rgba(212,175,55,0.02);
  overflow: hidden; animation: fadeInUp 0.5s ease-out forwards;
}
.bazi-card::before {
  content: ""; position: absolute; inset: 0;
  background: url("data:image/svg+xml,%3Csvg width='60' height='60' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M30 0L60 30L30 60L0 30Z' fill='none' stroke='%23d4af37' stroke-opacity='0.03'/%3E%3C/svg%3E");
  opacity: 0.5; pointer-events: none;
}
.card-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 18px; position: relative; z-index: 1; }
.card-title { font-size: 14px; color: var(--accent-light); letter-spacing: 4px; font-weight: 600; text-shadow: 0 0 10px rgba(212,175,55,0.3); }
.card-sub { font-size: 11px; color: var(--text-muted); letter-spacing: 2px; }

.pillars { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; position: relative; z-index: 1; }

.pillar {
  position: relative; background: rgba(255,255,255,0.02); border-radius: 12px; padding: 16px 10px;
  text-align: center; border: 1px solid var(--border); transition: all 0.3s ease;
  animation: fadeInUp 0.4s ease-out backwards;
}
.pillar:hover { transform: translateY(-3px); border-color: rgba(212,175,55,0.2); box-shadow: 0 6px 20px rgba(0,0,0,0.25); }

.pillar.day-master {
  background: linear-gradient(135deg, rgba(212,175,55,0.08), rgba(139,92,246,0.05));
  border-color: rgba(212,175,55,0.35); box-shadow: 0 0 16px rgba(212,175,55,0.1);
}

.pillar-glow {
  position: absolute; inset: 0; border-radius: 12px; opacity: 0;
  background: radial-gradient(circle at center, rgba(212,175,55,0.1), transparent 70%);
  transition: opacity 0.3s; pointer-events: none;
}
.pillar:hover .pillar-glow { opacity: 1; }

.pillar-name { font-size: 11px; color: var(--text-muted); margin-bottom: 10px; letter-spacing: 2px; }
.pillar-gan { font-size: 22px; font-weight: bold; color: var(--text); letter-spacing: 2px; margin-bottom: 4px; }
.pillar-zhi { font-size: 22px; font-weight: bold; color: var(--text); letter-spacing: 2px; margin-bottom: 6px; }
.pillar.day-master .pillar-gan,
.pillar.day-master .pillar-zhi { color: var(--accent-light); text-shadow: 0 0 10px rgba(212,175,55,0.4); }
.pillar-nayin { font-size: 11px; color: var(--text-muted); }

.day-badge {
  position: absolute; top: -6px; right: -4px; background: var(--accent); color: #0a0f1a;
  font-size: 9px; padding: 2px 8px; border-radius: 10px; font-weight: bold;
  box-shadow: 0 0 8px rgba(212,175,55,0.4);
}

@media (max-width: 600px) {
  .pillars { grid-template-columns: repeat(2, 1fr); gap: 10px; }
}
</style>