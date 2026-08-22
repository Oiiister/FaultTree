<template>
  <canvas ref="canvasRef" class="absolute inset-0 pointer-events-none"></canvas>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  enabled: { type: Boolean, default: true },
  gravityDecay: { type: Number, default: 0.98 },
  lifeMs: { type: Number, default: 800 },
  count: { type: Number, default: 20 }
})

const canvasRef = ref(null)
let raf = 0
let lastTs = 0
const particles = []

const resize = () => {
  const canvas = canvasRef.value
  if (!canvas) return
  const parent = canvas.parentElement
  if (!parent) return
  const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1))
  const w = Math.max(1, parent.clientWidth)
  const h = Math.max(1, parent.clientHeight)
  canvas.width = Math.floor(w * dpr)
  canvas.height = Math.floor(h * dpr)
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`
  const ctx = canvas.getContext('2d')
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

const tick = (ts) => {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const dtMs = lastTs ? Math.min(34, ts - lastTs) : 16
  lastTs = ts

  ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight)
  const now = ts

  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]
    const age = now - p.birth
    if (age >= p.life) {
      particles.splice(i, 1)
      continue
    }
    const t = age / p.life
    p.vx *= props.gravityDecay
    p.vy *= props.gravityDecay
    p.vy += p.g
    p.x += p.vx * (dtMs / 16)
    p.y += p.vy * (dtMs / 16)

    const a = (1 - t) * p.alpha
    ctx.globalAlpha = a
    ctx.strokeStyle = p.color
    ctx.lineWidth = p.w
    ctx.beginPath()
    ctx.moveTo(p.x, p.y)
    ctx.lineTo(p.x - p.vx * 0.7, p.y - p.vy * 0.7)
    ctx.stroke()
  }
  ctx.globalAlpha = 1

  if (particles.length) raf = window.requestAnimationFrame(tick)
  else raf = 0
}

const burst = (x, y, { colorA = 'rgba(34, 211, 238, 0.95)', colorB = 'rgba(167,139,250,0.89)' } = {}) => {
  if (!props.enabled) return
  if (!canvasRef.value) return

  const base = performance.now()
  const n = Math.max(1, Math.floor(props.count))
  for (let i = 0; i < n; i++) {
    const ang = (Math.PI * 2 * i) / n + (Math.random() - 0.5) * 0.2
    const speed = 4.6 + Math.random() * 2.8
    const c = i % 2 === 0 ? colorA : colorB
    particles.push({
      x,
      y,
      vx: Math.cos(ang) * speed,
      vy: Math.sin(ang) * speed - 1.4,
      g: 0.14 + Math.random() * 0.08,
      w: 1.4 + Math.random() * 0.9,
      alpha: 0.9,
      color: c,
      birth: base,
      life: props.lifeMs
    })
  }

  if (!raf) {
    lastTs = 0
    raf = window.requestAnimationFrame(tick)
  }
}

defineExpose({ burst })

let ro = null

onMounted(() => {
  resize()
  window.addEventListener('resize', resize)
  if (typeof ResizeObserver !== 'undefined' && canvasRef.value?.parentElement) {
    ro = new ResizeObserver(resize)
    ro.observe(canvasRef.value.parentElement)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  ro?.disconnect()
  ro = null
  if (raf) window.cancelAnimationFrame(raf)
})

watch(
  () => props.enabled,
  (v) => {
    if (!v) {
      particles.length = 0
      if (raf) window.cancelAnimationFrame(raf)
      raf = 0
      lastTs = 0
      const canvas = canvasRef.value
      const ctx = canvas?.getContext?.('2d')
      if (canvas && ctx) ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight)
    }
  }
)
</script>

