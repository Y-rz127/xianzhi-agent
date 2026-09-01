<template>
  <view class="md-render">
    <rich-text :nodes="nodes" />
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ content: string }>()

/**
 * 轻量 Markdown → HTML 转换（rich-text 兼容）
 * 支持：标题 / 加粗 / 斜体 / 行内代码 / 代码块 / 无序列表 / 有序列表 / 引用 / 段落 / 换行
 * 不引入 marked / highlight.js（小程序体积考虑）
 */
function mdToHtml(md: string): string {
  if (!md) return ''
  // 转义 HTML 特殊字符
  let s = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 代码块 ```...```
  s = s.replace(/```[\s\S]*?```/g, (m) => {
    const code = m.replace(/^```[a-zA-Z]*\n?/, '').replace(/```$/, '')
    return `<pre class="md-pre"><code class="md-code">${code}</code></pre>`
  })

  // 按行处理
  const lines = s.split('\n')
  const out: string[] = []
  let inUl = false
  let inOl = false
  let inQuote = false

  const closeLists = () => {
    if (inUl) { out.push('</ul>'); inUl = false }
    if (inOl) { out.push('</ol>'); inOl = false }
  }
  const closeQuote = () => {
    if (inQuote) { out.push('</blockquote>'); inQuote = false }
  }

  const inline = (t: string) => t
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="md-strong">$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em class="md-em">$1</em>')
    .replace(/`([^`]+)`/g, '<code class="md-code">$1</code>')

  for (const raw of lines) {
    const line = raw
    // 标题
    const h = line.match(/^(#{1,6})\s+(.*)/)
    if (h) {
      closeLists(); closeQuote()
      const level = h[1].length
      out.push(`<h${level} class="md-h${level}">${inline(h[2])}</h${level}>`)
      continue
    }
    // 代码块已在上面处理过，跳过 pre 内的行
    if (line.startsWith('<pre')) {
      closeLists(); closeQuote()
      out.push(line)
      continue
    }
    // 引用
    const q = line.match(/^&gt;\s?(.*)/)
    if (q) {
      if (!inQuote) { closeLists(); out.push('<blockquote class="md-quote">'); inQuote = true }
      out.push(`<p class="md-p">${inline(q[1])}</p>`)
      continue
    } else {
      closeQuote()
    }
    // 无序列表
    const ul = line.match(/^[-*+]\s+(.*)/)
    if (ul) {
      if (inOl) { out.push('</ol>'); inOl = false }
      if (!inUl) { out.push('<ul class="md-ul">'); inUl = true }
      out.push(`<li class="md-li">${inline(ul[1])}</li>`)
      continue
    }
    // 有序列表
    const ol = line.match(/^\d+\.\s+(.*)/)
    if (ol) {
      if (inUl) { out.push('</ul>'); inUl = false }
      if (!inOl) { out.push('<ol class="md-ol">'); inOl = true }
      out.push(`<li class="md-li">${inline(ol[1])}</li>`)
      continue
    }
    // 空行
    if (line.trim() === '') {
      closeLists(); closeQuote()
      continue
    }
    // 普通段落
    closeLists(); closeQuote()
    out.push(`<p class="md-p">${inline(line)}</p>`)
  }
  closeLists(); closeQuote()
  return out.join('')
}

const nodes = computed(() => mdToHtml(props.content))
</script>

<style lang="scss" scoped>
.md-render {
  font-size: 28rpx;
  line-height: 1.7;
  color: inherit;
  word-break: break-all;
  overflow-wrap: break-word;
}

/* /deep/ 穿透 rich-text */
.md-render :deep(.md-h1) { font-size: 36rpx; font-weight: bold; margin: 20rpx 0 12rpx; color: inherit; }
.md-render :deep(.md-h2) { font-size: 32rpx; font-weight: bold; margin: 18rpx 0 10rpx; color: inherit; }
.md-render :deep(.md-h3) { font-size: 30rpx; font-weight: bold; margin: 16rpx 0 8rpx; color: inherit; opacity: 0.9; }
.md-render :deep(.md-h4) { font-size: 28rpx; font-weight: bold; margin: 12rpx 0 6rpx; color: inherit; opacity: 0.9; }
.md-render :deep(.md-p) { margin: 8rpx 0; }
.md-render :deep(.md-strong) { font-weight: bold; color: inherit; opacity: 1; }
.md-render :deep(.md-em) { font-style: italic; }
.md-render :deep(.md-code) {
  font-family: monospace;
  background: rgba(107, 123, 142, 0.1);
  color: inherit;
  padding: 2rpx 8rpx;
  border-radius: 4rpx;
  font-size: 26rpx;
}
.md-render :deep(.md-pre) {
  background: rgba(107, 123, 142, 0.12);
  color: inherit;
  padding: 16rpx;
  border-radius: 8rpx;
  overflow-x: auto;
  margin: 12rpx 0;
}
.md-render :deep(.md-pre .md-code) {
  background: transparent;
  color: inherit;
  padding: 0;
}
.md-render :deep(.md-ul) { padding-left: 32rpx; margin: 8rpx 0; }
.md-render :deep(.md-ol) { padding-left: 32rpx; margin: 8rpx 0; }
.md-render :deep(.md-li) { margin: 4rpx 0; }
.md-render :deep(.md-quote) {
  border-left: 4rpx solid currentColor;
  padding-left: 16rpx;
  margin: 12rpx 0;
  color: inherit;
  opacity: 0.85;
  background: rgba(107, 123, 142, 0.06);
}
</style>
