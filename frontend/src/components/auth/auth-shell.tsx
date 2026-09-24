'use client'

import Link from 'next/link'
import { ReactNode } from 'react'

import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { RoleBadge } from '@/components/auth/auth-field'
import { GridSignal } from '@/components/auth/grid-signal'

/**
 * Role-specific authentication shells (V2 remediation + V3 onboarding grid).
 *
 * Mesh backgrounds are landing-only. Every auth / activation surface gets a
 * dark technical grid + multi-signal network, its own composition, visual
 * metaphor and depth treatment — shared typography, form controls, buttons
 * and logo treatment only.
 *
 * Role is cosmetic only — backend role checks remain authoritative.
 */

export type AuthShellRole =
  | 'teacher'
  | 'register'
  | 'school_admin'
  | 'platform_admin'
  | 'school_activate'
  | 'teacher_license'
  | 'password_reset'
  | 'first_run'

/** Light capsule so the canonical navy S reads on any surface. */
export function BrandCapsule({
  size = 40,
  mark = 26,
  dark = false,
  href = '/',
  showWordmark = false,
  className = '',
}: {
  size?: number
  mark?: number
  dark?: boolean
  href?: string
  showWordmark?: boolean
  className?: string
}) {
  const inner = (
    <span
      className={`inline-flex items-center justify-center rounded-xl border shadow-sm ${className}`}
      style={{
        width: size,
        height: size,
        background: dark ? '#F4F7FA' : '#FFFFFF',
        borderColor: dark ? 'rgba(16,42,67,0.12)' : 'rgba(16,42,67,0.1)',
        boxShadow: dark
          ? '0 0 0 1.5px rgba(4,169,206,0.35), 0 4px 14px rgba(0,0,0,0.2)'
          : '0 0 0 1.5px rgba(4,169,206,0.28), 0 2px 8px rgba(16,42,67,0.1)',
      }}
    >
      <SchemeKnitMark size={mark} />
    </span>
  )
  if (!href && !showWordmark) return inner
  return (
    <Link
      href={href || '/'}
      className="inline-flex items-center gap-3 rounded-xl transition hover:opacity-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/60"
      aria-label="SchemeKnit home"
    >
      {inner}
      {showWordmark && (
        <span
          className="text-lg font-bold tracking-tight"
          style={{ color: dark ? '#FFFFFF' : '#102A43' }}
        >
          Scheme<span className="text-[#04A9CE]">Knit</span>
        </span>
      )}
    </Link>
  )
}

/* ------------------------------------------------------------------ */
/* Decorative systems — unique per purpose, shared grid language      */
/* ------------------------------------------------------------------ */

function TeacherWorkspaceDecor() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[linear-gradient(165deg,#071826_0%,#0B1F3A_58%,#0A1B33_100%)]" />
      <GridSignal variant="teacher" />
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(1200px 700px at 50% 40%, transparent 40%, rgba(4,12,22,0.45) 100%)',
        }}
      />
      <div className="absolute right-[8%] top-[18%] hidden w-64 lg:block" style={{ perspective: '800px' }}>
        <div
          className="rounded-2xl border border-white/40 bg-white p-5 shadow-[0_20px_50px_rgba(0,0,0,0.45)]"
          style={{ transform: 'rotateY(-8deg) rotateX(4deg) translateZ(0)' }}
        >
          <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-[#0389a8]">Scheme of Learning</p>
          <p className="mt-2 text-base font-bold text-[#102A43]">Week 4 · Fractions</p>
          <div className="mt-3 space-y-1.5">
            {['Indicator 3.1', 'Teaching period 2', 'JHS · Term 2'].map((t) => (
              <div key={t} className="flex items-center gap-2 text-[13px] font-medium text-[#102A43]">
                <span className="h-1.5 w-1.5 rounded-full bg-[#04A9CE]" />
                {t}
              </div>
            ))}
          </div>
          <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-[#102A43]/12">
            <div className="h-full w-2/3 rounded-full bg-gradient-to-r from-[#04A9CE] to-[#7EDCF0]" />
          </div>
        </div>
        <div
          className="absolute -right-4 -top-4 -z-10 h-full w-full rounded-2xl border border-white/50 bg-white/85 shadow-lg"
          style={{ transform: 'rotateY(-8deg) rotateX(4deg) translateZ(-24px)' }}
        />
        <div
          className="absolute -right-8 -top-8 -z-20 h-full w-full rounded-2xl border border-white/40 bg-white/70"
          style={{ transform: 'rotateY(-8deg) rotateX(4deg) translateZ(-48px)' }}
        />
      </div>
      <div className="absolute left-0 top-1/4 hidden flex-col gap-3 xl:flex">
        {['Scheme', 'Lesson', 'Teach'].map((t, i) => (
          <div
            key={t}
            className="rounded-r-lg border border-l-0 border-white/20 bg-white/15 px-3 py-1.5 text-[11px] font-semibold text-white shadow-sm backdrop-blur-sm"
            style={{ transform: `translateX(${i * 6}px)` }}
          >
            {t}
          </div>
        ))}
      </div>
      <div className="absolute -left-20 bottom-10 h-64 w-64 rounded-full bg-[#04A9CE]/15 blur-3xl" />
      <div className="absolute right-0 top-0 h-48 w-48 rounded-full bg-[#7EDCF0]/8 blur-3xl" />
    </div>
  )
}

function RegisterOnboardingDecor() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[linear-gradient(135deg,#071826_0%,#0A1F35_55%,#0C2340_100%)]" />
      <GridSignal variant="register" />
      <div className="absolute right-10 top-1/3 hidden w-52 space-y-2.5 xl:block" style={{ perspective: '600px' }}>
        {['Upload scheme', 'Map indicators', 'Generate lesson'].map((t, i) => (
          <div
            key={t}
            className="rounded-xl border border-white/15 bg-white/95 px-4 py-2.5 text-xs font-medium text-[#102A43] shadow-md"
            style={{
              transform: `rotateY(${-6 + i * 3}deg) translateX(${i * 8}px)`,
              marginLeft: i * 8,
            }}
          >
            <span className="mr-2 inline-flex h-4 w-4 items-center justify-center rounded-full bg-[#04A9CE]/15 text-[10px] font-bold text-[#0389a8]">
              {i + 1}
            </span>
            {t}
          </div>
        ))}
      </div>
      <div className="absolute -left-16 bottom-12 hidden w-56 lg:block" style={{ perspective: '600px' }}>
        <div
          className="rounded-2xl border border-white/15 bg-white/92 p-4 shadow-lg"
          style={{ transform: 'rotateY(10deg) rotateX(-4deg)' }}
        >
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#04A9CE]">Workspace ready</p>
          <p className="mt-1.5 text-xs text-[#3D5A75]">Your lesson-planning desk opens after signup.</p>
        </div>
      </div>
      <div className="absolute -left-24 bottom-0 h-72 w-72 rounded-full bg-[#04A9CE]/10 blur-3xl" />
    </div>
  )
}

function SchoolInstitutionDecor() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[linear-gradient(160deg,#0A2240_0%,#0B1F3A_60%,#081C36_100%)]" />
      <GridSignal variant="school_activate" />
      <svg className="absolute inset-0 h-full w-full" style={{ opacity: 0.12 }} xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="school-bp" width="56" height="56" patternUnits="userSpaceOnUse">
            <path d="M56 0H0V56" fill="none" stroke="#7EDCF0" strokeWidth="0.5" />
            <circle cx="0" cy="0" r="1.5" fill="#7EDCF0" fillOpacity="0.4" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#school-bp)" />
      </svg>
      <div className="absolute left-[6%] top-1/2 hidden -translate-y-1/2 xl:block" style={{ perspective: '700px' }}>
        <svg width="180" height="140" viewBox="0 0 180 140" fill="none" style={{ transform: 'rotateX(18deg) rotateY(-12deg)' }}>
          <rect x="30" y="45" width="120" height="80" rx="4" stroke="#7EDCF0" strokeOpacity="0.45" strokeWidth="1.5" fill="rgba(255,255,255,0.06)" />
          <path d="M30 45 L90 12 L150 45" stroke="#7EDCF0" strokeOpacity="0.5" strokeWidth="1.5" fill="rgba(255,255,255,0.05)" />
          <rect x="50" y="68" width="24" height="30" rx="2" stroke="#7EDCF0" strokeOpacity="0.4" strokeWidth="1.2" fill="none" />
          <rect x="106" y="68" width="24" height="30" rx="2" stroke="#7EDCF0" strokeOpacity="0.4" strokeWidth="1.2" fill="none" />
          <rect x="78" y="82" width="24" height="43" rx="2" stroke="#34D399" strokeOpacity="0.75" strokeWidth="1.5" fill="rgba(52,211,153,0.1)" />
          <circle cx="90" cy="36" r="6" fill="#34D399" fillOpacity="0.4" />
        </svg>
      </div>
      <div className="absolute right-8 top-1/2 hidden -translate-y-1/2 flex-col items-end gap-5 lg:flex">
        {['Code', 'License', 'Admin', 'Live'].map((t, i) => (
          <div key={t} className="flex items-center gap-3">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-white/80">{t}</span>
            <span
              className={`h-2.5 w-2.5 rounded-full ${i === 0 ? 'bg-[#34D399] shadow-[0_0_0_4px_rgba(52,211,153,0.22)]' : 'bg-white/35'}`}
            />
          </div>
        ))}
      </div>
      <div className="absolute -right-16 bottom-8 h-56 w-56 rounded-full bg-[#34D399]/10 blur-3xl" />
      <div className="absolute left-10 top-20 h-48 w-48 rounded-full bg-[#04A9CE]/10 blur-3xl" />
    </div>
  )
}

function PlatformOpsDecor({ mode }: { mode: 'login' | 'bootstrap' }) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[#050E18]" />
      <GridSignal variant="platform" />
      <div className="absolute inset-x-0 top-[28%] h-px bg-gradient-to-r from-transparent via-[#04A9CE]/40 to-transparent" />
      <div className="absolute inset-x-0 top-[28%] h-24 bg-gradient-to-b from-[#04A9CE]/6 to-transparent" />
      <div className="absolute left-1/2 top-1/2 hidden -translate-x-1/2 -translate-y-1/2 lg:block" style={{ perspective: '800px' }}>
        <svg width="220" height="220" viewBox="0 0 220 220" fill="none" style={{ transform: 'rotateX(20deg) rotateY(-8deg)' }}>
          <rect x="30" y="30" width="160" height="160" rx="24" stroke="#3E5A78" strokeOpacity="0.5" strokeWidth="1.5" fill="rgba(255,255,255,0.02)" />
          <rect x="55" y="55" width="110" height="110" rx="16" stroke="#04A9CE" strokeOpacity="0.35" strokeWidth="1.5" fill="none" />
          {mode === 'login' ? (
            <>
              <path d="M110 78 L142 92 V118 C142 140 128 154 110 160 C92 154 78 140 78 118 V92 Z" stroke="#04A9CE" strokeOpacity="0.55" strokeWidth="2" fill="rgba(4,169,206,0.06)" />
              <rect x="98" y="112" width="24" height="20" rx="3" stroke="#04A9CE" strokeOpacity="0.7" strokeWidth="1.5" />
              <path d="M104 112 V104 a6 6 0 0 1 12 0 v8" stroke="#04A9CE" strokeOpacity="0.7" strokeWidth="1.5" />
            </>
          ) : (
            <>
              {[0, 1, 2, 3].map((i) => (
                <g key={i}>
                  <rect x="82" y={88 + i * 20} width="14" height="14" rx="3" stroke={i === 0 ? '#04A9CE' : '#3E5A78'} strokeWidth="1.5" fill={i === 0 ? 'rgba(4,169,206,0.2)' : 'none'} />
                  {i === 0 && <path d={`M85 ${95 + i * 20} l3 3 5-6`} stroke="#04A9CE" strokeWidth="1.5" fill="none" />}
                  <rect x="104" y={92 + i * 20} width={i % 2 === 0 ? 36 : 28} height="5" rx="2.5" fill="#3E5A78" fillOpacity="0.6" />
                </g>
              ))}
            </>
          )}
        </svg>
      </div>
      <div className="absolute bottom-28 left-8 hidden flex-col gap-2 lg:flex">
        {(mode === 'login'
          ? ['ENCRYPTED', 'RESTRICTED', 'AUDITED']
          : ['BOOTSTRAP', 'ONE-TIME', 'PROTECTED']
        ).map((t) => (
          <div key={t} className="flex items-center gap-2 text-[10px] font-bold tracking-[0.2em] text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full bg-[#04A9CE]/70" />
            {t}
          </div>
        ))}
      </div>
      <div className="absolute bottom-0 inset-x-0 h-40 bg-gradient-to-t from-black/50 to-transparent" />
    </div>
  )
}

function LicenseUnlockDecor() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[linear-gradient(160deg,#0E1C2E_0%,#0C1A2C_50%,#0A1628_100%)]" />
      <GridSignal variant="teacher_license" />
      <svg className="absolute inset-0 h-full w-full" style={{ opacity: 0.1 }} xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="lic-topo" width="80" height="80" patternUnits="userSpaceOnUse">
            <path d="M0 40 Q40 20 80 40" fill="none" stroke="#7EDCF0" strokeWidth="1" />
            <path d="M0 60 Q40 40 80 60" fill="none" stroke="#7EDCF0" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#lic-topo)" />
      </svg>
      <div className="absolute right-[10%] top-[20%] hidden w-72 lg:block" style={{ perspective: '700px' }}>
        <div
          className="rounded-3xl border border-amber-200/80 bg-gradient-to-br from-white via-[#FFFDF8] to-[#FFF8EC] p-6 shadow-[0_28px_60px_rgba(0,0,0,0.4)]"
          style={{ transform: 'rotateY(-14deg) rotateX(8deg) rotateZ(-2deg)' }}
        >
          <div className="flex items-start justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-600">SchemeKnit License</p>
              <p className="mt-2 text-lg font-bold text-[#102A43]">Teacher Pro</p>
            </div>
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-100 shadow-inner">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#D97706" strokeWidth="2" strokeLinecap="round">
                <circle cx="8" cy="14" r="5" />
                <path d="M12 14h9M18 14v4M15 14v3" />
              </svg>
            </div>
          </div>
          <div className="mt-5 space-y-2">
            {[['Status', 'Awaiting activation'], ['Tier', 'Free → Pro'], ['Seats', 'Included']].map(([k, v]) => (
              <div key={k} className="flex justify-between text-xs">
                <span className="text-[#3D5A75]">{k}</span>
                <span className="font-semibold text-[#102A43]">{v}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 h-1 w-full overflow-hidden rounded-full bg-amber-100">
            <div className="h-full w-1/3 rounded-full bg-gradient-to-r from-amber-400 to-[#04A9CE]" />
          </div>
        </div>
        <div
          className="absolute -right-5 -top-5 -z-10 h-full w-full rounded-3xl border border-white/12 bg-white/10 shadow-lg"
          style={{ transform: 'rotateY(-14deg) rotateX(8deg) translateZ(-30px)' }}
        />
      </div>
      <div className="absolute -left-20 top-1/3 h-64 w-64 rounded-full bg-amber-400/10 blur-3xl" />
      <div className="absolute right-1/4 bottom-16 h-48 w-48 rounded-full bg-[#04A9CE]/10 blur-3xl" />
    </div>
  )
}

function RecoverySecurityDecor() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[linear-gradient(180deg,#0A1628_0%,#0B1A30_100%)]" />
      <GridSignal variant="password_reset" />
      <div className="absolute left-[8%] top-[14%] hidden lg:block" style={{ perspective: '600px' }}>
        <div
          className="relative flex h-44 w-44 items-center justify-center"
          style={{ transform: 'rotateX(50deg) rotateZ(-12deg)' }}
        >
          <div className="absolute inset-0 rounded-full border-2 border-white/15" />
          <div className="absolute inset-5 rounded-full border-2 border-[#38BDF8]/40" />
          <div className="absolute inset-10 rounded-full border border-dashed border-white/25" />
          <div className="absolute inset-14 rounded-full bg-white/92 shadow-lg ring-1 ring-[#102A43]/10" />
          <svg width="36" height="36" viewBox="0 0 36 36" fill="none" className="relative z-10">
            <rect x="8" y="16" width="20" height="14" rx="3" stroke="#102A43" strokeWidth="2" fill="white" />
            <path d="M12 16 V12 a6 6 0 0 1 12 0 v4" stroke="#04A9CE" strokeWidth="2" fill="none" />
            <circle cx="18" cy="23" r="2" fill="#04A9CE" />
          </svg>
        </div>
      </div>
      <div className="absolute right-[8%] top-1/2 hidden -translate-y-1/2 flex-col gap-4 xl:flex">
        {['Token', 'Verify', 'New password'].map((t, i) => (
          <div key={t} className="flex items-center gap-3">
            <span
              className={`h-2.5 w-2.5 rounded-full ${i === 0 ? 'bg-[#38BDF8] shadow-[0_0_0_4px_rgba(56,189,248,0.2)]' : 'bg-white/35'}`}
            />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-white/80">{t}</span>
            {i < 2 && <span className="ml-2 h-px w-8 bg-white/25" />}
          </div>
        ))}
      </div>
      <div className="absolute -right-20 bottom-10 h-64 w-64 rounded-full bg-[#38BDF8]/10 blur-3xl" />
      <div className="absolute left-16 bottom-24 h-40 w-40 rounded-full bg-[#04A9CE]/10 blur-2xl" />
    </div>
  )
}

function FirstRunInitDecor() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[linear-gradient(145deg,#0D1630_0%,#0C1530_55%,#0B1430_100%)]" />
      <GridSignal variant="first_run" />
      <svg className="absolute inset-0 h-full w-full" style={{ opacity: 0.1 }} xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="init-hex" width="60" height="52" patternUnits="userSpaceOnUse">
            <path d="M30 0 L60 15 V45 L30 60 L0 45 V15 Z" fill="none" stroke="#A78BFA" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#init-hex)" />
      </svg>
      <div className="absolute left-1/2 top-[14%] hidden -translate-x-1/2 lg:block" style={{ perspective: '700px' }}>
        <div
          className="w-80 rounded-2xl border border-violet-300/40 bg-white/95 p-5 shadow-[0_24px_50px_rgba(0,0,0,0.35)]"
          style={{ transform: 'rotateX(10deg) rotateY(-6deg)' }}
        >
          <div className="flex items-center gap-2 border-b border-border pb-3">
            <span className="h-2.5 w-2.5 rounded-full bg-violet-400" />
            <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
            <span className="ml-2 text-[10px] font-bold tracking-wider text-muted-foreground">SYSTEM INIT</span>
          </div>
          <div className="mt-3 space-y-2 font-mono text-[11px]">
            <p className="text-emerald-600">✓ Environment detected</p>
            <p className="text-emerald-600">✓ Database reachable</p>
            <p className="text-violet-600">→ Create administrator…</p>
            <p className="text-muted-foreground">· Configure school (optional)</p>
          </div>
          <div className="mt-4 flex gap-1.5">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <span
                key={i}
                className={`h-1.5 flex-1 rounded-full ${i < 3 ? 'bg-violet-500' : 'bg-violet-100'}`}
              />
            ))}
          </div>
        </div>
      </div>
      <div className="absolute -left-16 top-1/4 h-56 w-56 rounded-full bg-violet-500/15 blur-3xl" />
      <div className="absolute right-12 bottom-16 h-48 w-48 rounded-full bg-[#04A9CE]/10 blur-3xl" />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Shared depth card wrapper (3D)                                      */
/* ------------------------------------------------------------------ */

function DepthCard({
  children,
  dark = false,
  accent,
  className = '',
}: {
  children: ReactNode
  dark?: boolean
  accent: string
  className?: string
}) {
  return (
    <div className={`relative ${className}`} style={{ perspective: '1200px' }}>
      <div
        aria-hidden="true"
        className={`absolute inset-x-3 -bottom-2 top-3 rounded-[1.35rem] ${
          dark ? 'bg-black/25' : 'bg-[#102A43]/6'
        }`}
        style={{ transform: 'translateZ(-40px) rotateX(4deg)' }}
      />
      <div
        className={`relative overflow-hidden rounded-2xl border ${
          dark
            ? 'border-white/10 bg-white text-[#102A43] shadow-[0_30px_70px_rgba(0,0,0,0.45)]'
            : 'border-[#102A43]/8 bg-white text-[#102A43] shadow-[0_24px_55px_rgba(16,42,67,0.12)]'
        }`}
        style={{ transform: 'translateZ(0)' }}
      >
        <div className={`h-1.5 ${accent}`} />
        {children}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Shell                                                               */
/* ------------------------------------------------------------------ */

interface RoleTheme {
  badge: string
  badgeClass: string
  title: string
  pageClass: string
  decor: ReactNode
  accentBar: string
  aside: ReactNode
  asideClass: string
  /** How the main content column is composed. */
  layout: 'split' | 'centered' | 'wide'
}

const THEMES: Record<AuthShellRole, RoleTheme> = {
  teacher: {
    badge: 'Teacher',
    badgeClass: 'border-[#04A9CE]/40 bg-[#04A9CE]/10 text-[#0389a8]',
    title: 'Teacher Sign In',
    pageClass: 'bg-[#071826]',
    decor: <TeacherWorkspaceDecor />,
    accentBar: 'bg-gradient-to-r from-[#102A43] via-[#04A9CE] to-[#7EDCF0]',
    aside: null,
    asideClass: 'text-[#102A43]',
    layout: 'centered',
  },
  register: {
    badge: 'Registration',
    badgeClass: 'border-[#04A9CE]/40 bg-[#04A9CE]/10 text-[#0389a8]',
    title: 'Create your account',
    pageClass: 'bg-[#0A1F35]',
    decor: <RegisterOnboardingDecor />,
    accentBar: 'bg-gradient-to-r from-[#04A9CE] to-[#7EDCF0]',
    aside: null,
    asideClass: 'text-[#102A43]',
    layout: 'centered',
  },
  school_admin: {
    badge: 'School Administration',
    badgeClass: 'border-emerald-400/50 bg-emerald-500/10 text-emerald-700',
    title: 'School Administration Sign In',
    pageClass: 'bg-[#0B1F3A] text-white',
    decor: (
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute inset-0 bg-[#0B1F3A]" />
        <GridSignal variant="school" />
        <svg className="absolute left-10 bottom-12 h-48 w-56 text-white/25" viewBox="0 0 200 160" fill="none">
          <rect x="30" y="50" width="140" height="90" stroke="currentColor" strokeWidth="2" />
          <path d="M30 50 L100 15 L170 50" stroke="currentColor" strokeWidth="2" />
          <rect x="55" y="80" width="28" height="36" stroke="currentColor" strokeWidth="1.5" />
          <rect x="117" y="80" width="28" height="36" stroke="currentColor" strokeWidth="1.5" />
          <rect x="88" y="95" width="24" height="45" stroke="#04A9CE" strokeOpacity="0.7" strokeWidth="1.5" />
        </svg>
        <div className="absolute right-16 top-24 hidden h-40 w-px bg-gradient-to-b from-transparent via-[#04A9CE]/50 to-transparent lg:block" />
        <div className="absolute right-12 top-24 hidden h-2 w-2 rounded-full bg-[#04A9CE]/70 lg:block" />
      </div>
    ),
    accentBar: 'bg-gradient-to-r from-emerald-600 to-[#04A9CE]',
    aside: (
      <div className="hidden max-w-md py-12 lg:block">
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7EDCF0]">
          Institutional workspace
        </p>
        <h2 className="text-3xl font-semibold leading-tight tracking-tight text-white xl:text-4xl">
          Manage your school
          <br />
          with clarity.
        </h2>
        <p className="mt-5 text-[15px] leading-relaxed text-white/75">
          Seats, teachers, license status and school settings — structured for
          headteachers and administrators.
        </p>
        <ul className="mt-8 space-y-3 text-sm text-white/70">
          <li className="flex gap-2.5">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#04A9CE]" />
            License and seat visibility
          </li>
          <li className="flex gap-2.5">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#04A9CE]" />
            Teacher account administration
          </li>
          <li className="flex gap-2.5">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#04A9CE]" />
            School-level workflow control
          </li>
        </ul>
      </div>
    ),
    asideClass: '',
    layout: 'split',
  },
  platform_admin: {
    badge: 'Platform Administration',
    badgeClass: 'border-slate-400/50 bg-slate-100 text-slate-700',
    title: 'Platform Administration Sign In',
    pageClass: 'bg-[#050E18] text-white',
    decor: <PlatformOpsDecor mode="login" />,
    accentBar: 'bg-gradient-to-r from-slate-600 via-[#04A9CE]/60 to-slate-700',
    aside: (
      <div className="hidden max-w-md py-12 lg:block">
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7EDCF0]">
          Restricted operations
        </p>
        <h2 className="text-3xl font-semibold leading-tight tracking-tight text-white xl:text-4xl">
          Platform control
          <br />
          surface.
        </h2>
        <p className="mt-5 text-[15px] leading-relaxed text-slate-400">
          Schools, licenses, payments and audit — for authorized SchemeKnit
          platform staff only.
        </p>
        <ul className="mt-8 space-y-3 text-sm text-slate-400">
          <li className="flex gap-2.5">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />
            Not listed on public pages
          </li>
          <li className="flex gap-2.5">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />
            Direct route only
          </li>
          <li className="flex gap-2.5">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />
            Backend authorization remains authoritative
          </li>
        </ul>
      </div>
    ),
    asideClass: '',
    layout: 'split',
  },
  school_activate: {
    badge: 'School activation',
    badgeClass: 'border-[#34D399]/45 bg-[#34D399]/12 text-[#0D7A58]',
    title: 'Activate Your School',
    pageClass: 'bg-[#0A2240] text-white',
    decor: <SchoolInstitutionDecor />,
    accentBar: 'bg-gradient-to-r from-[#04A9CE] to-emerald-500',
    aside: null,
    asideClass: 'text-white',
    layout: 'wide',
  },
  teacher_license: {
    badge: 'Teacher license',
    badgeClass: 'border-amber-400/50 bg-amber-500/10 text-amber-700',
    title: 'Activate Teacher License',
    pageClass: 'bg-[#0E1C2E] text-white',
    decor: <LicenseUnlockDecor />,
    accentBar: 'bg-gradient-to-r from-amber-500 to-[#04A9CE]',
    aside: null,
    asideClass: 'text-white',
    layout: 'wide',
  },
  password_reset: {
    badge: 'Account recovery',
    badgeClass: 'border-[#102A43]/20 bg-[#102A43]/5 text-[#102A43]',
    title: 'Reset Your Password',
    pageClass: 'bg-[#0A1628] text-white',
    decor: <RecoverySecurityDecor />,
    accentBar: 'bg-gradient-to-r from-[#102A43] to-[#38BDF8]',
    aside: null,
    asideClass: 'text-white',
    layout: 'centered',
  },
  first_run: {
    badge: 'First-run setup',
    badgeClass: 'border-violet-400/40 bg-violet-500/10 text-violet-700',
    title: 'Set Up SchemeKnit',
    pageClass: 'bg-[#0D1630] text-white',
    decor: <FirstRunInitDecor />,
    accentBar: 'bg-gradient-to-r from-violet-600 to-[#04A9CE]',
    aside: null,
    asideClass: 'text-white',
    layout: 'centered',
  },
}

const DARK_ROLES = new Set<AuthShellRole>([
  'teacher',
  'school_admin',
  'platform_admin',
  'register',
  'school_activate',
  'teacher_license',
  'password_reset',
  'first_run',
])

export interface AuthShellProps {
  role: AuthShellRole
  title: string
  description: string
  children: ReactNode
  footer?: ReactNode
  securityNote?: string
  steps?: { label: string; active?: boolean; done?: boolean }[]
  compactBrand?: boolean
  /** Override decor for variants (e.g. platform bootstrap vs login). */
  decorOverride?: ReactNode
}

function StepRail({
  steps,
  onDark = false,
}: {
  steps: { label: string; active?: boolean; done?: boolean }[]
  onDark?: boolean
}) {
  return (
    <ol className="mb-5 flex flex-wrap gap-2" aria-label="Progress">
      {steps.map((s, i) => (
        <li
          key={s.label}
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
            s.active
              ? onDark
                ? 'border-[#04A9CE]/60 bg-[#04A9CE]/18 text-[#7EDCF0] shadow-[0_0_0_3px_rgba(4,169,206,0.12)]'
                : 'border-[#04A9CE]/50 bg-[#04A9CE]/12 text-[#0389a8] shadow-[0_0_0_3px_rgba(4,169,206,0.1)]'
              : s.done
                ? onDark
                  ? 'border-emerald-400/45 bg-emerald-500/15 text-emerald-300'
                  : 'border-emerald-400/40 bg-emerald-500/10 text-emerald-700'
                : onDark
                  ? 'border-white/20 bg-white/12 text-white/75'
                  : 'border-[#102A43]/10 bg-white/70 text-muted-foreground'
          }`}
        >
          <span
            className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] ${
              s.active
                ? 'bg-[#04A9CE] text-white'
                : s.done
                  ? 'bg-emerald-500 text-white'
                  : onDark
                    ? 'bg-white/25 text-white'
                    : 'bg-[#102A43]/10'
            }`}
          >
            {i + 1}
          </span>
          {s.label}
        </li>
      ))}
    </ol>
  )
}

export function AuthShell({
  role,
  title,
  description,
  children,
  footer,
  securityNote,
  steps,
  decorOverride,
}: AuthShellProps) {
  const theme = THEMES[role]
  const isDark = DARK_ROLES.has(role)
  const showAside = theme.layout === 'split'
  const decor = decorOverride ?? theme.decor
  const isWide = theme.layout === 'wide'

  return (
    <div className={`relative min-h-screen overflow-hidden ${theme.pageClass}`}>
      {decor}

      <div
        className={`relative z-10 min-h-screen ${
          showAside ? 'lg:grid lg:grid-cols-[1.05fr_1fr] xl:grid-cols-[1.15fr_1fr]' : ''
        }`}
      >
        {showAside ? (
          <aside className="flex flex-col justify-between px-6 py-8 sm:px-10 lg:min-h-screen lg:px-14 lg:py-12">
            <BrandCapsule dark showWordmark />
            {theme.aside}
            <p
              className={`hidden text-xs lg:block ${
                role === 'platform_admin' ? 'text-slate-400' : 'text-white/50'
              }`}
            >
              © SchemeKnit · Trust · Clarity · Professionalism
            </p>
          </aside>
        ) : (
          <aside className="relative hidden lg:block" aria-hidden="true" />
        )}

        <main className="flex items-center justify-center px-4 pb-14 pt-6 sm:px-6 lg:px-10 lg:py-12">
          <div className={isWide ? 'w-full max-w-lg' : 'w-full max-w-md'}>
            <div className="mb-6 flex items-center justify-between gap-3">
              <BrandCapsule dark={isDark} href="/" size={44} mark={28} showWordmark />
              {!showAside && (
                <span
                  className={`rounded-full px-2.5 py-1 text-[11px] font-semibold shadow-sm backdrop-blur ${
                    isDark
                      ? 'border border-white/20 bg-white/12 text-white/90'
                      : 'border border-[#102A43]/10 bg-white/85 text-muted-foreground'
                  }`}
                >
                  {theme.badge}
                </span>
              )}
            </div>

            {isWide && (
              <div className="mb-5">
                <RoleBadge className="border-white/25 bg-white/12 text-white/90">
                  {theme.badge}
                </RoleBadge>
                <h1 className="mt-3 text-[1.65rem] font-bold leading-tight tracking-tight text-white sm:text-3xl">
                  {title || theme.title}
                </h1>
                <p className="mt-2 text-sm leading-relaxed text-white/70">{description}</p>
                {steps && steps.length > 0 && (
                  <div className="mt-4">
                    <StepRail steps={steps} onDark />
                  </div>
                )}
                {securityNote && (
                  <p className="mt-3 rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-xs text-white/70 shadow-sm">
                    {securityNote}
                  </p>
                )}
              </div>
            )}

            {!isWide && steps && steps.length > 0 && <StepRail steps={steps} onDark={isDark} />}

            <DepthCard dark={isDark} accent={theme.accentBar}>
              <div className="px-6 py-7 sm:px-8">
                {!isWide && (
                  <>
                    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                      <RoleBadge className={theme.badgeClass}>{theme.badge}</RoleBadge>
                      {role === 'platform_admin' && (
                        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                          <span className="relative flex h-2 w-2">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                          </span>
                          Restricted access
                        </span>
                      )}
                      {role === 'teacher' && (
                        <span className="rounded-full border border-border bg-[#F4F7FA] px-2.5 py-1 text-[11px] font-semibold text-muted-foreground">
                          Free Tier available
                        </span>
                      )}
                      {role === 'register' && (
                        <span className="rounded-full border border-[#04A9CE]/30 bg-[#04A9CE]/8 px-2.5 py-1 text-[11px] font-semibold text-[#0389a8]">
                          Step 1 of 2
                        </span>
                      )}
                    </div>
                    <h1 className="text-2xl font-bold tracking-tight text-[#102A43]">
                      {title || theme.title}
                    </h1>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {description}
                    </p>
                    {securityNote && (
                      <p className="mt-3 rounded-lg border border-border bg-[#F4F7FA] px-3 py-2 text-xs text-muted-foreground">
                        {securityNote}
                      </p>
                    )}
                  </>
                )}

                <div className={isWide ? '' : 'mt-6'}>{children}</div>

                {footer && (
                  <div className="mt-6 border-t border-border pt-5">{footer}</div>
                )}
              </div>
            </DepthCard>

            <p className="mt-5 text-center">
              <Link
                href="/"
                className={`inline-flex items-center rounded-lg border px-3.5 py-1.5 text-xs font-semibold shadow-sm transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/50 ${
                  isDark
                    ? 'border-white/25 bg-white/15 text-white'
                    : 'border-[#102A43]/15 bg-white/90 text-[#102A43]'
                }`}
              >
                Back to SchemeKnit
              </Link>
            </p>
          </div>
        </main>
      </div>
    </div>
  )
}
