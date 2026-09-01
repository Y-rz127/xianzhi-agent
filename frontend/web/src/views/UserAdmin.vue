<template>
  <div class="user-admin-view">
    <header class="page-header glass-card">
      <div class="header-left">
        <div class="header-icon">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
        </div>
        <div>
          <h2 class="text-glow-soft">用户管理</h2>
          <div class="header-info">查看注册用户及其八字档案、收藏、塔罗与对话数据</div>
        </div>
      </div>
      <div class="header-actions">
        <span class="total-badge">共 {{ total }} 位用户</span>
        <button class="btn" @click="loadUsers" :disabled="loading">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
          刷新
        </button>
      </div>
    </header>

    <div v-if="loading && !users.length" class="glass-card loading-box">加载中…</div>
    <div v-else-if="!users.length" class="glass-card empty-box">暂无注册用户</div>

    <div v-else class="table-wrap glass-card">
      <table class="user-table">
        <thead>
          <tr>
            <th>昵称</th>
            <th>八字档案</th>
            <th>收藏</th>
            <th>塔罗</th>
            <th>会话</th>
            <th>最近活跃</th>
            <th>注册时间</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id" @click="openDetail(u)" class="user-row">
            <td class="cell-nick">
              <span class="avatar" v-if="u.avatar"><img :src="u.avatar" alt="" /></span>
              <span class="avatar avatar-empty" v-else>{{ (u.nickname || '?').slice(0, 1) }}</span>
              <span class="nick">{{ u.nickname }}</span>
            </td>
            <td>{{ u.stats.profiles }}</td>
            <td>{{ u.stats.favorites }}</td>
            <td>{{ u.stats.tarotRecords }}</td>
            <td>{{ u.stats.sessions }}</td>
            <td class="cell-dim">{{ fmt(u.lastActiveAt) }}</td>
            <td class="cell-dim">{{ fmt(u.createdAt) }}</td>
            <td><span class="view-link">查看 ›</span></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 详情抽屉 -->
    <div v-if="detailOpen" class="drawer-mask" @click="closeDetail"></div>
    <aside v-if="detailOpen" class="drawer glass-card">
      <div class="drawer-head">
        <div>
          <h3 class="text-glow-soft">{{ detailUser?.nickname }}</h3>
          <p class="cell-dim">ID: {{ detailUser?.id }}</p>
        </div>
        <button class="btn btn-xs" @click="closeDetail">关闭</button>
      </div>

      <div v-if="detailLoading" class="drawer-loading">加载中…</div>
      <div v-else class="drawer-body">
        <section class="block">
          <h4>八字档案（{{ detail?.profiles.length || 0 }}）</h4>
          <div v-if="!detail?.profiles.length" class="block-empty">暂无</div>
          <div v-for="p in detail?.profiles" :key="p.id" class="item">
            <div class="item-title">{{ p.name }} <span class="tag">{{ p.relation || '本人' }}</span></div>
            <div class="cell-dim">出生：{{ p.birthTime }} · {{ p.gender }} · 流派 {{ p.sect }}</div>
          </div>
        </section>

        <section class="block">
          <h4>命例收藏（{{ detail?.favorites.length || 0 }}）</h4>
          <div v-if="!detail?.favorites.length" class="block-empty">暂无</div>
          <div v-for="f in detail?.favorites" :key="f.caseId" class="item">
            <div class="item-title">{{ f.name }}</div>
            <div class="cell-dim">出生：{{ f.birthTime }} · {{ f.gender }}</div>
          </div>
        </section>

        <section class="block">
          <h4>塔罗记录（{{ detail?.tarotRecords.length || 0 }}）</h4>
          <div v-if="!detail?.tarotRecords.length" class="block-empty">暂无</div>
          <div v-for="t in detail?.tarotRecords" :key="t.id" class="item">
            <div class="item-title">{{ t.spread }} <span class="cell-dim">· {{ t.createdAt }}</span></div>
            <div class="cell-dim" v-if="t.question">问题：{{ t.question }}</div>
          </div>
        </section>

        <section class="block">
          <h4>我的对话（{{ detail?.sessions.length || 0 }}）</h4>
          <div v-if="!detail?.sessions.length" class="block-empty">暂无</div>
          <div v-for="s in detail?.sessions" :key="s.id" class="item">
            <div class="item-title">{{ s.title || '（无标题）' }}</div>
            <div class="cell-dim">消息 {{ s.messageCount }} 条 · 最后：{{ fmt(s.lastTime) }}</div>
          </div>
        </section>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { listAdminUsers, getAdminUser, type AdminUser, type AdminUserDetail } from "../api"

const users = ref<AdminUser[]>([])
const total = ref(0)
const loading = ref(false)

const detailOpen = ref(false)
const detailUser = ref<AdminUser | null>(null)
const detail = ref<AdminUserDetail | null>(null)
const detailLoading = ref(false)

const fmt = (s?: string) => (s ? s.replace("T", " ").slice(0, 19) : "-")

async function loadUsers() {
  loading.value = true
  try {
    const res = await listAdminUsers()
    users.value = res.users
    total.value = res.total
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function openDetail(u: AdminUser) {
  detailUser.value = u
  detailOpen.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getAdminUser(u.id)
  } catch (e) {
    console.error(e)
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  detailOpen.value = false
  detailUser.value = null
  detail.value = null
}

onMounted(loadUsers)
</script>

<style scoped>
.user-admin-view { padding: 8px; }
.page-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 22px; margin-bottom: 16px; border-radius: 16px;
}
.header-left { display: flex; align-items: center; gap: 14px; }
.header-icon {
  width: 42px; height: 42px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
  background: rgba(212,175,55,0.12); color: var(--accent-light);
}
.header-left h2 { font-size: 18px; letter-spacing: 1px; }
.header-info { font-size: 12px; color: var(--text-dim); margin-top: 2px; }
.header-actions { display: flex; align-items: center; gap: 12px; }
.total-badge { font-size: 12px; color: var(--text-dim); }

.btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 10px;
  background: rgba(255,255,255,0.05); border: 1px solid var(--border); color: var(--text);
  font-size: 13px; cursor: pointer; transition: all 0.2s;
}
.btn:hover { border-color: var(--accent); color: var(--accent-light); }
.btn:disabled { opacity: 0.5; cursor: default; }
.btn-xs { padding: 5px 10px; font-size: 12px; }

.loading-box, .empty-box { padding: 40px; text-align: center; color: var(--text-dim); border-radius: 16px; }

.table-wrap { border-radius: 16px; overflow: hidden; }
.user-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.user-table th {
  text-align: left; padding: 12px 14px; color: var(--text-dim); font-weight: 500;
  border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.02);
}
.user-table td { padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.04); }
.user-row { cursor: pointer; transition: background 0.2s; }
.user-row:hover { background: rgba(212,175,55,0.05); }
.cell-nick { display: flex; align-items: center; gap: 10px; }
.avatar {
  width: 30px; height: 30px; border-radius: 50%; overflow: hidden; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; background: rgba(212,175,55,0.15);
  color: var(--accent-light); font-size: 13px;
}
.avatar img { width: 100%; height: 100%; object-fit: cover; }
.nick { color: var(--text); }
.cell-dim { color: var(--text-dim); font-size: 12px; }
.view-link { color: var(--accent); font-size: 12px; }

.drawer-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 100; }
.drawer {
  position: fixed; top: 0; right: 0; bottom: 0; width: 460px; max-width: 92vw; z-index: 101;
  border-radius: 18px 0 0 18px; padding: 22px; overflow-y: auto;
}
.drawer-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 16px; }
.drawer-head h3 { font-size: 16px; }
.drawer-loading { color: var(--text-dim); padding: 20px 0; }
.block { margin-bottom: 18px; }
.block h4 { font-size: 13px; color: var(--accent-light); margin-bottom: 8px; letter-spacing: 0.5px; }
.block-empty { font-size: 12px; color: var(--text-dim); padding: 4px 0; }
.item { padding: 10px 12px; border-radius: 10px; background: rgba(255,255,255,0.03); margin-bottom: 8px; }
.item-title { font-size: 13px; color: var(--text); margin-bottom: 3px; }
.tag {
  font-size: 11px; color: var(--text-dim); background: rgba(255,255,255,0.05);
  padding: 1px 7px; border-radius: 6px; margin-left: 6px;
}
</style>
