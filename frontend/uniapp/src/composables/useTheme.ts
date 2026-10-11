/**
 * useTheme - 小程序全局主题（白天纸墨 / 暗夜玻璃）
 *
 * 用法：页面根节点 :class="themeClass"，模板内即可整体换肤。
 * 持久化到本地存储（key: xz_theme），默认 light（纸墨浅色）。
 * 切换后写入存储；因小程序无全局响应式根节点，已打开页面在返回前台时
 * 由各页根节点的 themeClass 计算属性自然刷新（reactive 模块级单例）。
 *
 * 换肤管不到的两样系统控件，另有专门出口：
 *  - 原生导航栏 / 下拉背景：pages.json 未设 navigationStyle: custom 的页面，
 *    用 applyNativeBar() 显式改色（CSS 类无法作用于系统控件）。
 *  - 原生弹窗 uni.showModal：永远白底，改用 @/components/ThemeDialog 自定义弹层。
 */
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'

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

/**
 * 原生导航栏配色。frontColor 微信只收 #ffffff / #000000 两个值。
 * 深色取 #0a0f1a：暗夜页面顶部就是这条渐变（linear-gradient #0a0f1a → #050810），
 * 导航栏与页面接缝处看不出色差。
 */
const NATIVE_BAR = {
  light: { frontColor: '#000000', backgroundColor: '#FAFAF8' },
  dark: { frontColor: '#ffffff', backgroundColor: '#0a0f1a' },
} as const

/** 同步原生导航栏 + 下拉背景（原生栏页面专用；custom 导航页调用会静默失败） */
export function applyNativeBar(next: ThemeMode = mode.value) {
  const bar = NATIVE_BAR[next]
  const bg = bar.backgroundColor
  try {
    uni.setNavigationBarColor({ frontColor: bar.frontColor, backgroundColor: bg, fail: () => {} })
  } catch { /* 非小程序端无此 API */ }
  try {
    uni.setBackgroundColor({ backgroundColor: bg, backgroundColorTop: bg, backgroundColorBottom: bg, fail: () => {} })
  } catch { /* 同上 */ }
}

/**
 * 在「保留原生导航栏」的页面里调用：每次 onShow 按当前主题重刷导航栏/下拉背景。
 * 主题只在设置页切换，改完再回到这些页面时 onShow 必然触发，颜色跟得上。
 */
export function useThemeNativeBar() {
  onShow(() => applyNativeBar())
}

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
    // 设置页自己就是原生导航栏页面，切换后立刻跟上，不必等下次 onShow
    applyNativeBar(next)
  }

  function toggleTheme() {
    setTheme(mode.value === 'dark' ? 'light' : 'dark')
  }

  return { mode, themeClass, isDark, setTheme, toggleTheme }
}
