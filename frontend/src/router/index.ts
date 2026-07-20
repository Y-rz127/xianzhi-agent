import { createRouter, createWebHistory } from "vue-router"
import type { RouteLocationNormalized, RouteRecordRaw } from "vue-router"
import Xianzhi from "../views/Xianzhi.vue"
import Disclaimer from "../views/Disclaimer.vue"
import Privacy from "../views/Privacy.vue"
import Terms from "../views/Terms.vue"
import Hehun from "../views/Hehun.vue"
import Tarot from "../views/Tarot.vue"
import RagManager from "../views/RagManager.vue"
import ChartCases from "../views/ChartCases.vue"
import Observability from "../views/Observability.vue"
import UserAdmin from "../views/UserAdmin.vue"
import Feedback from "../views/Feedback.vue"
import AdminLogin from "../views/AdminLogin.vue"
import { isAdminLoggedIn } from "../utils/adminAuth"

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/xianzhi" },
  { path: "/xianzhi", name: "xianzhi", component: Xianzhi, meta: { title: "先知 · 命理分析" } },
  { path: "/disclaimer", name: "disclaimer", component: Disclaimer, meta: { title: "免责声明" } },
  { path: "/privacy", name: "privacy", component: Privacy, meta: { title: "隐私政策" } },
  { path: "/terms", name: "terms", component: Terms, meta: { title: "服务条款" } },
  { path: "/hehun", name: "hehun", component: Hehun, meta: { title: "八字合婚" } },
  { path: "/tarot", name: "tarot", component: Tarot, meta: { title: "每日塔罗" } },
  { path: "/rag-manager", name: "rag-manager", component: RagManager, meta: { title: "知识库管理" } },
  { path: "/chart-cases", name: "chart-cases", component: ChartCases, meta: { title: "命例库" } },
  { path: "/observability", name: "observability", component: Observability, meta: { title: "可观测性" } },
  { path: "/user-admin", name: "user-admin", component: UserAdmin, meta: { title: "用户管理" } },
  { path: "/feedback", name: "feedback", component: Feedback, meta: { title: "问题反馈" } },
  { path: "/admin-login", name: "admin-login", component: AdminLogin, meta: { title: "管理员登录" } },
  { path: "/admin-accounts", name: "admin-accounts", component: () => import("../views/AdminAccountManager.vue"), meta: { title: "账号管理" } },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to: RouteLocationNormalized) => {
  if (to.path === "/admin-login") return
  if (!isAdminLoggedIn()) {
    return { path: "/admin-login", query: { redirect: to.fullPath } }
  }
})

export default router