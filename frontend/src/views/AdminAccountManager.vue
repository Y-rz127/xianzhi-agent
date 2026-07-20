<template>
  <div class="admin-account-view">
    <header class="page-header glass-card">
      <div class="header-left">
        <div class="header-icon">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
        </div>
        <div>
          <h2 class="text-glow-soft">管理员账号管理</h2>
          <div class="header-info">管理系统员账号，支持创建、编辑、删除和启用/禁用操作</div>
        </div>
      </div>
      <div class="header-actions">
        <span class="total-badge">共 {{ accounts.length }} 个账号</span>
        <button class="btn btn-primary" @click="openCreateModal">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          新建账号
        </button>
        <button class="btn" @click="loadAccounts" :disabled="loading">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
          刷新
        </button>
      </div>
    </header>

    <div v-if="loading && !accounts.length" class="glass-card loading-box">加载中…</div>
    <div v-else-if="!accounts.length" class="glass-card empty-box">暂无管理员账号</div>

    <div v-else class="table-wrap glass-card">
      <table class="account-table">
        <thead>
          <tr>
            <th>用户名</th>
            <th>昵称</th>
            <th>状态</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="acc in accounts" :key="acc.id" class="account-row">
            <td class="cell-username">
              {{ acc.username }}
              <span v-if="acc.is_super" class="super-badge">超管</span>
            </td>
            <td>{{ acc.nickname || '-' }}</td>
            <td>
              <span :class="['status-tag', acc.enabled ? 'enabled' : 'disabled']">
                {{ acc.enabled ? '正常' : '已禁用' }}
              </span>
            </td>
            <td class="cell-dim">{{ fmt(acc.created_at) }}</td>
            <td class="cell-actions">
              <button class="action-btn edit-btn" @click="openEditModal(acc)">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                编辑
              </button>
              <template v-if="!acc.is_super">
                <button
                  v-if="acc.enabled"
                  class="action-btn disable-btn"
                  @click="toggleAccountStatus(acc)"
                >禁用</button>
                <button
                  v-else
                  class="action-btn enable-btn"
                  @click="toggleAccountStatus(acc)"
                >启用</button>
                <button class="action-btn delete-btn" @click="deleteAccount(acc)">
                  <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                  删除
                </button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 创建/编辑弹窗 -->
    <div v-if="showModal" class="modal-mask" @click="closeModal"></div>
    <div v-if="showModal" class="modal glass-card">
      <div class="modal-header">
        <h3>{{ isEditing ? '编辑账号' : '新建账号' }}</h3>
        <button class="modal-close" @click="closeModal">×</button>
      </div>
      <form @submit.prevent="handleSubmit" class="modal-form">
        <div class="form-group">
          <label>用户名 <span class="required">*</span></label>
          <input
            v-model="formData.username"
            type="text"
            placeholder="请输入用户名"
            :disabled="isEditing"
            required
          />
        </div>
        <div class="form-group">
          <label>昵称</label>
          <input
            v-model="formData.nickname"
            type="text"
            placeholder="请输入昵称（可选）"
          />
        </div>
        <div class="form-group">
          <label>密码 <span class="required">*</span></label>
          <input
            v-model="formData.password"
            type="password"
            placeholder="请输入密码"
            required
          />
          <p class="form-hint" v-if="!isEditing">新建账号时必填</p>
          <p class="form-hint" v-else>留空则不修改密码</p>
        </div>
        <div v-if="errMsg" class="error-msg">{{ errMsg }}</div>
        <div class="modal-actions">
          <button type="button" class="btn" @click="closeModal">取消</button>
          <button type="submit" class="btn btn-primary" :disabled="submitting">
            {{ submitting ? '提交中...' : (isEditing ? '保存' : '创建') }}
          </button>
        </div>
      </form>
    </div>
    <!-- 删除确认弹窗 -->
    <div v-if="showConfirmModal" class="modal-mask" @click="closeConfirmModal"></div>
    <div v-if="showConfirmModal" class="confirm-modal glass-card">
      <div class="confirm-icon">
        <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 8v4"/><path d="M12 16h.01"/>
        </svg>
      </div>
      <h3 class="confirm-title">确认删除</h3>
      <p class="confirm-body">确定要删除账号 <strong>"{{ confirmTarget?.username }}"</strong> 吗？</p>
      <p class="confirm-warn">此操作不可恢复，请谨慎操作。</p>
      <div class="confirm-actions">
        <button class="btn" @click="closeConfirmModal">取消</button>
        <button class="btn btn-danger" @click="confirmDelete" :disabled="confirmDeleting">
          {{ confirmDeleting ? '删除中...' : '确认删除' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { 
  listAdminAccounts, 
  createAdminAccount, 
  updateAdminAccount, 
  deleteAdminAccount as apiDeleteAccount,
  type AdminAccount 
} from "../api"

interface AccountFormData {
  username: string
  nickname: string
  password: string
}

const accounts = ref<AdminAccount[]>([])
const loading = ref(false)
const showModal = ref(false)
const isEditing = ref(false)
const editingId = ref<string | null>(null)
const formData = ref<AccountFormData>({
  username: '',
  nickname: '',
  password: ''
})
const errMsg = ref('')
const submitting = ref(false)

const showConfirmModal = ref(false)
const confirmTarget = ref<AdminAccount | null>(null)
const confirmDeleting = ref(false)

const fmt = (s?: string) => (s ? s.replace('T', ' ').slice(0, 19) : '-')

async function loadAccounts() {
  loading.value = true
  try {
    accounts.value = await listAdminAccounts()
  } catch (e) {
    console.error(e)
    errMsg.value = '加载账号列表失败'
  } finally {
    loading.value = false
  }
}

function openCreateModal() {
  isEditing.value = false
  editingId.value = null
  formData.value = { username: '', nickname: '', password: '' }
  errMsg.value = ''
  showModal.value = true
}

function openEditModal(account: AdminAccount) {
  isEditing.value = true
  editingId.value = account.id
  formData.value = {
    username: account.username,
    nickname: account.nickname || '',
    password: ''
  }
  errMsg.value = ''
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  errMsg.value = ''
}

async function handleSubmit() {
  if (!formData.value.username.trim()) {
    errMsg.value = '请输入用户名'
    return
  }
  
  if (!isEditing.value && !formData.value.password) {
    errMsg.value = '请输入密码'
    return
  }

  submitting.value = true
  errMsg.value = ''

  try {
    if (isEditing.value && editingId.value) {
      const updateData: any = {
        nickname: formData.value.nickname
      }
      if (formData.value.password) {
        updateData.password = formData.value.password
      }
      await updateAdminAccount(editingId.value, updateData)
    } else {
      await createAdminAccount({
        username: formData.value.username,
        password: formData.value.password,
        nickname: formData.value.nickname || undefined
      })
    }
    
    closeModal()
    await loadAccounts()
  } catch (e: any) {
    errMsg.value = e.message || '操作失败'
  } finally {
    submitting.value = false
  }
}

async function toggleAccountStatus(account: AdminAccount) {
  try {
    await updateAdminAccount(account.id, { enabled: !account.enabled })
    await loadAccounts()
  } catch (e: any) {
    errMsg.value = e.message || '更新状态失败'
  }
}

async function deleteAccount(account: AdminAccount) {
  confirmTarget.value = account
  showConfirmModal.value = true
}

function closeConfirmModal() {
  showConfirmModal.value = false
  confirmTarget.value = null
}

async function confirmDelete() {
  if (!confirmTarget.value) return
  confirmDeleting.value = true
  try {
    await apiDeleteAccount(confirmTarget.value.id)
    closeConfirmModal()
    await loadAccounts()
  } catch (e: any) {
    errMsg.value = e.message || '删除账号失败'
    closeConfirmModal()
  } finally {
    confirmDeleting.value = false
  }
}

onMounted(() => {
  loadAccounts()
})
</script>

<style scoped>
.admin-account-view {
  padding: 0;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 28px;
  margin-bottom: 20px;
  border-radius: 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(212, 175, 55, 0.12);
  color: var(--accent-light);
  box-shadow: 0 0 16px rgba(212, 175, 55, 0.18);
}

.page-header h2 {
  font-size: 18px;
  letter-spacing: 1px;
}

.header-info {
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 2px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.total-badge {
  font-size: 13px;
  color: var(--text-dim);
  background: rgba(255, 255, 255, 0.05);
  padding: 6px 14px;
  border-radius: 20px;
}

.btn {
  padding: 8px 16px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn:hover {
  border-color: var(--accent);
  color: var(--accent-light);
}

.btn-primary {
  background: linear-gradient(135deg, var(--accent), #8b6f47);
  border-color: transparent;
  color: #0c1220;
  font-weight: 500;
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(212, 175, 55, 0.3);
}

.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.loading-box, .empty-box {
  padding: 40px;
  text-align: center;
  color: var(--text-dim);
  border-radius: 16px;
}

.table-wrap {
  border-radius: 16px;
  overflow: hidden;
}

.account-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.account-table th {
  text-align: left;
  padding: 12px 14px;
  color: var(--text-dim);
  font-weight: 500;
  border-bottom: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
}

.account-table td {
  padding: 12px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.account-row {
  transition: background 0.2s;
}

.account-row:hover {
  background: rgba(212, 175, 55, 0.05);
}

.cell-username {
  font-weight: 500;
  color: var(--accent-light);
  display: flex;
  align-items: center;
  gap: 8px;
}

.super-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: linear-gradient(135deg, var(--accent), #8b6f47);
  color: #0c1220;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.cell-dim {
  color: var(--text-dim);
  font-size: 12px;
}

.cell-actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  line-height: 1.4;
}

.edit-btn {
  background: rgba(212, 175, 55, 0.15);
  color: #d4af37;
  border-color: rgba(212, 175, 55, 0.25);
}

.edit-btn:hover {
  background: rgba(212, 175, 55, 0.25);
  border-color: #d4af37;
  color: #e8c547;
}

.disable-btn {
  background: rgba(251, 146, 60, 0.15);
  color: #fb923c;
  border-color: rgba(251, 146, 60, 0.25);
}

.disable-btn:hover {
  background: rgba(251, 146, 60, 0.25);
  border-color: #fb923c;
  color: #fdba74;
}

.enable-btn {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
  border-color: rgba(74, 222, 128, 0.25);
}

.enable-btn:hover {
  background: rgba(74, 222, 128, 0.25);
  border-color: #4ade80;
  color: #86efac;
}

.delete-btn {
  background: rgba(248, 113, 113, 0.15);
  color: #f87171;
  border-color: rgba(248, 113, 113, 0.25);
}

.delete-btn:hover {
  background: rgba(248, 113, 113, 0.25);
  border-color: #f87171;
  color: #fca5a5;
}

.status-tag {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 12px;
  font-weight: 500;
}

.status-tag.enabled {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.12);
}

.status-tag.disabled {
  color: #f87171;
  background: rgba(248, 113, 113, 0.12);
}

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 100;
}

.modal {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 420px;
  max-height: 80vh;
  overflow-y: auto;
  z-index: 101;
  border-radius: 18px;
  padding: 24px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.modal-header h3 {
  font-size: 17px;
  color: var(--text);
}

.modal-close {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-dim);
  font-size: 20px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-close:hover {
  background: rgba(248, 113, 113, 0.15);
  color: #f87171;
}

.modal-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 13px;
  color: var(--text-dim);
  font-weight: 500;
}

.required {
  color: #f87171;
}

.form-group input {
  width: 100%;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: rgba(0, 0, 0, 0.3);
  color: var(--text);
  font-size: 14px;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.form-group input:focus {
  border-color: var(--accent);
}

.form-group input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.form-hint {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: -8px;
}

.error-msg {
  font-size: 12px;
  color: #fca5a5;
  background: rgba(248, 113, 113, 0.1);
  padding: 8px 12px;
  border-radius: 8px;
  border-left: 3px solid #f87171;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 8px;
}
.confirm-modal {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 380px;
  z-index: 101;
  border-radius: 18px;
  padding: 32px 28px 24px;
  text-align: center;
}

.confirm-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  border-radius: 50%;
  background: rgba(248, 113, 113, 0.12);
  color: #f87171;
  display: flex;
  align-items: center;
  justify-content: center;
}

.confirm-title {
  font-size: 17px;
  color: var(--text);
  margin-bottom: 8px;
}

.confirm-body {
  font-size: 13px;
  color: var(--text-dim);
  margin-bottom: 4px;
}

.confirm-body strong {
  color: var(--accent-light);
  font-weight: 600;
}

.confirm-warn {
  font-size: 11px;
  color: #f87171;
  margin-bottom: 20px;
}

.confirm-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
}

.btn-danger {
  background: rgba(248, 113, 113, 0.15);
  color: #fca5a5;
  border-color: rgba(248, 113, 113, 0.3);
  font-weight: 500;
}

.btn-danger:hover {
  background: rgba(248, 113, 113, 0.25);
  border-color: #f87171;
  color: #fecaca;
}

.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
