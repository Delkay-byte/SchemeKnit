'use client'

import { useEffect, useRef } from 'react'

/**
 * Interactive curriculum mesh (Hero V3).
 *
 * Connected flexible surface: grid nodes + neighbour springs + cursor force
 * with strong central lens bulge, elastic return, and subtle depth cues.
 * Canvas 2D only — no WebGL, no React re-renders per frame.
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

const ACCENT_LABELS = ['SCHEME', 'SUBJECT', 'WEEK', 'INDICATOR', 'PERIOD', 'LESSON']

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

/** 1 at center → 0 at radius edge, smooth, then power-shaped for a strong core. */
function lensFalloff(dist: number, radius: number, power: number): number {
  if (dist >= radius || radius <= 0) return 0
  const t = dist / radius
  const inv = 1 - t
  // smoothstep on inverted t: soft shoulder, strong core
  const s = inv * inv * (3 - 2 * inv)
  return Math.pow(s, power)
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
    const interactive = !reduce && mode === 'hero' && isFinePointer()
    const dpr = Math.min(window.devicePixelRatio || 1, 2)

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
      tx: -9999,
      ty: -9999,
      strength: 0,
    }

    // V3 tuning — stronger bulge, membrane cohesion, velocity lag.
    const cfg =
      mode === 'hero'
        ? {
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
    }

    function idx(r: number, c: number): number {
      return r * cols + c
    }

    function onPointerMove(e: PointerEvent) {
      if (!interactive) return
      const rect = wrapEl.getBoundingClientRect()
      pointer.tx = e.clientX - rect.left
      pointer.ty = e.clientY - rect.top
      const inside =
        pointer.tx >= 0 &&
        pointer.ty >= 0 &&
        pointer.tx <= rect.width &&
        pointer.ty <= rect.height
      pointer.active = inside
    }

    function onPointerLeave() {
      pointer.active = false
      pointer.tx = -9999
      pointer.ty = -9999
      pointer.vx = 0
      pointer.vy = 0
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
        pointer.strength += (1 - pointer.strength) * 0.14
      } else {
        pointer.strength += (0 - pointer.strength) * 0.055
        if (pointer.strength < 0.008) {
          pointer.strength = 0
          pointer.vx *= 0.9
          pointer.vy *= 0.9
        }
      }

      ctx!.clearRect(0, 0, width, height)
      const a = opacity
      const R = cfg.influenceRadius
      const velMag = Math.min(40, Math.hypot(pointer.vx, pointer.vy))

      // Pass 1 — forces: ambient rest + cursor lens + spring
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
            // Velocity coupling — fast cursor imparts momentum (lag/inertia).
            fx += pointer.vx * fall * cfg.velocityGain
            fy += pointer.vy * fall * cfg.velocityGain
            n.elevation = fall
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

          // Depth: elevated nodes read larger + brighter near cursor.
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

      // Soft lens light under the cursor (depth cue, not a neon ring).
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
        running = false
        cancelAnimationFrame(raf)
      } else if (!running && !reduce) {
        running = true
        last = performance.now()
        raf = requestAnimationFrame(frame)
      }
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

    window.addEventListener('pointermove', onPointerMove, { passive: true })
    window.addEventListener('pointerleave', onPointerLeave, { passive: true })
    window.addEventListener('blur', onPointerLeave, { passive: true })
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
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerleave', onPointerLeave)
      window.removeEventListener('blur', onPointerLeave)
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
