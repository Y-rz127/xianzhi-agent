<template>
  <div class="legal-page">
    <div class="legal-card">
      <div class="legal-header">
        <router-link to="/" class="back-link">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          返回首页
        </router-link>
        <h1>{{ title }}</h1>
      </div>
      <div class="legal-body">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<style scoped>
.legal-page {
  height: 100vh; overflow-y: auto; display: flex; justify-content: center;
  padding: 40px 20px;
}
.legal-card {
  width: 100%; max-width: 720px; background: linear-gradient(135deg, rgba(18,26,42,0.95), rgba(12,18,32,0.95));
  border: 1px solid var(--border); border-radius: var(--radius); padding: 32px;
}
.legal-header { margin-bottom: 28px; }
.back-link {
  display: inline-flex; align-items: center; gap: 6px; color: var(--text-dim);
  font-size: 13px; text-decoration: none; margin-bottom: 16px; transition: color 0.2s;
}
.back-link:hover { color: var(--accent); }
.legal-header h1 { font-size: 22px; color: var(--accent-light); letter-spacing: 2px; }
.legal-body { font-size: 13px; color: var(--text-dim); line-height: 1.9; }
.legal-body :deep(h2) { font-size: 16px; color: var(--text); margin: 24px 0 10px; }
.legal-body :deep(p) { margin-bottom: 12px; }
.legal-body :deep(strong) { color: var(--accent-light); }
</style>