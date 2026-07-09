<template>
  <div class="layout">
    <StarBackground />
     <button class="sidebar-toggle-btn" :class="{ 'sidebar-open': sidebarOpen }" @click="toggleSidebar" aria-label="切换侧边栏">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
    </button>
    <div class="sidebar-mask" v-if="sidebarOpen && isMobile" @click="sidebarOpen = false"></div>
    <aside class="sidebar" :class="{ 'open': sidebarOpen, 'collapsed': sidebarCollapsed }">
      <div class="logo">
        <div class="logo-icon animate-pulse-glow">
          <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
            <path d="M2 12h20" />
          </svg>
        </div>
        <div class="logo-text" v-if="!sidebarCollapsed">
          <h1 class="text-glow">先知</h1>
          <p>八字命理 · 智能预测</p>
        </div>
      </div>

      <nav class="nav">
        <router-link to="/xianzhi" class="nav-item" active-class="active" @click="onNavClick">
          <span class="nav-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
          </span>
          <span v-if="!sidebarCollapsed">命理分析</span>
        </router-link>
        <router-link to="/love" class="nav-item" active-class="active" @click="onNavClick">
          <span class="nav-icon love-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
          </span>
          <span v-if="!sidebarCollapsed">恋爱大师</span>
        </router-link>
        <router-link to="/hehun" class="nav-item" active-class="active" @click="onNavClick">
          <span class="nav-icon hehun-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </span>
          <span v-if="!sidebarCollapsed">八字合婚</span>
        </router-link>
        <router-link to="/tarot" class="nav-item" active-class="active" @click="onNavClick">
          <span class="nav-icon tarot-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10"/><path d="M12 2a15.3 15.3 0 0 0-4 10 15.3 15.3 0 0 0 4 10"/><path d="M2 12h20"/></svg>
          </span>
          <span v-if="!sidebarCollapsed">每日塔罗</span>
        </router-link>
        <router-link to="/chart-cases" class="nav-item" active-class="active" @click="onNavClick">
          <span class="nav-icon cases-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
          </span>
          <span v-if="!sidebarCollapsed">命例库</span>
        </router-link>
        <router-link to="/rag-manager" class="nav-item" active-class="active" @click="onNavClick">
          <span class="nav-icon rag-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
          </span>
          <span v-if="!sidebarCollapsed">知识库</span>
        </router-link>
        <router-link to="/observability" class="nav-item" active-class="active" @click="onNavClick">
          <span class="nav-icon observability-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/></svg>
          </span>
          <span v-if="!sidebarCollapsed">可观测性</span>
        </router-link>
      </nav>

      <div class="sidebar-footer" v-if="!sidebarCollapsed">
        <div class="divider"></div>
        <p class="motto">命由天定 · 运由己造</p>
        <p class="version">Xianzhi v0.1.0</p>
        <div class="legal-links">
          <router-link to="/disclaimer">免责声明</router-link>
          <router-link to="/privacy">隐私政策</router-link>
          <router-link to="/terms">服务条款</router-link>
        </div>
      </div>
    </aside>

    <main class="main">
      <keep-alive :include="['Xianzhi', 'Love']">
        <router-view />
      </keep-alive>
    </main>
    <CommandPalette />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue"
import StarBackground from "./components/StarBackground.vue"
import CommandPalette from "./components/CommandPalette.vue"

const sidebarCollapsed = ref(false)
const sidebarOpen = ref(true)
const isMobile = ref(false)

const appSidebarOpen = () => isMobile.value ? sidebarOpen.value : !sidebarCollapsed.value

const emitAppSidebarState = () => {
  window.dispatchEvent(new CustomEvent("app-sidebar-state", { detail: { open: appSidebarOpen() } }))
}

const toggleSidebar = () => {
  if (isMobile.value) {
    sidebarOpen.value = !sidebarOpen.value
  } else {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }
  emitAppSidebarState()
}

const onNavClick = () => {
  if (isMobile.value) {
    sidebarOpen.value = false
    emitAppSidebarState()
  }
}

const checkMobile = () => {
  isMobile.value = window.innerWidth <= 768
  if (isMobile.value) {
    sidebarCollapsed.value = false
    sidebarOpen.value = false
  } else {
    sidebarOpen.value = true
  }
  emitAppSidebarState()
}

const onAppToggleSidebar = () => toggleSidebar()

onMounted(() => {
  checkMobile()
  window.addEventListener("resize", checkMobile)
  window.addEventListener("app-toggle-sidebar", onAppToggleSidebar)
})
onUnmounted(() => {
  window.removeEventListener("resize", checkMobile)
  window.removeEventListener("app-toggle-sidebar", onAppToggleSidebar)
})
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  position: relative;
  z-index: 1;
  background: linear-gradient(135deg, rgba(5, 8, 16, 0.92), rgba(10, 15, 26, 0.96));
}
.sidebar-toggle-btn {
  position: fixed; top: 12px; left: 12px; z-index: 110;
  width: 44px; height: 44px; border-radius: 12px;
  background: rgba(12,18,32,0.98); border: 1px solid var(--border);
  color: var(--text); cursor: pointer; display: none; align-items: center; justify-content: center;
  transition: all 0.25s; box-shadow: 0 4px 16px rgba(0,0,0,0.4);
}
.sidebar-toggle-btn:hover { border-color: var(--accent); color: var(--accent); }
.sidebar-toggle-btn:active { transform: scale(0.96); }
@media (max-width: 768px) {
  .sidebar-toggle-btn { display: flex; }
}
.sidebar-mask {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.65); z-index: 90;
}
.sidebar {
  width: 288px; display: flex; flex-direction: column; padding: 24px 12px;
  background: linear-gradient(180deg, rgba(10,15,26,0.96) 0%, rgba(6,10,18,0.98) 100%);
  border-right: 1px solid var(--border); backdrop-filter: blur(16px);
  box-shadow: 4px 0 30px rgba(0,0,0,0.35);
  transition: width 0.35s ease, transform 0.35s ease;
  overflow-y: auto;
  min-height: 0;
}
.sidebar.collapsed { width: 72px; }
.logo {
  display: flex; align-items: center; gap: 14px; padding: 0 0 24px;
  border-bottom: 1px solid var(--border);
}
.logo-icon {
  width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, var(--accent), #8b6f47); color: #0c1220;
  box-shadow: 0 0 18px rgba(212,175,55,0.35);
  flex-shrink: 0;
}
.logo-text h1 { font-size: 20px; letter-spacing: 3px; color: var(--accent-light); }
.logo-text p { font-size: 11px; color: var(--text-dim); margin-top: 2px; letter-spacing: 1px; }
.nav { flex: 1; padding: 24px 0; display: flex; flex-direction: column; gap: 10px; }
.nav-item {
  display: flex; align-items: center; gap: 14px; padding: 14px 12px; border-radius: 14px;
  color: var(--text-dim); text-decoration: none; font-size: 14px; position: relative; overflow: hidden;
  transition: all 0.3s ease; border: 1px solid transparent;
  justify-content: flex-start;
}
.nav-item::before {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: linear-gradient(180deg, var(--accent), transparent); opacity: 0; transition: opacity 0.3s;
}
.nav-item:hover { background: rgba(212,175,55,0.06); color: var(--text); border-color: rgba(212,175,55,0.15); }
.nav-item:hover::before { opacity: 1; }
.nav-item.active { background: linear-gradient(90deg, rgba(212,175,55,0.12), transparent); color: var(--accent-light); border-color: rgba(212,175,55,0.25); }
.nav-item.active::before { opacity: 1; }
.nav-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.04); flex-shrink: 0; }
.nav-item.active .nav-icon { background: rgba(212,175,55,0.15); color: var(--accent-light); box-shadow: 0 0 12px rgba(212,175,55,0.2); }
.love-icon { color: var(--love); }
.nav-item.active .love-icon { background: rgba(232,139,139,0.15); color: var(--love); box-shadow: 0 0 12px rgba(232,139,139,0.2); }
.hehun-icon { color: #e8b48b; }
.nav-item.active .hehun-icon { background: rgba(232,180,139,0.15); color: #e8b48b; box-shadow: 0 0 12px rgba(232,180,139,0.2); }
.tarot-icon { color: #b886e8; }
.nav-item.active .tarot-icon { background: rgba(184,134,232,0.15); color: #b886e8; box-shadow: 0 0 12px rgba(184,134,232,0.2); }
.cases-icon { color: #8bb8e8; }
.nav-item.active .cases-icon { background: rgba(139,184,232,0.15); color: #8bb8e8; box-shadow: 0 0 12px rgba(139,184,232,0.2); }
.rag-icon { color: #8be8c7; }
.nav-item.active .rag-icon { background: rgba(139,232,199,0.15); color: #8be8c7; box-shadow: 0 0 12px rgba(139,232,199,0.2); }
.observability-icon { color: #d4af37; }
.nav-item.active .observability-icon { background: rgba(212,175,55,0.15); color: #d4af37; box-shadow: 0 0 12px rgba(212,175,55,0.2); }
.sidebar-footer { padding: 16px 4px 0; }
.divider { height: 1px; background: linear-gradient(90deg, transparent, var(--border), transparent); margin-bottom: 14px; }
.motto { font-size: 12px; color: var(--text-dim); text-align: center; letter-spacing: 2px; margin-bottom: 6px; }
.version { font-size: 10px; color: rgba(138,155,176,0.5); text-align: center; }
.legal-links { display: flex; justify-content: center; gap: 12px; margin-top: 10px; }
.legal-links a { font-size: 10px; color: rgba(138,155,176,0.4); text-decoration: none; transition: color 0.2s; }
.legal-links a:hover { color: var(--accent); }
.main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  position: relative;
  z-index: 2;
  background: linear-gradient(180deg, rgba(8, 13, 24, 0.72), rgba(5, 8, 16, 0.92));
  height: 100%;
}

@media (max-width: 768px) {
  .sidebar-toggle-btn { left: 12px; top: 12px; display: flex; }
  .sidebar-mask { display: block; }
  .sidebar {
    position: fixed; left: 0; top: 0; bottom: 0; z-index: 95;
    width: 288px; transform: translateX(-100%); padding-top: 70px;
  }
  .sidebar.open { transform: translateX(0); }
  .sidebar.collapsed { width: 288px; }
  .logo { padding: 0 14px 16px; }
  .logo-icon { width: 44px; height: 44px; }
  .logo-text h1 { font-size: 19px; }
}
</style>
