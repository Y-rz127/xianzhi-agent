import { createSSRApp } from 'vue'
import App from './App.vue'
// 主题变量（白天 .t-light / 暗夜 .t-dark 两套 --x-*）：纯 CSS，模块方式全局引入，
// 规避 style 块内 Sass @import 废弃告警
import './styles/theme.scss'

export function createApp() {
  const app = createSSRApp(App)
  return {
    app,
  }
}
