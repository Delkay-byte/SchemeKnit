'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'
import { PasswordInput } from '@/components/password-input'
import { AuthShell } from '@/components/auth/auth-shell'
import { AuthField, AuthError } from '@/components/auth/auth-field'
import { validateEmail } from '@/lib/password-policy'
import { isDesktop } from '@/lib/build-target'
import { Building2, Shield, GraduationCap, KeyRound, AlertCircle } from 'lucide-react'

/**
 * Sign-in entry points (Hero V2 / auth redesign).
 *
 * Routes unchanged: /login · /login/school-admin · /login/platform-admin
 * All submit to the same backend endpoint. Role routing uses the account's
 * real role — never the entry URL. Platform Admin is not linked from public
 * pages; the direct route keeps working.
 */
export type EntryRole = 'teacher' | 'school_admin' | 'platform_admin'

const ENTRY_COPY: Record<
  EntryRole,
  {
    title: string
    description: string
    emailPlaceholder: string
    note: string
    icon: typeof GraduationCap
    securityNote?: string
    showForgot: boolean
    forgotHint: string
  }
> = {
  teacher: {
    title: 'Teacher Sign In',
    description:
      'Sign in to create, manage and export your lesson plans with SchemeKnit.',
    emailPlaceholder: 'teacher@school.edu.gh',
    note:
      'Your SchemeKnit administrator creates teacher accounts for school installations. ' +
      'Independent teachers can create a free account below.',
    icon: GraduationCap,
    showForgot: true,
    forgotHint:
      'Password resets are issued by your administrator. Contact your school admin or SchemeKnit support if you cannot sign in.',
  },
  school_admin: {
    title: 'School Administration Sign In',
    description:
      'Sign in to manage your school, teachers and SchemeKnit access.',
    emailPlaceholder: 'headteacher@school.edu.gh',
    note:
      'Headteacher accounts are created when your school activates SchemeKnit. ' +
      'Platform-level questions go to the SchemeKnit administrator.',
    icon: Building2,
    showForgot: true,
    forgotHint:
      'Password resets for school administrators are handled by SchemeKnit support or your activation contact.',
  },
  platform_admin: {
    title: 'Platform Administration Sign In',
    description: 'Authorized SchemeKnit platform staff only.',
    emailPlaceholder: 'platform.admin@bloomcore.com',
    note:
      'Access is restricted and cannot be self-registered. ' +
      'If you have lost your password, contact another platform administrator ' +
      'or your server operator for a controlled password reset.',
    icon: Shield,
    securityNote:
      'Authorized SchemeKnit platform staff only. Direct route — not listed on public pages.',
    showForgot: false,
    forgotHint: '',
  },
}

const ENTRIES: { role: EntryRole; href: string; label: string }[] = [
  { role: 'teacher', href: '/login', label: 'Teacher' },
  { role: 'school_admin', href: '/login/school-admin', label: 'School Administration' },
]

export function RoleLogin({ entry }: { entry: EntryRole }) {
  const router = useRouter()
  const { login, user, loading: authLoading } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [showForgot, setShowForgot] = useState(false)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(true)

  const copy = ENTRY_COPY[entry]

  useEffect(() => {
    if (!authLoading && user) {
      if (user.role === 'school_admin') {
        router.push('/school-admin')
      } else if (!isDesktop && user.role === 'platform_admin') {
        router.push('/platform-admin')
      } else {
        router.push('/dashboard')
      }
      return
    }
    api.getSetupStatus()
      .then((res) => {
        if (res.needs_setup) {
          router.push('/setup')
        } else {
          setChecking(false)
        }
      })
      .catch(() => {
        setChecking(false)
      })
  }, [user, authLoading, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const emailCheck = validateEmail(email)
    if (!emailCheck.ok) {
      setError(emailCheck.message)
      return
    }
    setError('')
    setLoading(true)
    try {
      await login(email, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  // Loading skeleton matches each role's page theme (no mesh).
  if (authLoading || checking) {
    const loadingBg =
      entry === 'school_admin'
        ? 'bg-[#0B1F3A]'
        : entry === 'platform_admin'
          ? 'bg-[#050E18]'
          : 'bg-[#F7F5F0]'
    const spin =
      entry === 'school_admin'
        ? 'border-[#04A9CE]'
        : entry === 'platform_admin'
          ? 'border-slate-400'
          : 'border-[#04A9CE]'
    return (
      <div className={`min-h-screen ${loadingBg} flex items-center justify-center`}>
        <div
          className={`animate-spin rounded-full h-12 w-12 border-b-2 ${spin}`}
          role="status"
          aria-label="Loading"
        />
      </div>
    )
  }

  return (
    <AuthShell
      role={entry}
      title={copy.title}
      description={copy.description}
      securityNote={copy.securityNote}
      footer={
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
            {ENTRIES.filter((e) => e.role !== entry).map((e) => (
              <Link
                key={e.role}
                href={e.href}
                className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
              >
                {e.label} sign in
              </Link>
            ))}
            {entry === 'teacher' && (
              <Link
                href="/signup"
                className="text-xs font-semibold text-[#04A9CE] hover:text-[#0389a8] underline underline-offset-2"
              >
                Create teacher account
              </Link>
            )}
            {entry === 'school_admin' && (
              <Link
                href="/activate-school"
                className="text-xs font-semibold text-emerald-600 hover:text-emerald-700 underline underline-offset-2"
              >
                Have a school activation code?
              </Link>
            )}
          </div>
          <p className="text-xs text-muted-foreground text-center leading-relaxed">
            {copy.note}
          </p>
        </div>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <AuthField id={`${entry}-email`} label="Email">
          <Input
            id={`${entry}-email`}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder={copy.emailPlaceholder}
            autoComplete="email"
            autoFocus
            aria-invalid={error ? true : undefined}
          />
        </AuthField>

        <AuthField
          id={`${entry}-password`}
          label="Password"
          hint={
            copy.showForgot ? (
              <button
                type="button"
                onClick={() => setShowForgot((v) => !v)}
                className="inline-flex items-center gap-1 font-semibold text-[#04A9CE] hover:text-[#0389a8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/50 rounded"
              >
                <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
                Forgot password?
              </button>
            ) : undefined
          }
        >
          <PasswordInput
            id={`${entry}-password`}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            placeholder="Your password"
            autoComplete="current-password"
            toggleLabel="Show password"
            className="h-11 rounded-lg border-input bg-white px-3.5 text-sm text-[#102A43] shadow-[0_1px_2px_rgba(16,42,67,0.04)] transition-all hover:border-[#04A9CE]/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45 focus-visible:border-[#04A9CE]/70"
          />
        </AuthField>

        {showForgot && copy.showForgot && (
          <div
            className="flex gap-2 rounded-lg border border-[#04A9CE]/25 bg-[#04A9CE]/10 px-3 py-2.5 text-xs text-muted-foreground"
            role="status"
          >
            <AlertCircle className="h-4 w-4 shrink-0 text-[#04A9CE]" aria-hidden="true" />
            <span className="leading-relaxed">
              {copy.forgotHint}{' '}
              <Link href="/contact" className="font-semibold text-[#04A9CE] underline">
                Contact support
              </Link>
            </span>
          </div>
        )}

        <AuthError message={error} />

        <Button
          type="submit"
          disabled={loading}
          className="h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold hover:bg-[#0d2740] active:scale-[0.99] transition focus-visible:ring-2 focus-visible:ring-[#04A9CE] focus-visible:ring-offset-2 disabled:opacity-60"
        >
          {loading ? (
            <span className="inline-flex items-center gap-2">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Signing in…
            </span>
          ) : (
            'Sign in'
          )}
        </Button>
      </form>

      {entry === 'teacher' && (
        <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="rounded-xl border border-blue-200 bg-blue-50/70 p-3">
            <p className="text-[11px] font-bold text-blue-700 uppercase tracking-wide mb-1">
              School Teacher
            </p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Your school provides access. Sign in with the details your school
              administrator gave you.
            </p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-3">
            <p className="text-[11px] font-bold text-emerald-700 uppercase tracking-wide mb-1">
              Individual Teacher
            </p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              No school? Start free, or upgrade to Teacher Pro for batch
              generation and more.
            </p>
          </div>
        </div>
      )}

      {entry === 'teacher' && (
        <div className="mt-4">
          <Link
            href="/signup"
            className="inline-flex h-11 w-full items-center justify-center rounded-lg border border-[#04A9CE]/40 bg-[#04A9CE]/10 text-sm font-semibold text-[#0389a8] transition hover:bg-[#04A9CE]/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/50"
          >
            Create teacher account
          </Link>
        </div>
      )}
    </AuthShell>
  )
}
