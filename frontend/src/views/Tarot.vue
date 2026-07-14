<template>
  <div class="tarot-page page-transition">
    <div class="tarot-card-a glass-card">
      <div class="tarot-header">
        <h2>塔罗占卜</h2>
        <p>选择牌阵，抽取塔罗牌，按需获取 AI 深度解读</p>
      </div>

      <div class="spread-selector">
        <div class="spread-label">选择牌阵</div>
        <div class="spread-options">
          <button
            v-for="s in spreads"
            :key="s.key"
            class="btn spread-btn"
            :class="{ active: selectedSpread === s.key }"
            :disabled="drawing || interpreting"
            @click="selectSpread(s.key)"
            :aria-label="s.name"
          >{{ s.name }}</button>
        </div>
      </div>

      <div v-if="!drawn" class="tarot-deck">
        <div class="deck-area" @click="drawCards">
          <div class="card-back" :class="{ pulsing: drawing }">
            <div class="card-back-pattern">✦</div>
            <div class="card-back-text">{{ drawing ? "抽牌中…" : "点击抽牌" }}</div>
          </div>
        </div>
        <div class="deck-hint">{{ deckHint }}</div>
      </div>

      <div v-else class="tarot-result" :class="'layout-' + selectedSpread">
        <div
          v-for="(c, idx) in cards"
          :key="idx"
          class="tc-card"
        >
          <div class="tc-position-label">{{ positions[idx] }}</div>
          <div class="tc-card-wrap" @click="flipCard(c)">
            <div class="tc-inner" :class="{ flipped: c.revealed, reversed: c.isReversed }">
              <div class="tc-front">
                <div class="card-emblem">{{ c.emblem }}</div>
                <div class="card-name">{{ c.isReversed ? "逆位" : "正位" }} {{ c.name }}</div>
                <div class="card-name-en">{{ c.nameEn }}</div>
              </div>
              <div class="tc-back">
                <div class="card-back-mini">✦</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="drawn" class="reading-meanings">
        <div v-for="(c, idx) in cards" :key="'m-' + idx" class="meaning-block">
          <div class="meaning-title">{{ positions[idx] }} · {{ c.isReversed ? "逆位" : "正位" }} {{ c.name }}</div>
          <p>{{ c.meaning }}</p>
        </div>

        <!-- AI 详细解读按钮：所有牌翻开后才出现 -->
        <div v-if="allFlipped && !interpretation && !interpreting" class="interpret-cta-wrap">
          <button class="btn interpret-btn" @click="onInterpret">获取详细解读</button>
        </div>

        <!-- AI 解读内容 -->
        <div v-if="interpretation || interpreting" class="ai-reading">
          <div class="ai-reading-title">塔罗师解读</div>
          <MarkdownRender v-if="interpretation" :content="interpretation" />
          <div v-else class="ai-typing">解读中…</div>
        </div>

        <div class="action-row">
          <button class="btn" :disabled="interpreting" @click="reset" aria-label="重新抽取">重新抽取</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue"
import {
  drawTarotCardsWS,
  interpretTarotWS,
  type TarotSpread,
  type TarotDrawnCard,
} from "@/api"
import MarkdownRender from "@/components/MarkdownRender.vue"

interface DrawnCard extends TarotDrawnCard {
  revealed: boolean
}

const spreads: { key: TarotSpread; name: string; positions: string[] }[] = [
  { key: "daily", name: "每日一牌", positions: ["今日指引"] },
  { key: "three_card", name: "三牌阵", positions: ["过去", "现在", "未来"] },
  { key: "relationship", name: "关系牌阵", positions: ["你自己", "对方", "关系"] },
]

const selectedSpread = ref<TarotSpread>("daily")
const drawn = ref(false)
const drawing = ref(false)
const interpreting = ref(false)
const cards = ref<DrawnCard[]>([])
const interpretation = ref("")

const currentSpread = computed(() => spreads.find((s) => s.key === selectedSpread.value)!)
const positions = computed(() => currentSpread.value.positions)
const deckHint = computed(() => `将抽取 ${currentSpread.value.positions.length} 张牌：${currentSpread.value.positions.join(" / ")}`)
const allFlipped = computed(() => drawn.value && cards.value.length > 0 && cards.value.every(c => c.revealed))

const selectSpread = (key: TarotSpread) => {
  if (drawing.value || interpreting.value) return
  selectedSpread.value = key
  drawn.value = false
  cards.value = []
  interpretation.value = ""
}

/** 阶段一：抽牌（不调用 LLM） */
function drawCards() {
  if (drawing.value) return
  drawn.value = true
  drawing.value = true
  cards.value = []
  interpretation.value = ""

  drawTarotCardsWS(selectedSpread.value, {
    onCards: (data: TarotDrawnCard[]) => {
      cards.value = data.map((c) => ({ ...c, revealed: false }))
      drawing.value = false
      // 错开翻开动画
      cards.value.forEach((c, i) => {
        setTimeout(() => { c.revealed = true }, 200 + i * 250)
      })
    },
    onError: (err: string) => {
      drawing.value = false
      if (!cards.value.length) {
        alert(`抽牌失败：${err}`)
      }
    },
  })
}

function flipCard(c: DrawnCard) {
  if (c.revealed) return
  c.revealed = true
}

/** 阶段二：AI 详细解读（用户点击触发） */
function onInterpret() {
  if (interpreting.value) return
  if (!allFlipped.value) return
  interpreting.value = true
  interpretation.value = ""

  const payload: TarotDrawnCard[] = cards.value.map(c => ({
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
      cards: payload,
    },
    {
      onMessage: (chunk: string) => {
        interpretation.value += chunk
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

function reset() {
  if (interpreting.value) return
  drawn.value = false
  cards.value = []
  interpretation.value = ""
}
</script>

<style scoped>
.tarot-page {
  height: 100vh; overflow-y: auto; padding: 20px;
  display: flex; justify-content: center; align-items: flex-start;
}
.tarot-card-a { width: 100%; max-width: 720px; padding: 28px; text-align: center; }
.tarot-header { margin-bottom: 20px; }
.tarot-header h2 { font-size: 22px; color: #b886e8; letter-spacing: 3px; }
.tarot-header p { font-size: 12px; color: var(--text-dim); margin-top: 6px; }

.spread-selector { margin-bottom: 24px; }
.spread-label { font-size: 12px; color: var(--text-dim); margin-bottom: 10px; letter-spacing: 2px; }
.spread-options { display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; }
.spread-btn { min-width: 90px; }
.spread-btn.active { border-color: rgba(184,134,232,0.6); color: #b886e8; background: rgba(184,134,232,0.08); }
.spread-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.tarot-deck { display: flex; flex-direction: column; align-items: center; gap: 16px; }
.deck-area { cursor: pointer; -webkit-user-select: none; user-select: none; }
.card-back {
  width: 180px; height: 280px; border-radius: 16px;
  background: linear-gradient(135deg, #2a1a4a, #1a0a2a);
  border: 2px solid rgba(184,134,232,0.4); display: flex;
  flex-direction: column; align-items: center; justify-content: center;
  transition: all 0.3s; box-shadow: 0 0 30px rgba(184,134,232,0.2);
}
.card-back:hover { transform: scale(1.05); border-color: rgba(184,134,232,0.7); box-shadow: 0 0 50px rgba(184,134,232,0.4); }
.card-back.pulsing { animation: pulse-glow 1s ease-in-out infinite; }
.card-back-pattern { font-size: 48px; color: rgba(184,134,232,0.5); margin-bottom: 16px; }
.card-back-text { font-size: 14px; color: rgba(184,134,232,0.7); letter-spacing: 2px; }
.deck-hint { font-size: 12px; color: var(--text-dim); }

.tarot-result { margin-top: 8px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.layout-daily { display: flex; justify-content: center; }
.layout-three_card, .layout-relationship {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; justify-items: center;
}

.tc-card { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.tc-position-label { font-size: 12px; color: #b886e8; letter-spacing: 1px; text-align: center; }

.tc-card-wrap {
  width: 160px; aspect-ratio: 2/3; perspective: 800px; cursor: pointer;
}
.layout-three_card .tc-card-wrap, .layout-relationship .tc-card-wrap { width: 140px; }

.tc-inner {
  position: relative; width: 100%; height: 100%;
  transform-style: preserve-3d;
  transition: transform 0.7s cubic-bezier(0.4, 0, 0.2, 1);
  transform: rotateY(180deg);
}
.tc-inner.flipped { transform: rotateY(0deg); }
.tc-inner.reversed .tc-front { transform: rotate(180deg); }

.tc-front, .tc-back {
  position: absolute; inset: 0; border-radius: 14px; backface-visibility: hidden;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
}
.tc-front {
  background: linear-gradient(135deg, #3a2a5a, #2a1a4a);
  border: 2px solid rgba(184,134,232,0.5);
  box-shadow: 0 0 40px rgba(184,134,232,0.3);
  padding: 12px;
}
.tc-back {
  background: linear-gradient(135deg, #2a1a4a, #1a0a2a);
  border: 2px solid rgba(184,134,232,0.4);
  transform: rotateY(180deg);
  box-shadow: 0 0 30px rgba(184,134,232,0.2);
}
.card-back-mini { font-size: 32px; color: rgba(184,134,232,0.5); }

.card-emblem { font-size: 36px; margin-bottom: 10px; }
.card-name { font-size: 15px; color: #b886e8; letter-spacing: 2px; }
.card-name-en { font-size: 10px; color: rgba(184,134,232,0.5); margin-top: 4px; }

.reading-meanings { margin-top: 28px; text-align: left; }
.meaning-block {
  background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 12px;
  padding: 16px; margin-bottom: 12px; animation: fadeInUp 0.5s ease forwards;
}
.meaning-title { font-size: 13px; color: #b886e8; letter-spacing: 2px; margin-bottom: 8px; }
.meaning-block p { font-size: 13px; color: var(--text-dim); line-height: 1.7; margin: 0; }

/* AI 解读按钮 */
.interpret-cta-wrap { text-align: center; margin: 24px 0; }
.interpret-btn {
  background: linear-gradient(135deg, #b886e8, #7c4dff) !important;
  color: #fff !important;
  border: none !important;
  padding: 12px 32px !important;
  font-size: 14px !important;
  letter-spacing: 2px;
  box-shadow: 0 4px 20px rgba(124, 77, 255, 0.4);
  cursor: pointer;
  transition: transform 0.2s;
}
.interpret-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 24px rgba(124, 77, 255, 0.5); }

/* AI 解读内容 */
.ai-reading {
  background: rgba(184,134,232,0.05);
  border: 1px solid rgba(184,134,232,0.3);
  border-radius: 12px;
  padding: 20px;
  margin: 16px 0;
  animation: fadeInUp 0.5s ease forwards;
}
.ai-reading-title {
  font-size: 14px;
  color: #b886e8;
  letter-spacing: 2px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(184,134,232,0.2);
}
.ai-typing {
  font-size: 13px;
  color: var(--text-dim);
  font-style: italic;
  animation: pulse-glow 1.5s ease-in-out infinite;
}

.action-row { text-align: center; margin-top: 16px; }
.action-row .btn { min-width: 120px; }
.action-row .btn:disabled { opacity: 0.5; cursor: not-allowed; }

@keyframes pulse-glow { 0%, 100% { opacity: 0.5; } 50% { opacity: 1; } }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }

@media (max-width: 720px) {
  .layout-three_card, .layout-relationship { grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .tc-card-wrap { width: 120px; }
  .layout-three_card .tc-card-wrap, .layout-relationship .tc-card-wrap { width: 100px; }
  .card-name { font-size: 12px; letter-spacing: 1px; }
  .card-emblem { font-size: 28px; }
}
@media (max-width: 480px) {
  .layout-three_card, .layout-relationship { grid-template-columns: 1fr; }
}
</style>
