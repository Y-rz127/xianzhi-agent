import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
import { readFileSync, writeFileSync, existsSync } from 'fs'
import { resolve } from 'path'

// 编译后往 app.json 注入 lazyCodeLoading（uniapp 不支持通过 manifest 配置）
function injectLazyCodeLoading() {
  const appJsonPath = resolve(__dirname, 'dist/dev/mp-weixin/app.json')
  if (!existsSync(appJsonPath)) return
  const json = JSON.parse(readFileSync(appJsonPath, 'utf-8'))
  if (!json.lazyCodeLoading) {
    json.lazyCodeLoading = 'requiredComponents'
    writeFileSync(appJsonPath, JSON.stringify(json, null, 2))
    console.log('[injectLazyCodeLoading] lazyCodeLoading injected into app.json')
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    uni(),
    {
      name: 'inject-lazy-code-loading',
      closeBundle() {
        try { injectLazyCodeLoading() } catch (e) { console.warn('[injectLazyCodeLoading]', e) }
      },
    },
  ],
  css: {
    preprocessorOptions: {
      scss: {
        // 使用现代 Sass API，消除 legacy-js-api 弃用警告
        api: 'modern',
        silenceDeprecations: ['legacy-js-api'],
      },
    },
  },
  server: {
    port: 8080,
    proxy: {
      // HTTP 代理：/api -> http://localhost:8123
      '/api': {
        target: 'http://localhost:8123',
        changeOrigin: true,
      },
      // WebSocket 代理：/ws -> ws://localhost:8123
      // 前端 wsPath() 在 H5 dev 下会把 /api/ai/xianzhi/ws 转成 /ws/api/ai/xianzhi/ws
      '/ws': {
        target: 'ws://localhost:8123',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/ws/, ''),
      },
    },
  },
})
