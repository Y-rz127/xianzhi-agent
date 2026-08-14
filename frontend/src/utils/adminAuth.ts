/**
 * 管理端登录态：保存后端登录接口签发的会话 token。
 * 前端不再内置任何静态 API Key，所有管理接口凭该 token 鉴权。
 */
const ADMIN_TOKEN_KEY = "XZ_ADMIN_TOKEN"

export function getAdminToken(): string {
  return localStorage.getItem(ADMIN_TOKEN_KEY) || ""
}

export function isAdminLoggedIn(): boolean {
  return !!getAdminToken()
}

export function setAdminToken(token: string): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, token)
}

export function clearAdminAuth(): void {
  localStorage.removeItem(ADMIN_TOKEN_KEY)
}
