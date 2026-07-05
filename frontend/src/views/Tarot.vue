<template>
  <div class="tarot-page">
    <div class="tarot-card-a glass-card">
      <div class="tarot-header">
        <h2>每日塔罗</h2>
        <p>抽取一张塔罗牌，获得今日指引</p>
      </div>

      <div v-if="!drawn" class="tarot-deck">
        <div class="deck-area" @click="drawCard">
          <div class="card-back">
            <div class="card-back-pattern">✦</div>
            <div class="card-back-text">点击抽取</div>
          </div>
        </div>
      </div>

      <div v-else class="tarot-result">
        <div class="drawn-card" :class="card.isReversed ? 'reversed' : ''">
          <div class="card-face">
            <div class="card-emblem">{{ card.emblem }}</div>
            <div class="card-name">{{ card.isReversed ? '逆位' : '正位' }} {{ card.name }}</div>
            <div class="card-name-en">{{ card.nameEn }}</div>
          </div>
        </div>
        <div class="card-meaning">
          <div class="meaning-title">解读</div>
          <p>{{ card.isReversed ? card.reversedMeaning : card.meaning }}</p>
        </div>
        <div class="card-advice">
          <div class="meaning-title">今日建议</div>
          <p>{{ card.advice }}</p>
        </div>
        <button class="btn" @click="drawn = false; card = {} as any"  aria-label="重新抽取">重新抽取</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"

interface TarotCard {
  name: string; nameEn: string; emblem: string; meaning: string; reversedMeaning: string; advice: string
}

const majorArcana: TarotCard[] = [
  { name: "愚者", nameEn: "The Fool", emblem: "🌟", meaning: "新的开始、冒险、天真无邪。是时候勇敢迈出第一步，相信宇宙的指引。", reversedMeaning: "鲁莽、犹豫不决。你需要停下来重新审视当前的处境，不要盲目行动。", advice: "保持开放的心态，敢于尝试新事物。今天适合开启新计划。" },
  { name: "魔术师", nameEn: "The Magician", emblem: "🪄", meaning: "创造力、技能、意志力。你拥有实现目标所需的一切资源，现在是行动的时候。", reversedMeaning: "欺骗、能力不足。你可能在浪费自己的才华，或被表象迷惑。", advice: "今天你的创造力和沟通能力很强，善用它们解决难题。" },
  { name: "女祭司", nameEn: "The High Priestess", emblem: "🌙", meaning: "直觉、潜意识、神秘。静下心来倾听内心的声音，答案就在你心中。", reversedMeaning: "忽视直觉、情绪封闭。你与内心的连接被切断，需要重新建立信任。", advice: "相信你的直觉，不必急于做决定。今天适合静心冥想。" },
  { name: "女皇", nameEn: "The Empress", emblem: "👑", meaning: "丰饶、母性、感官享受。创造力与滋养的能量充沛，享受生活的美好。", reversedMeaning: "依赖、停滞。过度依赖他人或物质享受，忽视了内在成长。", advice: "今天适合关注家庭和自我滋养，享受生活中的小确幸。" },
  { name: "皇帝", nameEn: "The Emperor", emblem: "🏰", meaning: "权威、秩序、掌控。建立规则和结构，用理性与纪律引导自己。", reversedMeaning: "专制、失控。你可能过于强势，或缺乏自律导致混乱。", advice: "今天需要建立秩序，制定计划，以理性和纪律行事。" },
  { name: "教皇", nameEn: "The Hierophant", emblem: "📜", meaning: "传统、导师、精神指引。遵循传统智慧，寻求导师或制度的帮助。", reversedMeaning: "叛逆、盲目追随。你可能被困在陈规中，或盲目追随权威。", advice: "今天适合学习传统知识，或向有经验的人请教。" },
  { name: "恋人", nameEn: "The Lovers", emblem: "💕", meaning: "爱情、选择、和谐。面临重要抉择，跟随内心做出真诚的决定。", reversedMeaning: "分离、错误选择。关系中可能出现裂痕，需要真诚沟通。", advice: "今天适合处理感情关系，做决定时听从内心的声音。" },
  { name: "战车", nameEn: "The Chariot", emblem: "⚔️", meaning: "胜利、意志力、前进。克服困难，通过坚定的意志力取得胜利。", reversedMeaning: "失控、失败。你可能失去了方向，需要重新掌控局面。", advice: "今天充满动力和决心，适合推进拖延已久的事情。" },
  { name: "力量", nameEn: "Strength", emblem: "🦁", meaning: "勇气、耐心、内在力量。以柔克刚，用爱与耐心驯服内心的野兽。", reversedMeaning: "软弱、恐惧。你被恐惧支配，需要找回内在的力量。", advice: "今天需要耐心和勇气，相信自己的内在力量能克服挑战。" },
  { name: "隐士", nameEn: "The Hermit", emblem: "🏮", meaning: "内省、孤独、智慧。退一步反思，寻找内心的光明与真理。", reversedMeaning: "孤立、逃避。过度的孤独变成了逃避，需要重新连接外界。", advice: "今天适合独处和反思，给自己一些安静的时间。" },
  { name: "命运之轮", nameEn: "Wheel of Fortune", emblem: "🎡", meaning: "命运、转折、机遇。命运的齿轮转动，好运即将到来，抓住机会。", reversedMeaning: "厄运、停滞。你可能处于低谷，但变化是必然的，保持信念。", advice: "今天可能会遇到意外的转机，保持开放和灵活。" },
  { name: "正义", nameEn: "Justice", emblem: "⚖️", meaning: "公正、真相、因果。种瓜得瓜，真理必将显现，做出公正的决定。", reversedMeaning: "不公、逃避责任。你可能在逃避应承担的责任或真相。", advice: "今天适合做出公正的决定，诚实面对自己和他人。" },
  { name: "倒吊人", nameEn: "The Hanged Man", emblem: "🙃", meaning: "牺牲、换个视角、等待。暂停行动，换个角度看问题，会有新的领悟。", reversedMeaning: "固执、无谓牺牲。你不愿改变视角，导致停滞不前。", advice: "今天适合换个角度看问题，有时退一步海阔天空。" },
  { name: "死神", nameEn: "Death", emblem: "💀", meaning: "结束、转变、重生。旧的不去新的不来，接受改变，迎接新生。", reversedMeaning: "抗拒改变、停滞。你拒绝放手，导致无法获得新的成长。", advice: "今天适合放下过去，迎接新的开始。改变是成长的必经之路。" },
  { name: "节制", nameEn: "Temperance", emblem: "🌊", meaning: "平衡、调和、耐心。寻找中庸之道，调和内在的矛盾，保持平衡。", reversedMeaning: "失衡、过度。你可能在某个方面走极端，需要回归平衡。", advice: "今天需要保持中庸，避免走极端，寻找生活的平衡点。" },
  { name: "恶魔", nameEn: "The Devil", emblem: "😈", meaning: "束缚、欲望、阴影。直面内心的欲望和恐惧，认识自己的阴暗面。", reversedMeaning: "解脱、觉醒。你正在摆脱束缚，看清真相，获得自由。", advice: "今天适合审视自己的欲望和执念，觉察哪些在束缚你。" },
  { name: "高塔", nameEn: "The Tower", emblem: "⚡", meaning: "突变、崩塌、觉醒。突如其来的改变打破旧有结构，虽然痛苦但是必要的。", reversedMeaning: "抗拒改变、危机延迟。你在逃避不可避免的改变，但终究要面对。", advice: "今天可能有意外的冲击，但这是重建的契机，坦然接受。" },
  { name: "星星", nameEn: "The Star", emblem: "⭐", meaning: "希望、灵感、治愈。黑暗中看到了光芒，保持信念，未来充满希望。", reversedMeaning: "绝望、失去信心。你可能感到迷茫，但希望从未真正离开。", advice: "今天充满希望和灵感，相信自己的梦想，保持乐观。" },
  { name: "月亮", nameEn: "The Moon", emblem: "🌑", meaning: "幻觉、恐惧、潜意识。面对内心的恐惧，穿越迷雾方能看清真相。", reversedMeaning: "恐惧消散、真相显现。迷雾正在散去，真相即将揭晓。", advice: "今天可能会有困惑和不安，但不要被表象迷惑，耐心等待。" },
  { name: "太阳", nameEn: "The Sun", emblem: "☀️", meaning: "快乐、成功、活力。阳光普照，一切顺利，享受生命的美好时刻。", reversedMeaning: "暂时的阴霾、热情减退。快乐被暂时遮蔽，但太阳终会再次升起。", advice: "今天是充满能量和快乐的一天，尽情享受，分享你的光芒。" },
  { name: "审判", nameEn: "Judgement", emblem: "📯", meaning: "觉醒、重生、召唤。听到内心的召唤，做出改变，迎接新生。", reversedMeaning: "拒绝觉醒、自我怀疑。你忽视了内心的召唤，需要重新审视。", advice: "今天适合反思过去，做出重要的决定，迎接新的阶段。" },
  { name: "世界", nameEn: "The World", emblem: "🌍", meaning: "完成、圆满、成就。一个周期的圆满结束，你已经达成了目标。", reversedMeaning: "未完成、拖延。你接近完成但尚未达成，需要最后一步努力。", advice: "今天是一个圆满的日子，庆祝你的成就，准备迎接新的旅程。" },
]

const drawn = ref(false)
const card = ref<TarotCard & { isReversed: boolean }>({} as any)

const drawCard = () => {
  const idx = Math.floor(Math.random() * majorArcana.length)
  const isReversed = Math.random() > 0.5
  card.value = { ...majorArcana[idx], isReversed }
  drawn.value = true
}
</script>

<style scoped>
.tarot-page {
  height: 100vh; overflow-y: auto; padding: 20px;
  display: flex; justify-content: center; align-items: flex-start;
}
.tarot-card-a { width: 100%; max-width: 520px; padding: 28px; text-align: center; }
.tarot-header { margin-bottom: 24px; }
.tarot-header h2 { font-size: 22px; color: #b886e8; letter-spacing: 3px; }
.tarot-header p { font-size: 12px; color: var(--text-dim); margin-top: 6px; }
.tarot-deck { display: flex; justify-content: center; }
.deck-area { cursor: pointer; -webkit-user-select: none; user-select: none; }
.card-back {
  width: 180px; height: 280px; border-radius: 16px;
  background: linear-gradient(135deg, #2a1a4a, #1a0a2a);
  border: 2px solid rgba(184,134,232,0.4); display: flex;
  flex-direction: column; align-items: center; justify-content: center;
  transition: all 0.3s; box-shadow: 0 0 30px rgba(184,134,232,0.2);
}
.card-back:hover { transform: scale(1.05); border-color: rgba(184,134,232,0.7); box-shadow: 0 0 50px rgba(184,134,232,0.4); }
.card-back-pattern { font-size: 48px; color: rgba(184,134,232,0.5); margin-bottom: 16px; animation: pulse-glow 2s ease-in-out infinite; }
.card-back-text { font-size: 14px; color: rgba(184,134,232,0.7); letter-spacing: 2px; }
@keyframes pulse-glow { 0%, 100% { opacity: 0.5; } 50% { opacity: 1; } }
.tarot-result { animation: fadeIn 0.5s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
.drawn-card { width: 140px; height: 220px; margin: 0 auto 20px; border-radius: 14px;
  background: linear-gradient(135deg, #3a2a5a, #2a1a4a); border: 2px solid rgba(184,134,232,0.5);
  display: flex; align-items: center; justify-content: center; box-shadow: 0 0 40px rgba(184,134,232,0.3);
}
.drawn-card.reversed { transform: rotate(180deg); }
.drawn-card.reversed .card-face { transform: rotate(180deg); }
.card-face { text-align: center; }
.card-emblem { font-size: 40px; margin-bottom: 10px; }
.card-name { font-size: 16px; color: #b886e8; letter-spacing: 2px; }
.card-name-en { font-size: 11px; color: rgba(184,134,232,0.5); margin-top: 4px; }
.card-meaning, .card-advice { text-align: left; margin-top: 18px; }
.meaning-title { font-size: 13px; color: #b886e8; letter-spacing: 2px; margin-bottom: 8px; }
.card-meaning p, .card-advice p { font-size: 13px; color: var(--text-dim); line-height: 1.7; }
.drawn-card + .btn { margin-top: 20px; }
</style>