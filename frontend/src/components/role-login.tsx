'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'
import { PasswordInput } from '@/components/password-input'
import { validateEmail } from '@/lib/password-policy'
import { BookOpen, Shield, Building2, GraduationCap } from 'lucide-react'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { isDesktop } from '@/lib/build-target'

/**
 * Sign-in entry points.
 *
 * These routes exist so each role has its own URL to bookmark; they all submit
 * to the same authentication endpoint. The role on an account always decides
 * where a session lands (see the redirect effect below) — an entry route never
 * grants access to another role's console.
 *
 * Each role has a deliberately distinct presentation (PART 1): its own icon,
 * colour band and wording, so the three consoles are never confused at the
 * keyboard. The distinction is cosmetic only — real authorization is the
 * backend's role check, not the page the form lives on.
 */
export type EntryRole = 'teacher' | 'school_admin' | 'platform_admin'

const ENTRY_COPY: Record<EntryRole, {
  title: string
  description: string
  emailPlaceholder: string
  note: string
  icon: typeof BookOpen
  /** Tailwind classes for the role's distinctive colour band. */
  band: string
  badge: string
}> = {
  teacher: {
    title: 'SchemeKnit Teacher',
    description: 'Create, manage and export your lesson plans.',
    emailPlaceholder: 'teacher@school.edu.gh',
    note: 'Your SchemeKnit administrator creates teacher accounts for this installation. ' +
      'Contact your school administrator if you do not yet have login details.',
    icon: GraduationCap,
    band: 'from-blue-600 to-blue-500',
    badge: 'Teacher Console',
  },
  school_admin: {
    title: 'SchemeKnit School Administration',
    description: 'Manage your school, teachers, seats and school license.',
    emailPlaceholder: 'headteacher@school.edu.gh',
    note: 'Headteacher accounts are created by your school when it activates SchemeKnit. ' +
      'Platform-level questions go to the SchemeKnit administrator.',
    icon: Building2,
    band: 'from-emerald-700 to-emerald-600',
    badge: 'Headteacher / Institution Administrator',
  },
  platform_admin: {
    title: 'SchemeKnit Platform Administration',
    description: 'Manage schools, licenses, plans and platform operations.',
    emailPlaceholder: 'platform.admin@bloomcore.com',
    note: 'Authorized SchemeKnit platform administrators only. ' +
      'Access is restricted and cannot be self-registered. ' +
      'If you have lost your password, contact another platform administrator ' +
      'or your server operator for a controlled password reset.',
    icon: Shield,
    band: 'from-slate-800 to-slate-700',
    badge: 'Platform Operations',
  },
}

const ENTRIES: { role: EntryRole; href: string; label: string }[] = [
  { role: 'teacher', href: '/login', label: 'Teacher' },
  { role: 'school_admin', href: '/login/school-admin', label: 'Headteacher' },
  ...(!isDesktop ? [{ role: 'platform_admin' as EntryRole, href: '/login/platform-admin', label: 'Platform admin' }] : []),
]

export function RoleLogin({ entry }: { entry: EntryRole }) {
  const router = useRouter()
  const { login, user, loading: authLoading } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(true)

  const copy = ENTRY_COPY[entry]
  const RoleIcon = copy.icon

  useEffect(() => {
    // A live session always wins: route by the account's real role, never by
    // the entry point that was used to sign in (PART 2).
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
    api.getSetupStatus().then((res) => {
      if (res.needs_setup) {
        router.push('/setup')
      } else {
        setChecking(false)
      }
    }).catch(() => {
      setChecking(false)
    })
  }, [user, authLoading, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    // Validate the email identifier client-side for immediate feedback; the
    // backend re-checks and is authoritative (PART 6).
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

  if (authLoading || checking) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md overflow-hidden">
        {/* SchemeKnit brand mark */}
        <div className="flex justify-center pt-4">
          <SchemeKnitMark size={28} />
        </div>
        {/* Distinctive colour band + role badge: the first thing the user sees
            identifies which console this is, before any credential is typed. */}
        <div className={`h-2 bg-gradient-to-r ${copy.band}`} />
        <CardHeader className="text-center">
          <div className="flex justify-center mb-2">
            <div className={`p-3 rounded-full bg-gradient-to-br ${copy.band} text-white`}>
              <RoleIcon className="h-7 w-7" />
            </div>
          </div>
          <span className="inline-block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            {copy.badge}
          </span>
          <CardTitle className="text-2xl">{copy.title}</CardTitle>
          <CardDescription>{copy.description}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-3 py-2 border rounded-md"
                placeholder={copy.emailPlaceholder}
                autoComplete="email"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Password</label>
              <PasswordInput
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                placeholder="Your password"
                autoComplete="current-password"
                toggleLabel="Show password"
              />
            </div>

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 p-2 rounded">{error}</p>
            )}

            <Button type="submit" disabled={loading} className="w-full">
              {loading ? 'Please wait...' : 'Sign In'}
            </Button>
          </form>

          <div className="mt-6 p-4 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground text-center">{copy.note}</p>
          </div>

          {/* Teacher entry explains the two audiences it serves (§10, §11). */}
          {entry === 'teacher' && (
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="p-3 rounded-lg border border-blue-200 bg-blue-50">
                <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide mb-1">
                  School Teacher
                </p>
                <p className="text-sm text-muted-foreground">
                  Your school provides access. Sign in with the details your
                  school administrator gave you.
                </p>
              </div>
              <div className="p-3 rounded-lg border border-emerald-200 bg-emerald-50">
                <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide mb-1">
                  Individual Teacher
                </p>
                <p className="text-sm text-muted-foreground">
                  No school? Start free, or upgrade to Teacher Pro for batch
                  generation and more.
                </p>
              </div>
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
            {ENTRIES.filter((e) => e.role !== entry).map((e) => (
              <Link
                key={e.role}
                href={e.href}
                className="text-xs text-muted-foreground hover:text-foreground underline"
              >
                {e.label} sign in
              </Link>
            ))}
            {entry === 'teacher' && (
              <Link
                href="/signup"
                className="text-xs font-medium text-blue-600 hover:text-blue-700 underline"
              >
                Register as individual teacher
              </Link>
            )}
            {entry === 'school_admin' && (
              <Link
                href="/activate-school"
                className="text-xs font-medium text-emerald-600 hover:text-emerald-700 underline"
              >
                Have a school activation code?
              </Link>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
