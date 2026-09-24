'use client'

import Link from 'next/link'
import { ReactNode } from 'react'

import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { RoleBadge } from '@/components/auth/auth-field'

/**
 * Role-specific authentication shells.
 *
 * Mesh backgrounds are landing-only (Hero V3). Every auth / activation
 * surface gets its own professional visual concept — shared typography,
 * buttons, inputs and logo treatment only.
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

interface RoleTheme {
  badge: string
  badgeClass: string
  title: string
  /** Outer page background (no mesh). */
  pageClass: string
  /** Decorative layer className / style */
  decor: ReactNode
  /** Card accent bar */
  accentBar: string
  /** Side panel content for desktop */
  aside: ReactNode
  /** Text color mode for aside */
  asideClass: string
}

/** Light capsule so the canonical navy S reads on dark surfaces. */
export function BrandCapsule({
  size = 40,
  mark = 26,
  dark = false,
  href = '/',
  className = '',
}: {
  size?: number
  mark?: number
  dark?: boolean
  href?: string
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
          ? '0 0 0 1px rgba(4,169,206,0.28), 0 4px 14px rgba(0,0,0,0.18)'
          : '0 0 0 1px rgba(4,169,206,0.22), 0 1px 3px rgba(16,42,67,0.08)',
      }}
    >
      <SchemeKnitMark size={mark} />
    </span>
  )
  if (!href) return inner
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-3 rounded-xl transition hover:opacity-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/60"
      aria-label="SchemeKnit home"
    >
      {inner}
      <span className="text-lg font-bold tracking-tight">
        Scheme<span className="text-[#04A9CE]">Knit</span>
      </span>
    </Link>
  )
}

function TeacherDecor() {
  // Soft geometric education motifs — no mesh.
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute -left-24 top-16 h-72 w-72 rounded-full bg-[#04A9CE]/10 blur-2xl" />
      <div className="absolute right-10 bottom-24 h-56 w-56 rounded-3xl bg-[#102A43]/8 rotate-12 blur-xl" />
      <svg className="absolute left-8 bottom-16 h-40 w-40 text-[#102A43]/10" viewBox="0 0 160 160" fill="none">
        <rect x="20" y="30" width="70" height="90" rx="6" stroke="currentColor" strokeWidth="2" />
        <path d="M30 50h50M30 65h40M30 80h45" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <circle cx="115" cy="95" r="28" stroke="#04A9CE" strokeOpacity="0.35" strokeWidth="2" />
        <path d="M105 95h20M115 85v20" stroke="#04A9CE" strokeOpacity="0.45" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <div className="absolute right-16 top-20 hidden gap-3 lg:flex">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-2.5 w-2.5 rounded-full"
            style={{ background: i === 1 ? '#04A9CE' : 'rgba(16,42,67,0.2)' }}
          />
        ))}
      </div>
    </div>
  )
}

function RegisterDecor() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-[#04A9CE]/12 to-transparent" />
      <div className="absolute right-8 top-28 hidden w-56 space-y-3 lg:block">
        {['Upload scheme', 'Review indicators', 'Generate lessons'].map((t, i) => (
          <div
            key={t}
            className="rounded-xl border border-[#102A43]/10 bg-white/90 px-4 py-3 text-sm text-[#102A43] shadow-sm"
            style={{ marginLeft: i * 16 }}
          >
            <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-[#04A9CE]/15 text-[11px] font-bold text-[#0389a8]">
              {i + 1}
            </span>
            {t}
          </div>
        ))}
      </div>
      <div className="absolute -left-16 bottom-0 h-64 w-64 rounded-full bg-[#102A43]/6 blur-2xl" />
    </div>
  )
}

function SchoolDecor() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      {/* Architectural grid / building motif */}
      <svg className="absolute inset-0 h-full w-full opacity-[0.12]" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="school-grid" width="48" height="48" patternUnits="userSpaceOnUse">
            <path d="M48 0H0V48" fill="none" stroke="#7EDCF0" strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#school-grid)" />
      </svg>
      <svg className="absolute left-10 bottom-12 h-48 w-56 text-white/20" viewBox="0 0 200 160" fill="none">
        <rect x="30" y="50" width="140" height="90" stroke="currentColor" strokeWidth="2" />
        <path d="M30 50 L100 15 L170 50" stroke="currentColor" strokeWidth="2" />
        <rect x="55" y="80" width="28" height="36" stroke="currentColor" strokeWidth="1.5" />
        <rect x="117" y="80" width="28" height="36" stroke="currentColor" strokeWidth="1.5" />
        <rect x="88" y="95" width="24" height="45" stroke="#04A9CE" strokeOpacity="0.7" strokeWidth="1.5" />
      </svg>
      <div className="absolute right-16 top-24 hidden h-40 w-px bg-gradient-to-b from-transparent via-[#04A9CE]/50 to-transparent lg:block" />
      <div className="absolute right-12 top-24 hidden h-2 w-2 rounded-full bg-[#04A9CE]/70 lg:block" />
    </div>
  )
}

function PlatformDecor() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(16,42,67,0.9),transparent_60%)]" />
      <svg className="absolute left-1/2 top-1/3 h-56 w-56 -translate-x-1/2 text-white/10" viewBox="0 0 120 120" fill="none">
        <path d="M60 12 L100 28 V58 C100 84 82 102 60 110 C38 102 20 84 20 58 V28 Z" stroke="currentColor" strokeWidth="2" />
        <rect x="44" y="52" width="32" height="28" rx="4" stroke="#04A9CE" strokeOpacity="0.45" strokeWidth="2" />
        <path d="M50 52 V44 a10 10 0 0 1 20 0 v8" stroke="#04A9CE" strokeOpacity="0.45" strokeWidth="2" />
      </svg>
      <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-black/35 to-transparent" />
    </div>
  )
}

function ActivateDecor({ kind }: { kind: 'school' | 'teacher' | 'reset' }) {
  if (kind === 'reset') {
    return (
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-12 h-40 w-40 -translate-x-1/2 rounded-full bg-[#04A9CE]/10 blur-2xl" />
        <svg className="absolute left-1/2 top-16 h-24 w-24 -translate-x-1/2 text-[#102A43]/25" viewBox="0 0 96 96" fill="none">
          <circle cx="48" cy="40" r="16" stroke="currentColor" strokeWidth="3" />
          <path d="M36 52 L28 78 H68 L60 52" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" />
          <circle cx="48" cy="40" r="5" fill="#04A9CE" fillOpacity="0.7" />
        </svg>
      </div>
    )
  }
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute left-1/2 top-8 h-48 w-48 -translate-x-1/2 rounded-full bg-[#04A9CE]/12 blur-3xl" />
      <svg className="absolute left-1/2 top-14 h-28 w-28 -translate-x-1/2 text-[#102A43]/30" viewBox="0 0 112 112" fill="none">
        <circle cx="40" cy="56" r="18" stroke="currentColor" strokeWidth="4" />
        <path d="M54 56 H96 M84 56 V70 M72 56 V66" stroke="#04A9CE" strokeWidth="4" strokeLinecap="round" />
        <circle cx="40" cy="56" r="6" fill="#04A9CE" fillOpacity="0.65" />
      </svg>
      {kind === 'school' && (
        <div className="absolute left-1/2 top-44 -translate-x-1/2 text-xs font-semibold uppercase tracking-[0.2em] text-[#04A9CE]/70">
          School activation
        </div>
      )}
      {kind === 'teacher' && (
        <div className="absolute left-1/2 top-44 -translate-x-1/2 text-xs font-semibold uppercase tracking-[0.2em] text-[#04A9CE]/70">
          Teacher license
        </div>
      )}
    </div>
  )
}

const THEMES: Record<AuthShellRole, RoleTheme> = {
  teacher: {
    badge: 'Teacher',
    badgeClass: 'border-[#04A9CE]/40 bg-[#04A9CE]/10 text-[#0389a8]',
    title: 'Teacher Sign In',
    pageClass: 'bg-[#F7F5F0]',
    decor: <TeacherDecor />,
    accentBar: 'bg-gradient-to-r from-[#102A43] via-[#04A9CE] to-[#7EDCF0]',
    aside: null,
    asideClass: 'text-[#102A43]',
  },
  register: {
    badge: 'Teacher',
    badgeClass: 'border-[#04A9CE]/40 bg-[#04A9CE]/10 text-[#0389a8]',
    title: 'Create your account',
    pageClass: 'bg-white',
    decor: <RegisterDecor />,
    accentBar: 'bg-gradient-to-r from-[#04A9CE] to-[#7EDCF0]',
    aside: null,
    asideClass: 'text-[#102A43]',
  },
  school_admin: {
    badge: 'School Administration',
    badgeClass: 'border-emerald-400/50 bg-emerald-500/10 text-emerald-700',
    title: 'School Administration Sign In',
    pageClass: 'bg-[#0B1F3A] text-white',
    decor: <SchoolDecor />,
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
        <p className="mt-5 text-[15px] leading-relaxed text-white/70">
          Seats, teachers, license status and school settings — structured for
          headteachers and administrators.
        </p>
        <ul className="mt-8 space-y-3 text-sm text-white/65">
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
  },
  platform_admin: {
    badge: 'Platform Administration',
    badgeClass: 'border-slate-400/40 bg-slate-500/15 text-slate-200',
    title: 'Platform Administration Sign In',
    pageClass: 'bg-[#050E18] text-white',
    decor: <PlatformDecor />,
    accentBar: 'bg-slate-600',
    aside: (
      <div className="hidden max-w-md py-12 lg:block">
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
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
        <ul className="mt-8 space-y-3 text-sm text-slate-500">
          <li className="flex gap-2.5">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-500" />
            Not listed on public pages
          </li>
          <li className="flex gap-2.5">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-500" />
            Direct route only
          </li>
          <li className="flex gap-2.5">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-500" />
            Backend authorization remains authoritative
          </li>
        </ul>
      </div>
    ),
    asideClass: '',
  },
  school_activate: {
    badge: 'School activation',
    badgeClass: 'border-[#04A9CE]/40 bg-[#04A9CE]/10 text-[#0389a8]',
    title: 'Activate Your School',
    pageClass: 'bg-[#F3F6FA]',
    decor: <ActivateDecor kind="school" />,
    accentBar: 'bg-gradient-to-r from-[#04A9CE] to-emerald-500',
    aside: null,
    asideClass: 'text-[#102A43]',
  },
  teacher_license: {
    badge: 'Teacher license',
    badgeClass: 'border-amber-400/50 bg-amber-500/10 text-amber-700',
    title: 'Activate Teacher License',
    pageClass: 'bg-[#FAFAF7]',
    decor: <ActivateDecor kind="teacher" />,
    accentBar: 'bg-gradient-to-r from-amber-500 to-[#04A9CE]',
    aside: null,
    asideClass: 'text-[#102A43]',
  },
  password_reset: {
    badge: 'Account recovery',
    badgeClass: 'border-[#102A43]/20 bg-[#102A43]/5 text-[#102A43]',
    title: 'Reset Your Password',
    pageClass: 'bg-[#F4F7FA]',
    decor: <ActivateDecor kind="reset" />,
    accentBar: 'bg-gradient-to-r from-[#102A43] to-[#04A9CE]',
    aside: null,
    asideClass: 'text-[#102A43]',
  },
  first_run: {
    badge: 'First-run setup',
    badgeClass: 'border-violet-400/40 bg-violet-500/10 text-violet-700',
    title: 'Set Up SchemeKnit',
    pageClass: 'bg-[#F8F7FC]',
    decor: (
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -right-20 top-1/4 h-72 w-72 rounded-full bg-violet-500/10 blur-3xl" />
        <div className="absolute left-1/2 top-16 h-40 w-40 -translate-x-1/2 rounded-full bg-[#04A9CE]/10 blur-2xl" />
        <svg className="absolute left-1/2 top-20 h-24 w-24 -translate-x-1/2 text-violet-500/35" viewBox="0 0 96 96" fill="none">
          <path d="M20 30 h56 v40 H20 Z" stroke="currentColor" strokeWidth="3" />
          <path d="M20 30 L48 52 L76 30" stroke="#04A9CE" strokeOpacity="0.6" strokeWidth="3" />
        </svg>
      </div>
    ),
    accentBar: 'bg-gradient-to-r from-violet-600 to-[#04A9CE]',
    aside: null,
    asideClass: 'text-[#102A43]',
  },
}

export interface AuthShellProps {
  role: AuthShellRole
  title: string
  description: string
  children: ReactNode
  footer?: ReactNode
  securityNote?: string
  /** Optional step indicator (activation / registration). */
  steps?: { label: string; active?: boolean; done?: boolean }[]
  /** Hide default brand header row above the card (desktop aside provides it). */
  compactBrand?: boolean
}

export function AuthShell({
  role,
  title,
  description,
  children,
  footer,
  securityNote,
  steps,
}: AuthShellProps) {
  const theme = THEMES[role]
  const isDark =
    role === 'school_admin' || role === 'platform_admin'
  const showAside = role === 'school_admin' || role === 'platform_admin'

  return (
    <div className={`relative min-h-screen overflow-hidden ${theme.pageClass}`}>
      {theme.decor}

      <div className="relative z-10 min-h-screen lg:grid lg:grid-cols-[1.05fr_1fr] xl:grid-cols-[1.15fr_1fr]">
        {showAside ? (
          <aside className="flex flex-col justify-between px-6 py-8 sm:px-10 lg:min-h-screen lg:px-14 lg:py-12">
            <BrandCapsule dark href="/" />
            {theme.aside}
            <p
              className={`hidden text-xs lg:block ${
                role === 'platform_admin' ? 'text-slate-500' : 'text-white/40'
              }`}
            >
              © SchemeKnit · Trust · Clarity · Professionalism
            </p>
          </aside>
        ) : (
          <aside className="relative hidden lg:block" aria-hidden="true" />
        )}

        <main className="flex items-center justify-center px-4 pb-12 pt-6 sm:px-6 lg:px-10 lg:py-12">
          <div className="w-full max-w-md">
            <div className="mb-6 flex items-center justify-between gap-3">
              <BrandCapsule dark={isDark} href="/" size={40} mark={26} />
              {!isDark && (
                <span className="rounded-full border border-[#102A43]/10 bg-white/80 px-2.5 py-1 text-[11px] font-semibold text-muted-foreground backdrop-blur">
                  SchemeKnit
                </span>
              )}
            </div>

            {steps && steps.length > 0 && (
              <ol className="mb-5 flex flex-wrap gap-2" aria-label="Progress">
                {steps.map((s, i) => (
                  <li
                    key={s.label}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
                      s.active
                        ? 'border-[#04A9CE]/50 bg-[#04A9CE]/12 text-[#0389a8]'
                        : s.done
                          ? 'border-emerald-400/40 bg-emerald-500/10 text-emerald-700'
                          : 'border-[#102A43]/10 bg-white/70 text-muted-foreground'
                    }`}
                  >
                    <span
                      className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] ${
                        s.active
                          ? 'bg-[#04A9CE] text-white'
                          : s.done
                            ? 'bg-emerald-500 text-white'
                            : 'bg-[#102A43]/10'
                      }`}
                    >
                      {i + 1}
                    </span>
                    {s.label}
                  </li>
                ))}
              </ol>
            )}

            <div
              className={`overflow-hidden rounded-2xl border ${
                isDark
                  ? 'border-white/10 bg-white text-[#102A43] shadow-[0_24px_60px_rgba(0,0,0,0.4)]'
                  : 'border-[#102A43]/8 bg-white text-[#102A43] shadow-[0_20px_50px_rgba(16,42,67,0.1)]'
              }`}
            >
              <div className={`h-1.5 ${theme.accentBar}`} />
              <div className="px-6 py-7 sm:px-8">
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

                <div className="mt-6">{children}</div>

                {footer && (
                  <div className="mt-6 border-t border-border pt-5">{footer}</div>
                )}
              </div>
            </div>

            <p
              className={`mt-5 text-center text-xs ${
                isDark ? 'text-white/45' : 'text-muted-foreground'
              }`}
            >
              <Link
                href="/"
                className="underline-offset-2 hover:underline"
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
