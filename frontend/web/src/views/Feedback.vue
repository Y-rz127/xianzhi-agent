<template>
  <div class="feedback-page">
    <div class="page-header">
      <h2>用户反馈</h2>
      <div class="header-actions">
        <span class="count">{{ items.length }} 条</span>
        <button class="btn-refresh" :disabled="loading" @click="loadData">
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div v-if="loading && items.length === 0" class="loading">
      加载中...
    </div>

    <div v-else-if="items.length === 0" class="empty">
      <p>暂无用户反馈</p>
    </div>

    <div v-else class="feedback-list">
      <div v-for="item in items" :key="item.id" class="feedback-card">
        <div class="card-meta">
          <span class="meta-time">{{ formatTime(item.created_at) }}</span>
          <span v-if="item.contact" class="meta-contact">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
            {{ item.contact }}
          </span>
          <span v-if="item.user_nickname" class="meta-user">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            {{ item.user_nickname }}
          </span>
          <span v-else class="meta-anonymous">匿名</span>
          <button class="btn-delete" @click="handleDelete(item.id)" title="删除此条反馈">删除</button>
        </div>
        <div class="card-content">{{ item.content }}</div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <Teleport to="body">
      <div v-if="showConfirm" class="confirm-overlay" @click.self="showConfirm = false">
        <div class="confirm-dialog">
          <p class="confirm-msg">确定删除此条反馈？</p>
          <div class="confirm-actions">
            <button class="btn-confirm-cancel" @click="showConfirm = false">取消</button>
            <button class="btn-confirm-ok" :disabled="deleting" @click="confirmDelete">
              {{ deleting ? '删除中...' : '确定' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchFeedbacks, deleteFeedback } from '@/api'

export interface FeedbackItem {
  id: string
  user_id: string | null
  user_nickname?: string | null
  content: string
  contact: string
  created_at: string
}

const items = ref<FeedbackItem[]>([])
const loading = ref(false)
const showConfirm = ref(false)
const pendingDeleteId = ref<string | null>(null)
const deleting = ref(false)

onMounted(() => loadData())

async function loadData() {
  loading.value = true
  try {
    items.value = await fetchFeedbacks()
  } catch (e) {
    console.error('获取反馈失败', e)
  } finally {
    loading.value = false
  }
}

function formatTime(t: string): string {
  try {
    const d = new Date(t)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch { return t }
}

function handleDelete(fid: string) {
  pendingDeleteId.value = fid
  showConfirm.value = true
}

async function confirmDelete() {
  if (!pendingDeleteId.value) return
  deleting.value = true
  try {
    await deleteFeedback(pendingDeleteId.value)
    items.value = items.value.filter(i => i.id !== pendingDeleteId.value)
  } catch (e) {
    console.error('删除失败', e)
  } finally {
    deleting.value = false
    showConfirm.value = false
    pendingDeleteId.value = null
  }
}
</script>

<style scoped>
.feedback-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 40px 28px 80px;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 32px;
}
.page-header h2 {
  font-size: 26px;
  color: var(--accent-light);
  letter-spacing: 3px;
  margin: 0;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}
.count {
  font-size: 13px;
  color: var(--text-dim);
}
.btn-refresh {
  padding: 8px 20px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: rgba(212,175,55,0.08);
  color: var(--accent-light);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.25s;
}
.btn-refresh:hover:not(:disabled) { background: rgba(212,175,55,0.16); border-color: rgba(212,175,55,0.3); }
.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }

.loading, .empty {
  text-align: center;
  padding: 80px 0;
  color: var(--text-dim);
  font-size: 15px;
}

.feedback-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.feedback-card {
  background: rgba(10,15,26,0.6);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 22px 24px;
  transition: border-color 0.25s;
}
.feedback-card:hover { border-color: rgba(126,200,227,0.25); }

.card-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.meta-time {
  font-size: 12px;
  color: rgba(138,155,176,0.5);
  font-family: monospace;
}
.meta-contact {
  font-size: 12px;
  color: #7ec8e3;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.meta-user {
  font-size: 12px;
  color: #e88bb8;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.meta-anonymous {
  font-size: 12px;
  color: rgba(138,155,176,0.35);
  padding: 1px 8px;
  border-radius: 8px;
  background: rgba(255,255,255,0.03);
}

.card-content {
  font-size: 15px;
  color: var(--text);
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.btn-delete {
  margin-left: auto;
  padding: 3px 12px;
  border-radius: 8px;
  border: 1px solid rgba(220,100,100,0.25);
  background: transparent;
  color: rgba(220,120,120,0.7);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-delete:hover { background: rgba(220,80,80,0.12); color: #dc7878; border-color: rgba(220,100,100,0.4); }

/* 确认弹窗 */
.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.55);
  backdrop-filter: blur(3px);
}
.confirm-dialog {
  background: #151c2c;
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 28px 32px;
  min-width: 300px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.5);
}
.confirm-msg {
  font-size: 15px;
  color: var(--text);
  margin: 0 0 24px;
}
.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.btn-confirm-cancel,
.btn-confirm-ok {
  padding: 7px 20px;
  border-radius: 9px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid var(--border);
}
.btn-confirm-cancel {
  background: transparent;
  color: var(--text-dim);
}
.btn-confirm-cancel:hover { background: rgba(255,255,255,0.05); }
.btn-confirm-ok {
  background: rgba(220,80,80,0.15);
  color: #dc7878;
  border-color: rgba(220,80,80,0.25);
}
.btn-confirm-ok:hover:not(:disabled) { background: rgba(220,80,80,0.25); }
.btn-confirm-ok:disabled { opacity: 0.5; cursor: not-allowed; }
</style>