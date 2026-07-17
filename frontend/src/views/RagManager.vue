<template>
  <div class="rag-manager">
    <header class="page-header glass-card">
      <div class="header-left">
        <div class="header-icon">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
          </svg>
        </div>
        <div>
          <h2 class="text-glow-soft">知识库管理</h2>
          <div class="header-info">管理 RAG 命理知识文档与向量库</div>
        </div>
      </div>
      <button class="btn btn-primary" @click="rebuild" :disabled="rebuilding" aria-label="重建向量库">
        <svg v-if="!rebuilding" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
        <span>{{ rebuilding ? "重建中" : "重建向量库" }}</span>
      </button>
    </header>

    <section class="status-bar">
      <div class="status-card glass-card" :class="{ ready: status?.ready }">
        <div class="status-dot"></div>
        <div class="status-body">
          <div class="status-title">{{ status?.ready ? "向量库已就绪" : "向量库未就绪" }}</div>
          <div class="status-desc">{{ status ? `知识文档 ${status.count} 篇` : "加载中..." }}</div>
        </div>
      </div>
    </section>

    <section class="upload-section glass-card">
      <div class="section-title">上传知识文档</div>
      <div
        class="upload-drop"
        :class="{ dragging }"
        @dragenter.prevent="dragging = true"
        @dragover.prevent
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
        @click="triggerFileInput"
      >
        <input ref="fileInput" type="file" accept=".md" @change="onFileChange" />
        <div class="upload-icon">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/></svg>
        </div>
        <p class="upload-hint">点击或拖拽上传 .md 文件</p>
        <p class="upload-sub">仅支持 Markdown 文档，将存入知识库目录</p>
      </div>
    </section>

    <section class="docs-section glass-card">
      <div class="section-header">
        <div class="section-title">文档列表</div>
        <button class="btn btn-xs" @click="refresh" :disabled="loading" aria-label="刷新列表">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
        </button>
      </div>

      <div v-if="loading" class="skeleton-list">
        <div v-for="i in 5" :key="i" class="skeleton-item">
          <div class="skeleton-line skeleton-title"></div>
          <div class="skeleton-line skeleton-meta"></div>
        </div>
      </div>

      <div v-else-if="docs.length === 0" class="empty-docs">
        <div class="empty-icon">
          <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        </div>
        <p>暂无知识文档，请上传 .md 文件</p>
      </div>

      <div v-else class="docs-list">
        <div v-for="doc in visibleDocs" :key="doc.filename" class="doc-item">
          <div class="doc-info">
            <div class="doc-name">{{ doc.filename }}</div>
            <div class="doc-meta">{{ formatSize(doc.size) }} · {{ formatTime(doc.modified) }}</div>
          </div>
          <button class="btn btn-danger btn-xs" @click="removeDoc(doc.filename)" :disabled="deleting[doc.filename]" aria-label="删除文档">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            <span>删除</span>
          </button>
        </div>
        <button v-if="docs.length > 5" class="btn btn-xs show-more-btn" @click="showAllDocs = !showAllDocs">
          {{ showAllDocs ? '收起' : `查看更多（${docs.length - 5} 条）` }}
        </button>
      </div>
    </section>

    <div v-if="message" class="toast" :class="message.type">{{ message.text }}</div>

    <!-- 确认弹窗 -->
    <Teleport to="body">
      <div v-if="showConfirm" class="confirm-overlay" @click.self="showConfirm = false">
        <div class="confirm-dialog">
          <p class="confirm-msg">{{ confirmMsg }}</p>
          <div class="confirm-actions">
            <button class="btn-confirm-cancel" @click="showConfirm = false">取消</button>
            <button class="btn-confirm-ok" :disabled="confirmLoading" @click="onConfirmOk">
              {{ confirmLoading ? '处理中...' : '确定' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { getRagStatus, listRagDocs, uploadRagDoc, deleteRagDoc, rebuildRagIndex, type RagDoc, type RagStatus } from "../api"

const status = ref<RagStatus | null>(null)
const docs = ref<RagDoc[]>([])
const loading = ref(false)
const rebuilding = ref(false)
const dragging = ref(false)
const deleting = ref<Record<string, boolean>>({})
const fileInput = ref<HTMLInputElement | null>(null)
const message = ref<{ text: string; type: "success" | "error" } | null>(null)
const showAllDocs = ref(false)
const visibleDocs = computed(() => showAllDocs.value ? docs.value : docs.value.slice(0, 5))

// 确认弹窗
const showConfirm = ref(false)
const confirmMsg = ref("")
const confirmLoading = ref(false)
const pendingAction: ref<(() => Promise<void>) | null> = ref(null)

function askConfirm(msg: string, action: () => Promise<void>) {
  confirmMsg.value = msg
  pendingAction.value = action
  showConfirm.value = true
}
async function onConfirmOk() {
  if (!pendingAction.value) return
  confirmLoading.value = true
  try {
    await pendingAction.value()
  } finally {
    confirmLoading.value = false
    showConfirm.value = false
    pendingAction.value = null
  }
}

function showMessage(text: string, type: "success" | "error" = "success") {
  message.value = { text, type }
  setTimeout(() => { message.value = null }, 3000)
}

async function fetchStatus() {
  try {
    status.value = await getRagStatus()
  } catch (e: any) {
    showMessage(e.message || "获取状态失败", "error")
  }
}

async function fetchDocs() {
  loading.value = true
  try {
    docs.value = await listRagDocs()
  } catch (e: any) {
    showMessage(e.message || "获取文档失败", "error")
  } finally {
    loading.value = false
  }
}

async function refresh() {
  await Promise.all([fetchStatus(), fetchDocs()])
}

async function handleUpload(file: File) {
  if (!file.name.toLowerCase().endsWith(".md")) {
    showMessage("仅支持上传 .md 文件", "error")
    return
  }
  try {
    await uploadRagDoc(file)
    showMessage("上传成功")
    await refresh()
  } catch (e: any) {
    showMessage(e.message || "上传失败", "error")
  }
}

function triggerFileInput() {
  fileInput.value?.click()
}

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) handleUpload(file)
  if (target) target.value = ""
}

function onDrop(e: DragEvent) {
  dragging.value = false
  const file = e.dataTransfer?.files[0]
  if (file) handleUpload(file)
}

async function removeDoc(filename: string) {
  askConfirm(`确定删除文档「${filename}」？`, async () => {
    deleting.value[filename] = true
    try {
      await deleteRagDoc(filename)
      showMessage("删除成功")
      await refresh()
    } catch (e: any) {
      showMessage(e.message || "删除失败", "error")
    } finally {
      deleting.value[filename] = false
    }
  })
}

async function rebuild() {
  askConfirm("重建向量库会重新加载所有知识文档，可能需要一些时间，是否继续？", async () => {
    rebuilding.value = true
    try {
      const result = await rebuildRagIndex()
      showMessage(result.ready ? "向量库重建成功" : "向量库重建失败", result.ready ? "success" : "error")
      await fetchStatus()
    } catch (e: any) {
      showMessage(e.message || "重建失败", "error")
    } finally {
      rebuilding.value = false
    }
  })
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("zh-CN")
  } catch {
    return iso
  }
}

onMounted(() => {
  refresh()
})
</script>

<style scoped>
.rag-manager {
  max-width: 900px;
  margin: 0 auto;
  padding: var(--spacing-lg) var(--spacing-lg) 60px;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  min-height: 100%;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  border-radius: var(--radius);
}
.header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}
.header-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(212, 175, 55, 0.12);
  color: var(--accent-light);
  box-shadow: 0 0 16px rgba(212, 175, 55, 0.18);
}
.page-header h2 { font-size: 18px; letter-spacing: 1px; }
.header-info { font-size: 12px; color: var(--text-dim); margin-top: 2px; }

.status-bar { display: flex; }
.status-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md) var(--spacing-lg);
  border-radius: var(--radius);
  border-left: 3px solid var(--danger);
  transition: border-color 0.3s;
}
.status-card.ready { border-left-color: var(--success); }
.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--danger);
  box-shadow: 0 0 10px var(--danger);
  animation: pulse-dot 2s infinite;
}
.status-card.ready .status-dot {
  background: var(--success);
  box-shadow: 0 0 10px var(--success);
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
.status-title { font-size: 15px; font-weight: 600; }
.status-desc { font-size: 12px; color: var(--text-dim); margin-top: 2px; }

.upload-section, .docs-section {
  padding: var(--spacing-lg);
  border-radius: var(--radius);
}
.section-title { font-size: 15px; font-weight: 600; margin-bottom: var(--spacing-md); }
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-md);
}
.section-header .section-title { margin-bottom: 0; }

.upload-drop {
  border: 2px dashed var(--border);
  border-radius: var(--radius-sm);
  padding: var(--spacing-xl);
  text-align: center;
  cursor: pointer;
  transition: all 0.25s;
  background: rgba(255, 255, 255, 0.02);
}
.upload-drop:hover, .upload-drop.dragging {
  border-color: var(--border-hover);
  background: rgba(212, 175, 55, 0.04);
}
.upload-drop input { display: none; }
.upload-icon {
  color: var(--accent);
  margin-bottom: var(--spacing-sm);
  opacity: 0.8;
}
.upload-hint { font-size: 14px; color: var(--text); }
.upload-sub { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

.skeleton-list { display: flex; flex-direction: column; gap: var(--spacing-sm); }
.skeleton-item {
  padding: var(--spacing-md);
  border-radius: var(--radius-sm);
  background: rgba(255,255,255,0.03);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.skeleton-line {
  height: 12px;
  border-radius: 4px;
  background: linear-gradient(90deg, rgba(255,255,255,0.05) 25%, rgba(255,255,255,0.12) 50%, rgba(255,255,255,0.05) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
.skeleton-title { width: 40%; }
.skeleton-meta { width: 25%; }

.empty-docs {
  text-align: center;
  padding: var(--spacing-xl) 0;
  color: var(--text-dim);
}
.empty-icon { color: var(--text-muted); margin-bottom: var(--spacing-sm); }

.docs-list { display: flex; flex-direction: column; gap: var(--spacing-sm); }
.doc-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  border-radius: var(--radius-sm);
  background: rgba(255,255,255,0.03);
  border: 1px solid transparent;
  transition: all 0.2s;
}
.doc-item:hover {
  background: rgba(255,255,255,0.05);
  border-color: var(--border);
}
.doc-name { font-size: 14px; color: var(--text); word-break: break-all; }
.doc-meta { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 20px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: #fff;
  z-index: 200;
  box-shadow: var(--shadow);
  animation: fadeInUp 0.3s ease;
}
.toast.success { background: rgba(34, 197, 94, 0.9); }
.toast.error { background: rgba(239, 68, 68, 0.9); }

@media (max-width: 768px) {
  .rag-manager { padding: var(--spacing-md); gap: var(--spacing-md); }
  .page-header { flex-direction: column; align-items: flex-start; gap: var(--spacing-md); }
  .doc-item { align-items: flex-start; flex-direction: column; }
}

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
.confirm-actions { display: flex; justify-content: flex-end; gap: 10px; }
.btn-confirm-cancel,
.btn-confirm-ok {
  padding: 7px 20px;
  border-radius: 9px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid var(--border);
}
.btn-confirm-cancel { background: transparent; color: var(--text-dim); }
.btn-confirm-cancel:hover { background: rgba(255,255,255,0.05); }
.btn-confirm-ok {
  background: rgba(220,80,80,0.15);
  color: #dc7878;
  border-color: rgba(220,80,80,0.25);
}
.btn-confirm-ok:hover:not(:disabled) { background: rgba(220,80,80,0.25); }
.btn-confirm-ok:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
