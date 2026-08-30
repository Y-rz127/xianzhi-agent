<template>
  <view class="page" :class="themeClass">
    <view class="meteor meteor-1" v-if="themeClass === 't-dark'"></view>
    <view class="meteor meteor-2" v-if="themeClass === 't-dark'"></view>
    <view class="meteor meteor-3" v-if="themeClass === 't-dark'"></view>
    <view class="nav" @tap="back">‹</view>
    <scroll-view scroll-y class="scroll">
      <view class="hero">
        <text>六爻算卦</text>
        <small class="hero-sub">心诚则灵 · 仅作自省与决策参考</small>
      </view>

      <view class="panel">
        <text class="label">所问何事</text>
        <textarea v-model="question" placeholder="例如：这次工作变动应当如何准备？" auto-height maxlength="100"/>
        <text class="label">起卦方式</text>
        <view class="methods">
          <view v-for="m in methods" :key="m.key" :class="['method', method === m.key && 'active']" @tap="method = m.key">{{ m.name }}</view>
        </view>
        <view v-if="method === 'numbers'" class="nums">
          <input v-model.number="numbers[0]" type="number" placeholder="第一个数字"/>
          <input v-model.number="numbers[1]" type="number" placeholder="第二个数字"/>
        </view>
        <button class="cast" :loading="loading" :disabled="loading || phase === 'revealing'" @tap="doCast">
          {{ method === 'coins' ? '摇动三枚铜钱' : '开始起卦' }}
        </button>

        <!-- 起卦动画：摇卦 → 逐爻揭示 -->
        <view v-if="phase === 'casting'" class="cast-stage">
          <view v-if="method === 'coins'" class="coins shake"><view v-for="n in 3" :key="n" class="coin"/></view>
          <view v-else-if="method === 'numbers'" class="num-orbit">
            <text class="num">{{ numbers[0] === '' || numbers[0] == null ? '—' : numbers[0] }}</text>
            <text class="taiji">☯</text>
            <text class="num">{{ numbers[1] === '' || numbers[1] == null ? '—' : numbers[1] }}</text>
          </view>
          <view v-else class="clock"><view class="clock-hand"/><view class="clock-dot"/></view>
          <text class="cast-tip">{{ method === 'coins' ? '凝神静气，摇卦中…' : method === 'numbers' ? '以心念入卦，推演六爻…' : '感时应物，此刻起卦…' }}</text>
        </view>

        <view v-if="phase === 'revealing'" class="cast-stage">
          <view class="reveal-head">
            <view v-if="method === 'coins'" class="coins settled">
              <view v-for="(face, n) in currentFaces" :key="n" class="coin" :class="{ yang: face }"/>
            </view>
            <text v-else class="reveal-symbol">{{ currentSymbol }}</text>
            <text class="cast-tip">第 {{ revealCount }} 爻 · {{ currentLabel }}</text>
          </view>
          <view class="yao-progress">
            <view v-for="n in 6" :key="n" class="yao-slot" :class="{ filled: n <= revealCount, yang: revealedLines[n - 1] && revealedLines[n - 1].yang }">
              <view class="yao-fill"/>
            </view>
          </view>
        </view>
      </view>

      <view v-if="result && phase === 'done'" class="panel result result-in">
        <view class="hexagram-display">
          <view class="hexagram-col">
            <view class="hexagram-title">
              <small class="ht-label">本卦</small>
              <text>{{ result.original.name }}</text>
              <text class="sub-info">{{ result.original.upper.symbol }} {{ result.original.upper.name }}上 · {{ result.original.lower.symbol }} {{ result.original.lower.name }}下</text>
            </view>
            <view class="yao-stack">
              <view v-for="line in reversedLines" :key="'orig-' + line.index" :class="['yao-item', line.moving && 'moving']">
                <view class="yao-line" :class="{ yang: line.yang }"></view>
                <text class="yao-label">第{{ line.index }}爻</text>
                <text v-if="line.moving" class="moving-tag">动</text>
              </view>
            </view>
          </view>
          <view v-if="result.changed" class="hexagram-col">
            <view class="hexagram-title">
              <small class="ht-label">变卦</small>
              <text>{{ result.changed.name }}</text>
              <text class="sub-info">{{ result.changed.upper.symbol }} {{ result.changed.upper.name }}上 · {{ result.changed.lower.symbol }} {{ result.changed.lower.name }}下</text>
            </view>
            <view class="yao-stack">
              <view v-for="line in getChangedLines()" :key="'changed-' + line.index" class="yao-item">
                <view class="yao-line" :class="{ yang: line.yang }"></view>
                <text class="yao-label">第{{ line.index }}爻</text>
              </view>
            </view>
          </view>
        </view>
        <text class="summary">{{ result.summary }}</text>
        <button class="interpret" :loading="interpreting" @tap="doInterpret">{{ interpretation ? '重新 AI 解读' : 'AI 解读此卦' }}</button>
        <view v-if="interpretation" class="answer">
          <text>卦象解读</text>
          <text>{{ interpretation }}</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue'
import { castLiuYao, interpretLiuYao, type LiuYaoResult } from '@/api'
import { useTheme } from '@/composables/useTheme'


const { themeClass } = useTheme()
const methods = [
  { key: 'coins', name: '铜钱起卦' },
  { key: 'numbers', name: '数字起卦' },
  { key: 'time', name: '时间起卦' },
] as const

const method = ref<typeof methods[number]['key']>('coins')
const question = ref('')
const numbers = ref<number[]>([])
const loading = ref(false)
const interpreting = ref(false)
const result = ref<LiuYaoResult | null>(null)
const interpretation = ref('')
const phase = ref<'idle' | 'casting' | 'revealing' | 'done'>('idle')
const revealCount = ref(0)
let revealTimer: ReturnType<typeof setInterval> | null = null

const reversedLines = computed(() => (result.value ? [...result.value.lines].reverse() : []))
const revealedLines = computed(() => (result.value ? [...result.value.lines].slice(0, revealCount.value) : []))
const currentFaces = computed(() => {
  const value = revealedLines.value.length ? revealedLines.value[revealedLines.value.length - 1].value : 7
  return { 6: [0, 0, 0], 7: [1, 0, 0], 8: [1, 1, 0], 9: [1, 1, 1] }[value] || [0, 0, 0]
})
const currentSymbol = computed(() => {
  const line = revealedLines.value.length ? revealedLines.value[revealedLines.value.length - 1] : null
  return line && line.yang ? '━' : '━ ━'
})
const currentLabel = computed(() => {
  const line = revealedLines.value.length ? revealedLines.value[revealedLines.value.length - 1] : null
  return line ? { 6: '老阴 · 动', 7: '少阳', 8: '少阴', 9: '老阳 · 动' }[line.value] : ''
})

function back() { uni.navigateBack() }

async function doCast() {
  if (method.value === 'numbers' && (!Number.isInteger(numbers.value[0]) || !Number.isInteger(numbers.value[1]))) {
    uni.showToast({ title: '请输入两个整数', icon: 'none' })
    return
  }
  loading.value = true
  result.value = null
  interpretation.value = ''
  phase.value = 'casting'
  try {
    // 摇卦动画固定展示约 1.6s，避免接口过快导致仪式感缺失
    const [data] = await Promise.all([
      castLiuYao(method.value, numbers.value),
      new Promise<void>(resolve => setTimeout(resolve, 1600)),
    ])
    result.value = data
    revealCount.value = 0
    phase.value = 'revealing'
    revealTimer = setInterval(() => {
      revealCount.value += 1
      if (revealCount.value >= 6 && revealTimer) {
        clearInterval(revealTimer)
        revealTimer = null
        setTimeout(() => { phase.value = 'done' }, 650)
      }
    }, 650)
  } catch (e: any) {
    uni.showToast({ title: e.message || '起卦失败', icon: 'none' })
    phase.value = 'idle'
  } finally {
    loading.value = false
  }
}

async function doInterpret() {
  if (!result.value || !question.value.trim()) {
    uni.showToast({ title: '请先填写问题并起卦', icon: 'none' })
    return
  }
  interpreting.value = true
  try {
    interpretation.value = (await interpretLiuYao(question.value, result.value)).interpretation
  } catch (e: any) {
    uni.showToast({ title: e.message || '解读失败', icon: 'none' })
  } finally {
    interpreting.value = false
  }
}

function getChangedLines() {
  if (!result.value?.changed) return []
  return [...result.value.lines].map(line => ({ ...line, yang: line.moving ? !line.yang : line.yang })).reverse()
}

onBeforeUnmount(() => {
  if (revealTimer) clearInterval(revealTimer)
})
</script>

<style lang="scss">
.page { min-height: 100vh; background: linear-gradient(180deg, $nx-bg, $nx-bg-2 55%, $nx-bg-3); color: $nx-text; }
.scroll { height: 100vh; }
.nav { position: fixed; z-index: 2; top: 50rpx; left: 28rpx; font-size: 60rpx; }
.hero { text-align: center; padding: 140rpx 0 64rpx; }
.hero text, .hero .hero-sub { display: block; }
.hero text { font-size: 64rpx; letter-spacing: 14rpx; color: $nx-gold-light; }
.hero .hero-sub { margin-top: 24rpx; color: $nx-text-dim; font-size: 28rpx; }

.panel { margin: 32rpx 36rpx; padding: 40rpx 36rpx; border: 1rpx solid $nx-border; border-radius: 24rpx; background: $nx-card; }
.label { display: block; color: $nx-gold-light; margin: 20rpx 0 16rpx; font-size: 30rpx; font-weight: 600; letter-spacing: 2rpx; }
.panel textarea { width: 100%; box-sizing: border-box; padding: 24rpx; background: $nx-bg-3; color: $nx-text; border: 1rpx solid $nx-border; border-radius: 14rpx; font-size: 29rpx; line-height: 1.7; min-height: 120rpx; }
.methods { display: flex; gap: 18rpx; margin-top: 8rpx; }
.method { flex: 1; text-align: center; padding: 24rpx 12rpx; border: 1rpx solid $nx-border; border-radius: 14rpx; color: $nx-text-dim; font-size: 29rpx; transition: all .25s; }
.method.active { background: rgba(202, 169, 93, .15); color: $nx-gold-light; border-color: $nx-accent-liuyao; }
.nums { display: flex; gap: 28rpx; margin-top: 32rpx; }
.nums input { flex: 1; min-width: 0; box-sizing: border-box; padding: 32rpx 28rpx; height: 120rpx; background: $nx-bg-3; color: $nx-text; border: 1rpx solid $nx-border; border-radius: 18rpx; font-size: 34rpx; line-height: 1.6; }
.cast, .interpret { margin-top: 40rpx; padding: 28rpx; background: linear-gradient(135deg, #b58b35, #e7bd67); color: #271b08; font-size: 32rpx; font-weight: 600; border-radius: 16rpx; letter-spacing: 4rpx; }
.cast[disabled] { opacity: .6; }

/* ===== 起卦动画 ===== */
.cast-stage { margin-top: 40rpx; padding-top: 34rpx; border-top: 1rpx solid $nx-border; min-height: 220rpx; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 30rpx; }
.cast-tip { color: $nx-text-dim; font-size: 26rpx; letter-spacing: 4rpx; }

/* 铜钱 */
.coins { display: flex; gap: 30rpx; align-items: center; justify-content: center; height: 110rpx; }
.coin {
  width: 92rpx; height: 92rpx; border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #f3d488, #b4862f 60%, #7c5a1c);
  box-shadow: inset 0 0 0 8rpx rgba(120, 84, 24, .5), 0 8rpx 20rpx rgba(0, 0, 0, .45);
  position: relative;
}
.coin::before, .coin::after { content: ""; position: absolute; background: rgba(70, 46, 10, .85); }
.coin::before { width: 100%; height: 18rpx; top: 50%; left: 0; transform: translateY(-50%); }
.coin::after { width: 18rpx; height: 100%; left: 50%; top: 0; transform: translateX(-50%); }
.coin.yang::before, .coin.yang::after { background: rgba(250, 226, 160, .9); }
.coins.shake { animation: coinShake .7s ease-in-out infinite; }
@keyframes coinShake {
  0%, 100% { transform: translateX(0) rotate(0deg); }
  25% { transform: translateX(-20rpx) rotate(-18deg); }
  75% { transform: translateX(20rpx) rotate(18deg); }
}
.coins.settled .coin { animation: coinSettle .5s ease both; }
.coins.settled .coin:nth-child(2) { animation-delay: .12s; }
.coins.settled .coin:nth-child(3) { animation-delay: .24s; }
@keyframes coinSettle {
  0% { transform: translateY(-70rpx) rotate(540deg); opacity: 0; }
  100% { transform: translateY(0) rotate(0); opacity: 1; }
}

/* 数字起卦 */
.num-orbit { display: flex; align-items: center; gap: 40rpx; font-size: 56rpx; }
.num { min-width: 100rpx; padding: 14rpx 8rpx; border: 1rpx solid #caa95d; border-radius: 14rpx; background: rgba(202, 169, 93, .12); color: #f1d894; text-align: center; animation: numFloat 1.1s ease-in-out infinite; }
.num:first-child { animation-delay: .15s; }
.taiji { font-size: 70rpx; animation: spin 3s linear infinite; }
@keyframes numFloat { 50% { transform: translateY(-18rpx); } }
@keyframes spin { to { transform: rotate(360deg); } }

/* 时间起卦：罗盘 */
.clock {
  width: 140rpx; height: 140rpx; border-radius: 50%;
  border: 5rpx solid #caa95d; position: relative;
  background: radial-gradient(circle, #241b0d, #171221 72%);
  box-shadow: 0 0 30rpx rgba(202, 169, 93, .3);
}
.clock::before { content: ""; position: absolute; inset: 8rpx; border-radius: 50%; border: 2rpx dashed rgba(202, 169, 93, .4); }
.clock-hand { position: absolute; left: 50%; top: 50%; width: 5rpx; height: 48rpx; margin: -48rpx 0 0 -2.5rpx; background: #e5c27c; transform-origin: bottom center; animation: clockSpin 2s linear infinite; }
.clock-dot { position: absolute; left: 50%; top: 50%; width: 12rpx; height: 12rpx; margin: -6rpx; border-radius: 50%; background: #e5c27c; }
@keyframes clockSpin { to { transform: rotate(360deg); } }

/* 逐爻揭示 */
.reveal-head { display: flex; flex-direction: column; align-items: center; gap: 20rpx; }
.reveal-symbol { font-size: 60rpx; color: #f1d894; animation: numFloat 1s ease-in-out infinite; }
.yao-progress { display: flex; flex-direction: column-reverse; gap: 10rpx; align-items: center; margin-top: 10rpx; }
.yao-slot { width: 240rpx; height: 12rpx; border-radius: 6rpx; background: rgba(255, 255, 255, .06); }
.yao-slot .yao-fill { width: 0; height: 100%; border-radius: 6rpx; background: #d4b26b; transition: width .45s ease; }
.yao-slot.filled { background: rgba(212, 178, 107, .2); }
.yao-slot.filled .yao-fill { width: 100%; }
.yao-slot.filled.yang .yao-fill { background: linear-gradient(90deg, #d4b26b, #f1d894); }

/* 成卦定格 */
.result-in { animation: resultIn .6s ease both; }
@keyframes resultIn {
  0% { opacity: 0; transform: translateY(20rpx); }
  100% { opacity: 1; transform: translateY(0); }
}

.result { margin-bottom: 100rpx; }
.hexagram-display { display: flex; justify-content: center; gap: 48rpx; margin: 40rpx 0; padding: 28rpx; background: rgba(255, 255, 255, .02); border-radius: 20rpx; border: 1rpx solid $nx-border; }
.hexagram-col { flex: 1; max-width: 320rpx; text-align: center; }
.hexagram-title .ht-label, .hexagram-title text { display: block; }
.hexagram-title .ht-label { font-size: 22rpx; color: $nx-text-dim; margin-bottom: 10rpx; letter-spacing: 2rpx; }
.hexagram-title text:first-of-type { font-size: 38rpx; color: $nx-gold-light; margin: 8rpx 0; font-weight: 700; letter-spacing: 4rpx; }
.sub-info { font-size: 23rpx; color: $nx-text-muted; margin-top: 6rpx; line-height: 1.5; }
.yao-stack { margin-top: 24rpx; display: flex; flex-direction: column-reverse; gap: 14rpx; }
.yao-item { display: flex; align-items: center; gap: 16rpx; height: 52rpx; position: relative; }
.yao-line { width: 100%; height: 12rpx; border-radius: 6rpx; background: linear-gradient(90deg, #dcc077 0 42%, transparent 42% 58%, #dcc077 58%); transition: all .3s; }
.yao-line.yang { background: linear-gradient(90deg, #f0cf7b, #e7bd67); box-shadow: 0 2rpx 12rpx rgba(240, 207, 123, .4); }
.yao-item.moving .yao-line { animation: yaoGlow 2s ease-in-out infinite; }
@keyframes yaoGlow { 0%, 100% { box-shadow: 0 0 8rpx #f3d075; } 50% { box-shadow: 0 0 24rpx #f3d075, 0 0 40rpx rgba(243, 208, 117, .4); } }
.yao-label { width: 80rpx; color: $nx-text-dim; font-size: 24rpx; flex-shrink: 0; }
.moving-tag { position: absolute; right: -60rpx; color: #f0ce75; font-size: 24rpx; font-weight: 700; background: rgba(240, 206, 117, .15); padding: 4rpx 14rpx; border-radius: 8rpx; border: 1rpx solid rgba(240, 206, 117, .3); }
.summary { display: block; text-align: center; line-height: 1.9; color: $nx-text-dim; margin: 36rpx 0; font-size: 29rpx; padding: 0 8rpx; }
.answer { margin-top: 32rpx; padding: 32rpx; background: rgba(255, 255, 255, .04); border: 1rpx solid $nx-border; border-radius: 16rpx; }
.answer text { display: block; line-height: 2; font-size: 29rpx; color: $nx-text; }
.answer text:first-child { color: $nx-gold-light; margin-bottom: 16rpx; font-size: 32rpx; font-weight: 600; letter-spacing: 2rpx; }
</style>
