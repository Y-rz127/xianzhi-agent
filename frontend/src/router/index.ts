import { createRouter, createWebHistory } from "vue-router"
import type { RouteRecordRaw } from "vue-router"
import Xianzhi from "../views/Xianzhi.vue"
import Love from "../views/Love.vue"
import Disclaimer from "../views/Disclaimer.vue"
import Privacy from "../views/Privacy.vue"
import Terms from "../views/Terms.vue"
import Huangli from "../views/Huangli.vue"
import Hehun from "../views/Hehun.vue"
import Tarot from "../views/Tarot.vue"

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/xianzhi" },
  { path: "/xianzhi", name: "xianzhi", component: Xianzhi, meta: { title: "先知 · 命理分析" } },
  { path: "/love", name: "love", component: Love, meta: { title: "恋爱大师" } },
  { path: "/disclaimer", name: "disclaimer", component: Disclaimer, meta: { title: "免责声明" } },
  { path: "/privacy", name: "privacy", component: Privacy, meta: { title: "隐私政策" } },
  { path: "/terms", name: "terms", component: Terms, meta: { title: "服务条款" } },
  { path: "/huangli", name: "huangli", component: Huangli, meta: { title: "黄历 · 择日" } },
  { path: "/hehun", name: "hehun", component: Hehun, meta: { title: "八字合婚" } },
  { path: "/tarot", name: "tarot", component: Tarot, meta: { title: "每日塔罗" } },
]

const router = createRouter({ history: createWebHistory(), routes })
router.afterEach((to) => { document.title = (to.meta.title as string) || "先知" })
export default router
