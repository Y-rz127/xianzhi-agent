<template>
  <div class="star-bg" aria-hidden="true">
    <div class="nebula"></div>
    <div class="stars">
      <span v-for="n in 60" :key="n" class="star" :style="starStyle(n)"></span>
    </div>
    <div class="runes">
      <svg class="bagua" viewBox="0 0 200 200">
        <circle cx="100" cy="100" r="96" fill="none" stroke="rgba(212,175,55,0.08)" stroke-width="1" />
        <circle cx="100" cy="100" r="78" fill="none" stroke="rgba(212,175,55,0.06)" stroke-width="1" stroke-dasharray="6 6" />
        <circle cx="100" cy="100" r="60" fill="none" stroke="rgba(138,92,246,0.08)" stroke-width="1" />
        <path d="M100,4 L100,196 M4,100 L196,100" stroke="rgba(212,175,55,0.05)" stroke-width="1" />
        <text x="100" y="18" text-anchor="middle" fill="rgba(212,175,55,0.12)" font-size="10">乾</text>
        <text x="100" y="192" text-anchor="middle" fill="rgba(212,175,55,0.12)" font-size="10">坤</text>
        <text x="16" y="104" text-anchor="middle" fill="rgba(212,175,55,0.12)" font-size="10">离</text>
        <text x="184" y="104" text-anchor="middle" fill="rgba(212,175,55,0.12)" font-size="10">坎</text>
      </svg>
    </div>
    <div class="glow-orb"></div>
  </div>
</template>

<script setup lang="ts">
const starStyle = (n: number) => {
  const top = Math.random() * 100
  const left = Math.random() * 100
  const size = Math.random() * 2 + 1
  const delay = Math.random() * 4
  const duration = Math.random() * 3 + 2
  return {
    top: `${top}%`,
    left: `${left}%`,
    width: `${size}px`,
    height: `${size}px`,
    animationDelay: `${delay}s`,
    animationDuration: `${duration}s`,
  }
}
</script>

<style scoped>
.star-bg {
  position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden;
}
.nebula {
  position: absolute; inset: -20%;
  background:
    radial-gradient(circle at 25% 35%, rgba(139, 92, 246, 0.12), transparent 35%),
    radial-gradient(circle at 75% 65%, rgba(212, 175, 55, 0.1), transparent 38%),
    radial-gradient(circle at 50% 50%, rgba(34, 211, 238, 0.05), transparent 45%);
  filter: blur(40px);
  animation: breathe 10s ease-in-out infinite;
}
.stars { position: absolute; inset: 0; }
.star {
  position: absolute; background: #fff; border-radius: 50%;
  box-shadow: 0 0 6px rgba(255,255,255,0.6);
  animation: twinkle var(--duration, 3s) ease-in-out infinite;
  animation-delay: var(--delay, 0s);
}
@keyframes twinkle {
  0%, 100% { opacity: 0.15; transform: scale(0.8); }
  50% { opacity: 0.9; transform: scale(1.2); }
}
.runes {
  position: absolute; right: -80px; top: -80px; width: 400px; height: 400px;
  opacity: 0.6; pointer-events: none;
}
.bagua { width: 100%; height: 100%; animation: spin-slow 60s linear infinite; }
.glow-orb {
  position: absolute; left: 10%; bottom: -120px; width: 300px; height: 300px;
  background: radial-gradient(circle, rgba(212,175,55,0.12), transparent 70%);
  border-radius: 50%; filter: blur(30px);
  animation: float 8s ease-in-out infinite;
}
</style>