'use client'

import { useEffect, useRef } from 'react'

/**
 * Interactive curriculum mesh (Hero V4).
 *
 * Connected flexible surface: grid nodes + neighbour springs + pointer force
 * with strong central lens bulge, elastic return, touch wake, and depth cues.
 * Canvas 2D only — no WebGL, no React re-renders per frame.
 *
 * Pointer model (V4): unified Pointer Events for mouse / pen / touch.
 *  - Mouse: hover-driven deformation (V3 desktop behaviour preserved).
 *  - Touch/pen: press-driven — strong bulge on down, interpolated drag with a
 *    short-lived trail that deforms the same network, velocity-scaled wake,
 *    and a ~250–700ms decay on release (springs finish the settle).
 *  - Passive listeners only; never preventDefault — page scroll stays natural.
 *
 * Landing-exclusive: do not mount on auth/activation routes.
 */

type MeshMode = 'hero' | 'ambient'

export interface MeshBackgroundProps {
  mode?: MeshMode
  className?: string
  opacity?: number
}

interface Node {
  ox: number
  oy: number
  x: number
  y: number
  vx: number
  vy: number
  /** Neighbor average displacement for membrane cohesion (scratch). */
  lx: number
  ly: number
  phase: number
  accent: boolean
  elevation: number
}

/** Short-lived previous pointer positions — drives the trailing wake. */
interface TrailPoint {
  x: number
  y: number
  t: number
  w: number
}

const ACCENT_LABELS = ['SCHEME', 'SUBJECT', 'WEEK', 'INDICATOR', 'PERIOD', 'LESSON']

/** Wake history: ~9 samples over ~480ms — enough for a soft elongated trail. */
const TRAIL_MAX = 9
const TRAIL_LIFE = 480
/** Hard clamp on pointer velocity so fast flicks cannot explode the mesh. */
const VEL_CLAMP = 55

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

function isFinePointer(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(hover: hover) and (pointer: fine)').matches
  )
}

function isCoarsePointer(): boolean {
  return (
    typeof window !== 'undefined' && window.matchMedia('(pointer: coarse)').matches
  )
}

/** 1 at center → 0 at radius edge, smooth, then power-shaped for a strong core. */
function lensFalloff(dist: number, radius: number, power: number): number {
  if (dist >= radius || radius <= 0) return 0
  const t = dist / radius
  const inv = 1 - t
  // smoothstep on inverted t: soft shoulder, strong core
  const s = inv * inv * (3 - 2 * inv)
  return Math.pow(s, power)
}

function clamp(v: number, min: number, max: number): number {
  return v < min ? min : v > max ? max : v
}

export function MeshBackground({
  mode = 'hero',
  className = '',
  opacity = 1,
}: MeshBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return
    const ctx = canvas.getContext('2d', { alpha: true })
    if (!ctx) return

    const canvasEl: HTMLCanvasElement = canvas
    const wrapEl: HTMLDivElement = wrap

    const reduce = prefersReducedMotion()
    // V4: interactive on any pointer type (touch included). Reduced motion → static only.
    const interactive = !reduce && mode === 'hero'
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    // Mobile tune: coarse primary pointer or compact viewport.
    const mobileTune = isCoarsePointer() || window.innerWidth < 768

    let width = 0
    let height = 0
    let cols = 0
    let rows = 0
    let spacing = 0
    let nodes: Node[] = []
    let raf = 0
    let running = true
    const t0 = performance.now()
    let last = t0
    let frameCost = 0

    const pointer = {
      x: -9999,
      y: -9999,
      px: -9999,
      py: -9999,
      vx: 0,
      vy: 0,
      active: false,
      /** True while touch/pen is held down (or mouse button held). */
      pressed: false,
      pointerType: 'mouse' as string,
      tx: -9999,
      ty: -9999,
      strength: 0,
      /** Faster strength decay after an explicit release (touch up / cancel). */
      releaseFast: false,
    }

    /** Temporal wake: recent smoothed pointer samples, deforms the network. */
    const trail: TrailPoint[] = []

    // V3 desktop tuning preserved; V4 mobile variant: lower density, larger
    // influence radius, stronger local push, softer damping, velocity wake.
    const cfg =
      mode === 'hero'
        ? mobileTune
          ? {
              baseSpacing: 54,
              minCols: 12,
              maxCols: 28,
              spring: 0.048,
              damping: 0.89,
              neighborBlend: 0.14,
              influenceRadius: 235,
              pushStrength: 64,
              tangential: 0.14,
              ambientAmp: 1.6,
              ambientSpeed: 0.00032,
              lineBase: 0.075,
              lineBoost: 0.55,
              nodeBase: 0.18,
              accentEvery: 12,
              lensPower: 2.1,
              velocityGain: 0.65,
              elevationGain: 1.8,
            }
          : {
              baseSpacing: 42,
              minCols: 18,
              maxCols: 42,
              spring: 0.048,
              damping: 0.86,
              neighborBlend: 0.14,
              influenceRadius: 200,
              pushStrength: 52,
              tangential: 0.14,
              ambientAmp: 1.6,
              ambientSpeed: 0.00032,
              lineBase: 0.075,
              lineBoost: 0.55,
              nodeBase: 0.18,
              accentEvery: 13,
              lensPower: 2.1,
              velocityGain: 0.55,
              elevationGain: 1.6,
            }
        : {
            baseSpacing: 56,
            minCols: 10,
            maxCols: 24,
            spring: 0.05,
            damping: 0.86,
            neighborBlend: 0.08,
            influenceRadius: 0,
            pushStrength: 0,
            tangential: 0,
            ambientAmp: 1.4,
            ambientSpeed: 0.00022,
            lineBase: 0.055,
            lineBoost: 0,
            nodeBase: 0.14,
            accentEvery: 14,
            lensPower: 2,
            velocityGain: 0,
            elevationGain: 0,
          }

    const effectiveSpacing =
      mode === 'ambient'
        ? Math.max(cfg.baseSpacing, Math.round(56 * Math.min(2, window.innerWidth / 430)))
        : cfg.baseSpacing

    function buildGrid() {
      const rect = wrapEl.getBoundingClientRect()
      width = Math.max(1, Math.floor(rect.width))
      height = Math.max(1, Math.floor(rect.height))
      canvasEl.width = Math.floor(width * dpr)
      canvasEl.height = Math.floor(height * dpr)
      canvasEl.style.width = `${width}px`
      canvasEl.style.height = `${height}px`
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)

      cols = Math.min(
        cfg.maxCols,
        Math.max(cfg.minCols, Math.round(width / effectiveSpacing)),
      )
      spacing = width / Math.max(1, cols - 1)
      rows = Math.max(4, Math.ceil(height / spacing) + 1)

      nodes = []
      let accentIdx = 0
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const jitterX = ((r * 17 + c * 31) % 7) / 7 - 0.5
          const jitterY = ((r * 13 + c * 19) % 5) / 5 - 0.5
          const ox = c * spacing + jitterX * spacing * 0.14
          const oy = r * spacing + jitterY * spacing * 0.14
          const accent = accentIdx > 0 && accentIdx % cfg.accentEvery === 0
          accentIdx++
          nodes.push({
            ox,
            oy,
            x: ox,
            y: oy,
            vx: 0,
            vy: 0,
            lx: 0,
            ly: 0,
            phase: (r * 0.37 + c * 0.61) % (Math.PI * 2),
            accent,
            elevation: 0,
          })
        }
      }
      // Reset pointer scale after rebuild (prevents huge stale displacement).
      pointer.px = pointer.x
      pointer.py = pointer.y
      pointer.vx = 0
      pointer.vy = 0
      trail.length = 0
    }

    function idx(r: number, c: number): number {
      return r * cols + c
    }

    function localPoint(e: PointerEvent | MouseEvent): { x: number; y: number; inside: boolean } {
      const rect = wrapEl.getBoundingClientRect()
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top
      const inside = x >= 0 && y >= 0 && x <= rect.width && y <= rect.height
      return { x, y, inside }
    }

    function isTouchLike(type: string): boolean {
      return type === 'touch' || type === 'pen'
    }

    /** Touch/pen down: strong controlled local bulge at the touch point. */
    function onPointerDown(e: PointerEvent) {
      if (!interactive) return
      const type = e.pointerType || 'mouse'
      const { x, y, inside } = localPoint(e)
      if (!inside) return
      pointer.pointerType = type
      pointer.pressed = true
      pointer.tx = x
      pointer.ty = y
      if (pointer.x < -1000) {
        pointer.x = x
        pointer.y = y
        pointer.px = x
        pointer.py = y
      }
      pointer.active = true
      pointer.releaseFast = false
      // Obvious but controlled press — not a giant shockwave.
      pointer.strength = Math.max(pointer.strength, isTouchLike(type) ? 0.62 : 0.5)
    }

    function onPointerMove(e: PointerEvent) {
      if (!interactive) return
      const type = e.pointerType || 'mouse'
      // Touch/pen has no hover — only track while pressed. Prevents stale
      // compatibility mouse events from re-arming after lift.
      if (isTouchLike(type) && !pointer.pressed) return
      const { x, y, inside } = localPoint(e)
      pointer.pointerType = type
      pointer.tx = x
      pointer.ty = y
      // Mouse: hover-driven (V3). Touch/pen: active only inside the hero.
      pointer.active = inside
    }

    /** Release: decay in place — no instant reset; springs finish the settle. */
    function onPointerUp(e: PointerEvent) {
      const type = e.pointerType || 'mouse'
      pointer.pressed = false
      if (isTouchLike(type)) {
        pointer.active = false
        pointer.releaseFast = true
        pointer.tx = -9999
        pointer.ty = -9999
        // Keep velocity — it bleeds off with strength for a natural spring-back.
        return
      }
      // Mouse button up: keep hover influence if still inside.
      const { inside } = localPoint(e)
      pointer.active = inside
      if (!inside) {
        pointer.tx = -9999
        pointer.ty = -9999
      }
    }

    function onPointerCancel() {
      pointer.pressed = false
      pointer.active = false
      pointer.releaseFast = true
      pointer.tx = -9999
      pointer.ty = -9999
    }

    function onPointerLeave() {
      pointer.pressed = false
      pointer.active = false
      pointer.releaseFast = true
      pointer.tx = -9999
      pointer.ty = -9999
    }

    /** Hard release — no stale coordinates after hide / rotate / blur. */
    function releasePointerHard() {
      pointer.pressed = false
      pointer.active = false
      pointer.releaseFast = true
      pointer.tx = -9999
      pointer.ty = -9999
      pointer.vx = 0
      pointer.vy = 0
      trail.length = 0
    }

    function drawStatic() {
      ctx!.clearRect(0, 0, width, height)
      const a = opacity
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const n = nodes[idx(r, c)]
          if (c < cols - 1) {
            const right = nodes[idx(r, c + 1)]
            ctx!.strokeStyle = `rgba(197, 210, 223, ${cfg.lineBase * a})`
            ctx!.lineWidth = 1
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(right.x, right.y)
            ctx!.stroke()
          }
          if (r < rows - 1) {
            const down = nodes[idx(r + 1, c)]
            ctx!.strokeStyle = `rgba(197, 210, 223, ${cfg.lineBase * a * 0.9})`
            ctx!.lineWidth = 1
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(down.x, down.y)
            ctx!.stroke()
          }
          if (c < cols - 1 && r < rows - 1) {
            const diag = nodes[idx(r + 1, c + 1)]
            ctx!.strokeStyle = `rgba(4, 169, 206, ${cfg.lineBase * a * 0.45})`
            ctx!.lineWidth = 1
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(diag.x, diag.y)
            ctx!.stroke()
          }
          if (n.accent) {
            ctx!.fillStyle = `rgba(4, 169, 206, ${0.5 * a})`
            ctx!.beginPath()
            ctx!.arc(n.x, n.y, 2.2, 0, Math.PI * 2)
            ctx!.fill()
          } else {
            ctx!.fillStyle = `rgba(197, 210, 223, ${cfg.nodeBase * a})`
            ctx!.beginPath()
            ctx!.arc(n.x, n.y, 1.3, 0, Math.PI * 2)
            ctx!.fill()
          }
        }
      }
    }

    function frame(now: number) {
      if (!running) return
      const dt = Math.min(48, now - last)
      last = now
      const elapsed = now - t0
      const start = now

      // Interpolated pointer + velocity for momentum / lag.
      if (interactive && pointer.active) {
        const prevX = pointer.x
        const prevY = pointer.y
        if (pointer.x < -1000) {
          pointer.x = pointer.tx
          pointer.y = pointer.ty
          pointer.px = pointer.tx
          pointer.py = pointer.ty
        } else {
          pointer.x += (pointer.tx - pointer.x) * 0.18
          pointer.y += (pointer.ty - pointer.y) * 0.18
        }
        pointer.vx = (pointer.x - prevX) * 0.85 + pointer.vx * 0.15
        pointer.vy = (pointer.y - prevY) * 0.85 + pointer.vy * 0.15
        // Clamp velocity — fast finger/mouse flicks must not explode the mesh.
        pointer.vx = clamp(pointer.vx, -VEL_CLAMP, VEL_CLAMP)
        pointer.vy = clamp(pointer.vy, -VEL_CLAMP, VEL_CLAMP)

        const velMag = Math.hypot(pointer.vx, pointer.vy)
        const still = velMag < 0.45
        let target = 1
        if (pointer.pressed && still) {
          // Finger holding still → slow pulsing/settling feel.
          target = 1 + 0.05 * Math.sin(elapsed * 0.0045)
        }
        // Fast movement → slightly stronger elongated wake energy (clamped).
        target = Math.min(1.12, target + velMag * 0.0035)
        pointer.strength += (target - pointer.strength) * 0.16

        // Record trail samples from the smoothed position (wake follows the finger).
        const lastT = trail[trail.length - 1]
        if (
          !lastT ||
          Math.hypot(pointer.x - lastT.x, pointer.y - lastT.y) > 8 ||
          now - lastT.t > 55
        ) {
          trail.push({ x: pointer.x, y: pointer.y, t: now, w: 1 })
          if (trail.length > TRAIL_MAX) trail.shift()
        }
      } else {
        // Release / leave → active influence decays (~250–700ms when fast),
        // while spring physics returns nodes to rest.
        const k = pointer.releaseFast ? 0.1 : 0.055
        pointer.strength += (0 - pointer.strength) * k
        if (pointer.strength < 0.008) {
          pointer.strength = 0
          pointer.releaseFast = false
          pointer.vx *= 0.85
          pointer.vy *= 0.85
        }
      }

      // Prune expired wake samples.
      while (trail.length > 0 && now - trail[0].t > TRAIL_LIFE) trail.shift()

      ctx!.clearRect(0, 0, width, height)
      const a = opacity
      const R = cfg.influenceRadius
      const velMag = Math.min(40, Math.hypot(pointer.vx, pointer.vy))
      const trailActive =
        interactive && trail.length > 0 && R > 0 && pointer.strength > 0.01
      const trailR = R * 0.6

      // Pass 1 — forces: ambient rest + cursor/finger lens + wake + spring
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i]
        const ambX = Math.sin(elapsed * cfg.ambientSpeed + n.phase) * cfg.ambientAmp
        const ambY =
          Math.cos(elapsed * cfg.ambientSpeed * 0.85 + n.phase * 1.1) * cfg.ambientAmp
        const restX = n.ox + ambX
        const restY = n.oy + ambY

        let fx = (restX - n.x) * cfg.spring
        let fy = (restY - n.y) * cfg.spring

        n.elevation = 0

        if (interactive && pointer.strength > 0.001 && R > 0) {
          const dx = n.x - pointer.x
          const dy = n.y - pointer.y
          const d = Math.hypot(dx, dy)
          if (d < R && d > 0.001) {
            const fall = lensFalloff(d, R, cfg.lensPower) * pointer.strength
            const nx = dx / d
            const ny = dy / d
            // Strong outward radial push → local surface bulge / lens.
            const push = fall * cfg.pushStrength
            fx += nx * push
            fy += ny * push
            // Slight tangential shear for fabric elasticity.
            fx += -ny * push * cfg.tangential
            fy += nx * push * cfg.tangential
            // Velocity coupling — fast cursor/finger imparts momentum (lag/inertia).
            fx += pointer.vx * fall * cfg.velocityGain
            fy += pointer.vy * fall * cfg.velocityGain
            n.elevation = fall
          }
        }

        // Trailing wake — short-lived previous touch positions bend the SAME
        // network (not a decorative overlay circle).
        if (trailActive) {
          for (let t = 0; t < trail.length; t++) {
            const tp = trail[t]
            const age = now - tp.t
            if (age > TRAIL_LIFE) continue
            const life = 1 - age / TRAIL_LIFE
            const w = life * life * 0.4 * tp.w * pointer.strength
            if (w < 0.03) continue
            const dx = n.x - tp.x
            const dy = n.y - tp.y
            const d = Math.hypot(dx, dy)
            if (d < trailR && d > 0.001) {
              const fall = lensFalloff(d, trailR, cfg.lensPower) * w
              const nx = dx / d
              const ny = dy / d
              const push = fall * cfg.pushStrength * 0.45
              fx += nx * push
              fy += ny * push
              if (fall * 0.75 > n.elevation) n.elevation = fall * 0.75
            }
          }
        }

        n.vx = (n.vx + fx) * cfg.damping
        n.vy = (n.vy + fy) * cfg.damping
        if (dt > 32) {
          n.vx *= 0.98
          n.vy *= 0.98
        }
      }

      // Pass 2 — neighbour membrane smoothing (coherent surface, not isolated dots).
      if (cfg.neighborBlend > 0 && cols > 1 && rows > 1) {
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) {
            const n = nodes[idx(r, c)]
            let sx = 0
            let sy = 0
            let count = 0
            if (c > 0) {
              const w = nodes[idx(r, c - 1)]
              sx += w.x
              sy += w.y
              count++
            }
            if (c < cols - 1) {
              const w = nodes[idx(r, c + 1)]
              sx += w.x
              sy += w.y
              count++
            }
            if (r > 0) {
              const w = nodes[idx(r - 1, c)]
              sx += w.x
              sy += w.y
              count++
            }
            if (r < rows - 1) {
              const w = nodes[idx(r + 1, c)]
              sx += w.x
              sy += w.y
              count++
            }
            n.lx = count ? sx / count : n.x
            n.ly = count ? sy / count : n.y
          }
        }
        for (let i = 0; i < nodes.length; i++) {
          const n = nodes[i]
          n.vx += (n.lx - n.x) * cfg.neighborBlend
          n.vy += (n.ly - n.y) * cfg.neighborBlend
          n.x += n.vx
          n.y += n.vy
        }
      } else {
        for (let i = 0; i < nodes.length; i++) {
          const n = nodes[i]
          n.x += n.vx
          n.y += n.vy
        }
      }

      // Draw membrane
      let accentCount = 0
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const n = nodes[idx(r, c)]
          let boost = n.elevation * pointer.strength

          if (c < cols - 1) {
            const right = nodes[idx(r, c + 1)]
            const midEl = (n.elevation + right.elevation) * 0.5 * pointer.strength
            const alpha = (cfg.lineBase + midEl * cfg.lineBoost) * a
            ctx!.strokeStyle =
              midEl > 0.12
                ? `rgba(126, 220, 240, ${alpha})`
                : `rgba(197, 210, 223, ${alpha * 0.9})`
            ctx!.lineWidth = 1 + midEl * 0.7
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(right.x, right.y)
            ctx!.stroke()
          }
          if (r < rows - 1) {
            const down = nodes[idx(r + 1, c)]
            const midEl = (n.elevation + down.elevation) * 0.5 * pointer.strength
            const alpha = (cfg.lineBase * 0.92 + midEl * cfg.lineBoost * 0.9) * a
            ctx!.strokeStyle =
              midEl > 0.12
                ? `rgba(126, 220, 240, ${alpha})`
                : `rgba(197, 210, 223, ${alpha * 0.9})`
            ctx!.lineWidth = 1 + midEl * 0.65
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(down.x, down.y)
            ctx!.stroke()
          }
          if (c < cols - 1 && r < rows - 1) {
            const diag = nodes[idx(r + 1, c + 1)]
            const midEl = (n.elevation + diag.elevation) * 0.5 * pointer.strength
            const alpha = (cfg.lineBase * 0.5 + midEl * cfg.lineBoost * 0.55) * a
            ctx!.strokeStyle = `rgba(4, 169, 206, ${alpha})`
            ctx!.lineWidth = 1
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(diag.x, diag.y)
            ctx!.stroke()
          }

          // Depth: elevated nodes read larger + brighter near cursor/finger.
          const elev = n.elevation * pointer.strength * cfg.elevationGain
          if (boost > 0.15) {
            ctx!.fillStyle = `rgba(4, 169, 206, ${boost * 0.1 * a})`
            ctx!.beginPath()
            ctx!.arc(n.x, n.y, 2.4 + boost * 4, 0, Math.PI * 2)
            ctx!.fill()
          }

          if (n.accent) {
            accentCount++
            const pulse = 0.5 + 0.22 * Math.sin(elapsed * 0.002 + n.phase)
            const alpha = Math.min(1, pulse + boost * 0.35) * a
            ctx!.fillStyle = `rgba(4, 169, 206, ${alpha})`
            ctx!.beginPath()
            ctx!.arc(n.x, n.y, 2.4 + elev * 1.4, 0, Math.PI * 2)
            ctx!.fill()
            if (accentCount % 4 === 1) {
              ctx!.fillStyle = `rgba(126, 220, 240, ${(0.14 + boost * 0.22) * a})`
              ctx!.font = '600 8px ui-sans-serif, system-ui, sans-serif'
              ctx!.fillText(
                ACCENT_LABELS[(accentCount - 1) % ACCENT_LABELS.length],
                n.x + 6,
                n.y - 5,
              )
            }
          } else {
            ctx!.fillStyle = `rgba(197, 210, 223, ${(cfg.nodeBase + boost * 0.4) * a})`
            ctx!.beginPath()
            ctx!.arc(n.x, n.y, 1.25 + boost * 1.5, 0, Math.PI * 2)
            ctx!.fill()
          }
          boost = 0
        }
      }

      // Soft lens light under the cursor/finger (depth cue, not a neon ring).
      if (interactive && pointer.strength > 0.08 && R > 0) {
        const g = ctx!.createRadialGradient(
          pointer.x,
          pointer.y,
          0,
          pointer.x,
          pointer.y,
          R * 0.9,
        )
        g.addColorStop(0, `rgba(4, 169, 206, ${0.09 * pointer.strength * a})`)
        g.addColorStop(0.55, `rgba(4, 169, 206, ${0.035 * pointer.strength * a})`)
        g.addColorStop(1, 'rgba(4, 169, 206, 0)')
        ctx!.fillStyle = g
        ctx!.beginPath()
        ctx!.arc(pointer.x, pointer.y, R * 0.9, 0, Math.PI * 2)
        ctx!.fill()
        // Soft outer wake from velocity
        if (velMag > 4) {
          ctx!.fillStyle = `rgba(126, 220, 240, ${Math.min(0.06, velMag * 0.0015) * a})`
          ctx!.beginPath()
          ctx!.arc(
            pointer.x - pointer.vx * 2,
            pointer.y - pointer.vy * 2,
            R * 0.45,
            0,
            Math.PI * 2,
          )
          ctx!.fill()
        }
      }

      frameCost = performance.now() - start
      // Adaptive: if frames are consistently heavy, pause non-essential labels next frames (cheap guard).
      if (frameCost > 40 && nodes.length > 800) {
        // already drawn; no further action needed — density is viewport-capped
      }

      raf = requestAnimationFrame(frame)
    }

    function onVisibility() {
      if (document.hidden) {
        releasePointerHard()
        running = false
        cancelAnimationFrame(raf)
      } else if (!running && !reduce) {
        running = true
        last = performance.now()
        raf = requestAnimationFrame(frame)
      }
    }

    function onOrientation() {
      releasePointerHard()
      buildGrid()
      if (reduce) drawStatic()
    }

    function onDprChange() {
      buildGrid()
      if (reduce) drawStatic()
    }

    buildGrid()

    if (reduce) {
      drawStatic()
    } else {
      raf = requestAnimationFrame(frame)
    }

    const ro = new ResizeObserver(() => {
      buildGrid()
      if (reduce) drawStatic()
    })
    ro.observe(wrapEl)

    // Passive only — never preventDefault; vertical page scroll stays natural.
    window.addEventListener('pointerdown', onPointerDown, { passive: true })
    window.addEventListener('pointermove', onPointerMove, { passive: true })
    window.addEventListener('pointerup', onPointerUp, { passive: true })
    window.addEventListener('pointercancel', onPointerCancel, { passive: true })
    window.addEventListener('pointerleave', onPointerLeave, { passive: true })
    window.addEventListener('blur', onPointerLeave, { passive: true })
    window.addEventListener('orientationchange', onOrientation, { passive: true })
    document.addEventListener('visibilitychange', onVisibility)
    // DPR / monitor change
    const mqDpr =
      typeof window !== 'undefined'
        ? window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`)
        : null
    mqDpr?.addEventListener?.('change', onDprChange)

    return () => {
      running = false
      cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointercancel', onPointerCancel)
      window.removeEventListener('pointerleave', onPointerLeave)
      window.removeEventListener('blur', onPointerLeave)
      window.removeEventListener('orientationchange', onOrientation)
      document.removeEventListener('visibilitychange', onVisibility)
      mqDpr?.removeEventListener?.('change', onDprChange)
    }
  }, [mode, opacity])

  return (
    <div
      ref={wrapRef}
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      aria-hidden="true"
    >
      <canvas ref={canvasRef} className="block h-full w-full" />
      {mode === 'hero' && (
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              'radial-gradient(720px 400px at 70% 40%, rgba(4,169,206,0.08), transparent 65%)',
          }}
        />
      )}
    </div>
  )
}
