const ADMIN_KEY = "XZ_ADMIN_AUTH"

export function isAdminLoggedIn(): boolean {
  return localStorage.getItem(ADMIN_KEY) === "1"
}

export function setAdminLoggedIn(): void {
  localStorage.setItem(ADMIN_KEY, "1")
}

export function clearAdminAuth(): void {
  localStorage.removeItem(ADMIN_KEY)
}