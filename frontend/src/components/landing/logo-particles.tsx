'use client'

import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

/**
 * Scroll-scrubbed logo particle field (Canvas 2D, no dependency).
 *
 * The particle targets are sampled ONCE from the real SchemeKnit mark
 * (`/icons/icon-512.png`, the same navy/cyan artwork as `SchemeKnitMark`).
 * Scroll only moves those precomputed points; no pixels are re-sampled and no
 * random particles are generated per frame.
 *
 * The DOM logo remains the crisp initial state. The canvas crossfades in only
 * after the mark starts moving, so the first paint never waits for a loader.
 */

interface Props {
  trackRef: RefObject<HTMLElement | null>
  stageRef: RefObject<HTMLDivElement | null>
  markRef: RefObject<HTMLSpanElement | null>
  logoRef: RefObject<HTMLDivElement | null>
  copyRef: RefObject<HTMLDivElement | null>
  cueRef: RefObject<HTMLDivElement | null>
  className?: string
}

interface Particle {
  x: number
  y: number
  angle: number
  distance: number
  size: number
  phase: number
  swirl: number
  /** 0-2 cyan / 3-5 steel, indexing the three alpha bands. */
  bucket: number
}

const BUCKET_COLORS = [
  'rgb(66, 211, 239)',
  'rgb(66, 211, 239)',
  'rgb(66, 211, 239)',
  'rgb(158, 190, 207)',
  'rgb(158, 190, 207)',
  'rgb(158, 190, 207)',
]
const BUCKET_ALPHAS = [0.5, 0.68, 0.86, 0.5, 0.68, 0.86]

const LOGO_SOURCE = '/icons/icon-512.png'
const SAMPLE_SIZE = 112
const MOBILE_SAMPLE_SIZE = 96
const MAX_DESKTOP = 980
const MAX_MOBILE = 900

function clamp(value: number, min: number, max: number): number {
  return value < min ? min : value > max ? max : value
}

function smoothstep(edge0: number, edge1: number, value: number): number {
  if (edge0 === edge1) return value < edge0 ? 0 : 1
  const t = clamp((value - edge0) / (edge1 - edge0), 0, 1)
  return t * t * (3 - 2 * t)
}

/** Small deterministic PRNG so a resize rebuilds the same field. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function particleBucket(r: number, g: number, b: number, alpha: number): number {
  // Cyan artwork stays bright; the navy body becomes a light steel so it
  // remains visible on the #071826 stage without adding a glow.
  const isCyan = g > 105 && b > 125 && g > r * 1.8
  const band = alpha < 0.65 ? 0 : alpha < 0.85 ? 1 : 2
  return (isCyan ? 0 : 3) + band
}

export function LogoParticleCanvas({
  trackRef,
  stageRef,
  markRef,
  logoRef,
  copyRef,
  cueRef,
  className = '',
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const track = trackRef.current
    const stage = stageRef.current
    const mark = markRef.current
    const logo = logoRef.current
    const copy = copyRef.current
    const cue = cueRef.current
    if (!canvas || !track || !stage || !mark || !logo || !copy || !cue) return

    const ctx = canvas.getContext('2d', { alpha: true })
    if (!ctx) {
      track.dataset.fallback = 'true'
      return
    }

    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    let dpr = Math.min(window.devicePixelRatio || 1, 2)

    let disposed = false
    let ready = false
    let started = false
    let raf = 0
    let animationRaf = 0
    let resizeRaf = 0
    let active = true
    let currentProgress = 0
    let particles: Particle[] = []
    let stageW = 1
    let stageH = 1
    let image: HTMLImageElement | null = null

    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches
    const pointerCurrent = { x: 0, y: 0, strength: 0 }
    const pointerTarget = { x: 0, y: 0, strength: 0 }
    const pointerClient = { x: 0, y: 0, valid: false }
    let pointerInit = false

    const setFallback = () => {
      track.dataset.fallback = 'true'
      canvas.style.display = 'none'
      logo.style.visibility = 'visible'
      logo.style.opacity = '1'
      logo.style.transform = 'none'
      copy.style.visibility = 'visible'
      copy.style.opacity = '1'
      copy.style.transform = 'none'
      copy.style.pointerEvents = 'auto'
      cue.style.opacity = '1'
      cue.style.visibility = 'visible'
    }

    const progressFromScroll = (): number => {
      const trackRect = track.getBoundingClientRect()
      // The scrub runs through the hero and the “Inside the lesson” copy,
      // finishing only as the whole extended stage leaves the viewport.
      const distance = Math.max(1, trackRect.height * 0.82)
      return clamp(Math.max(0, -trackRect.top) / distance, 0, 1)
    }

    const draw = (progress: number, now: number) => {
      ctx.clearRect(0, 0, stageW, stageH)
      if (!ready || particles.length === 0) return

      const scatter = smoothstep(0.1, 0.6, progress)
      const fade = 1 - smoothstep(0.8, 0.98, progress)
      const breathe = 1 - smoothstep(0.32, 0.9, progress)
      const seconds = now * 0.001
      const drift = 0.65 + 5.6 * scatter
      const pointerRadius = stageW < 768 ? 118 : 165
      const pointerStrength = pointerCurrent.strength
      const pointerX = pointerCurrent.x
      const pointerY = pointerCurrent.y

      // Batch by colour and opacity band: six fills per frame instead of
      // 1,000+ fillStyle/globalAlpha changes. The per-particle geometry is
      // still unique; only the paint state is shared.
      for (let bucket = 0; bucket < 6; bucket += 1) {
        ctx.globalAlpha =
          BUCKET_ALPHAS[bucket] * fade * (0.8 + 0.2 * breathe)
        ctx.fillStyle = BUCKET_COLORS[bucket]
        ctx.beginPath()

        for (const particle of particles) {
          if (particle.bucket !== bucket) continue
          const t = scatter
          const angle = particle.angle + particle.swirl * t
          const distance = particle.distance * t
          let x =
            particle.x +
            Math.cos(angle) * distance +
            Math.sin(t * Math.PI + particle.phase) * 7 * t
          let y =
            particle.y +
            Math.sin(angle) * distance +
            Math.cos(t * Math.PI * 1.3 + particle.phase) * 9 * t

          // The cloud keeps breathing while the stage is visible.
          x += Math.sin(seconds * 0.52 + particle.phase) * drift
          y += Math.cos(seconds * 0.39 + particle.phase * 1.3) * drift * 0.78

          // A soft cursor lens: nearby particles drift away and swirl, then
          // settle when the pointer leaves.
          if (pointerStrength > 0.01) {
            const dx = x - pointerX
            const dy = y - pointerY
            const dist2 = dx * dx + dy * dy
            if (dist2 < pointerRadius * pointerRadius) {
              const dist = Math.sqrt(dist2) || 1
              const falloff = 1 - dist / pointerRadius
              const push = falloff * falloff * pointerStrength * 38
              const nx = dx / dist
              const ny = dy / dist
              x += nx * push - ny * push * 0.32
              y += ny * push + nx * push * 0.32
            }
          }

          const size = particle.size * (1 - 0.34 * t)
          // Sub-pixel dust reads as a dot at this size; the axis-aligned
          // batch is much cheaper than one arc path per particle.
          ctx.rect(x - size, y - size, size * 2, size * 2)
        }
        ctx.fill()
      }
      ctx.globalAlpha = 1
    }

    const stopLoop = () => {
      if (animationRaf) {
        window.cancelAnimationFrame(animationRaf)
        animationRaf = 0
      }
    }

    const startLoop = () => {
      if (
        disposed ||
        !ready ||
        animationRaf ||
        !active ||
        document.hidden ||
        motion.matches ||
        currentProgress <= 0.002 ||
        currentProgress >= 0.999
      ) {
        return
      }
      animationRaf = window.requestAnimationFrame(function tick(now) {
        animationRaf = 0
        if (disposed || !active || document.hidden || motion.matches) return
        pointerCurrent.x += (pointerTarget.x - pointerCurrent.x) * 0.16
        pointerCurrent.y += (pointerTarget.y - pointerCurrent.y) * 0.16
        pointerCurrent.strength +=
          (pointerTarget.strength - pointerCurrent.strength) * 0.12
        draw(currentProgress, now)
        if (currentProgress < 0.999) {
          animationRaf = window.requestAnimationFrame(tick)
        }
      })
    }

    const applyProgress = (progress: number) => {
      const p = clamp(progress, 0, 1)
      currentProgress = p

      const logoOpacity = 1 - smoothstep(0.01, 0.1, p)
      const copyOpacity = 1 - smoothstep(0.5, 0.78, p)
      const cueOpacity = 1 - smoothstep(0.008, 0.05, p)
      const particleOpacity =
        smoothstep(0.01, 0.06, p) * (1 - smoothstep(0.8, 0.98, p))

      stage.style.setProperty('--hero-progress', p.toFixed(4))
      stage.dataset.phase =
        p < 0.08
          ? 'logo'
          : p < 0.6
            ? 'dispersion'
            : p < 0.98
              ? 'dissipation'
              : 'complete'

      logo.style.opacity = logoOpacity.toFixed(3)
      logo.style.transform = `translate3d(0, ${(-16 * p).toFixed(2)}px, 0)`
      logo.style.visibility = logoOpacity <= 0.01 ? 'hidden' : 'visible'

      copy.style.opacity = copyOpacity.toFixed(3)
      copy.style.transform = `translate3d(0, ${(-10 * p).toFixed(2)}px, 0)`
      copy.style.pointerEvents = copyOpacity < 0.35 ? 'none' : 'auto'
      copy.style.visibility = copyOpacity <= 0.01 ? 'hidden' : 'visible'

      cue.style.opacity = cueOpacity.toFixed(3)
      cue.style.visibility = cueOpacity <= 0.01 ? 'hidden' : 'visible'

      canvas.style.opacity = particleOpacity.toFixed(3)

      // Keep the intact field painted at progress 0 (canvas transparent),
      // then animate only while the dissolving field is actually visible.
      if (p <= 0.002 || p >= 0.999) {
        stopLoop()
        draw(p, performance.now())
      } else {
        startLoop()
      }
    }

    const updatePointer = (clientX: number, clientY: number) => {
      const rect = stage.getBoundingClientRect()
      pointerTarget.x = clientX - rect.left
      pointerTarget.y = clientY - rect.top
      if (!pointerInit) {
        pointerCurrent.x = pointerTarget.x
        pointerCurrent.y = pointerTarget.y
        pointerInit = true
      }
      pointerTarget.strength = 1
      pointerClient.x = clientX
      pointerClient.y = clientY
      pointerClient.valid = true
      stage.dataset.pointer = 'active'
    }

    const onPointerMove = (event: PointerEvent) => {
      updatePointer(event.clientX, event.clientY)
      startLoop()
    }

    const onPointerLeave = () => {
      pointerTarget.strength = 0
      stage.dataset.pointer = 'idle'
    }

    const syncPointer = () => {
      if (pointerTarget.strength > 0 && pointerClient.valid) {
        updatePointer(pointerClient.x, pointerClient.y)
      }
    }

    const resizeCanvas = () => {
      const stageRect = stage.getBoundingClientRect()
      stageW = Math.max(1, stageRect.width)
      stageH = Math.max(1, stageRect.height)
      canvas.width = Math.round(stageW * dpr)
      canvas.height = Math.round(stageH * dpr)
      canvas.style.width = `${stageW}px`
      canvas.style.height = `${stageH}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const buildParticles = (image: HTMLImageElement) => {
      if (disposed) return
      const stageRect = stage.getBoundingClientRect()
      const markRect = mark.getBoundingClientRect()
      if (stageRect.width < 40 || stageRect.height < 40 || markRect.width < 20) {
        return
      }

      dpr = Math.min(window.devicePixelRatio || 1, 2)
      resizeCanvas()

      const mobile = window.matchMedia('(max-width: 767px)').matches
      const sample = mobile ? MOBILE_SAMPLE_SIZE : SAMPLE_SIZE
      const offscreen = document.createElement('canvas')
      offscreen.width = sample
      offscreen.height = sample
      const offCtx = offscreen.getContext('2d', { alpha: true })
      if (!offCtx) {
        setFallback()
        return
      }
      offCtx.clearRect(0, 0, sample, sample)
      offCtx.drawImage(image, 0, 0, sample, sample)
      let pixels: Uint8ClampedArray
      try {
        pixels = offCtx.getImageData(0, 0, sample, sample).data
      } catch {
        setFallback()
        return
      }

      const markX = markRect.left - stageRect.left
      const markY = markRect.top - stageRect.top
      const markW = Math.max(1, markRect.width)
      const markH = Math.max(1, markRect.height)
      const maxParticles = mobile ? MAX_MOBILE : MAX_DESKTOP
      const candidates: Particle[] = []

      // A 2px stride at this sample size gives roughly 900-1,500 hits; the
      // deterministic shuffle below caps the field without grid artefacts.
      for (let y = 0; y < sample; y += 2) {
        for (let x = 0; x < sample; x += 2) {
          const index = (y * sample + x) * 4
          const r = pixels[index]
          const g = pixels[index + 1]
          const b = pixels[index + 2]
          const a = pixels[index + 3]
          if (a < 40) continue

          const nx = (x + 0.5) / sample
          const ny = (y + 0.5) / sample
          const rand = mulberry32(
            ((x + 1) * 73856093) ^ ((y + 1) * 19349663) ^ (sample * 83492791),
          )
          const dx = nx - 0.5
          const dy = ny - 0.5
          const baseAngle = Math.atan2(dy, dx)
          // A controlled downward share carries the cloud through the
          // “Inside the lesson” copy instead of letting half of it leave
          // sideways on a narrow phone viewport.
          const downward = rand() < (mobile ? 0.62 : 0.46)
          const angle = downward
            ? Math.PI / 2 + (rand() - 0.5) * 1.15
            : baseAngle + (rand() - 0.5) * 1.35
          const distance = downward
            ? stageH * (0.35 + rand() * 0.55)
            : stageH * (0.22 + rand() * 0.58)
          const alpha = 0.45 + rand() * 0.5

          candidates.push({
            x: markX + nx * markW,
            y: markY + ny * markH,
            angle,
            // The field fades before the next section, so off-screen
            // horizontal drift is harmless.
            distance: distance + Math.abs(dx) * 46,
            size: 0.72 + rand() * (mobile ? 1.7 : 2.15),
            phase: rand() * Math.PI * 2,
            swirl: (rand() - 0.5) * 1.1,
            bucket: particleBucket(r, g, b, alpha),
          })
        }
      }

      if (candidates.length === 0) {
        setFallback()
        return
      }

      if (candidates.length > maxParticles) {
        const shuffle = mulberry32(0x5eedc0de)
        for (let i = candidates.length - 1; i > 0; i -= 1) {
          const j = Math.floor(shuffle() * (i + 1))
          const tmp = candidates[i]
          candidates[i] = candidates[j]
          candidates[j] = tmp
        }
        candidates.length = maxParticles
      }

      candidates.sort((a, b) => b.size - a.size)
      particles = candidates
      ready = true
      canvas.dataset.particles = String(particles.length)
      track.dataset.ready = 'true'
      currentProgress = progressFromScroll()
      draw(currentProgress, performance.now())
    }

    const schedule = () => {
      if (disposed || !ready || !active) return
      if (raf) return
      raf = window.requestAnimationFrame(() => {
        raf = 0
        if (!disposed && active) {
          applyProgress(progressFromScroll())
          syncPointer()
        }
      })
    }

    const onScroll = () => {
      schedule()
      syncPointer()
    }

    const onVisibility = () => {
      if (document.hidden) {
        if (raf) {
          window.cancelAnimationFrame(raf)
          raf = 0
        }
        stopLoop()
        return
      }
      schedule()
      startLoop()
    }

    const rebuild = () => {
      if (disposed) return
      if (resizeRaf) window.cancelAnimationFrame(resizeRaf)
      resizeRaf = window.requestAnimationFrame(() => {
        resizeRaf = 0
        image?.decode?.().catch(() => undefined)
        if (image?.complete && image.naturalWidth > 0) {
          buildParticles(image)
          schedule()
        }
      })
    }

    const observer = new ResizeObserver(rebuild)
    observer.observe(stage)
    observer.observe(mark)

    const intersection = new IntersectionObserver(
      ([entry]) => {
        active = entry.isIntersecting
        if (active) {
          schedule()
          startLoop()
        } else {
          stopLoop()
        }
      },
      { rootMargin: '12% 0px', threshold: 0 },
    )
    intersection.observe(track)

    image = new Image()
    image.decoding = 'async'
    image.src = LOGO_SOURCE

    const start = () => {
      if (disposed || started || !image) return
      started = true
      if (motion.matches) {
        track.dataset.motion = 'reduced'
        buildParticles(image)
        return
      }
      buildParticles(image)
      applyProgress(progressFromScroll())
      startLoop()
      if (finePointer) {
        stage.dataset.pointer = 'idle'
        stage.addEventListener('pointermove', onPointerMove, { passive: true })
        stage.addEventListener('pointerleave', onPointerLeave, { passive: true })
        stage.addEventListener('pointercancel', onPointerLeave, { passive: true })
      }
      window.addEventListener('scroll', onScroll, { passive: true })
      document.addEventListener('visibilitychange', onVisibility)
      window.addEventListener('resize', rebuild, { passive: true })
    }

    image.onload = start
    image.onerror = () => {
      if (!disposed) setFallback()
    }
    // Cached images may have completed before the handler was attached.
    if (image.complete && image.naturalWidth > 0) start()

    const onMotionChange = () => {
      if (motion.matches) {
        track.dataset.motion = 'reduced'
        if (raf) {
          window.cancelAnimationFrame(raf)
          raf = 0
        }
        stopLoop()
        window.removeEventListener('scroll', onScroll)
        canvas.style.display = 'none'
        logo.style.visibility = 'visible'
        logo.style.opacity = '1'
        copy.style.visibility = 'visible'
        copy.style.opacity = '1'
        copy.style.pointerEvents = 'auto'
      } else {
        track.dataset.motion = ''
        canvas.style.display = ''
        applyProgress(progressFromScroll())
        startLoop()
        window.addEventListener('scroll', onScroll, { passive: true })
      }
    }
    motion.addEventListener?.('change', onMotionChange)

    return () => {
      disposed = true
      if (raf) window.cancelAnimationFrame(raf)
      stopLoop()
      if (resizeRaf) window.cancelAnimationFrame(resizeRaf)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', rebuild)
      document.removeEventListener('visibilitychange', onVisibility)
      stage.removeEventListener('pointermove', onPointerMove)
      stage.removeEventListener('pointerleave', onPointerLeave)
      stage.removeEventListener('pointercancel', onPointerLeave)
      motion.removeEventListener?.('change', onMotionChange)
      observer.disconnect()
      intersection.disconnect()
    }
  }, [trackRef, stageRef, markRef, logoRef, copyRef, cueRef])

  return (
    <canvas
      ref={canvasRef}
      data-mesh="logo-particles"
      data-particle-canvas
      aria-hidden="true"
      className={className}
    />
  )
}
