'use client'

import { useEffect, useRef } from 'react'

/**
 * Auth/onboarding grid + multiple continuous signals.
 *
 * Lightweight Canvas 2D technical grid with 3–4 independent nodes that
 * travel intersection-to-intersection along shared grid paths — live data
 * signals through one curriculum network. Not the landing mesh: no springs,
 * no pointer force, no particle field. Calmer, deterministic, form-first.
 *
 * Variants share one construction but differ in cell size, line weight,
 * intensity and accent so Teacher / School / Platform / Signup / Activation
 * feel like one family with distinct personality.
 * Reduced motion → static polished grid, signals parked.
 */

export type GridSignalVariant =
  | 'teacher'
  | 'school'
  | 'platform'
  | 'register'
  | 'school_activate'
  | 'teacher_license'
  | 'password_reset'
  | 'first_run'

interface VariantCfg {
  /** Base cell size in CSS px (desktop). */
  cell: number
  /** Minimum cells across (keeps mobile from over-density). */
  minCols: number
  /** Line RGB triple (tuned for dark navy fields). */
  lineRgb: string
  /** Base line alpha — visible network, not graph paper. */
  lineAlpha: number
  /** Primary signal core / halo colors. */
  core: string
  halo: string
  /** Optional secondary accent for signal rotation (e.g. green/blue). */
  altHalo?: string
  /** Base edge travel duration ms → ~45–75 px/s at desktop cell size. */
  edgeMs: number
  /** Extra line brightness near signals. */
  proximityBoost: number
}

const VARIANTS: Record<GridSignalVariant, VariantCfg> = {
  teacher: {
    cell: 44,
    minCols: 8,
    lineRgb: '110, 165, 205',
    lineAlpha: 0.2,
    core: '#04A9CE',
    halo: '4, 169, 206',
    altHalo: '126, 220, 240',
    edgeMs: 750,
    proximityBoost: 0.22,
  },
  school: {
    cell: 48,
    minCols: 8,
    lineRgb: '126, 220, 240',
    lineAlpha: 0.17,
    core: '#7EDCF0',
    halo: '126, 220, 240',
    altHalo: '52, 211, 153',
    edgeMs: 720,
    proximityBoost: 0.24,
  },
  platform: {
    cell: 56,
    minCols: 7,
    lineRgb: '90, 130, 170',
    lineAlpha: 0.2,
    core: '#04A9CE',
    halo: '4, 169, 206',
    altHalo: '96, 165, 250',
    edgeMs: 840,
    proximityBoost: 0.2,
  },
  register: {
    cell: 46,
    minCols: 8,
    lineRgb: '100, 155, 200',
    lineAlpha: 0.19,
    core: '#04A9CE',
    halo: '4, 169, 206',
    altHalo: '125, 211, 252',
    edgeMs: 760,
    proximityBoost: 0.22,
  },
  school_activate: {
    cell: 52,
    minCols: 7,
    lineRgb: '120, 200, 220',
    lineAlpha: 0.18,
    core: '#34D399',
    halo: '52, 211, 153',
    altHalo: '4, 169, 206',
    edgeMs: 780,
    proximityBoost: 0.22,
  },
  teacher_license: {
    cell: 48,
    minCols: 8,
    lineRgb: '140, 170, 200',
    lineAlpha: 0.18,
    core: '#04A9CE',
    halo: '4, 169, 206',
    altHalo: '251, 191, 36',
    edgeMs: 770,
    proximityBoost: 0.21,
  },
  password_reset: {
    cell: 50,
    minCols: 8,
    lineRgb: '110, 150, 190',
    lineAlpha: 0.18,
    core: '#38BDF8',
    halo: '56, 189, 248',
    altHalo: '4, 169, 206',
    edgeMs: 800,
    proximityBoost: 0.21,
  },
  first_run: {
    cell: 50,
    minCols: 8,
    lineRgb: '120, 140, 200',
    lineAlpha: 0.19,
    core: '#04A9CE',
    halo: '4, 169, 206',
    altHalo: '167, 139, 250',
    edgeMs: 760,
    proximityBoost: 0.22,
  },
}

/** Short trail samples along each signal's current path (grid-aligned). */
const TRAIL_MAX = 8

/** Desktop default simultaneous signals. */
const DEFAULT_SIGNALS = 4

/** Mobile default (also multiplies edge duration → calmer). */
const MOBILE_SIGNALS = 3
const MOBILE_SPEED_SCALE = 1.28

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

function easeMove(t: number): number {
  // Mild smoothstep blended with linear — smooth corners, never stalls
  // at edge endpoints (keeps screenshot samples always showing travel).
  const smooth = t * t * (3 - 2 * t)
  return 0.42 * t + 0.58 * smooth
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

interface SignalState {
  from: Node
  to: Node
  prev: Node | null
  edgeT: number
  edgeDur: number
  /** Per-signal speed multiplier (phase + rate offsets). */
  speedMul: number
  /** Halo RGB for this signal (primary or alt accent). */
  halo: string
  trail: TrailSample[]
  rand: () => number
}

export interface GridSignalProps {
  variant: GridSignalVariant
  /** Simultaneous signals (default 4 desktop / 3 mobile). */
  signalCount?: number
  className?: string
}

export function GridSignal({
  variant,
  signalCount,
  className = '',
}: GridSignalProps) {
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
    let speedScale = 1
    let activeCount = DEFAULT_SIGNALS
    let frameNo = 0

    const seeds = [42, 7, 99, 17, 61, 23]
    const signals: SignalState[] = []

    const flashes = new Map<string, number>()

    function nodeKey(n: Node): string {
      return `${n.r},${n.c}`
    }

    function nodeXY(n: Node): { x: number; y: number } {
      return { x: ox + n.c * cell, y: oy + n.r * cell }
    }

    function inBounds(r: number, c: number): boolean {
      return r >= 0 && c >= 0 && r < rows && c < cols
    }

    function pickNext(
      cur: Node,
      incoming: Node | null,
      rand: () => number,
    ): Node {
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
        if (incoming) {
          const inDr = cur.r - incoming.r
          const inDc = cur.c - incoming.c
          if (dr === inDr && dc === inDc) straight = n
        }
      }
      if (options.length === 0) {
        return incoming ?? { r: cur.r, c: Math.min(cur.c + 1, cols - 1) }
      }
      if (straight && (options.length === 1 || rand() < 0.55)) return straight
      return options[Math.floor(rand() * options.length)]
    }

    function startEdge(sig: SignalState, immediate = false) {
      sig.prev = { ...sig.from }
      sig.to = pickNext(sig.from, sig.prev, sig.rand)
      sig.edgeDur =
        cfg.edgeMs * speedScale * sig.speedMul * (0.9 + sig.rand() * 0.28)
      sig.edgeT = 0
      if (immediate) {
        const a = nodeXY(sig.from)
        sig.trail.length = 0
        sig.trail.push(a)
      }
    }

    /** Distinct start nodes so signals don't stack. */
    function startNodeFor(i: number, count: number): Node {
      const midR = Math.floor(rows / 2)
      const midC = Math.floor(cols / 2)
      const anchors: Node[] = [
        { r: midR, c: Math.max(1, Math.floor(cols * 0.18)) },
        { r: Math.max(1, Math.floor(rows * 0.72)), c: Math.min(cols - 2, Math.floor(cols * 0.55)) },
        { r: Math.min(rows - 2, Math.floor(rows * 0.28)), c: Math.min(cols - 2, Math.floor(cols * 0.78)) },
        { r: midR, c: Math.min(cols - 2, Math.max(2, midC + 2)) },
        { r: Math.max(1, Math.floor(rows * 0.2)), c: Math.max(1, Math.floor(cols * 0.3)) },
        { r: Math.min(rows - 2, Math.floor(rows * 0.8)), c: Math.max(1, Math.floor(cols * 0.4)) },
      ]
      const base = anchors[i % anchors.length]
      return {
        r: Math.min(rows - 1, Math.max(0, base.r)),
        c: Math.min(cols - 1, Math.max(0, base.c)),
      }
    }

    function rebuildSignals() {
      const requested =
        signalCount ??
        (width < 640 ? MOBILE_SIGNALS : DEFAULT_SIGNALS)
      activeCount = Math.max(2, Math.min(6, requested))
      signals.length = 0
      for (let i = 0; i < activeCount; i++) {
        const rand = mulberry32(seeds[i % seeds.length] + variant.length * 13)
        // Phase offset so edges don't synchronize.
        for (let w = 0; w < i * 3; w++) rand()
        const halo =
          i > 0 && cfg.altHalo && i % 2 === 1 ? cfg.altHalo! : cfg.halo
        signals.push({
          from: startNodeFor(i, activeCount),
          to: { r: 0, c: 1 },
          prev: null,
          edgeT: rand() * 0.85,
          edgeDur: cfg.edgeMs,
          speedMul: 0.88 + rand() * 0.35,
          halo,
          trail: [],
          rand,
        })
        startEdge(signals[i], true)
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

      const compact = width < 640
      speedScale = compact ? MOBILE_SPEED_SCALE : 1
      cell = compact ? Math.max(cfg.cell, 56) : cfg.cell
      if (width < 420) cell = Math.max(cell, 64)

      cols = Math.max(cfg.minCols, Math.round(width / cell) + 1)
      rows = Math.max(4, Math.round(height / cell) + 1)
      cell = width / Math.max(1, cols - 1)
      rows = Math.max(4, Math.ceil(height / cell) + 1)
      ox = 0
      oy = (height - (rows - 1) * cell) / 2

      flashes.clear()
      rebuildSignals()
      canvas.setAttribute('data-signal-count', String(activeCount))
      canvas.setAttribute('data-signal-frame', '0')
    }

    function signalPos(sig: SignalState): { x: number; y: number } {
      const t = easeMove(Math.min(1, Math.max(0, sig.edgeT)))
      const a = nodeXY(sig.from)
      const b = nodeXY(sig.to)
      return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t }
    }

    /** Chebyshev-ish distance in cell units — brighten lines near signals. */
    function proximity(x: number, y: number, px: number, py: number): number {
      const dx = Math.abs(x - px)
      const dy = Math.abs(y - py)
      const d = Math.min(dx, dy) * 0.65 + Math.max(dx, dy) * 0.35
      const r = cell * 2.4
      if (d >= r) return 0
      const t = 1 - d / r
      return t * t
    }

    /** Max proximity across all live signals. */
    function nearAny(x: number, y: number, positions: { x: number; y: number }[]): number {
      let m = 0
      for (const p of positions) {
        const v = proximity(x, y, p.x, p.y)
        if (v > m) m = v
      }
      return m
    }

    function drawGridBase(positions: { x: number; y: number }[]) {
      const baseA = cfg.lineAlpha
      const boost = cfg.proximityBoost
      ctx!.lineWidth = 1

      for (let r = 0; r < rows; r++) {
        const y = oy + r * cell
        let near = 0
        const steps = Math.max(2, Math.ceil(width / (cell * 2)))
        for (let s = 0; s <= steps; s++) {
          const x = (s / steps) * width
          const v = nearAny(x, y, positions)
          if (v > near) near = v
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
          const v = nearAny(x, y, positions)
          if (v > near) near = v
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

      // Network nodes at every other intersection.
      ctx!.fillStyle = `rgba(${cfg.lineRgb}, ${Math.min(1, baseA * 2.4)})`
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          if ((r + c) % 2 !== 0) continue
          const x = ox + c * cell
          const y = oy + r * cell
          const n = nearAny(x, y, positions)
          ctx!.fillStyle = `rgba(${n > 0.2 ? cfg.halo : cfg.lineRgb}, ${Math.min(0.9, baseA * 2.4 + n * 0.5)})`
          ctx!.beginPath()
          ctx!.arc(x, y, 1.25 + n * 0.8, 0, Math.PI * 2)
          ctx!.fill()
        }
      }
    }

    function drawFlashes() {
      const baseA = cfg.lineAlpha
      for (const [k, v] of Array.from(flashes)) {
        const [rs, cs] = k.split(',')
        const r = Number(rs)
        const c = Number(cs)
        const x = ox + c * cell
        const y = oy + r * cell
        const rad = 2.5 + v * 4
        const g = ctx!.createRadialGradient(x, y, 0, x, y, rad * 2.8)
        g.addColorStop(0, `rgba(${cfg.halo}, ${0.5 * v})`)
        g.addColorStop(1, `rgba(${cfg.halo}, 0)`)
        ctx!.fillStyle = g
        ctx!.beginPath()
        ctx!.arc(x, y, rad * 2.8, 0, Math.PI * 2)
        ctx!.fill()
        ctx!.fillStyle = `rgba(${cfg.lineRgb}, ${Math.min(1, baseA * 3.2 + v * 0.5)})`
        ctx!.beginPath()
        ctx!.arc(x, y, 1.8, 0, Math.PI * 2)
        ctx!.fill()
      }
    }

    function drawTrail(sig: SignalState) {
      if (sig.trail.length < 2) return
      for (let i = 1; i < sig.trail.length; i++) {
        const t = i / sig.trail.length
        const alpha = 0.08 + t * 0.46
        ctx!.strokeStyle = `rgba(${sig.halo}, ${alpha})`
        ctx!.lineWidth = 1.15 + t * 2
        ctx!.lineCap = 'round'
        ctx!.beginPath()
        ctx!.moveTo(sig.trail[i - 1].x, sig.trail[i - 1].y)
        ctx!.lineTo(sig.trail[i].x, sig.trail[i].y)
        ctx!.stroke()
      }
      ctx!.lineWidth = 1
      ctx!.lineCap = 'butt'
    }

    function drawSignalHead(pos: { x: number; y: number }, halo: string) {
      const haloR = cell * 1.35
      const hg = ctx!.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, haloR)
      hg.addColorStop(0, `rgba(${halo}, 0.4)`)
      hg.addColorStop(0.4, `rgba(${halo}, 0.15)`)
      hg.addColorStop(1, `rgba(${halo}, 0)`)
      ctx!.fillStyle = hg
      ctx!.beginPath()
      ctx!.arc(pos.x, pos.y, haloR, 0, Math.PI * 2)
      ctx!.fill()

      ctx!.fillStyle = `rgba(${halo}, 0.16)`
      ctx!.beginPath()
      ctx!.arc(pos.x, pos.y, cell * 0.45, 0, Math.PI * 2)
      ctx!.fill()

      ctx!.fillStyle = cfg.core
      ctx!.beginPath()
      ctx!.arc(pos.x, pos.y, 3.2, 0, Math.PI * 2)
      ctx!.fill()
      ctx!.fillStyle = 'rgba(255,255,255,0.92)'
      ctx!.beginPath()
      ctx!.arc(pos.x, pos.y, 1.4, 0, Math.PI * 2)
      ctx!.fill()
    }

    function updateDiagnostics(positions: { x: number; y: number }[]) {
      // Test-safe non-sensitive state (positions are CSS px on the decor canvas).
      canvas!.setAttribute('data-signal-count', String(signals.length))
      canvas!.setAttribute('data-signal-frame', String(frameNo))
      canvas!.setAttribute(
        'data-signal-positions',
        positions.map((p) => `${Math.round(p.x)},${Math.round(p.y)}`).join(' '),
      )
    }

    function drawStatic() {
      ctx!.clearRect(0, 0, width, height)
      const positions = signals.map((s) => nodeXY(s.from))
      drawGridBase(positions)
      drawFlashes()
      for (let i = 0; i < signals.length; i++) {
        drawSignalHead(positions[i], signals[i].halo)
      }
      updateDiagnostics(positions)
    }

    function frame(now: number) {
      if (!running) return
      const dt = Math.min(48, now - last)
      last = now
      frameNo++

      for (const sig of signals) {
        sig.edgeT += dt / sig.edgeDur
        if (sig.edgeT >= 1) {
          sig.edgeT = 0
          sig.from = { ...sig.to }
          flashes.set(nodeKey(sig.from), 1)
          sig.prev = { ...sig.to }
          sig.to = pickNext(sig.from, sig.prev, sig.rand)
          sig.edgeDur =
            cfg.edgeMs * speedScale * sig.speedMul * (0.9 + sig.rand() * 0.28)
          sig.trail.push({ ...nodeXY(sig.from) })
          if (sig.trail.length > TRAIL_MAX) sig.trail.shift()
        } else {
          const pos = signalPos(sig)
          const lastS = sig.trail[sig.trail.length - 1]
          if (!lastS || Math.hypot(pos.x - lastS.x, pos.y - lastS.y) > cell * 0.14) {
            sig.trail.push(pos)
            if (sig.trail.length > TRAIL_MAX) sig.trail.shift()
          }
        }
      }

      for (const [k, v] of Array.from(flashes)) {
        const nv = v - dt / 700
        if (nv <= 0) flashes.delete(k)
        else flashes.set(k, nv)
      }

      const positions = signals.map((s) => signalPos(s))

      ctx!.clearRect(0, 0, width, height)
      drawGridBase(positions)
      drawFlashes()
      for (const sig of signals) drawTrail(sig)
      for (let i = 0; i < signals.length; i++) {
        drawSignalHead(positions[i], signals[i].halo)
      }
      if (frameNo % 3 === 0) updateDiagnostics(positions)

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
  }, [variant, signalCount])

  return (
    <div
      ref={wrapRef}
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      aria-hidden="true"
      data-grid-signal-root={variant}
    >
      <canvas
        ref={canvasRef}
        data-grid-signal={variant}
        className="block h-full w-full"
      />
    </div>
  )
}
