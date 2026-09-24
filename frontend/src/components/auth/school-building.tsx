'use client'

/**
 * Decorative 3D school building with human-like figures walking into
 * the entrance on a loop. Pure SVG + CSS keyframes (no canvas/WebGL).
 * Reduced motion → static building, figures parked on the path.
 */

interface Walker {
  /** Start X in viewBox units (left of door). */
  x0: number
  /** End X (door threshold). */
  x1: number
  /** Ground Y. */
  y: number
  /** Animation duration seconds. */
  dur: number
  /** Delay before this walker starts a cycle. */
  delay: number
  /** Scale (0.8–1.1). */
  scale: number
  /** Accent color for clothing. */
  color: string
}

const WALKERS: Walker[] = [
  { x0: -18, x1: 96, y: 148, dur: 7.2, delay: 0, scale: 1, color: '#04A9CE' },
  { x0: 210, x1: 118, y: 152, dur: 8.1, delay: 1.4, scale: 0.92, color: '#34D399' },
  { x0: -28, x1: 92, y: 156, dur: 9, delay: 2.8, scale: 0.85, color: '#7EDCF0' },
  { x0: 220, x1: 122, y: 146, dur: 7.6, delay: 4.2, scale: 0.95, color: '#FBBF24' },
  { x0: -10, x1: 98, y: 150, dur: 8.6, delay: 5.5, scale: 0.88, color: '#A78BFA' },
]

function Figure({ w, i }: { w: Walker; i: number }) {
  const travel = w.x1 - w.x0
  const steps = Math.max(6, Math.round(Math.abs(travel) / 14))
  return (
    <g
      className="sk-school-walker"
      style={{
        ['--sk-x0' as string]: `${w.x0}`,
        ['--sk-x1' as string]: `${w.x1}`,
        ['--sk-dur' as string]: `${w.dur}s`,
        ['--sk-delay' as string]: `${w.delay}s`,
        ['--sk-y' as string]: `${w.y}`,
        ['--sk-scale' as string]: `${w.scale}`,
        opacity: 0,
      }}
    >
      {/* soft ground shadow */}
      <ellipse cx={0} cy={1} rx={7} ry={2.2} fill="rgba(0,0,0,0.28)" />
      {/* legs — simple stride */}
      <g className="sk-school-legs" style={{ ['--sk-step' as string]: `${1 / steps}s` }}>
        <line x1={-2.5} y1={-10} x2={-4} y2={0} stroke="#0E1C2E" strokeWidth={2.2} strokeLinecap="round" />
        <line x1={2.5} y1={-10} x2={4.5} y2={0} stroke="#0E1C2E" strokeWidth={2.2} strokeLinecap="round" />
      </g>
      {/* torso */}
      <path
        d="M-4.5,-10 L-5,-22 Q0,-25 5,-22 L4.5,-10 Z"
        fill={w.color}
        stroke="rgba(14,28,46,0.35)"
        strokeWidth={0.6}
      />
      {/* arms */}
      <line x1={-4} y1={-20} x2={-7} y2={-13} stroke={w.color} strokeWidth={2} strokeLinecap="round" />
      <line x1={4} y1={-20} x2={7} y2={-13} stroke={w.color} strokeWidth={2} strokeLinecap="round" />
      {/* head */}
      <circle cx={0} cy={-27} r={4.2} fill="#F5D0A9" stroke="rgba(14,28,46,0.25)" strokeWidth={0.5} />
      {/* hair / cap */}
      <path d="M-4.2,-28 Q0,-33 4.2,-28" fill="#0E1C2E" opacity={0.85} />
      {/* bag for a couple of figures */}
      {i % 2 === 0 && (
        <rect x={5} y={-19} width={5} height={7} rx={1} fill="#102A43" opacity={0.75} />
      )}
      {/* entry fade marker (invisible; animation handles it) */}
      <rect x={-8} y={-34} width={16} height={36} fill="transparent" />
    </g>
  )
}

export function SchoolBuildingScene({ className = '' }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none relative ${className}`}
      data-school-scene="1"
    >
      <style>{`
        @keyframes sk-school-walk {
          0% {
            transform: translate(calc(var(--sk-x0) * 1px), calc(var(--sk-y) * 1px)) scale(var(--sk-scale));
            opacity: 0;
          }
          6% { opacity: 1; }
          78% { opacity: 1; }
          88%, 100% {
            transform: translate(calc(var(--sk-x1) * 1px), calc(var(--sk-y) * 1px)) scale(calc(var(--sk-scale) * 0.72));
            opacity: 0;
          }
        }
        @keyframes sk-school-stride {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-1.2px); }
        }
        [data-school-scene] .sk-school-walker {
          animation: sk-school-walk var(--sk-dur, 8s) linear var(--sk-delay, 0s) infinite;
        }
        [data-school-scene] .sk-school-legs {
          animation: sk-school-stride 0.38s ease-in-out infinite;
          transform-origin: center top;
        }
        @media (prefers-reduced-motion: reduce) {
          [data-school-scene] .sk-school-walker {
            animation: none !important;
            opacity: 1 !important;
            transform: translate(
                calc((var(--sk-x0) + (var(--sk-x1) - var(--sk-x0)) * 0.45) * 1px),
                calc(var(--sk-y) * 1px)
              )
              scale(var(--sk-scale)) !important;
          }
          [data-school-scene] .sk-school-legs {
            animation: none !important;
          }
        }
      `}</style>

      <svg
        width="320"
        height="200"
        viewBox="0 0 320 200"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="block h-auto w-full max-w-[320px] overflow-visible"
      >
        <defs>
          {/* building face gradients */}
          <linearGradient id="sk-bldg-front" x1="70" y1="50" x2="170" y2="160" gradientUnits="userSpaceOnUse">
            <stop stopColor="#1A3A5C" />
            <stop offset="1" stopColor="#0F2744" />
          </linearGradient>
          <linearGradient id="sk-bldg-side" x1="170" y1="60" x2="230" y2="160" gradientUnits="userSpaceOnUse">
            <stop stopColor="#0E2240" />
            <stop offset="1" stopColor="#0A1A32" />
          </linearGradient>
          <linearGradient id="sk-bldg-roof" x1="60" y1="20" x2="230" y2="70" gradientUnits="userSpaceOnUse">
            <stop stopColor="#2A5A82" />
            <stop offset="0.5" stopColor="#1E4568" />
            <stop offset="1" stopColor="#14304E" />
          </linearGradient>
          <linearGradient id="sk-roof-cap" x1="70" y1="18" x2="220" y2="55" gradientUnits="userSpaceOnUse">
            <stop stopColor="#3D7AAB" />
            <stop offset="1" stopColor="#1E4568" />
          </linearGradient>
          <linearGradient id="sk-window" x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="#7EDCF0" stopOpacity="0.55" />
            <stop offset="1" stopColor="#04A9CE" stopOpacity="0.18" />
          </linearGradient>
          <linearGradient id="sk-door-glow" x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="#34D399" stopOpacity="0.45" />
            <stop offset="1" stopColor="#34D399" stopOpacity="0.05" />
          </linearGradient>
          <radialGradient id="sk-door-light" cx="0.5" cy="0.4" r="0.6">
            <stop stopColor="#A7F3D0" stopOpacity="0.55" />
            <stop offset="1" stopColor="#34D399" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="sk-ground" x1="0" y1="0" x2="1" y2="0">
            <stop stopColor="#04A9CE" stopOpacity="0" />
            <stop offset="0.35" stopColor="#04A9CE" stopOpacity="0.35" />
            <stop offset="0.65" stopColor="#34D399" stopOpacity="0.35" />
            <stop offset="1" stopColor="#34D399" stopOpacity="0" />
          </linearGradient>
          <filter id="sk-soft" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="1.2" />
          </filter>
        </defs>

        {/* ground plane / path */}
        <ellipse cx={160} cy={172} rx={130} ry={16} fill="rgba(4,12,22,0.35)" />
        <rect x={40} y={168} width={240} height={3} rx={1.5} fill="url(#sk-ground)" opacity={0.7} />
        {/* walkway to door */}
        <path d="M96,170 L124,170 L118,148 L102,148 Z" fill="rgba(126,220,240,0.08)" stroke="rgba(126,220,240,0.2)" strokeWidth={0.8} />

        {/* —— 3D school building (front + side + roof) —— */}
        {/* side face (right) */}
        <path d="M170,62 L230,48 L230,148 L170,160 Z" fill="url(#sk-bldg-side)" stroke="#2A5A82" strokeOpacity={0.55} strokeWidth={1.2} />
        {/* front face */}
        <path d="M70,62 L170,62 L170,160 L70,160 Z" fill="url(#sk-bldg-front)" stroke="#3D7AAB" strokeOpacity={0.65} strokeWidth={1.3} />
        {/* roof slope front */}
        <path d="M62,62 L120,22 L238,22 L170,62 Z" fill="url(#sk-bldg-roof)" stroke="#4A8FC0" strokeOpacity={0.7} strokeWidth={1.3} />
        {/* roof slope side */}
        <path d="M170,62 L238,22 L238,36 L170,72 Z" fill="url(#sk-roof-cap)" stroke="#3D7AAB" strokeOpacity={0.5} strokeWidth={1} opacity={0.9} />
        {/* roof ridge highlight */}
        <path d="M62,62 L120,22 L238,22" stroke="#7EDCF0" strokeOpacity={0.35} strokeWidth={1.2} fill="none" />
        {/* eave shadow */}
        <path d="M70,62 L170,62" stroke="#04A9CE" strokeOpacity={0.35} strokeWidth={1.5} />

        {/* —— front windows (2 rows × 3) —— */}
        {[0, 1].map((row) =>
          [0, 1, 2].map((col) => {
            const x = 82 + col * 30
            const y = 74 + row * 34
            // skip middle bottom (door zone)
            if (row === 1 && col === 1) return null
            return (
              <g key={`w${row}${col}`}>
                <rect x={x} y={y} width={20} height={24} rx={2} fill="url(#sk-window)" stroke="#7EDCF0" strokeOpacity={0.45} strokeWidth={1} />
                <line x1={x + 10} y1={y} x2={x + 10} y2={y + 24} stroke="#7EDCF0" strokeOpacity={0.3} strokeWidth={0.8} />
                <line x1={x} y1={y + 12} x2={x + 20} y2={y + 12} stroke="#7EDCF0" strokeOpacity={0.3} strokeWidth={0.8} />
                {/* warm interior glow */}
                <rect x={x + 2} y={y + 2} width={7} height={9} rx={1} fill="#FBBF24" opacity={0.12} />
              </g>
            )
          }),
        )}

        {/* —— side windows —— */}
        {[0, 1].map((row) => (
          <g key={`sw${row}`}>
            <path
              d={`M182,${78 + row * 34} L204,${73 + row * 34} L204,${95 + row * 34} L182,${100 + row * 34} Z`}
              fill="url(#sk-window)"
              stroke="#7EDCF0"
              strokeOpacity={0.35}
              strokeWidth={0.9}
            />
            <path
              d={`M212,${71 + row * 34} L226,${68 + row * 34} L226,${90 + row * 34} L212,${93 + row * 34} Z`}
              fill="url(#sk-window)"
              stroke="#7EDCF0"
              strokeOpacity={0.3}
              strokeWidth={0.9}
            />
          </g>
        ))}

        {/* —— entrance —— */}
        {/* door frame */}
        <path d="M98,112 L142,112 L142,160 L98,160 Z" fill="#0A1628" stroke="#34D399" strokeOpacity={0.7} strokeWidth={1.6} />
        {/* door panels */}
        <path d="M102,116 L118,116 L118,160 L102,160 Z" fill="url(#sk-door-glow)" stroke="#34D399" strokeOpacity={0.4} strokeWidth={0.9} />
        <path d="M122,116 L138,116 L138,160 L122,160 Z" fill="url(#sk-door-glow)" stroke="#34D399" strokeOpacity={0.4} strokeWidth={0.9} />
        {/* door light spill on ground */}
        <ellipse cx={120} cy={162} rx={28} ry={8} fill="url(#sk-door-light)" />
        {/* pediment / clock */}
        <path d="M100,112 L120,96 L140,112 Z" fill="#1A3A5C" stroke="#4A8FC0" strokeOpacity={0.6} strokeWidth={1.1} />
        <circle cx={120} cy={107} r={5.5} fill="#0A1628" stroke="#7EDCF0" strokeOpacity={0.7} strokeWidth={1} />
        <line x1={120} y1={107} x2={120} y2={103.5} stroke="#7EDCF0" strokeWidth={1} strokeLinecap="round" />
        <line x1={120} y1={107} x2={123} y2={107.5} stroke="#7EDCF0" strokeWidth={1} strokeLinecap="round" />
        {/* steps */}
        <path d="M94,160 L146,160 L150,166 L90,166 Z" fill="#14304E" stroke="#2A5A82" strokeWidth={1} />
        <path d="M90,166 L150,166 L154,172 L86,172 Z" fill="#0F2744" stroke="#2A5A82" strokeWidth={1} />

        {/* flag pole + flag */}
        <line x1={120} y1={22} x2={120} y2={8} stroke="#7EDCF0" strokeOpacity={0.7} strokeWidth={1.2} />
        <path d="M120,8 L138,12 L120,17 Z" fill="#34D399" opacity={0.85}>
          <animateTransform
            attributeName="transform"
            type="skewX"
            values="0;4;0;-2;0"
            dur="3s"
            repeatCount="indefinite"
          />
        </path>

        {/* —— animated human-like figures walking into the door —— */}
        <g data-school-walkers="1">
          {WALKERS.map((w, i) => (
            <Figure key={i} w={w} i={i} />
          ))}
        </g>

        {/* atmospheric glow behind building */}
        <ellipse cx={160} cy={90} rx={90} ry={60} fill="#04A9CE" opacity={0.06} filter="url(#sk-soft)" />
      </svg>
    </div>
  )
}
