/**
 * 全局配置中心 - 支持 H5/小程序/App 多端动态切换请求基址
 *
 * 优先级:
 *   1. 运行时调用 setConfig() 覆盖（推荐：小程序内可在设置页切换）
 *   2. uni.getStorageSync('XIANZHI_CONFIG') 持久化值（用户手动填过）
 *   3. 编译时环境变量（VITE_API_BASE / VITE_WS_BASE）
 *   4. 默认值（H5 走 /api + vite proxy；小程序走 localhost）
 *
 * 注意：H5 在开发期走 vite proxy(/api -> localhost:8123)，
 *      小程序/App 端必须填实际可达的地址（局域网 IP 或备案域名）。
 */

const STORAGE_KEY = 'XIANZHI_CONFIG'

interface RuntimeConfig {
  apiBase: string
  wsBase: string
}

function isH5(): boolean {
  // #ifdef H5
  return true
  // #endif
  // #ifndef H5
  return false
  // #endif
}

function defaultConfig(): RuntimeConfig {
  if (isH5()) {
    return { apiBase: '/api', wsBase: '' /* 自动取 location.host */ }
  }
  // 小程序/App 默认：本地后端
  // 真机调试请在设置页改成电脑局域网 IP，如 http://192.168.1.100:8123/api
  return { apiBase: 'http://localhost:8123/api', wsBase: 'ws://localhost:8123' }
}

function loadFromStorage(): RuntimeConfig | null {
  try {
    const s = uni.getStorageSync(STORAGE_KEY) as RuntimeConfig | string | undefined
    if (s && typeof s === 'object' && 'apiBase' in s) return s
  } catch { /* ignore */ }
  return null
}

let _config: RuntimeConfig = (() => {
  const stored = loadFromStorage()
  if (stored) return stored
  // 编译时变量（仅 H5 编译时可注入）
  // #ifdef H5
  const envBase = (import.meta as any).env?.VITE_API_BASE as string | undefined
  if (envBase) return { apiBase: envBase, wsBase: '' }
  // #endif
  return defaultConfig()
})()

/** 运行时动态切换请求基址（小程序/App 端必备） */
export function setConfig(cfg: Partial<RuntimeConfig>) {
  _config = { ..._config, ...cfg }
  try { uni.setStorageSync(STORAGE_KEY, _config) } catch { /* ignore */ }
}

/** 获取当前配置 */
export function getConfig(): RuntimeConfig {
  return _config
}

/** 把 wsBase 解析为带协议的具体地址（小程序端无 location） */
export function resolveWsBase(): string {
  if (_config.wsBase) return _config.wsBase
  if (isH5()) {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${location.host}`
  }
  // 小程序端从 apiBase 推导
  return _config.apiBase.replace(/^http/, 'ws')
}
