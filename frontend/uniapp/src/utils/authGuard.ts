/**
 * 登录守卫：未登录时跳转到登录页。
 * 在需要登录的页面（先知/塔罗/我的）的 onShow 中调用。
 */
// 临时关闭强制登录守卫，允许未登录直接访问
export function requireLogin(): boolean {
  return true
}