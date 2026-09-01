<template>
  <div class="liuyao-page page-transition">
    <section class="liuyao-card glass-card">
      <header>
        <span>THE SIX LINES</span>
        <h2>六爻算卦</h2>
        <p>以当下心念起卦；结果用于自省与决策参考。</p>
      </header>

      <textarea v-model="question" class="question" placeholder="写下你想问的事，起卦后可获取 AI 解读" maxlength="100"></textarea>

      <div class="method-tabs">
        <button
          v-for="item in methods"
          :key="item.key"
          :class="{ active: method === item.key }"
          :disabled="busy"
          @click="method = item.key"
        >
          <b>{{ item.name }}</b><small>{{ item.hint }}</small>
        </button>
      </div>

      <div v-if="method === 'numbers'" class="number-inputs">
        <input v-model.number="numbers[0]" type="number" placeholder="第一个数字">
        <input v-model.number="numbers[1]" type="number" placeholder="第二个数字">
      </div>

      <div class="btn-center">
        <button class="cast-btn" :disabled="busy" @click="cast">
          {{ loading ? '正在起卦…' : method === 'coins' ? '摇动三枚铜钱' : '开始起卦' }}
        </button>
      </div>

      <!-- 起卦动画：摇卦 → 逐爻揭示 -->
      <div v-if="phase === 'casting'" class="casting-stage">
        <div class="cast-anim" :class="'method-' + method">
          <template v-if="method === 'coins'">
            <div class="coins"><i v-for="n in 3" :key="n" class="coin"></i></div>
            <p class="cast-tip">凝神静气，摇卦中…</p>
          </template>
          <template v-else-if="method === 'numbers'">
            <div class="num-orbit"><b>{{ numbers[0] == null ? '—' : numbers[0] }}</b><span>☯</span><b>{{ numbers[1] == null ? '—' : numbers[1] }}</b></div>
            <p class="cast-tip">以心念入卦，推演六爻…</p>
          </template>
          <template v-else>
            <div class="clock"><i class="clock-hand"></i><span class="clock-dot"></span></div>
            <p class="cast-tip">感时应物，此刻起卦…</p>
          </template>
        </div>
      </div>

      <div v-if="phase === 'revealing'" class="casting-stage">
        <div class="reveal-stage">
          <div v-if="method === 'coins'" class="coins settled">
            <i v-for="(face, n) in currentFaces" :key="n" class="coin" :class="{ yang: face }"></i>
          </div>
          <div v-else class="reveal-symbol">{{ currentSymbol }}</div>
          <p class="cast-tip">第 {{ revealCount }} 爻 · {{ currentLabel }}</p>
        </div>
        <div class="yao-progress">
          <div
            v-for="n in 6"
            :key="n"
            class="yao-slot"
            :class="{ filled: n <= revealCount, yang: revealedLines[n - 1]?.yang }"
          >
            <i></i>
          </div>
        </div>
      </div>

      <div v-if="result && phase === 'done'" class="result result-in">
        <div class="result-head">
          <div>
            <small>本卦</small>
            <h3>{{ result.original.name }}</h3>
            <p>{{ result.original.upper.symbol }} {{ result.original.upper.name }}上 · {{ result.original.lower.symbol }} {{ result.original.lower.name }}下</p>
          </div>
          <div v-if="result.changed">
            <small>变卦</small>
            <h3>{{ result.changed.name }}</h3>
            <p>{{ result.changed.upper.symbol }} {{ result.changed.upper.name }}上 · {{ result.changed.lower.symbol }} {{ result.changed.lower.name }}下</p>
          </div>
        </div>
        <p class="summary">{{ result.summary }}</p>
        <div class="hexagrams">
          <section>
            <b>本卦 · 自上而下</b>
            <div v-for="line in reversedLines" :key="line.index" class="yao" :class="{ moving: line.moving }">
              <span>第{{ line.index }}爻</span>
              <i :class="{ yang: line.yang }"></i>
              <em v-if="line.moving">动</em>
            </div>
          </section>
          <section v-if="result.changed">
            <b>变卦 · 动爻已变</b>
            <div v-for="line in changedLines" :key="line.index" class="yao">
              <span>第{{ line.index }}爻</span>
              <i :class="{ yang: line.yang }"></i>
            </div>
          </section>
        </div>
        <div class="btn-center">
          <button class="cast-btn" :disabled="interpreting" @click="interpret">
            {{ interpreting ? '解读中…' : 'AI 解读此卦' }}
          </button>
        </div>
        <p v-if="interpretation" class="ai-result">{{ interpretation }}</p>
        <footer>起卦时间：{{ new Date(result.createdAt).toLocaleString() }} · {{ methodName }}</footer>
      </div>
    </section>
    <Transition name="toast-fade">
      <div v-if="error" class="toast">{{ error }}</div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import { castLiuYao, interpretLiuYao, type LiuYaoResult } from "@/api"

const methods = [
  { key: "coins", name: "铜钱起卦", hint: "模拟三枚铜钱，逐爻摇卦" },
  { key: "numbers", name: "数字起卦", hint: "输入两个心中浮现的数字" },
  { key: "time", name: "时间起卦", hint: "以此刻时间起念" },
] as const

const method = ref<typeof methods[number]["key"]>("coins")
const numbers = ref<number[]>([])
const question = ref("")
const loading = ref(false)
const interpreting = ref(false)
const interpretation = ref("")
const result = ref<LiuYaoResult | null>(null)
const error = ref("")
const phase = ref<"idle" | "casting" | "revealing" | "done">("idle")
const revealCount = ref(0)
let revealTimer: number | null = null

const busy = computed(() => loading.value || interpreting.value || phase.value === "revealing")
const methodName = computed(() => methods.find(item => item.key === method.value)?.name)
const reversedLines = computed(() => (result.value ? [...result.value.lines].reverse() : []))
const changedLines = computed(() =>
  result.value ? [...result.value.lines].map(line => ({ ...line, yang: line.moving ? !line.yang : line.yang })).reverse() : []
)
// 已揭示的爻（自下而上），用于卦位进度
const revealedLines = computed(() => (result.value ? [...result.value.lines].slice(0, revealCount.value) : []))
// 六爻三枚铜钱正反：6 老阴(动) 全字；7 少阳 一背二字；8 少阴 二背一字；9 老阳(动) 全背
const currentFaces = computed(() => {
  const value = revealedLines.value[revealCount.value - 1]?.value ?? 7
  return { 6: [0, 0, 0], 7: [1, 0, 0], 8: [1, 1, 0], 9: [1, 1, 1] }[value] || [0, 0, 0]
})
const currentSymbol = computed(() => (revealedLines.value[revealCount.value - 1]?.yang ? "━" : "━ ━"))
const currentLabel = computed(() => {
  const value = revealedLines.value[revealCount.value - 1]?.value
  return { 6: "老阴 · 动", 7: "少阳", 8: "少阴", 9: "老阳 · 动" }[value] || ""
})

async function cast() {
  if (method.value === "numbers" && (!Number.isInteger(numbers.value[0]) || !Number.isInteger(numbers.value[1]))) {
    error.value = "请输入两个整数后再起卦"
    return
  }
  loading.value = true
  error.value = ""
  result.value = null
  interpretation.value = ""
  phase.value = "casting"
  try {
    // 摇卦动画固定展示约 1.6s，避免 API 过快导致仪式感缺失
    const [data] = await Promise.all([
      castLiuYao(method.value, numbers.value),
      new Promise<void>(resolve => setTimeout(resolve, 1600)),
    ])
    result.value = data
    revealCount.value = 0
    phase.value = "revealing"
    revealTimer = window.setInterval(() => {
      revealCount.value += 1
      if (revealCount.value >= 6) {
        if (revealTimer) window.clearInterval(revealTimer)
        revealTimer = window.setTimeout(() => {
          phase.value = "done"
          revealTimer = null
        }, 650)
      }
    }, 650)
  } catch (e) {
    error.value = e instanceof Error ? e.message : "起卦失败"
    phase.value = "idle"
  } finally {
    loading.value = false
  }
}

async function interpret() {
  if (!result.value || !question.value.trim()) {
    error.value = "请填写问题后再请求 AI 解读"
    return
  }
  interpreting.value = true
  try {
    interpretation.value = await interpretLiuYao(question.value, result.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : "解读失败"
  } finally {
    interpreting.value = false
  }
}

onBeforeUnmount(() => {
  if (revealTimer) window.clearTimeout(revealTimer)
})
</script>

<style scoped>
.liuyao-page { min-height: 100vh; padding: 22px; display: flex; justify-content: center; }
.liuyao-card { width: min(100%, 850px); padding: 32px; text-align: center; }
.liuyao-card header > span { font-size: 10px; letter-spacing: 4px; color: #cfad65; }
.liuyao-card h2 { color: #e5c27c; letter-spacing: 8px; }
.liuyao-card header p, .result-head p { color: var(--text-dim); font-size: 13px; }

.method-tabs { display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; margin: 28px 0 16px; }
.method-tabs button { width: 180px; padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: rgba(20, 16, 26, .45); color: var(--text-dim); cursor: pointer; }
.method-tabs b, .method-tabs small { display: block; }
.method-tabs small { font-size: 10px; margin-top: 5px; }
.method-tabs .active { color: #f1d894; border-color: #caa95d; background: rgba(202, 169, 93, .1); }
.method-tabs button:disabled { opacity: .5; cursor: not-allowed; }

.question { display: block; width: min(100%, 560px); height: 70px; margin: 0 auto 12px; padding: 10px; box-sizing: border-box; border: 1px solid var(--border); border-radius: 8px; background: #171221; color: #eee; }
.number-inputs { display: flex; justify-content: center; gap: 10px; }
.number-inputs input { max-width: 190px; padding: 10px; border: 1px solid var(--border); border-radius: 7px; background: #171221; color: #eee; }

.btn-center { text-align: center; display: flex; justify-content: center; margin: 24px 0; }
.cast-btn { margin: 0; padding: 14px 40px; border: 1px solid #d1ae62; border-radius: 10px; background: linear-gradient(135deg, #694b1c, #a47b31); color: #fff; letter-spacing: 2px; cursor: pointer; font-size: 15px; font-weight: 600; transition: all .25s; }
.cast-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(164, 123, 49, .45); }
.cast-btn:disabled { opacity: .6; cursor: not-allowed; }

/* ===== 起卦动画 ===== */
.casting-stage { border-top: 1px solid rgba(210, 179, 112, .35); margin-top: 16px; padding-top: 26px; }
.cast-anim { min-height: 150px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px; }
.cast-tip { color: #c9ad74; font-size: 13px; letter-spacing: 2px; }

/* 铜钱 */
.coins { display: flex; gap: 18px; align-items: center; justify-content: center; height: 74px; }
.coin {
  width: 58px; height: 58px; border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #f3d488, #b4862f 60%, #7c5a1c);
  box-shadow: inset 0 0 0 4px rgba(120, 84, 24, .5), 0 6px 14px rgba(0, 0, 0, .45);
  position: relative; display: inline-block;
}
.coin::before, .coin::after { content: ""; position: absolute; background: rgba(70, 46, 10, .85); }
.coin::before { width: 100%; height: 11px; top: 50%; left: 0; transform: translateY(-50%); }
.coin::after { width: 11px; height: 100%; left: 50%; top: 0; transform: translateX(-50%); }
.coin.yang::before, .coin.yang::after { background: rgba(250, 226, 160, .9); }
.method-coins .coins { animation: coinShake .7s ease-in-out infinite; }
@keyframes coinShake {
  0%, 100% { transform: translateX(0) rotate(0deg); }
  25% { transform: translateX(-12px) rotate(-18deg); }
  75% { transform: translateX(12px) rotate(18deg); }
}
.coins.settled .coin { animation: coinSettle .5s ease both; }
.coins.settled .coin:nth-child(2) { animation-delay: .12s; }
.coins.settled .coin:nth-child(3) { animation-delay: .24s; }
@keyframes coinSettle {
  0% { transform: translateY(-46px) rotate(540deg); opacity: 0; }
  100% { transform: translateY(0) rotate(0); opacity: 1; }
}

/* 数字起卦：太极汇聚 */
.num-orbit { display: flex; align-items: center; gap: 26px; font-size: 34px; }
.num-orbit b { min-width: 62px; padding: 10px 6px; border: 1px solid #caa95d; border-radius: 12px; background: rgba(202, 169, 93, .12); color: #f1d894; animation: numFloat 1.1s ease-in-out infinite; }
.num-orbit b:first-child { animation-delay: .15s; }
.num-orbit span { font-size: 44px; animation: spin 3s linear infinite; }
@keyframes numFloat { 50% { transform: translateY(-12px); box-shadow: 0 8px 18px rgba(164, 123, 49, .4); } }
@keyframes spin { to { transform: rotate(360deg); } }

/* 时间起卦：罗盘 */
.clock {
  width: 92px; height: 92px; border-radius: 50%;
  border: 3px solid #caa95d; position: relative;
  background: radial-gradient(circle, #241b0d, #171221 72%);
  box-shadow: 0 0 22px rgba(202, 169, 93, .3);
}
.clock::before { content: ""; position: absolute; inset: 5px; border-radius: 50%; border: 1px dashed rgba(202, 169, 93, .4); }
.clock-hand { position: absolute; left: 50%; top: 50%; width: 3px; height: 32px; margin: -32px 0 0 -1.5px; background: #e5c27c; transform-origin: bottom center; animation: clockSpin 2s linear infinite; }
.clock-dot { position: absolute; left: 50%; top: 50%; width: 8px; height: 8px; margin: -4px; border-radius: 50%; background: #e5c27c; }
@keyframes clockSpin { to { transform: rotate(360deg); } }

/* 逐爻揭示 */
.reveal-stage { min-height: 140px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; }
.reveal-symbol { font-size: 40px; color: #f1d894; animation: numFloat 1s ease-in-out infinite; }
.yao-progress { display: flex; flex-direction: column-reverse; gap: 6px; align-items: center; margin: 14px 0 8px; }
.yao-slot { width: 150px; height: 8px; border-radius: 4px; background: rgba(255, 255, 255, .06); transition: background .3s; }
.yao-slot i { display: block; width: 0; height: 100%; border-radius: 4px; background: #d4b26b; transition: width .45s ease; }
.yao-slot.filled { background: rgba(212, 178, 107, .2); }
.yao-slot.filled i { width: 100%; }
.yao-slot.filled.yang i { background: linear-gradient(90deg, #d4b26b, #f1d894); box-shadow: 0 0 10px rgba(212, 178, 107, .6); }

/* 成卦定格 */
.result { border-top: 1px solid rgba(210, 179, 112, .35); margin-top: 16px; padding-top: 22px; text-align: left; }
.result-in { animation: resultIn .6s ease both; }
@keyframes resultIn {
  0% { opacity: 0; transform: translateY(18px); }
  100% { opacity: 1; transform: translateY(0); }
}
.result-head { display: flex; justify-content: center; gap: 70px; text-align: center; }
.result-head small, .result footer { color: #b99b61; font-size: 11px; }
.result-head h3 { margin: 4px 0; color: #f0d490; font-size: 21px; }
.summary, .ai-result { max-width: 620px; margin: 20px auto; color: #d9c9a3; text-align: center; line-height: 1.7; }
.ai-result { white-space: pre-wrap; text-align: left; background: rgba(255, 255, 255, .04); padding: 16px; border-radius: 8px; }
.hexagrams { display: flex; justify-content: center; gap: 60px; margin: 20px; }
.hexagrams section { width: 260px; }
.hexagrams section > b { display: block; text-align: center; color: #d9bd79; font-size: 12px; margin-bottom: 12px; }
.yao { display: flex; align-items: center; gap: 10px; height: 32px; }
.yao span { width: 42px; color: var(--text-dim); font-size: 10px; }
.yao i { height: 5px; flex: 1; background: linear-gradient(90deg, #d4b26b 0 43%, transparent 43% 57%, #d4b26b 57%); }
.yao i.yang { background: #d4b26b; }
.yao.moving i { box-shadow: 0 0 10px #e7c87c; }
.yao em { font-style: normal; color: #f0cc72; font-size: 11px; }
.result footer { text-align: center; margin-top: 22px; }

.toast { position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%); padding: 10px 20px; border-radius: 8px; background: #b54b62; color: #fff; }
.toast-fade-enter-active, .toast-fade-leave-active { transition: .25s; }
.toast-fade-enter-from, .toast-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(10px); }

@media (max-width: 600px) {
  .liuyao-card { padding: 20px; }
  .result-head, .hexagrams { gap: 14px; }
  .hexagrams { margin: 20px 0; }
  .hexagrams section { width: calc(50vw - 30px); }
}
</style>
