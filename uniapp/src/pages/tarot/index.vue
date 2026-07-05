<template>
  <view class="page">
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

    <scroll-view class="scroll" scroll-y>
      <!-- 宇宙能量入口 Hero -->
      <view class="hero">
        <!-- 星点装饰 -->
        <view class="stars" aria-hidden="true">
          <view class="star star-1"></view>
          <view class="star star-2"></view>
          <view class="star star-3"></view>
          <view class="star star-4"></view>
          <view class="star star-5"></view>
          <view class="star star-6"></view>
          <view class="star star-7"></view>
        </view>

        <!-- 三色能量环 -->
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

      <!-- 牌阵扇形展示 -->
      <view class="cards-fan">
        <view class="fan-card fan-left">
          <view class="card-corner corner-tl"></view>
          <view class="card-corner corner-tr"></view>
          <view class="card-corner corner-bl"></view>
          <view class="card-corner corner-br"></view>
          <view class="hex-mark">
            <view class="tri-up"></view>
            <view class="tri-down"></view>
            <view class="hex-ring"></view>
            <view class="hex-dot"></view>
          </view>
        </view>
        <view class="fan-card fan-center">
          <view class="card-corner corner-tl"></view>
          <view class="card-corner corner-tr"></view>
          <view class="card-corner corner-bl"></view>
          <view class="card-corner corner-br"></view>
          <view class="hex-mark hex-mark-large">
            <view class="tri-up"></view>
            <view class="tri-down"></view>
            <view class="hex-ring"></view>
            <view class="hex-ring-2"></view>
            <view class="hex-dot"></view>
            <view class="hex-cross-h"></view>
            <view class="hex-cross-v"></view>
          </view>
          <view class="center-orb-top"></view>
          <view class="center-orb-bottom"></view>
        </view>
        <view class="fan-card fan-right">
          <view class="card-corner corner-tl"></view>
          <view class="card-corner corner-tr"></view>
          <view class="card-corner corner-bl"></view>
          <view class="card-corner corner-br"></view>
          <view class="hex-mark">
            <view class="tri-up"></view>
            <view class="tri-down"></view>
            <view class="hex-ring"></view>
            <view class="hex-dot"></view>
          </view>
        </view>
      </view>

      <!-- 牌阵选择 -->
      <view class="section">
        <text class="section-title">选择牌阵</text>
        <scroll-view class="spread-scroll" scroll-x>
          <view class="spread-list">
            <view
              v-for="s in spreads"
              :key="s.name"
              :class="['spread-card', selectedSpread === s.key && 'active']"
              @tap="selectedSpread = s.key"
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
        <view class="cta-btn" @tap="onDivine">
          <text class="cta-text">开始占卜</text>
        </view>
      </view>

      <!-- 占卜结果 -->
      <view v-if="drawn" class="result-card">
        <view class="drawn-card" :class="{ reversed: card.isReversed }">
          <view class="card-face">
            <text class="card-emblem">{{ card.emblem }}</text>
            <text class="card-name">{{ card.isReversed ? '逆位' : '正位' }} {{ card.name }}</text>
            <text class="card-name-en">{{ card.nameEn }}</text>
          </view>
        </view>
        <view class="meaning-block">
          <text class="meaning-title">牌意解读</text>
          <text class="meaning-text">{{ meaning }}</text>
        </view>
        <view class="meaning-block">
          <text class="meaning-title">今日建议</text>
          <text class="meaning-text">{{ advice }}</text>
        </view>
        <view class="cta-wrap">
          <view class="cta-btn" @tap="resetDivine">
            <text class="cta-text">重新抽取</text>
          </view>
        </view>
      </view>

      <view class="bottom-spacer"></view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface TarotCard {
  name: string
  nameEn: string
  emblem: string
  meaning: string
  reversedMeaning: string
  advice: string
}

const selectedSpread = ref('love')

const spreads = [
  { key: 'love', name: '爱情占卜', desc: '解读情感缘分', icon: '♥' },
  { key: 'career', name: '事业指引', desc: '探索职场方向', icon: '✦' },
  { key: 'daily', name: '每日一牌', desc: '每日运势指引', icon: '☀' },
]

const majorArcana: TarotCard[] = [
  { name: '愚者', nameEn: 'The Fool', emblem: '☆', meaning: '新的开始、冒险、天真无邪。是时候勇敢迈出第一步，相信宇宙的指引。', reversedMeaning: '鲁莽、犹豫不决。你需要停下来重新审视当前的处境，不要盲目行动。', advice: '保持开放的心态，敢于尝试新事物。今天适合开启新计划。' },
  { name: '魔术师', nameEn: 'The Magician', emblem: '✦', meaning: '创造力、技能、意志力。你拥有实现目标所需的一切资源，现在是行动的时候。', reversedMeaning: '欺骗、能力不足。你可能在浪费自己的才华，或被表象迷惑。', advice: '今天你的创造力和沟通能力很强，善用它们解决难题。' },
  { name: '女祭司', nameEn: 'The High Priestess', emblem: '☽', meaning: '直觉、潜意识、神秘。静下心来倾听内心的声音，答案就在你心中。', reversedMeaning: '忽视直觉、情绪封闭。你与内心的连接被切断，需要重新建立信任。', advice: '相信你的直觉，不必急于做决定。今天适合静心冥想。' },
  { name: '女皇', nameEn: 'The Empress', emblem: '♔', meaning: '丰饶、母性、感官享受。创造力与滋养的能量充沛，享受生活的美好。', reversedMeaning: '依赖、停滞。过度依赖他人或物质享受，忽视了内在成长。', advice: '今天适合关注家庭和自我滋养，享受生活中的小确幸。' },
  { name: '皇帝', nameEn: 'The Emperor', emblem: '⚔', meaning: '权威、秩序、掌控。建立规则和结构，用理性与纪律引导自己。', reversedMeaning: '专制、失控。你可能过于强势，或缺乏自律导致混乱。', advice: '今天需要建立秩序，制定计划，以理性和纪律行事。' },
  { name: '教皇', nameEn: 'The Hierophant', emblem: '✠', meaning: '传统、导师、精神指引。遵循传统智慧，寻求导师或制度的帮助。', reversedMeaning: '叛逆、盲目追随。你可能被困在陈规中，或盲目追随权威。', advice: '今天适合学习传统知识，或向有经验的人请教。' },
  { name: '恋人', nameEn: 'The Lovers', emblem: '♥', meaning: '爱情、选择、和谐。面临重要抉择，跟随内心做出真诚的决定。', reversedMeaning: '分离、错误选择。关系中可能出现裂痕，需要真诚沟通。', advice: '今天适合处理感情关系，做决定时听从内心的声音。' },
  { name: '战车', nameEn: 'The Chariot', emblem: '⚡', meaning: '胜利、意志力、前进。克服困难，通过坚定的意志力取得胜利。', reversedMeaning: '失控、失败。你可能失去了方向，需要重新掌控局面。', advice: '今天充满动力和决心，适合推进拖延已久的事情。' },
  { name: '力量', nameEn: 'Strength', emblem: '♌', meaning: '勇气、耐心、内在力量。以柔克刚，用爱与耐心驯服内心的野兽。', reversedMeaning: '软弱、恐惧。你被恐惧支配，需要找回内在的力量。', advice: '今天需要耐心和勇气，相信自己的内在力量能克服挑战。' },
  { name: '隐士', nameEn: 'The Hermit', emblem: '✶', meaning: '内省、孤独、智慧。退一步反思，寻找内心的光明与真理。', reversedMeaning: '孤立、逃避。过度的孤独变成了逃避，需要重新连接外界。', advice: '今天适合独处和反思，给自己一些安静的时间。' },
  { name: '命运之轮', nameEn: 'Wheel of Fortune', emblem: '☸', meaning: '命运、转折、机遇。命运的齿轮转动，好运即将到来，抓住机会。', reversedMeaning: '厄运、停滞。你可能处于低谷，但变化是必然的，保持信念。', advice: '今天可能会遇到意外的转机，保持开放和灵活。' },
  { name: '正义', nameEn: 'Justice', emblem: '⚖', meaning: '公正、真相、因果。种瓜得瓜，真理必将显现，做出公正的决定。', reversedMeaning: '不公、逃避责任。你可能在逃避应承担的责任或真相。', advice: '今天适合做出公正的决定，诚实面对自己和他人。' },
  { name: '倒吊人', nameEn: 'The Hanged Man', emblem: '〰', meaning: '牺牲、换个视角、等待。暂停行动，换个角度看问题，会有新的领悟。', reversedMeaning: '固执、无谓牺牲。你不愿改变视角，导致停滞不前。', advice: '今天适合换个角度看问题，有时退一步海阔天空。' },
  { name: '死神', nameEn: 'Death', emblem: '☠', meaning: '结束、转变、重生。旧的不去新的不来，接受改变，迎接新生。', reversedMeaning: '抗拒改变、停滞。你拒绝放手，导致无法获得新的成长。', advice: '今天适合放下过去，迎接新的开始。改变是成长的必经之路。' },
  { name: '节制', nameEn: 'Temperance', emblem: '≈', meaning: '平衡、调和、耐心。寻找中庸之道，调和内在的矛盾，保持平衡。', reversedMeaning: '失衡、过度。你可能在某个方面走极端，需要回归平衡。', advice: '今天需要保持中庸，避免走极端，寻找生活的平衡点。' },
  { name: '恶魔', nameEn: 'The Devil', emblem: '♄', meaning: '束缚、欲望、阴影。直面内心的欲望和恐惧，认识自己的阴暗面。', reversedMeaning: '解脱、觉醒。你正在摆脱束缚，看清真相，获得自由。', advice: '今天适合审视自己的欲望和执念，觉察哪些在束缚你。' },
  { name: '高塔', nameEn: 'The Tower', emblem: '▲', meaning: '突变、崩塌、觉醒。突如其来的改变打破旧有结构，虽然痛苦但是必要的。', reversedMeaning: '抗拒改变、危机延迟。你在逃避不可避免的改变，但终究要面对。', advice: '今天可能有意外的冲击，但这是重建的契机，坦然接受。' },
  { name: '星星', nameEn: 'The Star', emblem: '★', meaning: '希望、灵感、治愈。黑暗中看到了光芒，保持信念，未来充满希望。', reversedMeaning: '绝望、失去信心。你可能感到迷茫，但希望从未真正离开。', advice: '今天充满希望和灵感，相信自己的梦想，保持乐观。' },
  { name: '月亮', nameEn: 'The Moon', emblem: '☾', meaning: '幻觉、恐惧、潜意识。面对内心的恐惧，穿越迷雾方能看清真相。', reversedMeaning: '恐惧消散、真相显现。迷雾正在散去，真相即将揭晓。', advice: '今天可能会有困惑和不安，但不要被表象迷惑，耐心等待。' },
  { name: '太阳', nameEn: 'The Sun', emblem: '☀', meaning: '快乐、成功、活力。阳光普照，一切顺利，享受生命的美好时刻。', reversedMeaning: '暂时的阴霾、热情减退。快乐被暂时遮蔽，但太阳终会再次升起。', advice: '今天是充满能量和快乐的一天，尽情享受，分享你的光芒。' },
  { name: '审判', nameEn: 'Judgement', emblem: '♫', meaning: '觉醒、重生、召唤。听到内心的召唤，做出改变，迎接新生。', reversedMeaning: '拒绝觉醒、自我怀疑。你忽视了内心的召唤，需要重新审视。', advice: '今天适合反思过去，做出重要的决定，迎接新的阶段。' },
  { name: '世界', nameEn: 'The World', emblem: '⬡', meaning: '完成、圆满、成就。一个周期的圆满结束，你已经达成了目标。', reversedMeaning: '未完成、拖延。你接近完成但尚未达成，需要最后一步努力。', advice: '今天是一个圆满的日子，庆祝你的成就，准备迎接新的旅程。' },
]

const drawn = ref(false)
const card = ref<TarotCard & { isReversed: boolean }>({} as any)

const meaning = computed(() => {
  if (!card.value.name) return ''
  let base = card.value.isReversed ? card.value.reversedMeaning : card.value.meaning
  if (selectedSpread.value === 'love') {
    base = base.replace(/目标|计划|工作/g, '感情')
  } else if (selectedSpread.value === 'career') {
    base = base.replace(/感情|关系|家庭/g, '事业')
  }
  return base
})

const advice = computed(() => {
  if (!card.value.name) return ''
  return card.value.advice
})

// 状态栏高度
const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getSystemInfoSync()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}

function drawCard() {
  const idx = Math.floor(Math.random() * majorArcana.length)
  const isReversed = Math.random() > 0.5
  card.value = { ...majorArcana[idx], isReversed }
}

function onDivine() {
  drawCard()
  drawn.value = true
}

function resetDivine() {
  drawn.value = false
  card.value = {} as any
}
</script>

<style lang="scss">
.page {
  height: 100vh;
  background: linear-gradient(180deg, #160F2E 0%, #0F0B1E 100%);
  color: #E2E8F0;
}
.scroll { height: 100vh; }
.status-bar { width: 100%; }

/* === Hero 宇宙能量入口 === */
.hero {
  position: relative;
  padding: 56rpx 40rpx 80rpx;
  background: radial-gradient(ellipse at 50% 40%,
    rgba(124, 58, 237, 0.25) 0%,
    rgba(6, 182, 212, 0.12) 40%,
    rgba(245, 158, 11, 0.06) 70%,
    #0F0B1E 100%);
  overflow: hidden;
}

/* 星点装饰 */
.stars {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.star {
  position: absolute;
  border-radius: 50%;
}
.star-1 {
  top: 10%; left: 12%;
  width: 6rpx; height: 6rpx;
  background: #A78BFA;
  box-shadow: 0 0 16rpx 4rpx rgba(124, 58, 237, 0.5);
}
.star-2 {
  top: 18%; right: 14%;
  width: 4rpx; height: 4rpx;
  background: #67E8F9;
  box-shadow: 0 0 20rpx 6rpx rgba(6, 182, 212, 0.5);
}
.star-3 {
  top: 38%; left: 18%;
  width: 4rpx; height: 4rpx;
  background: #FDE68A;
  box-shadow: 0 0 12rpx 4rpx rgba(245, 158, 11, 0.5);
}
.star-4 {
  top: 52%; right: 8%;
  width: 4rpx; height: 4rpx;
  background: #A78BFA;
  box-shadow: 0 0 14rpx 4rpx rgba(124, 58, 237, 0.4);
}
.star-5 {
  top: 75%; left: 55%;
  width: 4rpx; height: 4rpx;
  background: #22D3EE;
  box-shadow: 0 0 12rpx 2rpx rgba(6, 182, 212, 0.5);
}
.star-6 {
  top: 8%; left: 48%;
  width: 2rpx; height: 2rpx;
  background: #F59E0B;
  box-shadow: 0 0 8rpx 2rpx rgba(245, 158, 11, 0.4);
}
.star-7 {
  top: 28%; left: 70%;
  width: 2rpx; height: 2rpx;
  background: #22D3EE;
  box-shadow: 0 0 8rpx 2rpx rgba(6, 182, 212, 0.3);
}

/* 三色能量环 */
.energy-rings {
  position: relative;
  width: 240rpx;
  height: 240rpx;
  margin: 0 auto 32rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ring {
  position: absolute;
  border-radius: 50%;
  border: 2rpx solid;
}
.ring-outer {
  width: 240rpx;
  height: 240rpx;
  border-color: rgba(124, 58, 237, 0.2);
}
.ring-mid {
  width: 192rpx;
  height: 192rpx;
  border-color: rgba(6, 182, 212, 0.25);
}
.ring-inner {
  width: 144rpx;
  height: 144rpx;
  border-color: rgba(245, 158, 11, 0.2);
}
.ring-core {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  background: rgba(124, 58, 237, 0.6);
  box-shadow: 0 0 24rpx 8rpx rgba(124, 58, 237, 0.3);
}

.hero-title {
  position: relative;
  display: block;
  text-align: center;
  font-size: 60rpx;
  font-weight: 600;
  color: #F59E0B;
  text-shadow: 0 0 48rpx rgba(245, 158, 11, 0.4), 0 0 96rpx rgba(245, 158, 11, 0.15);
  letter-spacing: 0.08em;
  line-height: 1.25;
}
.hero-sub {
  position: relative;
  display: block;
  text-align: center;
  margin-top: 24rpx;
  font-size: 30rpx;
  color: #22D3EE;
  letter-spacing: 0.08em;
  opacity: 0.85;
}
.hero-divider {
  position: relative;
  width: 96rpx;
  height: 4rpx;
  margin: 48rpx auto 0;
  background: linear-gradient(90deg, #7C3AED, #06B6D4, #F59E0B);
  border-radius: 2rpx;
  opacity: 0.5;
}

/* === 牌阵扇形 === */
.cards-fan {
  display: flex;
  justify-content: center;
  align-items: flex-end;
  min-height: 320rpx;
  padding: 0 40rpx;
  margin-top: -40rpx;
  position: relative;
  z-index: 2;
}
.fan-card {
  position: relative;
  width: 188rpx;
  height: 296rpx;
  background: rgba(15, 11, 30, 0.85);
  border: 2rpx solid rgba(124, 58, 237, 0.35);
  border-radius: 28rpx;
  box-shadow: 0 0 40rpx rgba(124, 58, 237, 0.3);
  backdrop-filter: blur(16rpx);
  -webkit-backdrop-filter: blur(16rpx);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fan-left {
  transform: rotate(-14deg) translateY(-20rpx);
  margin-right: -32rpx;
  z-index: 1;
}
.fan-center {
  width: 208rpx;
  height: 320rpx;
  border: 3rpx solid rgba(124, 58, 237, 0.5);
  box-shadow: 0 0 48rpx rgba(124, 58, 237, 0.4);
  transform: translateY(-40rpx);
  z-index: 3;
}
.fan-right {
  transform: rotate(14deg) translateY(-20rpx);
  margin-left: -32rpx;
  border-color: rgba(6, 182, 212, 0.35);
  box-shadow: 0 0 40rpx rgba(6, 182, 212, 0.3);
  z-index: 1;
}

/* 牌面六角符文 */
.hex-mark {
  position: relative;
  width: 108rpx;
  height: 108rpx;
}
.hex-mark-large {
  width: 120rpx;
  height: 120rpx;
}
.tri-up {
  position: absolute;
  top: 4rpx;
  left: 50%;
  width: 0;
  height: 0;
  border-left: 28rpx solid transparent;
  border-right: 28rpx solid transparent;
  border-bottom: 48rpx solid rgba(124, 58, 237, 0.3);
  transform: translateX(-50%);
}
.hex-mark-large .tri-up {
  border-left-width: 32rpx;
  border-right-width: 32rpx;
  border-bottom-width: 56rpx;
  border-bottom-color: rgba(124, 58, 237, 0.35);
}
.tri-down {
  position: absolute;
  bottom: 4rpx;
  left: 50%;
  width: 0;
  height: 0;
  border-left: 28rpx solid transparent;
  border-right: 28rpx solid transparent;
  border-top: 48rpx solid rgba(6, 182, 212, 0.25);
  transform: translateX(-50%);
}
.hex-mark-large .tri-down {
  border-left-width: 32rpx;
  border-right-width: 32rpx;
  border-top-width: 56rpx;
  border-top-color: rgba(6, 182, 212, 0.3);
}
.hex-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 36rpx;
  height: 36rpx;
  border: 2rpx solid rgba(245, 158, 11, 0.4);
  border-radius: 50%;
  transform: translate(-50%, -50%);
}
.hex-mark-large .hex-ring {
  width: 48rpx;
  height: 48rpx;
}
.hex-ring-2 {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 28rpx;
  height: 28rpx;
  border: 2rpx solid rgba(124, 58, 237, 0.35);
  border-radius: 50%;
  transform: translate(-50%, -50%);
}
.hex-dot {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 8rpx;
  height: 8rpx;
  background: rgba(245, 158, 11, 0.6);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 16rpx 4rpx rgba(245, 158, 11, 0.3);
}
.hex-cross-h {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 104rpx;
  height: 2rpx;
  background: rgba(124, 58, 237, 0.2);
  transform: translate(-50%, -50%);
}
.hex-cross-v {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 2rpx;
  height: 104rpx;
  background: rgba(124, 58, 237, 0.2);
  transform: translate(-50%, -50%);
}

/* 牌角装饰 */
.card-corner {
  position: absolute;
  width: 16rpx;
  height: 16rpx;
}
.corner-tl {
  top: 12rpx; left: 12rpx;
  border-top: 2rpx solid rgba(124, 58, 237, 0.4);
  border-left: 2rpx solid rgba(124, 58, 237, 0.4);
}
.corner-tr {
  top: 12rpx; right: 12rpx;
  border-top: 2rpx solid rgba(124, 58, 237, 0.4);
  border-right: 2rpx solid rgba(124, 58, 237, 0.4);
}
.corner-bl {
  bottom: 12rpx; left: 12rpx;
  border-bottom: 2rpx solid rgba(6, 182, 212, 0.3);
  border-left: 2rpx solid rgba(6, 182, 212, 0.3);
}
.corner-br {
  bottom: 12rpx; right: 12rpx;
  border-bottom: 2rpx solid rgba(6, 182, 212, 0.3);
  border-right: 2rpx solid rgba(6, 182, 212, 0.3);
}

/* 中央牌上下圆环 */
.center-orb-top {
  position: absolute;
  top: 16rpx;
  left: 50%;
  width: 28rpx;
  height: 28rpx;
  border: 2rpx solid rgba(6, 182, 212, 0.3);
  border-radius: 50%;
  transform: translateX(-50%);
}
.center-orb-bottom {
  position: absolute;
  bottom: 16rpx;
  left: 50%;
  width: 28rpx;
  height: 28rpx;
  border: 2rpx solid rgba(6, 182, 212, 0.3);
  border-radius: 50%;
  transform: translateX(-50%);
}

/* === 牌阵选择 === */
.section {
  padding: 40rpx 40rpx 24rpx;
}
.section-title {
  display: block;
  font-size: 32rpx;
  font-weight: 600;
  color: #E2E8F0;
  margin-bottom: 32rpx;
}
.spread-scroll {
  width: 100%;
  white-space: nowrap;
}
.spread-list {
  display: flex;
  gap: 24rpx;
  padding-bottom: 8rpx;
}
.spread-card {
  flex-shrink: 0;
  width: 280rpx;
  padding: 40rpx 32rpx;
  background: rgba(15, 11, 30, 0.7);
  border: 1rpx solid rgba(6, 182, 212, 0.35);
  border-radius: 32rpx;
  box-shadow: 0 0 32rpx rgba(6, 182, 212, 0.3);
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20rpx;
}
.spread-card.active {
  border-color: #06B6D4;
  box-shadow: 0 0 48rpx rgba(6, 182, 212, 0.45);
}
.spread-icon-wrap {
  width: 96rpx;
  height: 96rpx;
  line-height: 96rpx;
  text-align: center;
  border-radius: 50%;
  background: rgba(6, 182, 212, 0.12);
}
.spread-icon {
  color: #06B6D4;
  font-size: 40rpx;
}
.spread-name {
  font-size: 26rpx;
  font-weight: 600;
  color: #E2E8F0;
  text-align: center;
}
.spread-desc {
  font-size: 22rpx;
  color: #64748B;
  text-align: center;
}

/* === CTA 按钮 === */
.cta-wrap {
  padding: 16rpx 40rpx 32rpx;
}
.cta-btn {
  height: 96rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #6D28D9 0%, #7C3AED 50%, #8B5CF6 100%);
  border-radius: 32rpx;
  box-shadow: 0 0 40rpx rgba(124, 58, 237, 0.3);
}
.cta-text {
  color: #ffffff;
  font-size: 30rpx;
  font-weight: 600;
  letter-spacing: 0.08em;
}

/* === 敬请期待 === */
.coming-soon {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12rpx;
  padding: 16rpx 0 32rpx;
}
.coming-soon-icon {
  color: #64748B;
  font-size: 24rpx;
}
.coming-soon-text {
  font-size: 22rpx;
  color: #64748B;
  white-space: nowrap;
}

/* === 占卜结果 === */
.result-card {
  margin: 0 40rpx 40rpx;
  padding: 48rpx 40rpx;
  background: rgba(30, 22, 56, 0.8);
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid rgba(245, 158, 11, 0.2);
  border-radius: 32rpx;
  animation: fadeIn 0.5s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20rpx); }
  to { opacity: 1; transform: translateY(0); }
}
.drawn-card {
  width: 260rpx;
  height: 400rpx;
  margin: 0 auto 40rpx;
  border-radius: 28rpx;
  background: linear-gradient(135deg, #3a2a5a 0%, #2a1a4a 100%);
  border: 3rpx solid rgba(245, 158, 11, 0.4);
  box-shadow: 0 0 48rpx rgba(245, 158, 11, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.5s ease;
}
.drawn-card.reversed {
  transform: rotate(180deg);
}
.drawn-card.reversed .card-face {
  transform: rotate(180deg);
}
.card-face {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32rpx;
}
.card-emblem {
  font-size: 80rpx;
  margin-bottom: 24rpx;
  text-shadow: 0 0 32rpx rgba(245, 158, 11, 0.4);
}
.card-name {
  font-size: 34rpx;
  font-weight: 600;
  color: #F59E0B;
  letter-spacing: 4rpx;
  text-align: center;
}
.card-name-en {
  font-size: 22rpx;
  color: rgba(245, 158, 11, 0.6);
  margin-top: 12rpx;
  letter-spacing: 2rpx;
}
.meaning-block {
  margin-bottom: 32rpx;
}
.meaning-title {
  display: block;
  font-size: 28rpx;
  font-weight: 600;
  color: #F59E0B;
  letter-spacing: 4rpx;
  margin-bottom: 16rpx;
}
.meaning-text {
  display: block;
  font-size: 28rpx;
  color: #E2E8F0;
  line-height: 1.7;
  letter-spacing: 1rpx;
}

.bottom-spacer { height: 80rpx; }
</style>
