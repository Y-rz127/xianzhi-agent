<template>
  <div class="answer-feedback-page">
    <!-- Toast 提示 -->
    <Transition name="toast">
      <div v-if="toastMessage" class="toast" :class="toastType">
        <span class="toast-icon">{{ toastType === 'success' ? '✓' : '✗' }}</span>
        <span>{{ toastMessage }}</span>
      </div>
    </Transition>

    <!-- 自定义确认弹窗 -->
    <Transition name="modal">
      <div v-if="pendingUnpromote" class="modal-mask" @click.self="cancelUnpromote">
        <div class="modal-box">
          <div class="modal-title">
            <span class="title-dot" />
            取消案例沉淀
          </div>
          <div class="modal-body">
            <p>确认取消该案例的沉淀吗？</p>
            <p class="modal-hint">已沉淀到 <code>chart_cases</code> 的对应行会被删除，前端列表将恢复为「转案例」状态。</p>
          </div>
          <div class="modal-actions">
            <button class="modal-btn" :disabled="unpromoting" @click="cancelUnpromote">取消</button>
            <button class="modal-btn primary danger" :disabled="unpromoting" @click="confirmUnpromote">
              {{ unpromoting ? '处理中…' : '确认取消' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <div class="page-header">
      <div>
        <h2>回答反馈</h2>
        <p>用于筛选案例、构建 SFT 样本和观察回答质量</p>
      </div>
      <div class="header-actions">
        <select v-model="ratingFilter" class="filter-select" @change="loadData">
          <option value="">全部</option>
          <option value="up">好评</option>
          <option value="down">差评</option>
        </select>
        <button class="btn" :disabled="loading" @click="loadData">{{ loading ? "加载中..." : "刷新" }}</button>
        <button class="btn primary" @click="exportSft">导出 SFT</button>
        <button class="btn" @click="exportDpo" :disabled="!hasBoth">导出 DPO</button>
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <span>总反馈</span>
        <strong>{{ items.length }}</strong>
      </div>
      <div class="stat-card good">
        <span>好评</span>
        <strong>{{ upCount }}</strong>
      </div>
      <div class="stat-card bad">
        <span>差评</span>
        <strong>{{ downCount }}</strong>
      </div>
      <div class="stat-card">
        <span>好评率</span>
        <strong>{{ upRate }}%</strong>
      </div>
    </div>

    <div v-if="loading && items.length === 0" class="empty">加载中...</div>
    <div v-else-if="items.length === 0" class="empty">暂无回答反馈</div>

    <div v-else class="feedback-list">
      <article v-for="item in items" :key="item.id" class="feedback-card">
        <div class="card-top">
          <span :class="['rating-pill', item.rating]">{{ item.rating === "up" ? "好评" : "差评" }}</span>
          <span v-if="item.reason" class="reason-pill">{{ item.reason }}</span>
          <span v-if="item.reviewed" class="reviewed-pill">已审核</span>
          <span class="time">{{ formatTime(item.created_at) }}</span>
          <span class="session">{{ item.conversation_id || "无会话" }}</span>
          <span class="card-actions">
            <button v-if="!item.reviewed" class="act-btn" @click="doReview(item)">审核</button>
            <template v-if="item.rating === 'up' && item.reviewed">
              <button v-if="!item.case_id" class="act-btn promote" @click="doPromote(item)">转案例</button>
              <template v-else>
                <span class="act-btn done" title="已转案例 case_id 可在管理后台查看">已转案例</span>
                <button class="act-btn rollback" @click="doUnpromote(item)">取消案例沉淀</button>
              </template>
            </template>
          </span>
        </div>
        <div class="qa-block">
          <div class="label">问题</div>
          <p>{{ item.question || "未记录问题" }}</p>
        </div>
        <div class="qa-block answer">
          <div class="label">回答</div>
          <p>{{ item.answer }}</p>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { answerFeedbackSftExportUrl, answerFeedbackDpoExportUrl, fetchAnswerFeedbacks, reviewAnswerFeedback, promoteAnswerToCase, unpromoteAnswerToCase, type AnswerFeedbackItem } from "@/api"

const items = ref<AnswerFeedbackItem[]>([])
const loading = ref(false)
const ratingFilter = ref<"" | "up" | "down">("")

// 取消案例沉淀自定义弹窗状态
const pendingUnpromote = ref<AnswerFeedbackItem | null>(null)
const unpromoting = ref(false)

const toastMessage = ref('')
const toastType = ref<'success' | 'error'>('success')
let toastTimer: number | null = null

function showToast(msg: string, type: 'success' | 'error' = 'success') {
  toastMessage.value = msg
  toastType.value = type
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => { toastMessage.value = '' }, 3000)
}

const upCount = computed(() => items.value.filter(i => i.rating === "up").length)
const downCount = computed(() => items.value.filter(i => i.rating === "down").length)
const hasBoth = computed(() => upCount.value > 0 && downCount.value > 0)
const upRate = computed(() => {
  if (!items.value.length) return 0
  return Math.round((upCount.value / items.value.length) * 100)
})

onMounted(() => loadData())

async function loadData() {
  loading.value = true
  try {
    items.value = await fetchAnswerFeedbacks(300, ratingFilter.value || undefined)
  } catch (e) {
    console.error("获取回答反馈失败", e)
  } finally {
    loading.value = false
  }
}

function exportSft() {
  window.open(answerFeedbackSftExportUrl("up", 1000), "_blank")
}

function exportDpo() {
  window.open(answerFeedbackDpoExportUrl(500), "_blank")
}

async function doReview(item: AnswerFeedbackItem) {
  try {
    await reviewAnswerFeedback(item.id)
    item.reviewed = true
  } catch (e) {
    console.error("审核失败", e)
  }
}

async function doPromote(item: AnswerFeedbackItem) {
  try {
    const result = await promoteAnswerToCase(item.id)
    item.case_id = result.case_id
    showToast(`案例已沉淀: ${result.case_id}`, 'success')
  } catch (e: any) {
    console.error("转案例失败", e)
    showToast(`转案例失败: ${e.message || e}`, 'error')
  }
}

async function doUnpromote(item: AnswerFeedbackItem) {
  pendingUnpromote.value = item
}

function cancelUnpromote() {
  pendingUnpromote.value = null
}

async function confirmUnpromote() {
  const item = pendingUnpromote.value
  if (!item) return
  unpromoting.value = true
  try {
    await unpromoteAnswerToCase(item.id)
    item.case_id = ""
    pendingUnpromote.value = null
    showToast('案例沉淀已取消', 'success')
  } catch (e: any) {
    console.error("取消案例沉淀失败", e)
    showToast(`取消案例沉淀失败: ${e.message || e}`, 'error')
  } finally {
    unpromoting.value = false
  }
}

function formatTime(t: string): string {
  try {
    const d = new Date(t)
    const pad = (n: number) => String(n).padStart(2, "0")
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return t
  }
}
</script>

<style scoped>
.toast {
  position: fixed;
  top: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  border-radius: 10px;
  font-size: 14px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(10px);
  pointer-events: none;
}
.toast.success {
  background: rgba(139, 232, 199, 0.15);
  border: 1px solid rgba(139, 232, 199, 0.3);
  color: #8be8c7;
}
.toast.error {
  background: rgba(232, 139, 139, 0.15);
  border: 1px solid rgba(232, 139, 139, 0.3);
  color: #e88b8b;
}
.toast-icon {
  font-weight: bold;
  font-size: 16px;
}
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(-20px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-20px);
}

.answer-feedback-page { max-width: 1080px; margin: 0 auto; padding: 40px 28px 80px; }
.page-header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 24px; }
.page-header h2 { font-size: 26px; color: var(--accent-light); letter-spacing: 3px; margin: 0 0 8px; }
.page-header p { margin: 0; color: var(--text-muted); font-size: 13px; }
.header-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
.filter-select,
.btn { height: 36px; border-radius: 9px; border: 1px solid var(--border); background: rgba(255,255,255,0.04); color: var(--text-dim); padding: 0 14px; }
.btn { cursor: pointer; transition: all 0.2s; }
.btn:hover:not(:disabled) { border-color: rgba(212,175,55,0.35); color: var(--accent-light); }
.btn.primary { background: rgba(212,175,55,0.12); color: var(--accent-light); }
.stats-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 20px; }
.stat-card { background: rgba(10,15,26,0.62); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.stat-card span { display: block; color: var(--text-muted); font-size: 12px; margin-bottom: 8px; }
.stat-card strong { font-size: 28px; color: var(--text); }
.stat-card.good strong { color: #8be8c7; }
.stat-card.bad strong { color: #e88b8b; }
.empty { text-align: center; padding: 80px 0; color: var(--text-muted); }
.feedback-list { display: flex; flex-direction: column; gap: 14px; }
.feedback-card { background: rgba(10,15,26,0.6); border: 1px solid var(--border); border-radius: 12px; padding: 18px; }
.card-top { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }
.rating-pill,
.reason-pill { border-radius: 999px; padding: 3px 10px; font-size: 12px; }
.rating-pill.up { background: rgba(139,232,199,0.12); color: #8be8c7; }
.rating-pill.down { background: rgba(232,139,139,0.12); color: #e88b8b; }
.reason-pill { background: rgba(255,255,255,0.05); color: var(--text-dim); }
.reviewed-pill { background: rgba(212,175,55,0.1); color: var(--accent-light); border-radius: 999px; padding: 3px 10px; font-size: 12px; }
.card-actions { margin-left: auto; display: flex; gap: 6px; }
.act-btn { padding: 3px 10px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.04); color: var(--text-dim); font-size: 12px; cursor: pointer; transition: all 0.2s; }
.act-btn:hover { border-color: rgba(212,175,55,0.35); color: var(--accent-light); }
.act-btn.promote { background: rgba(139,232,199,0.08); border-color: rgba(139,232,199,0.2); color: #8be8c7; }
.act-btn.promote:hover { background: rgba(139,232,199,0.15); }
.act-btn.done { background: rgba(139,232,199,0.18); border-color: rgba(139,232,199,0.35); color: #8be8c7; cursor: default; }
.act-btn.done:hover { background: rgba(139,232,199,0.18); border-color: rgba(139,232,199,0.35); color: #8be8c7; }
.act-btn.rollback { background: rgba(232,139,139,0.06); border-color: rgba(232,139,139,0.22); color: #e88b8b; }
.act-btn.rollback:hover { background: rgba(232,139,139,0.14); border-color: rgba(232,139,139,0.4); color: #ffb0b0; }

/* 自定义确认弹窗：与全站深色 + 金色描边风格一致 */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 24px;
}
.modal-box {
  width: min(440px, 100%);
  background: linear-gradient(180deg, rgba(20, 26, 42, 0.96), rgba(12, 16, 28, 0.96));
  border: 1px solid rgba(212, 175, 55, 0.28);
  border-radius: 14px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(212, 175, 55, 0.08) inset;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.modal-title {
  padding: 18px 22px 14px;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--accent-light, #d4af37);
  border-bottom: 1px solid rgba(212, 175, 55, 0.14);
  display: flex;
  align-items: center;
  gap: 10px;
}
.title-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e88b8b;
  box-shadow: 0 0 8px rgba(232, 139, 139, 0.7);
}
.modal-body {
  padding: 18px 22px 22px;
  color: var(--text, #e6ebf5);
  line-height: 1.7;
  font-size: 14px;
}
.modal-body p { margin: 0 0 8px; }
.modal-body p:last-child { margin-bottom: 0; }
.modal-hint {
  color: var(--text-muted, #8a9bb0);
  font-size: 13px;
}
.modal-body code {
  background: rgba(212, 175, 55, 0.12);
  border: 1px solid rgba(212, 175, 55, 0.22);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 12px;
  color: var(--accent-light, #d4af37);
  font-family: monospace;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 18px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.18);
}
.modal-btn {
  height: 36px;
  padding: 0 18px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-dim, #aab4c4);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.modal-btn:hover:not(:disabled) { border-color: rgba(212, 175, 55, 0.35); color: var(--accent-light, #d4af37); }
.modal-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.modal-btn.primary { background: rgba(212, 175, 55, 0.15); border-color: rgba(212, 175, 55, 0.4); color: var(--accent-light, #d4af37); }
.modal-btn.primary:hover:not(:disabled) { background: rgba(212, 175, 55, 0.25); }
.modal-btn.danger { background: rgba(232, 139, 139, 0.12); border-color: rgba(232, 139, 139, 0.4); color: #ffb0b0; }
.modal-btn.danger:hover:not(:disabled) { background: rgba(232, 139, 139, 0.22); border-color: rgba(232, 139, 139, 0.6); }

.modal-enter-active,
.modal-leave-active {
  transition: all 0.2s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from .modal-box,
.modal-leave-to .modal-box {
  transform: translateY(8px) scale(0.97);
}
.modal-enter-active .modal-box,
.modal-leave-active .modal-box {
  transition: all 0.22s ease;
}
.time,
.session { color: rgba(138,155,176,0.55); font-size: 12px; font-family: monospace; }
.qa-block { display: grid; grid-template-columns: 48px 1fr; gap: 12px; margin-top: 10px; }
.label { color: var(--accent-light); font-size: 12px; padding-top: 2px; }
.qa-block p { margin: 0; color: var(--text); line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
.qa-block.answer p { color: var(--text-dim); max-height: 220px; overflow: auto; }
@media (max-width: 760px) {
  .page-header { flex-direction: column; }
  .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .qa-block { grid-template-columns: 1fr; gap: 4px; }
}
</style>