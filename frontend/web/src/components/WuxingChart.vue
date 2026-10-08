<template>
  <div class="wuxing-chart" v-if="items.length">
    <div class="card-header">
      <div class="chart-title">五行分布</div>
      <div class="chart-sub">金 · 木 · 水 · 火 · 土</div>
    </div>
    <div class="bars">
      <div v-for="(item, idx) in items" :key="item.name" class="bar-item" :style="{ animationDelay: `${idx * 0.1}s` }">
        <div class="bar-count">{{ item.count }}</div>
        <div class="bar-container">
          <div class="bar-glow" :style="{ height: barHeight(item.count) + '%', background: item.color, boxShadow: `0 0 12px ${item.color}` }"></div>
          <div class="bar-fill" :style="{ height: barHeight(item.count) + '%', background: item.color }"></div>
        </div>
        <div class="bar-label" :style="{ color: item.color }">{{ item.name }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import type { WuxingItem } from "../api"
const props = defineProps<{ items: WuxingItem[] }>()
const maxCount = computed(() => Math.max(...props.items.map((i) => i.count), 1))
const barHeight = (count: number) => (count / maxCount.value) * 100
</script>

<style scoped>
.wuxing-chart {
  position: relative; border-radius: var(--radius); padding: 20px; margin-bottom: 16px;
  background: rgba(15,21,32,0.92); border: 1px solid var(--border-bright); overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,0.35), inset 0 0 40px rgba(212,175,55,0.02);
  animation: fadeInUp 0.5s ease-out forwards;
}
.card-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 18px; }
.chart-title { font-size: 14px; color: var(--accent-light); letter-spacing: 4px; font-weight: 600; text-shadow: 0 0 10px rgba(212,175,55,0.3); }
.chart-sub { font-size: 11px; color: var(--text-muted); letter-spacing: 2px; }

.bars { display: flex; justify-content: space-around; align-items: flex-end; height: 150px; }
.bar-item { display: flex; flex-direction: column; align-items: center; gap: 8px; width: 16%; animation: fadeInUp 0.5s ease-out backwards; }

.bar-count { font-size: 14px; font-weight: bold; color: var(--text); min-height: 20px; }

.bar-container { position: relative; width: 100%; height: 100px; display: flex; align-items: flex-end;
  background: rgba(255,255,255,0.02); border-radius: 8px 8px 0 0; overflow: hidden; }

.bar-fill { width: 100%; border-radius: 8px 8px 0 0; transition: height 0.8s cubic-bezier(0.34, 1.56, 0.64, 1);
  min-height: 4px; position: relative; z-index: 2; }

.bar-glow { position: absolute; bottom: 0; left: 0; right: 0; opacity: 0.3; filter: blur(6px);
  z-index: 1; transition: height 0.8s cubic-bezier(0.34, 1.56, 0.64, 1); }

.bar-label { font-size: 14px; font-weight: bold; text-shadow: 0 0 8px currentColor; }

@media (max-width: 600px) {
  .bars { height: 120px; }
  .bar-container { height: 80px; }
  .bar-label { font-size: 12px; }
}
</style>
