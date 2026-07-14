<template>
  <view class="page">
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

    <scroll-view class="scroll" scroll-y :scroll-top="scrollTop" scroll-with-animation>
      <!-- 宇宙能量入口 Hero -->
      <view class="hero">
        <view class="stars" aria-hidden="true">
          <view class="star star-1"></view>
          <view class="star star-2"></view>
          <view class="star star-3"></view>
          <view class="star star-4"></view>
          <view class="star star-5"></view>
          <view class="star star-6"></view>
          <view class="star star-7"></view>
        </view>

        <view class="energy-rings">
          <view class="ring ring-outer"></view>
          <view class="ring ring-mid"></view>
          <view class="ring ring-inner"></view>
          <view class="ring-core"></view>
        </view>

        <text class="hero-title display-font">塔罗占卜</text>
        <text class="hero-sub">探索命运的维度</text>
        <view class="hero-divider"></view>
      </view>

      <!-- 问题输入 -->
      <view class="section">
        <text class="section-title">你的问题</text>
        <view class="question-wrap">
          <textarea
            class="question-input"
            v-model="question"
            placeholder="输入你的问题，或留空让塔罗为你指引今日运势"
            placeholder-class="q-placeholder"
            :auto-height="true"
            :show-confirm-bar="false"
            maxlength="80"
          />
        </view>
      </view>

      <!-- 牌阵选择 -->
      <view class="section">
        <text class="section-title">选择牌阵</text>
        <scroll-view class="spread-scroll" scroll-x>
          <view class="spread-list">
            <view
              v-for="s in spreads"
              :key="s.key"
              :class="['spread-card', selectedSpread === s.key && 'active']"
              @tap="onSelectSpread(s.key)"
            >
              <view class="spread-icon-wrap">
                <text class="spread-icon">{{ s.icon }}</text>
              </view>
              <text class="spread-name">{{ s.name }}</text>
              <text class="spread-desc">{{ s.desc }}</text>
            </view>
          </view>
        </scroll-view>
      </view>

      <!-- 开始占卜按钮 -->
      <view v-if="!drawn" class="cta-wrap">
        <view :class="['cta-btn', drawing && 'disabled']" @tap="onDivine">
          <text class="cta-text">{{ drawing ? '抽牌中…' : '开始占卜' }}</text>
        </view>
      </view>

      <!-- 占卜结果 -->
      <view v-if="drawn" class="result-card">
        <!-- 牌面展示 -->
        <view class="cards-row">
          <view
            v-for="(c, i) in cards"
            :key="i"
            :class="['drawn-card', c.isReversed && 'is-reversed', c.flipped ? 'flipped' : 'facedown', c.flipping && 'flipping']"
            @tap="onFlipCard(c, i)"
          >
            <view class="card-face">
              <text class="card-emblem">{{ c.emblem }}</text>
              <text class="card-name">{{ c.isReversed ? '逆位' : '正位' }} {{ c.name }}</text>
              <text class="card-name-en">{{ c.nameEn }}</text>
              <text class="card-pos">{{ positions[i] }}</text>
            </view>
            <view class="card-back">
              <view class="card-back-pattern"></view>
              <text class="card-back-emblem">✦</text>
            </view>
          </view>
        </view>

        <!-- 翻牌提示 -->
        <view v-if="!allFlipped" class="flip-hint">
          <text class="flip-hint-text">点击牌背翻开</text>
        </view>

        <!-- 获取 AI 详细解读按钮 -->
        <view v-if="allFlipped && !interpretation && !interpreting" class="cta-wrap">
          <view class="cta-btn cta-interpret" @tap="onInterpret">
            <text class="cta-text">获取详细解读</text>
          </view>
        </view>

        <!-- LLM 流式解读 -->
        <view v-if="interpretation || interpreting" class="meaning-block">
          <text class="meaning-title">塔罗师解读</text>
          <view class="meaning-text">
            <MarkdownRender v-if="interpretation" :content="interpretation" />
            <text v-else-if="interpreting" class="typing">解读中…</text>
          </view>
        </view>

        <!-- 重新占卜 -->
        <view v-if="allFlipped && !interpreting" class="cta-wrap">
          <view class="cta-btn" @tap="resetDivine">
            <text class="cta-text">重新占卜</text>
          </view>
        </view>
      </view>

      <view class="bottom-spacer"></view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
// 塔罗两阶段：draw 抽牌 + interpret AI 流式解读
import { drawTarotCards, interpretTarotWS } from '@/api/chat'

interface DrawnCard {
  name: string
  nameEn: string
  emblem: string
  arcana: string
  suit: string
  isReversed: boolean
  meaning: string
  flipped: boolean
  flipping: boolean
}

const selectedSpread = ref<'daily' | 'three_card' | 'relationship'>('daily')
const question = ref('')
const drawn = ref(false)
const drawing = ref(false)
const interpreting = ref(false)
const cards = ref<DrawnCard[]>([])
const interpretation = ref('')
const scrollTop = ref(0)

const spreads = [
  { key: 'daily' as const, name: '每日一牌', desc: '看今日运势指引', icon: '☀' },
  { key: 'three_card' as const, name: '过去现在未来', desc: '梳理时间脉络', icon: '✦' },
  { key: 'relationship' as const, name: '关系牌阵', desc: '解读人际缘分', icon: '♥' },
]

const positions = computed(() => {
  if (selectedSpread.value === 'three_card') return ['过去', '现在', '未来']
  if (selectedSpread.value === 'relationship') return ['你自己', '对方', '关系']
  return ['今日指引']
})

const allFlipped = computed(() => drawn.value && cards.value.length > 0 && cards.value.every(c => c.flipped))

// 状态栏高度
const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getWindowInfo()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}

function onSelectSpread(key: 'daily' | 'three_card' | 'relationship') {
  if (drawing.value || interpreting.value) return
  selectedSpread.value = key
}

function scrollToBottom() {
  nextTick(() => {
    scrollTop.value = scrollTop.value === 999 ? 998 : 999
  })
}

/** 阶段一：抽牌（不调用 LLM） */
function onDivine() {
  if (drawing.value) return
  drawn.value = true
  drawing.value = true
  cards.value = []
  interpretation.value = ''

  drawTarotCards(selectedSpread.value, {
    onCards: (data: any[]) => {
      cards.value = data.map((c) => ({
        name: c.name,
        nameEn: c.nameEn,
        emblem: c.emblem,
        arcana: c.arcana,
        suit: c.suit,
        isReversed: c.isReversed,
        meaning: c.meaning,
        flipped: false,
        flipping: false,
      }))
      drawing.value = false
      scrollToBottom()
    },
    onError: (err: string) => {
      drawing.value = false
      if (!cards.value.length) {
        uni.showToast({ title: `抽牌失败：${err}`, icon: 'none' })
      }
    },
  })
}

function onFlipCard(c: DrawnCard, _i: number) {
  if (c.flipped || c.flipping) return
  c.flipping = true
  setTimeout(() => {
    c.flipped = true
    c.flipping = false
    scrollToBottom()
  }, 300)
}

/** 阶段二：获取 AI 详细解读（用户点击触发） */
function onInterpret() {
  if (interpreting.value) return
  if (!allFlipped.value) return
  interpreting.value = true
  interpretation.value = ''

  // 回传抽到的牌组
  const payload = cards.value.map((c) => ({
    name: c.name,
    nameEn: c.nameEn,
    emblem: c.emblem,
    arcana: c.arcana,
    suit: c.suit,
    isReversed: c.isReversed,
    meaning: c.meaning,
  }))

  interpretTarotWS(
    {
      spread: selectedSpread.value,
      question: question.value,
      cards: payload,
    },
    {
      onMessage: (chunk: string) => {
        interpretation.value += chunk
        scrollToBottom()
      },
      onDone: () => {
        interpreting.value = false
      },
      onError: (err: string) => {
        interpreting.value = false
        if (!interpretation.value) {
          interpretation.value = `解读暂不可用：${err}`
        }
      },
    }
  )
}

function resetDivine() {
  if (drawing.value || interpreting.value) return
  drawn.value = false
  cards.value = []
  interpretation.value = ''
}
</script>

<style lang="scss">
/* === 塔罗 · 紫金神秘主题 === */
.page {
  height: 100vh;
  background: linear-gradient(180deg, #0d0b1a 0%, #1a1040 30%, #2a1860 60%, #1a1040 100%);
  color: #e8e0f0;
  overflow: hidden;
}

.scroll {
  height: 100vh;
  box-sizing: border-box;
}

/* === Hero === */
.hero {
  position: relative;
  padding: 48rpx 32rpx 32rpx;
  text-align: center;
}

.stars { position: absolute; inset: 0; pointer-events: none; }
.star {
  position: absolute;
  width: 6rpx;
  height: 6rpx;
  background: #f0d060;
  border-radius: 50%;
  box-shadow: 0 0 8rpx #f0d060;
  animation: twinkle 3s infinite ease-in-out;
}
.star-1 { top: 12%; left: 15%; animation-delay: 0s; }
.star-2 { top: 8%; right: 20%; animation-delay: 0.5s; }
.star-3 { top: 30%; left: 8%; animation-delay: 1s; }
.star-4 { top: 22%; right: 12%; animation-delay: 1.5s; }
.star-5 { top: 45%; left: 22%; animation-delay: 2s; width: 4rpx; height: 4rpx; }
.star-6 { top: 38%; right: 30%; animation-delay: 2.5s; width: 4rpx; height: 4rpx; }
.star-7 { top: 55%; left: 50%; animation-delay: 0.3s; }
@keyframes twinkle {
  0%, 100% { opacity: 0.3; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.4); }
}

.energy-rings {
  position: relative;
  width: 240rpx;
  height: 240rpx;
  margin: 0 auto 24rpx;
}
.ring {
  position: absolute;
  border-radius: 50%;
  border: 1rpx solid rgba(240, 208, 96, 0.2);
}
.ring-outer { inset: 0; border-color: rgba(240, 208, 96, 0.15); animation: rotate 20s linear infinite; }
.ring-mid { inset: 30rpx; border-color: rgba(240, 208, 96, 0.25); animation: rotate 15s linear infinite reverse; }
.ring-inner { inset: 60rpx; border-color: rgba(240, 208, 96, 0.35); animation: rotate 10s linear infinite; }
.ring-core {
  position: absolute;
  inset: 90rpx;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(240, 208, 96, 0.4) 0%, transparent 70%);
  animation: pulse 3s ease-in-out infinite;
}
@keyframes rotate { to { transform: rotate(360deg); } }
@keyframes pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

.hero-title {
  position: relative;
  display: block;
  text-align: center;
  font-size: 60rpx;
  font-weight: 600;
  color: #f0d060;
  letter-spacing: 0.12em;
  line-height: 1.25;
  text-shadow: 0 0 32rpx rgba(240, 208, 96, 0.4);
}
.hero-sub {
  display: block;
  margin-top: 12rpx;
  font-size: 24rpx;
  color: rgba(232, 224, 240, 0.6);
  letter-spacing: 0.08em;
}
.hero-divider {
  width: 120rpx;
  height: 2rpx;
  margin: 32rpx auto 0;
  background: linear-gradient(90deg, transparent, rgba(240, 208, 96, 0.4), transparent);
}

/* === Section === */
.section {
  padding: 32rpx 32rpx 0;
}
.section-title {
  display: block;
  font-size: 28rpx;
  color: #f0d060;
  letter-spacing: 0.1em;
  margin-bottom: 20rpx;
}

/* === 问题输入 === */
.question-wrap {
  background: rgba(240, 208, 96, 0.05);
  border: 1rpx solid rgba(240, 208, 96, 0.2);
  border-radius: 20rpx;
  padding: 8rpx 28rpx;
}
.question-input {
  width: 100%;
  min-height: 72rpx;
  max-height: 160rpx;
  padding: 16rpx 0;
  font-size: 28rpx;
  color: #f0e8d8;
  line-height: 1.5;
}
.q-placeholder {
  color: rgba(232, 224, 240, 0.35);
}

/* === 牌阵选择 === */
.spread-scroll {
  width: 100%;
  white-space: nowrap;
}
.spread-list {
  display: inline-flex;
  gap: 20rpx;
  padding: 4rpx;
}
.spread-card {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  width: 220rpx;
  padding: 24rpx 16rpx;
  background: rgba(42, 24, 96, 0.4);
  border: 1rpx solid rgba(240, 208, 96, 0.15);
  border-radius: 20rpx;
  transition: all 0.3s;
}
.spread-card.active {
  background: rgba(240, 208, 96, 0.12);
  border-color: rgba(240, 208, 96, 0.5);
  box-shadow: 0 0 20rpx rgba(240, 208, 96, 0.2);
}
.spread-icon-wrap {
  width: 72rpx;
  height: 72rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12rpx;
}
.spread-icon {
  font-size: 44rpx;
  color: #f0d060;
}
.spread-name {
  font-size: 26rpx;
  color: #f0e8d8;
  margin-bottom: 6rpx;
}
.spread-desc {
  font-size: 20rpx;
  color: rgba(232, 224, 240, 0.5);
  text-align: center;
  white-space: normal;
  line-height: 1.3;
}

/* === CTA 按钮 === */
.cta-wrap {
  padding: 40rpx 32rpx 24rpx;
}
.cta-btn {
  position: relative;
  width: 100%;
  height: 96rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #f0d060 0%, #d4a040 100%);
  border-radius: 48rpx;
  box-shadow: 0 8rpx 32rpx rgba(240, 208, 96, 0.3);
  transition: opacity 0.2s;
}
.cta-btn.disabled {
  opacity: 0.5;
}
/* AI 解读按钮：紫金渐变 */
.cta-btn.cta-interpret {
  background: linear-gradient(135deg, #b886e8 0%, #7c4dff 100%);
  box-shadow: 0 8rpx 32rpx rgba(124, 77, 255, 0.4);
}
.cta-btn.cta-interpret .cta-text {
  color: #fff;
}
.cta-text {
  font-size: 30rpx;
  font-weight: 600;
  color: #1a1040;
  letter-spacing: 0.1em;
}

/* === 占卜结果 === */
.result-card {
  padding: 24rpx 32rpx 0;
}
.cards-row {
  display: flex;
  justify-content: center;
  gap: 20rpx;
  flex-wrap: wrap;
  padding: 16rpx 0 24rpx;
}
.drawn-card {
  position: relative;
  width: 200rpx;
  height: 320rpx;
  border-radius: 20rpx;
  transform-style: preserve-3d;
  transition: transform 0.6s ease;
}
/* 翻牌中：整张牌绕 Y 轴旋转 */
.drawn-card.flipping {
  transform: rotateY(180deg);
}
/* 逆位：把牌面本身再旋转 180° */
.drawn-card.flipped.is-reversed .card-face {
  transform: rotate(180deg);
}

.card-face,
.card-back {
  position: absolute;
  inset: 0;
  border-radius: 20rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20rpx 12rpx;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}
.card-face {
  background: linear-gradient(135deg, #2a1860 0%, #1a1040 100%);
  border: 2rpx solid rgba(240, 208, 96, 0.3);
  box-shadow: 0 8rpx 32rpx rgba(0, 0, 0, 0.4), 0 0 16rpx rgba(240, 208, 96, 0.1);
  transform: rotateY(180deg);
}
.card-back {
  background: linear-gradient(135deg, #1a1040 0%, #0d0b1a 100%);
  border: 2rpx solid rgba(240, 208, 96, 0.2);
}
/* 牌面默认背面朝向用户（rotateY(180deg)），配合父级翻牌旋转 180° 后正向显示 */
.drawn-card.flipped .card-face {
  transform: rotateY(0deg);
}
.drawn-card.flipped .card-back {
  transform: rotateY(180deg);
}
.card-back-pattern {
  position: absolute;
  inset: 12rpx;
  border: 1rpx solid rgba(240, 208, 96, 0.15);
  border-radius: 16rpx;
}
.card-back-emblem {
  font-size: 48rpx;
  color: rgba(240, 208, 96, 0.4);
}
.card-emblem {
  font-size: 56rpx;
  color: #f0d060;
  margin-bottom: 12rpx;
  text-shadow: 0 0 16rpx rgba(240, 208, 96, 0.4);
}
.card-name {
  font-size: 24rpx;
  color: #f0e8d8;
  text-align: center;
  line-height: 1.3;
  margin-bottom: 6rpx;
}
.card-name-en {
  font-size: 18rpx;
  color: rgba(232, 224, 240, 0.5);
  text-align: center;
}
.card-pos {
  margin-top: 10rpx;
  font-size: 20rpx;
  color: rgba(240, 208, 96, 0.6);
  letter-spacing: 0.05em;
}

.flip-hint {
  text-align: center;
  padding: 16rpx 0;
}
.flip-hint-text {
  font-size: 24rpx;
  color: rgba(232, 224, 240, 0.5);
  letter-spacing: 0.1em;
}

/* === 解读区 === */
.meaning-block {
  margin-top: 24rpx;
  padding: 28rpx 24rpx;
  background: rgba(26, 16, 64, 0.6);
  border: 1rpx solid rgba(240, 208, 96, 0.2);
  border-radius: 20rpx;
}
.meaning-title {
  display: block;
  font-size: 28rpx;
  color: #f0d060;
  letter-spacing: 0.08em;
  margin-bottom: 16rpx;
}
.meaning-text {
  font-size: 26rpx;
  line-height: 1.7;
  color: #e8e0f0;
}
.typing {
  color: rgba(240, 208, 96, 0.6);
  font-style: italic;
}

.bottom-spacer {
  height: 80rpx;
}
</style>
