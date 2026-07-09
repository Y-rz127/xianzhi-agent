<template>
  <div class="chart-cases-view">
    <header class="page-header glass-card">
      <div class="header-left">
        <div class="header-icon">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
            <ellipse cx="12" cy="5" rx="9" ry="3"/>
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
          </svg>
        </div>
        <div>
          <h2 class="text-glow-soft">命例库</h2>
          <div class="header-info">收藏 · 管理 · 导出八字命例</div>
        </div>
      </div>
      <div class="header-actions">
        <button class="btn" @click="triggerImport" aria-label="导入 JSON">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/></svg>
          导入 JSON
        </button>
        <input ref="importInput" type="file" accept=".json,application/json" style="display: none" @change="onImportFile" />
        <button class="btn" @click="handleExport" aria-label="导出 JSON">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>
          导出 JSON
        </button>
        <button class="btn btn-primary" @click="openCreateModal" aria-label="新建命例">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          新建命例
        </button>
      </div>
    </header>

    <div class="filters glass-card">
      <div class="search-row">
        <div class="search-input-wrap">
          <svg class="search-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input v-model="searchQuery" placeholder="搜索名称、出生时间或标签..." aria-label="搜索命例" />
        </div>
        <button v-if="hasActiveFilter" class="btn btn-xs" @click="clearFilters">清除筛选</button>
      </div>
      <div v-if="allTags.length" class="tag-chips">
        <span class="tag-label">标签筛选：</span>
        <button
          v-for="tag in allTags"
          :key="tag"
          :class="['tag-chip', { active: selectedTags.includes(tag) }]"
          @click="toggleTag(tag)"
        >{{ tag }}</button>
      </div>
    </div>

    <div v-if="loading" class="cases-grid">
      <div v-for="i in 6" :key="i" class="case-card skeleton">
        <div class="skeleton-line skeleton-title"></div>
        <div class="skeleton-line"></div>
        <div class="skeleton-line skeleton-short"></div>
        <div class="skeleton-tags">
          <span v-for="j in 3" :key="j" class="skeleton-tag"></span>
        </div>
      </div>
    </div>

    <div v-else-if="filteredCases.length === 0" class="empty-state">
      <div class="empty-icon">库</div>
      <h3>暂无命例</h3>
      <p>点击右上角「新建命例」添加第一个八字命例，或导入已有 JSON 备份。</p>
    </div>

    <div v-else class="cases-grid">
      <div v-for="c in filteredCases" :key="c.id" class="case-card glass-card animate-fade-in-up">
        <div class="case-header">
          <div class="case-name">{{ c.name }}</div>
          <div class="case-gender">{{ c.gender }}</div>
        </div>
        <div class="case-meta">
          <div class="meta-item">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <span>{{ c.birthTime }}</span>
          </div>
          <div class="meta-item">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            <span>{{ formatTime(c.createdAt) }}</span>
          </div>
        </div>
        <div v-if="c.tags?.length" class="case-tags">
          <span v-for="tag in c.tags" :key="tag" class="case-tag">{{ tag }}</span>
        </div>
        <div class="case-actions">
          <button class="btn btn-xs" @click="viewCase(c)" aria-label="查看命盘">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            查看
          </button>
          <button class="btn btn-xs" @click="openEditModal(c)" aria-label="编辑命例">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            编辑
          </button>
          <button class="btn btn-xs btn-danger" @click="confirmDelete(c)" aria-label="删除命例">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            删除
          </button>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showModal" class="case-modal-overlay" @click.self="closeModal">
        <div class="case-modal">
          <div class="case-modal-header">
            <div class="case-modal-title">{{ modalMode === 'create' ? '新建命例' : '编辑命例' }}</div>
            <button class="modal-close" @click="closeModal" aria-label="关闭">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="case-modal-body">
            <div class="form-row">
              <label for="case-name">名称</label>
              <input id="case-name" v-model="form.name" placeholder="例如：我的命盘" />
            </div>
            <div class="form-row">
              <label for="case-tags">标签</label>
              <input id="case-tags" v-model="form.tags" placeholder="用逗号分隔，如：事业，婚姻" />
            </div>
            <div class="form-row">
              <label for="case-birth-time">出生时间</label>
              <input id="case-birth-time" v-model="form.birthTime" placeholder="1990-05-20 14:30" />
            </div>
            <div class="form-row">
              <label for="case-gender">性别</label>
              <select id="case-gender" v-model="form.gender">
                <option value="男">男</option>
                <option value="女">女</option>
              </select>
            </div>
          </div>
          <div class="case-modal-footer">
            <button class="btn" @click="closeModal">取消</button>
            <button class="btn btn-primary" @click="saveCase" :disabled="!canSave">保存</button>
          </div>
        </div>
      </div>
    </Teleport>

    <BaziModal
      :visible="showBaziModal"
      :pillars="activeChart?.pillars || []"
      :wuxing="activeChart?.wuxing || []"
      :dayun="activeChart?.dayun || []"
      :liunian="activeChart?.liunian || []"
      :shensha="activeChart?.shensha || []"
      :analysis="activeChart?.analysis"
      :startYun="activeChart?.startYun"
      :warnings="activeChart?.warnings || []"
      :birthTime="activeCase?.birthTime"
      :gender="activeCase?.gender"
      @close="closeBaziModal"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { fetchChartCases, createChartCase, updateChartCase, deleteChartCase, getChart, exportChartCasesJSON, importChartCasesJSON, type ChartCase, type ChartData } from "../api"
import BaziModal from "../components/BaziModal.vue"

const cases = ref<ChartCase[]>([])
const loading = ref(false)
const searchQuery = ref("")
const selectedTags = ref<string[]>([])

const showModal = ref(false)
const modalMode = ref<"create" | "edit">("create")
const editingId = ref<string>("")
const form = ref({ name: "", tags: "", birthTime: "", gender: "男" as "男" | "女" })

const showBaziModal = ref(false)
const activeCase = ref<ChartCase | null>(null)
const activeChart = ref<ChartData | null>(null)

const importInput = ref<HTMLInputElement | null>(null)

const allTags = computed(() => {
  const set = new Set<string>()
  cases.value.forEach((c) => c.tags?.forEach((t) => set.add(t)))
  return Array.from(set).sort()
})

const filteredCases = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  return cases.value.filter((c) => {
    const matchQuery = !q ||
      c.name.toLowerCase().includes(q) ||
      c.birthTime.toLowerCase().includes(q) ||
      c.tags?.some((t) => t.toLowerCase().includes(q))
    const matchTags = selectedTags.value.length === 0 || selectedTags.value.every((t) => c.tags?.includes(t))
    return matchQuery && matchTags
  })
})

const hasActiveFilter = computed(() => searchQuery.value.trim().length > 0 || selectedTags.value.length > 0)

const canSave = computed(() =>
  form.value.name.trim() && form.value.birthTime.trim() && (form.value.gender === "男" || form.value.gender === "女")
)

const formatTime = (time: string) => (time ? time.split("T")[0] : "-")

const loadCases = async () => {
  loading.value = true
  cases.value = await fetchChartCases()
  loading.value = false
}

const toggleTag = (tag: string) => {
  const idx = selectedTags.value.indexOf(tag)
  if (idx >= 0) selectedTags.value.splice(idx, 1)
  else selectedTags.value.push(tag)
}

const clearFilters = () => {
  searchQuery.value = ""
  selectedTags.value = []
}

const resetForm = () => {
  form.value = { name: "", tags: "", birthTime: "", gender: "男" }
  editingId.value = ""
}

const openCreateModal = () => {
  modalMode.value = "create"
  resetForm()
  showModal.value = true
}

const openEditModal = (c: ChartCase) => {
  modalMode.value = "edit"
  editingId.value = c.id
  form.value = {
    name: c.name,
    tags: c.tags?.join(", ") || "",
    birthTime: c.birthTime,
    gender: c.gender === "女" ? "女" : "男",
  }
  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
  resetForm()
}

const saveCase = async () => {
  if (!canSave.value) return
  const payload = {
    name: form.value.name.trim(),
    birthTime: form.value.birthTime.trim(),
    gender: form.value.gender,
    tags: form.value.tags.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
  }
  try {
    if (modalMode.value === "create") {
      await createChartCase(payload)
    } else if (editingId.value) {
      await updateChartCase(editingId.value, payload)
    }
    closeModal()
    await loadCases()
  } catch (e: any) {
    alert(e?.message || "保存失败")
  }
}

const confirmDelete = async (c: ChartCase) => {
  if (!confirm(`确定删除命例「${c.name}」吗？`)) return
  try {
    await deleteChartCase(c.id)
    await loadCases()
  } catch (e: any) {
    alert(e?.message || "删除失败")
  }
}

const viewCase = async (c: ChartCase) => {
  activeCase.value = c
  activeChart.value = c.chartData || null
  if (!activeChart.value && c.birthTime && c.gender) {
    try {
      activeChart.value = await getChart(c.birthTime, c.gender)
    } catch {
      activeChart.value = null
    }
  }
  showBaziModal.value = true
}

const closeBaziModal = () => {
  showBaziModal.value = false
  activeCase.value = null
  activeChart.value = null
}

const handleExport = () => {
  exportChartCasesJSON()
}

const triggerImport = () => {
  importInput.value?.click()
}

const onImportFile = async (e: Event) => {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  try {
    const res = await importChartCasesJSON(file)
    alert(`导入成功：新增 ${res.inserted} 条，跳过 ${res.skipped} 条`)
    await loadCases()
  } catch (err: any) {
    alert(err?.message || "导入失败")
  } finally {
    target.value = ""
  }
}

onMounted(loadCases)
</script>

<style scoped>
.chart-cases-view {
  height: 100%;
  overflow-y: auto;
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 24px;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.header-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.15), rgba(139, 92, 246, 0.1));
  border: 1px solid rgba(212, 175, 55, 0.3);
  color: var(--accent);
}

.page-header h2 {
  font-size: 17px;
  color: var(--text);
  letter-spacing: 1px;
  margin-bottom: 2px;
}

.header-info {
  font-size: 12px;
  color: var(--text-muted);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.filters {
  padding: 18px 20px;
  margin-bottom: 20px;
}

.search-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.search-input-wrap {
  flex: 1;
  position: relative;
  min-width: 0;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
}

.search-input-wrap input {
  width: 100%;
  padding: 10px 12px 10px 36px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  font-size: 13px;
  outline: none;
}

.search-input-wrap input:focus {
  border-color: var(--accent);
}

.search-input-wrap input::placeholder {
  color: var(--text-muted);
}

.tag-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.tag-label {
  font-size: 12px;
  color: var(--text-dim);
}

.tag-chip {
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.2s;
}

.tag-chip:hover {
  border-color: rgba(212, 175, 55, 0.25);
  color: var(--text);
}

.tag-chip.active {
  background: rgba(212, 175, 55, 0.12);
  border-color: rgba(212, 175, 55, 0.35);
  color: var(--accent-light);
}

.cases-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  max-width: 1400px;
}

.case-card {
  padding: 18px;
  display: flex;
  flex-direction: column;
  transition: all 0.25s;
}

.case-card:hover {
  border-color: var(--border-hover);
  box-shadow: var(--shadow-glow);
}

.case-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.case-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.case-gender {
  font-size: 12px;
  color: var(--accent-light);
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(212, 175, 55, 0.08);
  border: 1px solid rgba(212, 175, 55, 0.15);
  flex-shrink: 0;
}

.case-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-dim);
}

.meta-item svg {
  color: var(--text-muted);
  flex-shrink: 0;
}

.case-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 14px;
}

.case-tag {
  font-size: 11px;
  padding: 3px 9px;
  background: rgba(212, 175, 55, 0.08);
  border-radius: 6px;
  color: var(--accent-light);
}

.case-actions {
  margin-top: auto;
  display: flex;
  gap: 8px;
}

.case-actions .btn {
  flex: 1;
}

.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: var(--text-dim);
}

.empty-icon {
  width: 80px;
  height: 80px;
  margin: 0 auto 20px;
  background: linear-gradient(135deg, var(--accent), #b8942a);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  color: #0a0f1a;
  font-weight: bold;
  box-shadow: 0 0 30px rgba(212, 175, 55, 0.25);
}

.empty-state h3 {
  color: var(--text);
  font-size: 18px;
  margin-bottom: 8px;
}

.empty-state p {
  font-size: 13px;
  max-width: 420px;
  margin: 0 auto;
  line-height: 1.7;
}

.skeleton {
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.03) 25%, rgba(255, 255, 255, 0.06) 50%, rgba(255, 255, 255, 0.03) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

.skeleton-line {
  height: 12px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  margin-bottom: 10px;
}

.skeleton-title {
  width: 60%;
  height: 16px;
}

.skeleton-short {
  width: 40%;
}

.skeleton-tags {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.skeleton-tag {
  width: 44px;
  height: 20px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
}

.case-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.case-modal {
  width: 90%;
  max-width: 420px;
  background: rgba(15, 21, 32, 0.95);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.case-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.case-modal-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.modal-close {
  padding: 6px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-dim);
  cursor: pointer;
}

.modal-close:hover {
  border-color: var(--danger);
  color: var(--danger);
}

.case-modal-body {
  padding: 20px;
}

.form-row {
  margin-bottom: 16px;
}

.form-row label {
  display: block;
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 6px;
}

.form-row input,
.form-row select {
  width: 100%;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-size: 13px;
  outline: none;
}

.form-row input:focus,
.form-row select:focus {
  border-color: var(--accent);
}

.form-row select option {
  background: #0f1520;
  color: var(--text);
}

.case-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}

@media (max-width: 768px) {
  .chart-cases-view {
    padding: 14px;
    padding-top: 60px;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
    padding: 14px 16px;
  }

  .header-actions {
    width: 100%;
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  .filters {
    padding: 14px 16px;
  }

  .search-row {
    flex-wrap: wrap;
  }

  .cases-grid {
    grid-template-columns: 1fr;
  }
}
</style>
