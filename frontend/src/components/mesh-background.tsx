'use client'

import { useEffect, useRef } from 'react'

/**
 * Interactive curriculum mesh (Hero V2).
 *
 * A spring-damped grid of nodes with neighbour links (H/V/diagonal).
 * On fine-pointer desktops the cursor creates a soft radial bulge that
 * settles elastically. Ambient mode (mobile / coarse pointer) uses a slow
 * low-amplitude drift. Reduced-motion draws a static refined mesh once.
 *
 * Runs entirely in Canvas 2D outside React render cycles.
 */

type MeshMode = 'hero' | 'ambient'

export interface MeshBackgroundProps {
  /** Visual density + interaction strength preset. */
  mode?: MeshMode
  /** className for the canvas wrapper (layout only). */
  className?: string
  /** Optional opacity of the drawn mesh (0–1). */
  opacity?: number
}

interface Node {
  ox: number
  oy: number
  x: number
  y: number
  vx: number
  vy: number
  phase: number
  /** Curriculum accent node (brighter cyan). */
  accent: boolean
}

const ACCENT_LABELS = ['SCHEME', 'SUBJECT', 'WEEK', 'INDICATOR', 'PERIOD', 'LESSON']

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function isFinePointer(): boolean {
  return typeof window !== 'undefined'
    && window.matchMedia('(hover: hover) and (pointer: fine)').matches
}

function smoothFalloff(t: number): number {
  if (t <= 0 || t >= 1) return 0
  // Smoothstep — continuous, soft edges (no hard disc).
  const u = t * t * (3 - 2 * t)
  return u * u
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

    // Capture non-null refs for nested callbacks (TS narrowing does not
    // survive into function declarations below).
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
    let t0 = performance.now()
    let last = t0

    const pointer = {
      x: -9999,
      y: -9999,
      active: false,
      tx: -9999,
      ty: -9999,
      strength: 0,
    }

    // Tuning — hero is denser and stronger than ambient auth mesh.
    const cfg = mode === 'hero'
      ? {
          baseSpacing: 48,
          minCols: 14,
          maxCols: 36,
          spring: 0.055,
          damping: 0.84,
          influenceRadius: 160,
          pushStrength: 38,
          ambientAmp: mode === 'hero' ? 2.2 : 1.4,
          ambientSpeed: 0.00035,
          lineBase: 0.1,
          lineBoost: 0.42,
          nodeBase: 0.22,
          accentEvery: 11,
        }
      : {
          baseSpacing: 56,
          minCols: 10,
          maxCols: 24,
          spring: 0.05,
          damping: 0.86,
          influenceRadius: 0,
          pushStrength: 0,
          ambientAmp: 1.6,
          ambientSpeed: 0.00022,
          lineBase: 0.07,
          lineBoost: 0,
          nodeBase: 0.16,
          accentEvery: 14,
        }

    // Lower-powered / mobile: reduce density for ambient.
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

      const targetCols = mode === 'hero'
        ? Math.min(cfg.maxCols, Math.max(cfg.minCols, Math.round(width / effectiveSpacing)))
        : Math.min(cfg.maxCols, Math.max(cfg.minCols, Math.round(width / effectiveSpacing)))
      cols = targetCols
      spacing = width / Math.max(1, cols - 1)
      rows = Math.max(4, Math.ceil(height / spacing) + 1)

      nodes = []
      let accentIdx = 0
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          // Semi-irregular: slight jitter on rest positions for a woven feel.
          const jitterX = ((r * 17 + c * 31) % 7) / 7 - 0.5
          const jitterY = ((r * 13 + c * 19) % 5) / 5 - 0.5
          const ox = c * spacing + jitterX * spacing * 0.12
          const oy = r * spacing + jitterY * spacing * 0.12
          const accent = accentIdx > 0 && accentIdx % cfg.accentEvery === 0
          accentIdx++
          nodes.push({
            ox,
            oy,
            x: ox,
            y: oy,
            vx: 0,
            vy: 0,
            phase: (r * 0.37 + c * 0.61) % (Math.PI * 2),
            accent,
          })
        }
      }
    }

    function idx(r: number, c: number): number {
      return r * cols + c
    }

    // Listeners are on window because the wrapper is pointer-events:none
    // (so clicks/passes reach hero copy underneath). Coordinates are mapped
    // into wrap space so deformation still tracks the cursor over the hero.
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
    }

    function onTouchStart() {
      // Touch devices never run interactive deformation.
      pointer.active = false
    }

    function drawStatic() {
      // One refined still frame for reduced-motion / first paint.
      ctx!.clearRect(0, 0, width, height)
      const a = opacity
      ctx!.lineWidth = 1

      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const n = nodes[idx(r, c)]
          if (c < cols - 1) {
            const right = nodes[idx(r, c + 1)]
            ctx!.strokeStyle = `rgba(126, 220, 240, ${cfg.lineBase * a * 1.2})`
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(right.x, right.y)
            ctx!.stroke()
          }
          if (r < rows - 1) {
            const down = nodes[idx(r + 1, c)]
            ctx!.strokeStyle = `rgba(126, 220, 240, ${cfg.lineBase * a})`
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(down.x, down.y)
            ctx!.stroke()
          }
          if (c < cols - 1 && r < rows - 1) {
            const diag = nodes[idx(r + 1, c + 1)]
            ctx!.strokeStyle = `rgba(4, 169, 206, ${cfg.lineBase * a * 0.55})`
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(diag.x, diag.y)
            ctx!.stroke()
          }

          if (n.accent) {
            ctx!.fillStyle = `rgba(4, 169, 206, ${0.55 * a})`
            ctx!.beginPath()
            ctx!.arc(n.x, n.y, 2.4, 0, Math.PI * 2)
            ctx!.fill()
            // Very faint curriculum label — atmospheric, not a diagram.
            ctx!.fillStyle = `rgba(126, 220, 240, ${0.22 * a})`
            ctx!.font = '600 8px ui-sans-serif, system-ui, sans-serif'
            const label = ACCENT_LABELS[
              nodes.filter((x) => x.accent).indexOf(n) % ACCENT_LABELS.length
            ]
            ctx!.fillText(label, n.x + 6, n.y - 5)
          } else {
            ctx!.fillStyle = `rgba(197, 210, 223, ${cfg.nodeBase * a})`
            ctx!.beginPath()
            ctx!.arc(n.x, n.y, 1.4, 0, Math.PI * 2)
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

      // Smooth pointer interpolation for fluid follow.
      if (interactive && pointer.active) {
        pointer.x += (pointer.tx - pointer.x) * 0.22
        pointer.y += (pointer.ty - pointer.y) * 0.22
        pointer.strength += (1 - pointer.strength) * 0.12
      } else {
        pointer.strength += (0 - pointer.strength) * 0.06
        if (pointer.strength < 0.01) pointer.strength = 0
      }

      ctx!.clearRect(0, 0, width, height)
      const a = opacity
      const R = cfg.influenceRadius
      const R2 = R * R

      // Physics: ambient target + cursor force + spring + damping.
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i]
        const ambX = Math.sin(elapsed * cfg.ambientSpeed + n.phase) * cfg.ambientAmp
        const ambY = Math.cos(elapsed * cfg.ambientSpeed * 0.85 + n.phase * 1.1) * cfg.ambientAmp
        let restX = n.ox + ambX
        let restY = n.oy + ambY

        let fx = (restX - n.x) * cfg.spring
        let fy = (restY - n.y) * cfg.spring

        if (interactive && pointer.strength > 0.001 && R > 0) {
          const dx = n.x - pointer.x
          const dy = n.y - pointer.y
          const d2 = dx * dx + dy * dy
          if (d2 < R2 && d2 > 0.01) {
            const d = Math.sqrt(d2)
            const t = d / R
            const influence = smoothFalloff(t) * pointer.strength
            // Soft gravitational push (radial) — creates a clear local bulge.
            const nx = dx / d
            const ny = dy / d
            const push = influence * cfg.pushStrength
            fx += nx * push
            fy += ny * push
            // Slight tangential swirl for elastic fabric feel.
            fx += -ny * push * 0.18
            fy += nx * push * 0.18
          }
        }

        n.vx = (n.vx + fx) * cfg.damping
        n.vy = (n.vy + fy) * cfg.damping
        n.x += n.vx
        n.y += n.vy

        // dt awareness: scale soft damping extra on long frames.
        if (dt > 32) {
          n.vx *= 0.98
          n.vy *= 0.98
        }
      }

      // Draw links
      let accentCount = 0
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const n = nodes[idx(r, c)]
          const dxp = interactive ? n.x - pointer.x : 0
          const dyp = interactive ? n.y - pointer.y : 0
          const dist2 = interactive && R > 0 ? dxp * dxp + dyp * dyp : R2 + 1
          const near = dist2 < R2 ? 1 - Math.sqrt(dist2) / R : 0
          const boost = smoothFalloff(Math.max(0, Math.min(1, near))) * pointer.strength

          if (c < cols - 1) {
            const right = nodes[idx(r, c + 1)]
            const alpha = (cfg.lineBase + boost * cfg.lineBoost) * a
            ctx!.strokeStyle =
              boost > 0.08
                ? `rgba(126, 220, 240, ${alpha})`
                : `rgba(197, 210, 223, ${alpha * 0.85})`
            ctx!.lineWidth = 1 + boost * 0.45
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(right.x, right.y)
            ctx!.stroke()
          }
          if (r < rows - 1) {
            const down = nodes[idx(r + 1, c)]
            const alpha = (cfg.lineBase * 0.9 + boost * cfg.lineBoost * 0.85) * a
            ctx!.strokeStyle =
              boost > 0.08
                ? `rgba(126, 220, 240, ${alpha})`
                : `rgba(197, 210, 223, ${alpha * 0.85})`
            ctx!.lineWidth = 1 + boost * 0.4
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(down.x, down.y)
            ctx!.stroke()
          }
          if (c < cols - 1 && r < rows - 1) {
            const diag = nodes[idx(r + 1, c + 1)]
            const alpha = (cfg.lineBase * 0.55 + boost * cfg.lineBoost * 0.55) * a
            ctx!.strokeStyle = `rgba(4, 169, 206, ${alpha})`
            ctx!.lineWidth = 1
            ctx!.beginPath()
            ctx!.moveTo(n.x, n.y)
            ctx!.lineTo(diag.x, diag.y)
            ctx!.stroke()
          }

          // Soft cyan lens around the cursor (subtle, not a ring).
          if (boost > 0.2 && interactive) {
            ctx!.fillStyle = `rgba(4, 169, 206, ${boost * 0.08 * a})`
            ctx!.beginPath()
            ctx!.arc(n.x, n.y, 2.2 + boost * 2.5, 0, Math.PI * 2)
            ctx!.fill()
          }

          if (n.accent) {
            accentCount++
            const pulse = 0.55 + 0.25 * Math.sin(elapsed * 0.002 + n.phase)
            ctx!.fillStyle = `rgba(4, 169, 206, ${Math.min(1, pulse + boost * 0.3) * a})`
            ctx!.beginPath()
            ctx!.arc(n.x, n.y, 2.6, 0, Math.PI * 2)
            ctx!.fill()
            ctx!.fillStyle = `rgba(126, 220, 240, ${(0.18 + boost * 0.25) * a})`
            ctx!.font = '600 8px ui-sans-serif, system-ui, sans-serif'
            ctx!.fillText(
              ACCENT_LABELS[(accentCount - 1) % ACCENT_LABELS.length],
              n.x + 6,
              n.y - 5,
            )
          } else {
            ctx!.fillStyle = `rgba(197, 210, 223, ${(cfg.nodeBase + boost * 0.35) * a})`
            ctx!.beginPath()
            ctx!.arc(n.x, n.y, 1.35 + boost * 1.1, 0, Math.PI * 2)
            ctx!.fill()
          }
        }
      }

      // Cursor glow (very soft ambient light in the influence area).
      if (interactive && pointer.strength > 0.05 && R > 0) {
        const g = ctx!.createRadialGradient(
          pointer.x, pointer.y, 0,
          pointer.x, pointer.y, R * 0.85,
        )
        g.addColorStop(0, `rgba(4, 169, 206, ${0.1 * pointer.strength * a})`)
        g.addColorStop(1, 'rgba(4, 169, 206, 0)')
        ctx!.fillStyle = g
        ctx!.beginPath()
        ctx!.arc(pointer.x, pointer.y, R * 0.85, 0, Math.PI * 2)
        ctx!.fill()
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
    ro.observe(wrap)

    window.addEventListener('pointermove', onPointerMove, { passive: true })
    window.addEventListener('pointerleave', onPointerLeave, { passive: true })
    window.addEventListener('blur', onPointerLeave, { passive: true })
    window.addEventListener('touchstart', onTouchStart, { passive: true })
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      running = false
      cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerleave', onPointerLeave)
      window.removeEventListener('blur', onPointerLeave)
      window.removeEventListener('touchstart', onTouchStart)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [mode, opacity])

  return (
    <div
      ref={wrapRef}
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      aria-hidden="true"
    >
      <canvas ref={canvasRef} className="block h-full w-full" />
      {/* Subtle cursor glow companion (desktop hero only) */}
      {mode === 'hero' && (
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              'radial-gradient(720px 400px at 70% 40%, rgba(4,169,206,0.10), transparent 65%)',
          }}
        />
      )}
    </div>
  )
}
