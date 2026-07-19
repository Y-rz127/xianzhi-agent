/**
 * 登录守卫：未登录时跳转到登录页。
 * 在需要登录的页面（先知/塔罗/我的）的 onShow 中调用。
 */
import { isLoggedIn } from './storage'

const LOGIN_PATH = '/pages/login/index'

/** 检查登录状态，未登录则跳转。返回 true 表示已通过检查。 */
export function requireLogin(): boolean {
  if (isLoggedIn()) return true
  // TODO: 真机调试期间暂时关闭强制登录跳转，调试完成后恢复
  // uni.reLaunch({ url: LOGIN_PATH })
  return false
}