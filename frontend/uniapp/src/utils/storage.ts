/**
 * 本地存储：登录态（token + 用户资料）持久化。
 * 账号登录后写入，所有用户态接口通过 token 鉴权。
 */

const TOKEN_KEY = 'XZ_TOKEN'
const USER_KEY = 'XZ_USER'

export function getToken(): string {
  try {
    return uni.getStorageSync(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setToken(token: string) {
  try {
    if (token) uni.setStorageSync(TOKEN_KEY, token)
    else uni.removeStorageSync(TOKEN_KEY)
  } catch {}
}

export function getUser(): any | null {
  try {
    return uni.getStorageSync(USER_KEY) || null
  } catch {
    return null
  }
}

export function setUser(user: any) {
  try {
    if (user) uni.setStorageSync(USER_KEY, user)
    else uni.removeStorageSync(USER_KEY)
  } catch {}
}

export function clearAuth() {
  try {
    uni.removeStorageSync(TOKEN_KEY)
    uni.removeStorageSync(USER_KEY)
  } catch {}
}

export function isLoggedIn(): boolean {
  return !!getToken()
}

export function currentUserId(): string {
  const u = getUser()
  return u?.id || ''
}

/* ============ 会话级出生地（本地持久化，用于重新进入历史会话时恢复） ============ */
const BIRTH_PLACE_PREFIX = 'XZ_BIRTH_PLACE_'

export interface LocalBirthPlace { place: string; longitude: number }

export function getBirthPlaceLocal(sessionId: string): LocalBirthPlace | null {
  try {
    return uni.getStorageSync(BIRTH_PLACE_PREFIX + sessionId) || null
  } catch {
    return null
  }
}

export function setBirthPlaceLocal(sessionId: string, place: string, longitude: number) {
  try {
    if (sessionId) uni.setStorageSync(BIRTH_PLACE_PREFIX + sessionId, { place, longitude })
  } catch {}
}

export function clearBirthPlaceLocal(sessionId: string) {
  try {
    if (sessionId) uni.removeStorageSync(BIRTH_PLACE_PREFIX + sessionId)
  } catch {}
}

/* ============ 会话级出生信息（本地持久化） ============
 * 后端 chart_context 通知可能丢（长回答期间 socket 断开就没了），
 * 落一份本地副本：重新进会话时先用本地兜住，再用 /birth-info 接口校正。
 */
const BIRTH_INFO_PREFIX = 'XZ_BIRTH_INFO_'

export interface LocalBirthInfo { time: string; gender: '男' | '女' }

export function getBirthInfoLocal(sessionId: string): LocalBirthInfo | null {
  try {
    const v = uni.getStorageSync(BIRTH_INFO_PREFIX + sessionId)
    return v && v.time && v.gender ? (v as LocalBirthInfo) : null
  } catch {
    return null
  }
}

export function setBirthInfoLocal(sessionId: string, time: string, gender: '男' | '女') {
  try {
    if (sessionId && time && gender) uni.setStorageSync(BIRTH_INFO_PREFIX + sessionId, { time, gender })
  } catch {}
}

export function clearBirthInfoLocal(sessionId: string) {
  try {
    if (sessionId) uni.removeStorageSync(BIRTH_INFO_PREFIX + sessionId)
  } catch {}
}
