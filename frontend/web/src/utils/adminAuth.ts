const TOKEN_KEY = "XZ_ADMIN_TOKEN"
const EXP_KEY = "XZ_ADMIN_EXP"

/** 读取有效令牌；过期/缺失时清理并返回空串。 */
export function getAdminToken(): string {
  const token = sessionStorage.getItem(TOKEN_KEY) || ""
  const exp = Number(sessionStorage.getItem(EXP_KEY) || 0)
  if (!token || !exp || exp * 1000 <= Date.now()) {
    clearAdminAuth()
    return ""
  }
  return token
}

export function isAdminLoggedIn(): boolean {
  return !!getAdminToken()
}

/** 登录成功后保存短时令牌（token 有效期由后端 expires_in 给出，单位秒）。 */
export function setAdminLoggedIn(token: string, expiresIn: number): void {
  sessionStorage.setItem(TOKEN_KEY, token)
  sessionStorage.setItem(EXP_KEY, String(Math.floor(Date.now() / 1000) + Math.max(1, expiresIn)))
  // 清理旧版本只用 localStorage 标记的登录态
  localStorage.removeItem("XZ_ADMIN_AUTH")
}

export function clearAdminAuth(): void {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(EXP_KEY)
  localStorage.removeItem("XZ_ADMIN_AUTH")
}
