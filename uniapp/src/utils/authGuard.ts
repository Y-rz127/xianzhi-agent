/**
 * 登录守卫：未登录时跳转到登录页。
 * 在需要登录的页面（先知/塔罗/我的）的 onShow 中调用。
 */
import { isLoggedIn } from './storage'

const LOGIN_PATH = '/pages/login/index'

/** 检查登录状态，未登录则跳转。返回 true 表示已通过检查。 */
export function requireLogin(): boolean {
  if (isLoggedIn()) return true
  // tabBar 页不能用 navigateTo 跳转非 tabBar 页，需用 reLaunch / redirectTo
  uni.reLaunch({ url: LOGIN_PATH })
  return false
}
