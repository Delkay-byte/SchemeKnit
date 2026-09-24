'use client'

import Link from 'next/link'
import { ReactNode } from 'react'

import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { MeshBackground } from '@/components/mesh-background'
import { RoleBadge } from '@/components/auth/auth-field'

/**
 * Shared authentication shell.
 *
 * Desktop: left brand/value panel · right form card.
 * Mobile: brand stacks above a full-width form card.
 *
 * Visual language: deep navy #071826 / #102A43, cyan #04A9CE, white card,
 * cool gray type. Background uses a light ambient curriculum mesh (no cursor
 * deformation) so the form stays the focus.
 *
 * Role is cosmetic only — backend role checks remain authoritative.
 */

export type AuthShellRole = 'teacher' | 'school_admin' | 'platform_admin' | 'register'

const ROLE_ACCENT: Record<
  AuthShellRole,
  { badge: string; badgeClass: string; title: string }
> = {
  teacher: {
    badge: 'Teacher',
    badgeClass: 'border-[#04A9CE]/40 bg-[#04A9CE]/10 text-[#7EDCF0]',
    title: 'Teacher Sign In',
  },
  school_admin: {
    badge: 'School Administration',
    badgeClass: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-300',
    title: 'School Administration Sign In',
  },
  platform_admin: {
    badge: 'Platform Administration',
    badgeClass: 'border-slate-400/40 bg-slate-400/10 text-slate-300',
    title: 'Platform Administration Sign In',
  },
  register: {
    badge: 'Teacher',
    badgeClass: 'border-[#04A9CE]/40 bg-[#04A9CE]/10 text-[#7EDCF0]',
    title: 'Create your account',
  },
}

export interface AuthShellProps {
  role: AuthShellRole
  title: string
  description: string
  children: ReactNode
  footer?: ReactNode
  securityNote?: string
  operational?: boolean
}

export function AuthShell({
  role,
  title,
  description,
  children,
  footer,
  securityNote,
  operational = false,
}: AuthShellProps) {
  const accent = ROLE_ACCENT[role]

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#071826] text-white">
      <MeshBackground mode="ambient" opacity={operational ? 0.55 : 0.75} />

      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background: operational
            ? 'radial-gradient(900px 500px at 18% 30%, rgba(16,42,67,0.55), transparent 70%)'
            : 'radial-gradient(900px 500px at 18% 30%, rgba(4,169,206,0.12), transparent 65%), radial-gradient(700px 420px at 85% 70%, rgba(4,169,206,0.07), transparent 60%)',
        }}
      />

      <div className="relative z-10 min-h-screen lg:grid lg:grid-cols-[1.05fr_1fr] xl:grid-cols-[1.15fr_1fr]">
        <aside className="flex flex-col justify-between px-6 py-8 sm:px-10 lg:min-h-screen lg:px-14 lg:py-12">
          <Link
            href="/"
            className="inline-flex w-fit items-center gap-3 rounded-xl border border-white/10 bg-[#0d2740]/80 px-3 py-2 shadow-[0_8px_28px_rgba(0,0,0,0.28)] transition hover:border-[#04A9CE]/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/60"
          >
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#102A43] ring-1 ring-[#04A9CE]/30 shadow-[0_0_16px_rgba(4,169,206,0.18)]">
              <SchemeKnitMark size={26} />
            </span>
            <span className="text-lg font-bold tracking-tight">
              Scheme<span className="text-[#04A9CE]">Knit</span>
            </span>
          </Link>

          <div className="hidden max-w-md py-12 lg:block">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7EDCF0]">
              Curriculum first · AI constrained by your scheme
            </p>
            <h2 className="text-3xl font-semibold leading-tight tracking-tight text-white xl:text-4xl">
              From your scheme
              <br />
              to your next lesson.
            </h2>
            <p className="mt-5 text-[15px] leading-relaxed text-white/70">
              Upload your real curriculum, follow the right indicator and teaching
              period, and build teacher-ready lessons without losing the structure
              of your scheme.
            </p>
            <ul className="mt-8 space-y-3 text-sm text-white/65">
              <li className="flex gap-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#04A9CE]" />
                Source TLRs and week-ending dates stay authoritative
              </li>
              <li className="flex gap-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#04A9CE]" />
                Per-lesson review before generation
              </li>
              <li className="flex gap-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#04A9CE]" />
                Export-ready lesson plans for Ghanaian classrooms
              </li>
            </ul>
          </div>

          <p className="hidden text-xs text-white/40 lg:block">
            © SchemeKnit · Trust · Clarity · Professionalism
          </p>
        </aside>

        <main className="flex items-center justify-center px-4 pb-12 pt-4 sm:px-6 lg:px-10 lg:py-12">
          <div className="w-full max-w-md">
            <div className="mb-5 flex items-center justify-center gap-3 lg:hidden">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-[#0d2740]">
                <SchemeKnitMark size={26} />
              </span>
              <span className="text-lg font-bold">
                Scheme<span className="text-[#04A9CE]">Knit</span>
              </span>
            </div>

            <div className="overflow-hidden rounded-2xl border border-white/10 bg-white text-[#102A43] shadow-[0_24px_60px_rgba(0,0,0,0.35)]">
              <div
                className={`h-1.5 ${
                  operational
                    ? 'bg-gradient-to-r from-slate-700 via-slate-600 to-slate-500'
                    : role === 'school_admin'
                      ? 'bg-gradient-to-r from-emerald-700 to-[#04A9CE]'
                      : 'bg-gradient-to-r from-[#102A43] via-[#04A9CE] to-[#7EDCF0]'
                }`}
              />
              <div className="px-6 py-7 sm:px-8">
                <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                  <RoleBadge className={accent.badgeClass}>{accent.badge}</RoleBadge>
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
                </div>

                <h1 className="text-2xl font-bold tracking-tight text-[#102A43]">
                  {title || accent.title}
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

            <p className="mt-5 text-center text-xs text-white/50">
              <Link href="/" className="underline-offset-2 hover:text-white/80 hover:underline">
                Back to SchemeKnit
              </Link>
            </p>
          </div>
        </main>
      </div>
    </div>
  )
}
