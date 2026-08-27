<template>
  <view class="page">
    <!-- 背景 -->
    <view class="stars"></view>

    <!-- 顶部导航 -->
    <view class="nav" :style="{ paddingTop: statusBarHeight + 'px' }">
      <view class="nav-back" @tap="goBack">
        <text class="nav-back-icon">‹</text>
      </view>
      <text class="nav-title">六爻问卦</text>
      <view class="nav-placeholder"></view>
    </view>

    <scroll-view class="scroll" scroll-y :scroll-top="scrollTop" :style="{ top: statusBarHeight + 44 + 'px' }">
      <view class="container">
        <!-- 问题输入 -->
        <view class="question-card">
          <text class="section-title">所占问题</text>
          <textarea
            class="question-input"
            v-model="question"
            placeholder="心中默念想问的事，越具体越好..."
            placeholder-class="question-placeholder"
            :maxlength="200"
          />
          <text class="question-tip">例如：「这份工作是否适合我？」「这段感情能否继续？」</text>
        </view>

        <!-- 起卦方式 -->
        <view class="method-card">
          <text class="section-title">起卦方式</text>
          <view class="method-list">
            <view
              class="method-item"
              :class="{ active: method === 'coin' }"
              @tap="method = 'coin'"
            >
              <text class="method-name">铜钱摇卦</text>
              <text class="method-desc">随机模拟铜钱结果</text>
            </view>
            <view
              class="method-item"
              :class="{ active: method === 'number' }"
              @tap="method = 'number'"
            >
              <text class="method-name">数字起卦</text>
              <text class="method-desc">输入两个自然数</text>
            </view>
            <view
              class="method-item"
              :class="{ active: method === 'time' }"
              @tap="method = 'time'"
            >
              <text class="method-name">时间起卦</text>
              <text class="method-desc">以当前时间起卦</text>
            </view>
          </view>

          <!-- 数字起卦输入 -->
          <view v-if="method === 'number'" class="number-inputs">
            <input
              class="num-input"
              type="number"
              v-model="numA"
              placeholder="第一个数"
            />
            <input
              class="num-input"
              type="number"
              v-model="numB"
              placeholder="第二个数"
            />
          </view>
        </view>

        <!-- 起卦按钮 -->
        <view class="action-area">
          <button
            class="cast-btn"
            :disabled="casting || (method === 'number' && (!numA || !numB))"
            @tap="onCast"
          >
            <text class="cast-btn-text">{{ casting ? '起卦中...' : '开始起卦' }}</text>
          </button>
        </view>

        <!-- 卦象结果 -->
        <view v-if="result" class="result-card">
          <text class="section-title">本卦 · {{ result.primary_gua }}</text>
          <view class="gua-box">
            <view class="gua-line" v-for="(line, idx) in result.lines" :key="idx">
              <text class="line-symbol">{{ renderLine(line, result.line_kinds[idx]) }}</text>
              <text class="line-label">{{ result.line_kinds[idx] }}</text>
            </view>
          </view>
          <view class="result-info">
            <text class="info-item">下卦：{{ result.lower_trigram }}</text>
            <text class="info-item">上卦：{{ result.upper_trigram }}</text>
            <text class="info-item">变卦：{{ result.changed_gua }}</text>
            <text class="info-item" v-if="result.changing_yao_names.length">
              动爻：{{ result.changing_yao_names.join('、') }}
            </text>
          </view>

          <view class="interpret-title">AI 解读</view>
          <view class="interpret-body">
            <text class="interpret-text">{{ interpretation || '正在生成解读...' }}</text>
          </view>
        </view>

        <!-- 重新起卦 -->
        <view v-if="result && !casting" class="action-area">
          <button class="reset-btn" @tap="reset">重新起卦</button>
        </view>

        <view class="footer-space"></view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { liuyaoDivine } from '@/api/index'

const statusBarHeight = ref(20)
const scrollTop = ref(0)

const question = ref('')
const method = ref<'coin' | 'number' | 'time'>('coin')
const numA = ref('')
const numB = ref('')
const casting = ref(false)
const result = ref<any>(null)
const interpretation = ref('')

const lineSymbols: Record<string, Record<string, string>> = {
  yang: { normal: '━━━━━━━', changing: '━━━━━━━ ○' },
  yin: { normal: '━ ━ ━ ━', changing: '━ ━ ━ ━ ×' },
}

onLoad(() => {
  const sys = uni.getSystemInfoSync()
  statusBarHeight.value = sys.statusBarHeight || 20
})

function goBack() {
  const pages = getCurrentPages()
  if (pages.length > 1) uni.navigateBack()
  else uni.reLaunch({ url: '/pages/xianzhi/index' })
}

function renderLine(value: number, kind: string) {
  if (value % 2 === 1) return lineSymbols.yang[kind === '少阴' || kind === '少阳' ? 'normal' : 'changing'] || lineSymbols.yang.normal
  return lineSymbols.yin[kind === '少阴' || kind === '少阳' ? 'normal' : 'changing'] || lineSymbols.yin.normal
}

function scrollToBottom() {
  nextTick(() => {
    scrollTop.value = scrollTop.value === 999 ? 998 : 999
  })
}

async function onCast() {
  if (casting.value) return
  if (!question.value.trim()) {
    uni.showToast({ title: '请先输入所占问题', icon: 'none' })
    return
  }

  casting.value = true
  result.value = null
  interpretation.value = ''

  const payload: any = {
    method: method.value,
    question: question.value.trim(),
  }

  if (method.value === 'number') {
    const a = parseInt(numA.value, 10)
    const b = parseInt(numB.value, 10)
    if (isNaN(a) || isNaN(b) || a <= 0 || b <= 0) {
      uni.showToast({ title: '请输入两个自然数', icon: 'none' })
      casting.value = false
      return
    }
    payload.numbers = [a, b]
  }

  try {
    const res = await liuyaoDivine(payload)
    if (!res.success || !res.data) {
      uni.showToast({ title: res.error || '起卦失败', icon: 'none' })
      casting.value = false
      return
    }
    result.value = res.data.result
    interpretation.value = res.data.interpretation || ''
    scrollToBottom()
  } catch (err: any) {
    uni.showToast({ title: err.message || '起卦失败', icon: 'none' })
  } finally {
    casting.value = false
  }
}

function reset() {
  result.value = null
  interpretation.value = ''
  casting.value = false
}
</script>

<style lang="scss">
.page {
  height: 100vh;
  background: linear-gradient(180deg, #0d0b1a 0%, #1a1040 30%, #2a1860 60%, #1a1040 100%);
  color: #e8e0f0;
  overflow: hidden;
}

.stars {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  background-image:
    radial-gradient(circle at 20% 30%, rgba(255,255,255,0.08) 1px, transparent 1px),
    radial-gradient(circle at 70% 20%, rgba(255,255,255,0.06) 1px, transparent 1px),
    radial-gradient(circle at 50% 80%, rgba(255,255,255,0.05) 1px, transparent 1px);
}

.nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  z-index: 100;
  background: rgba(13, 11, 26, 0.6);
  backdrop-filter: blur(8px);
}

.nav-back {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.nav-back-icon {
  font-size: 28px;
  color: #e8d5a3;
}

.nav-title {
  font-size: 18px;
  font-weight: 600;
  color: #e8d5a3;
}

.nav-placeholder {
  width: 32px;
}

.scroll {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
}

.container {
  padding: 16px;
}

.question-card,
.method-card,
.result-card {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(232, 213, 163, 0.15);
  border-radius: 16px;
  padding: 16px;
  margin-bottom: 16px;
}

.section-title {
  display: block;
  font-size: 16px;
  font-weight: 600;
  color: #e8d5a3;
  margin-bottom: 12px;
}

.question-input {
  width: 100%;
  min-height: 90px;
  background: rgba(0, 0, 0, 0.18);
  border: 1px solid rgba(232, 213, 163, 0.2);
  border-radius: 12px;
  padding: 12px;
  color: #f5f0ff;
  font-size: 15px;
  line-height: 1.5;
  box-sizing: border-box;
}

.question-placeholder {
  color: rgba(232, 213, 163, 0.45);
}

.question-tip {
  display: block;
  font-size: 12px;
  color: rgba(232, 213, 163, 0.55);
  margin-top: 8px;
}

.method-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.method-item {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.16);
  border: 1px solid rgba(232, 213, 163, 0.12);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.method-item.active {
  border-color: #e8d5a3;
  background: rgba(232, 213, 163, 0.12);
}

.method-name {
  font-size: 15px;
  font-weight: 600;
  color: #f5f0ff;
}

.method-desc {
  font-size: 12px;
  color: rgba(245, 240, 255, 0.65);
}

.number-inputs {
  display: flex;
  gap: 12px;
  margin-top: 12px;
}

.num-input {
  flex: 1;
  background: rgba(0, 0, 0, 0.18);
  border: 1px solid rgba(232, 213, 163, 0.2);
  border-radius: 10px;
  padding: 12px;
  color: #f5f0ff;
  font-size: 14px;
  text-align: center;
}

.action-area {
  margin: 8px 0 16px;
}

.cast-btn,
.reset-btn {
  width: 100%;
  height: 48px;
  border-radius: 24px;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cast-btn {
  background: linear-gradient(90deg, #d4af37 0%, #f3cf55 100%);
  color: #1a1040;
}

.cast-btn[disabled] {
  opacity: 0.6;
}

.cast-btn-text {
  font-size: 16px;
  font-weight: 600;
}

.reset-btn {
  background: rgba(255, 255, 255, 0.1);
  color: #e8d5a3;
  border: 1px solid rgba(232, 213, 163, 0.25);
}

.result-card {
  background: rgba(232, 213, 163, 0.08);
  border-color: rgba(232, 213, 163, 0.25);
}

.gua-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  margin: 12px 0;
}

.gua-line {
  display: flex;
  align-items: center;
  gap: 12px;
}

.line-symbol {
  font-size: 18px;
  color: #f5f0ff;
  letter-spacing: 1px;
  font-family: monospace;
}

.line-label {
  font-size: 12px;
  color: rgba(245, 240, 255, 0.7);
  min-width: 40px;
}

.result-info {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.info-item {
  background: rgba(0, 0, 0, 0.18);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 13px;
  color: rgba(245, 240, 255, 0.9);
}

.interpret-title {
  font-size: 15px;
  font-weight: 600;
  color: #e8d5a3;
  margin: 16px 0 8px;
}

.interpret-body {
  background: rgba(0, 0, 0, 0.18);
  border-radius: 12px;
  padding: 12px;
}

.interpret-text {
  font-size: 14px;
  color: rgba(245, 240, 255, 0.92);
  line-height: 1.7;
  white-space: pre-wrap;
}

.footer-space {
  height: 30px;
}
</style>
