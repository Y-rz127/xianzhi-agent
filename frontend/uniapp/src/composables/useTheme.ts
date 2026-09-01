/**
 * useTheme - 小程序全局主题（白天纸墨 / 暗夜玻璃）
 *
 * 用法：页面根节点 :class="themeClass"，模板内即可整体换肤。
 * 持久化到本地存储（key: xz_theme），默认 light（纸墨浅色）。
 * 切换后写入存储；因小程序无全局响应式根节点，已打开页面在返回前台时
 * 由各页根节点的 themeClass 计算属性自然刷新（reactive 模块级单例）。
 */
import { computed, ref } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'xz_theme'

function readInitial(): ThemeMode {
  try {
    const saved = uni.getStorageSync(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* storage 不可用时静默回退默认 */
  }
  return 'light'
}

const mode = ref<ThemeMode>(readInitial())

export function useTheme() {
  const themeClass = computed(() => (mode.value === 'dark' ? 't-dark' : 't-light'))
  const isDark = computed(() => mode.value === 'dark')

  function setTheme(next: ThemeMode) {
    mode.value = next
    try {
      uni.setStorageSync(STORAGE_KEY, next)
    } catch {
      /* 持久化失败不影响当前会话生效 */
    }
  }

  function toggleTheme() {
    setTheme(mode.value === 'dark' ? 'light' : 'dark')
  }

  return { mode, themeClass, isDark, setTheme, toggleTheme }
}
