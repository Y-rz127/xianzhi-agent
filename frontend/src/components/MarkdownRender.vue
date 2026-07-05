<template>
  <div class="markdown-content" v-html="rendered"></div>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue"
import { marked } from "marked"
// 按需加载 highlight.js 核心，减少 bundle 体积（默认只注册常见语言）
import hljs from "highlight.js/lib/core"
import json from "highlight.js/lib/languages/json"
import python from "highlight.js/lib/languages/python"
import javascript from "highlight.js/lib/languages/javascript"
import typescript from "highlight.js/lib/languages/typescript"
import bash from "highlight.js/lib/languages/bash"
hljs.registerLanguage("json", json)
hljs.registerLanguage("python", python)
hljs.registerLanguage("javascript", javascript)
hljs.registerLanguage("typescript", typescript)
hljs.registerLanguage("bash", bash)
hljs.registerLanguage("shell", bash)

const props = defineProps<{ content: string }>()

marked.setOptions({ gfm: true, breaks: true })

marked.use({
  renderer: {
    code({ text, lang }) {
      const langClass = lang ? `language-${lang}` : ""
      const highlighted = lang ? hljs.highlight(text, { language: lang }).value : hljs.highlightAuto(text).value
      return `<pre><code class="${langClass}">${highlighted}</code></pre>`
    },
    heading({ text, depth }) {
      const size = depth === 1 ? "20px" : depth === 2 ? "17px" : depth === 3 ? "15px" : "14px"
      return `<h${depth} style="font-size:${size};font-weight:600;margin:14px 0 8px;color:var(--accent-light);letter-spacing:1px;">${text}</h${depth}>`
    },
    strong({ text }) {
      return `<strong style="color:var(--accent);font-weight:600;">${text}</strong>`
    },
    link({ href, text }) {
      return `<a href="${href}" target="_blank" rel="noopener" style="color:var(--cyan);text-decoration:none;border-bottom:1px dashed var(--cyan);">${text}</a>`
    },
    list({ items, ordered }) {
      const tag = ordered ? "ol" : "ul"
      const liItems = items.map(item => `<li style="margin:4px 0;padding-left:8px;">${item.text}</li>`).join("")
      return `<${tag} style="padding-left:24px;margin:8px 0;">${liItems}</${tag}>`
    },
    table(h) {
      const header = h.header.map((cell: any) => `<th style="padding:8px 12px;border:1px solid var(--border);background:rgba(212,175,55,0.08);text-align:left;">${cell.text}</th>`).join("")
      const tbody = h.rows.map((row: any) => `<tr>${row.map((cell: any) => `<td style="padding:8px 12px;border:1px solid var(--border);">${cell.text}</td>`).join("")}</tr>`).join("")
      return `<table style="border-collapse:collapse;width:100%;margin:12px 0;border:1px solid var(--border);"><thead><tr>${header}</tr></thead><tbody>${tbody}</tbody></table>`
    },
  },
})

const rendered = computed(() => marked(props.content) as string)

onMounted(() => { hljs.highlightAll() })
</script>

<style scoped>
.markdown-content { line-height: 1.8; color: var(--text); font-size: 14px; }
.markdown-content :deep(h1), .markdown-content :deep(h2), .markdown-content :deep(h3), .markdown-content :deep(h4) { margin-top: 18px; margin-bottom: 10px; }
.markdown-content :deep(p) { margin: 6px 0; }
.markdown-content :deep(ul), .markdown-content :deep(ol) { margin: 8px 0; }
.markdown-content :deep(code) { background: rgba(212,175,55,0.1); padding: 2px 6px; border-radius: 4px; font-size: 13px; color: var(--accent-light); font-family: "Consolas", monospace; }
.markdown-content :deep(pre) { background: rgba(0,0,0,0.4); padding: 14px; border-radius: 10px; overflow-x: auto; margin: 12px 0; border: 1px solid var(--border); }
.markdown-content :deep(pre code) { background: transparent; padding: 0; color: inherit; }
.markdown-content :deep(blockquote) { border-left: 3px solid var(--accent); padding-left: 12px; margin: 12px 0; color: var(--text-dim); font-style: italic; }
.markdown-content :deep(hr) { border: none; height: 1px; background: linear-gradient(90deg, transparent, var(--border), transparent); margin: 20px 0; }
</style>