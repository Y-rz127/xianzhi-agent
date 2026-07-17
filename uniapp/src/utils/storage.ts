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
