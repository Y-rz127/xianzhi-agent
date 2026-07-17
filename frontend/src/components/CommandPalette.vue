<template>
  <Teleport to="body">
    <div v-if="visible" class="cmd-overlay" @click.self="close">
      <div class="cmd-panel">
        <div class="cmd-header">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input
            id="cmd-search"
            name="cmd-search"
            aria-label="命令搜索"
            ref="inputEl"
            v-model="query"
            placeholder="输入命令搜索..."
            class="cmd-input"
            @keydown="onKeydown"
          />
          <kbd class="cmd-hint">ESC</kbd>
        </div>
        <div class="cmd-body">
          <div class="cmd-section-label" v-if="filteredItems.length > 0">导航</div>
          <div v-if="filteredItems.length === 0" class="cmd-empty">无匹配结果</div>
          <div
            v-for="(item, i) in filteredItems"
            :key="item.id"
            :class="['cmd-item', { active: i === activeIndex }]"
            @click="execute(item)"
            @mouseenter="activeIndex = i"
          >
            <span class="cmd-item-icon" v-html="item.icon"></span>
            <div class="cmd-item-info">
              <div class="cmd-item-title">{{ item.title }}</div>
              <div class="cmd-item-desc">{{ item.desc }}</div>
            </div>
            <kbd class="cmd-item-shortcut" v-if="item.shortcut">{{ item.shortcut }}</kbd>
          </div>
        </div>
        <div class="cmd-footer">
          <span><kbd>↑↓</kbd> 导航</span>
          <span><kbd>Enter</kbd> 选择</span>
          <span><kbd>Esc</kbd> 关闭</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from "vue"
import { useRouter } from "vue-router"

interface CmdItem {
  id: string
  title: string
  desc: string
  icon: string
  shortcut?: string
  action: () => void
}

const router = useRouter()
const visible = ref(false)
const query = ref("")
const activeIndex = ref(0)
const inputEl = ref<HTMLInputElement | null>(null)

const items: CmdItem[] = [
  {
    id: "xianzhi",
    title: "命理分析",
    desc: "八字排盘、大运流年、合婚分析",
    icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',
    shortcut: "Ctrl+1",
    action: () => router.push("/xianzhi"),
  },
  {
    id: "rag",
    title: "知识问答",
    desc: "命理知识库检索，古籍经典查询",
    icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
    action: () => { router.push("/xianzhi"); setTimeout(() => window.dispatchEvent(new CustomEvent("xianzhi-switch-rag")), 100) },
  },
  {
    id: "new-session",
    title: "新建会话",
    desc: "清空当前对话，开始新的命理分析",
    icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>',
    action: () => { router.push("/xianzhi"); setTimeout(() => window.dispatchEvent(new CustomEvent("xianzhi-new-session")), 100) },
  },
]

const filteredItems = computed(() => {
  if (!query.value.trim()) return items
  const q = query.value.toLowerCase()
  return items.filter(
    (item) =>
      item.title.toLowerCase().includes(q) ||
      item.desc.toLowerCase().includes(q)
  )
})

const open = () => {
  visible.value = true
  query.value = ""
  activeIndex.value = 0
  nextTick(() => inputEl.value?.focus())
}

const close = () => {
  visible.value = false
}

const execute = (item: CmdItem) => {
  item.action()
  close()
}

const onKeydown = (e: KeyboardEvent) => {
  if (e.key === "ArrowDown") {
    e.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, filteredItems.value.length - 1)
  } else if (e.key === "ArrowUp") {
    e.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  } else if (e.key === "Enter") {
    e.preventDefault()
    const item = filteredItems.value[activeIndex.value]
    if (item) execute(item)
  } else if (e.key === "Escape") {
    close()
  }
}

watch(visible, (val) => {
  if (val) {
    nextTick(() => inputEl.value?.focus())
  }
})

const onGlobalKeydown = (e: KeyboardEvent) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "k") {
    e.preventDefault()
    visible.value ? close() : open()
  }
  if (e.key === "Escape" && visible.value) {
    close()
  }
}

import { onMounted, onUnmounted } from "vue"
onMounted(() => window.addEventListener("keydown", onGlobalKeydown))
onUnmounted(() => window.removeEventListener("keydown", onGlobalKeydown))

defineExpose({ open, close })
</script>

<style scoped>
.cmd-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
  display: flex; align-items: flex-start; justify-content: center; padding-top: 12vh;
  z-index: 2000; animation: fadeIn 0.15s ease;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.cmd-panel {
  width: 90%; max-width: 520px; background: linear-gradient(135deg, rgba(18,26,42,0.98), rgba(12,18,32,0.98));
  border: 1px solid var(--border-bright); border-radius: 16px;
  box-shadow: 0 24px 60px rgba(0,0,0,0.5), 0 0 40px rgba(212,175,55,0.08);
  overflow: hidden;
  animation: slideDown 0.2s ease-out;
}
@keyframes slideDown { from { opacity: 0; transform: translateY(-12px) scale(0.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
.cmd-header {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 18px; border-bottom: 1px solid var(--border);
  color: var(--text-dim);
}
.cmd-input {
  flex: 1; background: transparent; border: none; outline: none;
  font-size: 15px; color: var(--text); caret-color: var(--accent);
}
.cmd-input::placeholder { color: var(--text-dim); }
.cmd-hint {
  font-size: 11px; padding: 3px 8px; background: rgba(255,255,255,0.06);
  border: 1px solid var(--border); border-radius: 5px; color: var(--text-dim);
  font-family: inherit;
}
.cmd-body { max-height: 320px; overflow-y: auto; padding: 8px; }
.cmd-section-label {
  font-size: 11px; color: var(--text-dim); letter-spacing: 2px;
  padding: 8px 12px 4px; text-transform: uppercase;
}
.cmd-empty { padding: 24px; text-align: center; color: var(--text-dim); font-size: 13px; }
.cmd-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 12px;
  border-radius: 10px; cursor: pointer; transition: all 0.15s;
}
.cmd-item:hover, .cmd-item.active { background: rgba(212,175,55,0.08); }
.cmd-item-icon { width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.04); flex-shrink: 0; color: var(--text-dim); }
.cmd-item.active .cmd-item-icon { background: rgba(212,175,55,0.12); color: var(--accent-light); }
.cmd-item-info { flex: 1; min-width: 0; }
.cmd-item-title { font-size: 14px; color: var(--text); font-weight: 500; }
.cmd-item.active .cmd-item-title { color: var(--accent-light); }
.cmd-item-desc { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
.cmd-item-shortcut {
  font-size: 11px; padding: 2px 6px; background: rgba(255,255,255,0.04);
  border: 1px solid var(--border); border-radius: 4px; color: var(--text-dim);
  font-family: inherit;
}
.cmd-footer {
  display: flex; justify-content: center; gap: 18px;
  padding: 10px 18px; border-top: 1px solid var(--border);
  font-size: 11px; color: var(--text-dim);
}
.cmd-footer kbd {
  font-size: 10px; padding: 1px 5px; background: rgba(255,255,255,0.05);
  border: 1px solid var(--border); border-radius: 3px; margin-right: 3px;
  font-family: inherit;
}
</style>