'use client'

import { useEffect, useRef } from 'react'

/**
 * Auth grid + continuous moving signal (login interfaces only).
 *
 * Lightweight Canvas 2D technical grid with a single node that travels
 * intersection-to-intersection along grid paths — a live signal through a
 * structured network. Not the landing mesh: no springs, no pointer force,
 * no particle field. Calmer, deterministic, form-first.
 *
 * Variants share one construction but differ in cell size, line weight and
 * intensity so Teacher / School / Platform feel like one family with distinct
 * personality. Reduced motion → static polished grid, no signal movement.
 */

export type GridSignalVariant = 'teacher' | 'school' | 'platform'

interface VariantCfg {
  /** Base cell size in CSS px (desktop). */
  cell: number
  /** Minimum cells across (keeps mobile from over-density). */
  minCols: number
  /** Line RGB triple. */
  lineRgb: string
  /** Base line alpha. */
  lineAlpha: number
  /** Signal core / halo colors. */
  core: string
  halo: string
  /** Edge travel duration ms (slow, smooth). */
  edgeMs: number
  /** Extra line brightness near the signal. */
  proximityBoost: number
}

const VARIANTS: Record<GridSignalVariant, VariantCfg> = {
  teacher: {
    cell: 40,
    minCols: 8,
    lineRgb: '16, 42, 67',
    lineAlpha: 0.075,
    core: '#04A9CE',
    halo: '4, 169, 206',
    edgeMs: 1150,
    proximityBoost: 0.1,
  },
  school: {
    cell: 48,
    minCols: 8,
    lineRgb: '126, 220, 240',
    lineAlpha: 0.12,
    core: '#7EDCF0',
    halo: '126, 220, 240',
    edgeMs: 1050,
    proximityBoost: 0.14,
  },
  platform: {
    cell: 56,
    minCols: 7,
    lineRgb: '62, 90, 120',
    lineAlpha: 0.14,
    core: '#04A9CE',
    halo: '4, 169, 206',
    edgeMs: 1250,
    proximityBoost: 0.12,
  },
}

/** Short trail samples along the current path (grid-aligned). */
const TRAIL_MAX = 7

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

function easeInOut(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
}

/** Deterministic-ish PRNG so paths vary but stay reproducible per seed. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

interface Node {
  r: number
  c: number
}

interface TrailSample {
  x: number
  y: number
}

export interface GridSignalProps {
  variant: GridSignalVariant
  className?: string
}

export function GridSignal({ variant, className = '' }: GridSignalProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return
    const ctx = canvas.getContext('2d', { alpha: true })
    if (!ctx) return

    const cfg = VARIANTS[variant]
    const reduce = prefersReducedMotion()
    const dpr = Math.min(window.devicePixelRatio || 1, 2)

    let width = 0
    let height = 0
    let cols = 0
    let rows = 0
    let cell = cfg.cell
    let ox = 0
    let oy = 0
    let raf = 0
    let running = true
    let last = performance.now()
    const rand = mulberry32(variant === 'teacher' ? 42 : variant === 'school' ? 7 : 99)

    // Signal path state — always on grid intersections.
    let from: Node = { r: 1, c: 1 }
    let to: Node = { r: 1, c: 2 }
    let prev: Node | null = null
    let edgeT = 0
    let edgeDur = cfg.edgeMs
    /** Intersection flash: key `${r},${c}` → intensity 0..1 */
    const flashes = new Map<string, number>()
    const trail: TrailSample[] = []

    function nodeKey(n: Node): string {
      return `${n.r},${n.c}`
    }

    function nodeXY(n: Node): { x: number; y: number } {
      return { x: ox + n.c * cell, y: oy + n.r * cell }
    }

    function inBounds(r: number, c: number): boolean {
      return r >= 0 && c >= 0 && r < rows && c < cols
    }

    function pickNext(cur: Node, incoming: Node | null): Node {
      const dirs: [number, number][] = [
        [0, 1],
        [1, 0],
        [0, -1],
        [-1, 0],
      ]
      const options: Node[] = []
      let straight: Node | null = null
      for (const [dr, dc] of dirs) {
        const nr = cur.r + dr
        const nc = cur.c + dc
        if (!inBounds(nr, nc)) continue
        if (incoming && nr === incoming.r && nc === incoming.c) continue
        const n = { r: nr, c: nc }
        options.push(n)
        // Prefer continuing in the same direction when available.
        if (incoming) {
          const inDr = cur.r - incoming.r
          const inDc = cur.c - incoming.c
          if (dr === inDr && dc === inDc) straight = n
        }
      }
      if (options.length === 0) {
        // Dead end — reverse is the only legal move.
        return incoming ?? { r: cur.r, c: Math.min(cur.c + 1, cols - 1) }
      }
      if (straight && (options.length === 1 || rand() < 0.55)) return straight
      return options[Math.floor(rand() * options.length)]
    }

    function startEdge(immediate = false) {
      prev = { ...from }
      to = pickNext(from, prev)
      // Vary edge duration slightly for organic feel (clamped).
      edgeDur = cfg.edgeMs * (0.85 + rand() * 0.35)
      edgeT = immediate ? 0 : 0
      if (immediate) {
        // Seed a valid first edge without animation jump.
        const a = nodeXY(from)
        trail.length = 0
        trail.push(a)
      }
    }

    function buildGrid() {
      if (!canvas || !wrap) return
      const rect = wrap.getBoundingClientRect()
      width = Math.max(1, Math.floor(rect.width))
      height = Math.max(1, Math.floor(rect.height))
      canvas.width = Math.floor(width * dpr)
      canvas.height = Math.floor(height * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)

      // Mobile: larger cells → fewer intersections, calmer signal.
      const compact = width < 640
      cell = compact ? Math.max(cfg.cell, 56) : cfg.cell
      if (width < 420) cell = Math.max(cell, 64)

      cols = Math.max(cfg.minCols, Math.round(width / cell) + 1)
      rows = Math.max(4, Math.round(height / cell) + 1)
      // Re-fit cell so the grid spans the viewport cleanly.
      cell = Math.min(width / Math.max(1, cols - 1), height / Math.max(1, rows - 1))
      // Prefer horizontal spacing as primary cell; recompute rows from that.
      cell = width / Math.max(1, cols - 1)
      rows = Math.max(4, Math.ceil(height / cell) + 1)
      ox = 0
      oy = (height - (rows - 1) * cell) / 2

      flashes.clear()
      trail.length = 0
      from = { r: Math.floor(rows / 2), c: 1 }
      prev = null
      startEdge(true)
    }

    function drawStatic() {
      ctx!.clearRect(0, 0, width, height)
      const a = cfg.lineAlpha
      ctx!.lineWidth = 1
      // Horizontal lines
      for (let r = 0; r < rows; r++) {
        const y = oy + r * cell
        ctx!.strokeStyle = `rgba(${cfg.lineRgb}, ${a})`
        ctx!.beginPath()
        ctx!.moveTo(0, y)
        ctx!.lineTo(width, y)
        ctx!.stroke()
      }
      // Vertical lines
      for (let c = 0; c < cols; c++) {
        const x = ox + c * cell
        ctx!.strokeStyle = `rgba(${cfg.lineRgb}, ${a * 0.92})`
        ctx!.beginPath()
        ctx!.moveTo(x, 0)
        ctx!.lineTo(x, height)
        ctx!.stroke()
      }
      // Static intersection ticks (subtle node treatment)
      ctx!.fillStyle = `rgba(${cfg.lineRgb}, ${Math.min(1, a * 2.2)})`
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          if ((r + c) % 3 !== 0) continue
          ctx!.beginPath()
          ctx!.arc(ox + c * cell, oy + r * cell, 1.1, 0, Math.PI * 2)
          ctx!.fill()
        }
      }
      // Resting signal node so the motif is still legible without motion.
      const rest = nodeXY(from)
      const g = ctx!.createRadialGradient(rest.x, rest.y, 0, rest.x, rest.y, cell * 0.9)
      g.addColorStop(0, `rgba(${cfg.halo}, 0.35)`)
      g.addColorStop(1, `rgba(${cfg.halo}, 0)`)
      ctx!.fillStyle = g
      ctx!.beginPath()
      ctx!.arc(rest.x, rest.y, cell * 0.9, 0, Math.PI * 2)
      ctx!.fill()
      ctx!.fillStyle = cfg.core
      ctx!.beginPath()
      ctx!.arc(rest.x, rest.y, 2.4, 0, Math.PI * 2)
      ctx!.fill()
    }

    function signalPos(): { x: number; y: number } {
      const t = easeInOut(Math.min(1, Math.max(0, edgeT)))
      const a = nodeXY(from)
      const b = nodeXY(to)
      return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t }
    }

    function proximity(x: number, y: number, px: number, py: number): number {
      // Chebyshev-ish distance in cell units — brighten lines near the signal.
      const dx = Math.abs(x - px)
      const dy = Math.abs(y - py)
      const d = Math.min(dx, dy) * 0.65 + Math.max(dx, dy) * 0.35
      const r = cell * 2.4
      if (d >= r) return 0
      const t = 1 - d / r
      return t * t
    }

    function frame(now: number) {
      if (!running) return
      const dt = Math.min(48, now - last)
      last = now

      // Advance along the current edge.
      edgeT += dt / edgeDur
      let arrived = false
      if (edgeT >= 1) {
        edgeT = 0
        from = { ...to }
        flashes.set(nodeKey(from), 1)
        prev = { ...to }
        to = pickNext(from, prev)
        edgeDur = cfg.edgeMs * (0.85 + rand() * 0.35)
        arrived = true
      }

      const pos = signalPos()

      // Trail: record grid-aligned samples (follows the edge).
      if (!arrived) {
        const lastS = trail[trail.length - 1]
        if (!lastS || Math.hypot(pos.x - lastS.x, pos.y - lastS.y) > cell * 0.12) {
          trail.push({ x: pos.x, y: pos.y })
          if (trail.length > TRAIL_MAX) trail.shift()
        }
      } else {
        trail.push({ ...nodeXY(from) })
        if (trail.length > TRAIL_MAX) trail.shift()
      }

      // Decay intersection flashes.
      for (const [k, v] of Array.from(flashes)) {
        const nv = v - dt / 700
        if (nv <= 0) flashes.delete(k)
        else flashes.set(k, nv)
      }

      // ---- Draw ----
      ctx!.clearRect(0, 0, width, height)
      const baseA = cfg.lineAlpha
      const boost = cfg.proximityBoost

      // Grid lines with local illumination near the signal.
      ctx!.lineWidth = 1
      for (let r = 0; r < rows; r++) {
        const y = oy + r * cell
        // Sample brightness at a few x positions along the row (cheap).
        let near = 0
        const steps = Math.max(2, Math.ceil(width / (cell * 2)))
        for (let s = 0; s <= steps; s++) {
          const x = (s / steps) * width
          near = Math.max(near, proximity(x, y, pos.x, pos.y))
        }
        const a = baseA + near * boost
        ctx!.strokeStyle =
          near > 0.25
            ? `rgba(${cfg.halo}, ${Math.min(0.55, a * 1.8)})`
            : `rgba(${cfg.lineRgb}, ${a})`
        ctx!.beginPath()
        ctx!.moveTo(0, y)
        ctx!.lineTo(width, y)
        ctx!.stroke()
      }
      for (let c = 0; c < cols; c++) {
        const x = ox + c * cell
        let near = 0
        const steps = Math.max(2, Math.ceil(height / (cell * 2)))
        for (let s = 0; s <= steps; s++) {
          const y = (s / steps) * height
          near = Math.max(near, proximity(x, y, pos.x, pos.y))
        }
        const a = baseA * 0.92 + near * boost
        ctx!.strokeStyle =
          near > 0.25
            ? `rgba(${cfg.halo}, ${Math.min(0.55, a * 1.8)})`
            : `rgba(${cfg.lineRgb}, ${a})`
        ctx!.beginPath()
        ctx!.moveTo(x, 0)
        ctx!.lineTo(x, height)
        ctx!.stroke()
      }

      // Intersection flashes (brief brighten, smooth decay).
      for (const [k, v] of Array.from(flashes)) {
        const [rs, cs] = k.split(',')
        const r = Number(rs)
        const c = Number(cs)
        const x = ox + c * cell
        const y = oy + r * cell
        const rad = 2 + v * 3
        const g = ctx!.createRadialGradient(x, y, 0, x, y, rad * 2.5)
        g.addColorStop(0, `rgba(${cfg.halo}, ${0.45 * v})`)
        g.addColorStop(1, `rgba(${cfg.halo}, 0)`)
        ctx!.fillStyle = g
        ctx!.beginPath()
        ctx!.arc(x, y, rad * 2.5, 0, Math.PI * 2)
        ctx!.fill()
        ctx!.fillStyle = `rgba(${cfg.lineRgb}, ${Math.min(1, baseA * 3 + v * 0.5)})`
        ctx!.beginPath()
        ctx!.arc(x, y, 1.6, 0, Math.PI * 2)
        ctx!.fill()
      }

      // Short fading trail along the path.
      if (trail.length >= 2) {
        for (let i = 1; i < trail.length; i++) {
          const t = i / trail.length
          const alpha = 0.06 + t * 0.3
          ctx!.strokeStyle = `rgba(${cfg.halo}, ${alpha})`
          ctx!.lineWidth = 1 + t * 1.2
          ctx!.beginPath()
          ctx!.moveTo(trail[i - 1].x, trail[i - 1].y)
          ctx!.lineTo(trail[i].x, trail[i].y)
          ctx!.stroke()
        }
        ctx!.lineWidth = 1
      }

      // Signal: halo + short glow + bright core.
      const haloR = cell * 1.1
      const hg = ctx!.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, haloR)
      hg.addColorStop(0, `rgba(${cfg.halo}, 0.28)`)
      hg.addColorStop(0.45, `rgba(${cfg.halo}, 0.1)`)
      hg.addColorStop(1, `rgba(${cfg.halo}, 0)`)
      ctx!.fillStyle = hg
      ctx!.beginPath()
      ctx!.arc(pos.x, pos.y, haloR, 0, Math.PI * 2)
      ctx!.fill()

      // Soft local illumination disc.
      ctx!.fillStyle = `rgba(${cfg.halo}, 0.12)`
      ctx!.beginPath()
      ctx!.arc(pos.x, pos.y, cell * 0.45, 0, Math.PI * 2)
      ctx!.fill()

      // Core.
      ctx!.fillStyle = cfg.core
      ctx!.beginPath()
      ctx!.arc(pos.x, pos.y, 2.6, 0, Math.PI * 2)
      ctx!.fill()
      ctx!.fillStyle = 'rgba(255,255,255,0.85)'
      ctx!.beginPath()
      ctx!.arc(pos.x, pos.y, 1.1, 0, Math.PI * 2)
      ctx!.fill()

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

    document.addEventListener('visibilitychange', onVisibility)
    const onReduceChange = () => {
      // If user flips reduce mid-session, stop or restart cleanly.
      cancelAnimationFrame(raf)
      running = false
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        drawStatic()
      } else {
        running = true
        last = performance.now()
        raf = requestAnimationFrame(frame)
      }
    }
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    mq.addEventListener?.('change', onReduceChange)

    return () => {
      running = false
      cancelAnimationFrame(raf)
      ro.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
      mq.removeEventListener?.('change', onReduceChange)
    }
  }, [variant])

  return (
    <div
      ref={wrapRef}
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      aria-hidden="true"
      data-grid-signal-root={variant}
    >
      <canvas ref={canvasRef} data-grid-signal={variant} className="block h-full w-full" />
    </div>
  )
}
