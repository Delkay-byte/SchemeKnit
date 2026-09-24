'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PasswordInput, PasswordMatchIndicator, passwordMatchStatus } from '@/components/password-input'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { AuthShell, BrandCapsule } from '@/components/auth/auth-shell'
import { AuthField, AuthError } from '@/components/auth/auth-field'
import { validateEmail, validatePassword, PASSWORD_POLICY } from '@/lib/password-policy'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { ArrowRight, CheckCircle2, Lock } from 'lucide-react'

/**
 * One-time Platform Admin bootstrap page.
 * Available ONLY while zero platform admins exist (backend 410 after first).
 * Requires bootstrap secret from server configuration.
 */
export default function SetupPlatformAdminPage() {
  const router = useRouter()
  const { login } = useAuth()
  const [checking, setChecking] = useState(true)
  const [bootstrapRequired, setBootstrapRequired] = useState(false)
  const [secret, setSecret] = useState('')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    api
      .getPlatformAdminSetupStatus()
      .then((res) => {
        setBootstrapRequired(res.bootstrap_required)
        setChecking(false)
      })
      .catch(() => {
        setBootstrapRequired(false)
        setChecking(false)
      })
  }, [])

  const match = passwordMatchStatus(password, confirmPassword)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!fullName.trim()) {
      setError('Please enter your full name.')
      return
    }
    const emailCheck = validateEmail(email)
    if (!emailCheck.ok) {
      setError(emailCheck.message)
      return
    }
    if (!secret.trim()) {
      setError('Bootstrap setup secret is required.')
      return
    }
    const pwCheck = validatePassword(password)
    if (!pwCheck.ok) {
      setError(pwCheck.message)
      return
    }
    if (!match.matched) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    try {
      const res = await api.setupPlatformAdmin({
        bootstrap_secret: secret,
        full_name: fullName.trim(),
        email,
        password,
      })
      if (res.access_token) {
        await login(email, password)
        setSuccess(true)
        setTimeout(() => router.push('/platform-admin'), 1500)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Setup failed')
    } finally {
      setLoading(false)
    }
  }

  if (checking) {
    return (
      <div className="min-h-screen bg-[#050E18] flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-slate-400" role="status" aria-label="Loading" />
      </div>
    )
  }

  if (!bootstrapRequired) {
    return (
      <div className="relative min-h-screen overflow-hidden bg-[#050E18] text-white">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              'linear-gradient(rgba(62,90,120,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(62,90,120,0.15) 1px, transparent 1px)',
            backgroundSize: '64px 64px',
          }}
        />
        <div className="relative z-10 flex min-h-screen items-center justify-center px-4">
          <div className="w-full max-w-md" style={{ perspective: '1000px' }}>
            <div className="mb-6">
              <BrandCapsule dark showWordmark />
            </div>
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-white text-[#102A43] shadow-[0_30px_70px_rgba(0,0,0,0.45)]">
              <div className="h-1.5 bg-gradient-to-r from-slate-600 via-[#04A9CE]/60 to-slate-700" />
              <div className="px-6 py-8 text-center sm:px-8">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 shadow-inner">
                  <Lock className="h-7 w-7 text-slate-600" aria-hidden="true" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight">Setup already complete</h1>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  Platform administrator setup has already been completed. This
                  page is no longer available.
                </p>
                <Link href="/login/platform-admin">
                  <Button className="mt-6 h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold shadow-[0_4px_14px_rgba(16,42,67,0.25)] hover:bg-[#0d2740]">
                    <span className="inline-flex items-center gap-2">
                      Go to platform admin login
                      <ArrowRight className="h-4 w-4" aria-hidden="true" />
                    </span>
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (success) {
    return (
      <div className="relative min-h-screen overflow-hidden bg-[#050E18] text-white">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              'linear-gradient(rgba(62,90,120,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(62,90,120,0.15) 1px, transparent 1px)',
            backgroundSize: '64px 64px',
          }}
        />
        <div className="relative z-10 flex min-h-screen items-center justify-center px-4">
          <div className="w-full max-w-md">
            <div className="mb-6">
              <BrandCapsule dark showWordmark />
            </div>
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-white text-[#102A43] shadow-[0_30px_70px_rgba(0,0,0,0.45)]">
              <div className="h-1.5 bg-gradient-to-r from-emerald-500 to-[#04A9CE]" />
              <div className="px-6 py-8 text-center sm:px-8">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-100 shadow-inner">
                  <CheckCircle2 className="h-8 w-8 text-emerald-600" aria-hidden="true" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight">Setup complete</h1>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  Platform administration setup has been completed successfully.
                  Redirecting to the platform admin console…
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Controlled administrative bootstrap — distinct from platform admin login.
  return (
    <AuthShell
      role="platform_admin"
      decorOverride={
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute inset-0 bg-[#050E18]" />
          <svg className="absolute inset-0 h-full w-full opacity-[0.14]" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <pattern id="bootstrap-v" width="64" height="64" patternUnits="userSpaceOnUse">
                <path d="M64 0H0V64" fill="none" stroke="#3E5A78" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#bootstrap-v)" />
          </svg>
          <div className="absolute inset-x-0 top-[28%] h-px bg-gradient-to-r from-transparent via-[#04A9CE]/40 to-transparent" />
          <div className="absolute left-1/2 top-1/2 hidden -translate-x-1/2 -translate-y-1/2 lg:block" style={{ perspective: '800px' }}>
            <svg width="220" height="220" viewBox="0 0 220 220" fill="none" style={{ transform: 'rotateX(20deg) rotateY(-8deg)' }}>
              <rect x="30" y="30" width="160" height="160" rx="24" stroke="#3E5A78" strokeOpacity="0.5" strokeWidth="1.5" fill="rgba(255,255,255,0.02)" />
              <rect x="55" y="55" width="110" height="110" rx="16" stroke="#04A9CE" strokeOpacity="0.35" strokeWidth="1.5" fill="none" />
              {[0, 1, 2, 3].map((i) => (
                <g key={i}>
                  <rect x="82" y={88 + i * 20} width="14" height="14" rx="3" stroke={i === 0 ? '#04A9CE' : '#3E5A78'} strokeWidth="1.5" fill={i === 0 ? 'rgba(4,169,206,0.2)' : 'none'} />
                  {i === 0 && <path d={`M85 ${95 + i * 20} l3 3 5-6`} stroke="#04A9CE" strokeWidth="1.5" fill="none" />}
                  <rect x="104" y={92 + i * 20} width={i % 2 === 0 ? 36 : 28} height="5" rx="2.5" fill="#3E5A78" fillOpacity="0.6" />
                </g>
              ))}
            </svg>
          </div>
          <div className="absolute left-8 top-8 hidden flex-col gap-2 lg:flex">
            {['BOOTSTRAP', 'ONE-TIME', 'PROTECTED'].map((t) => (
              <div key={t} className="flex items-center gap-2 text-[10px] font-bold tracking-[0.2em] text-slate-500">
                <span className="h-1.5 w-1.5 rounded-full bg-[#04A9CE]/70" />
                {t}
              </div>
            ))}
          </div>
          <div className="absolute bottom-0 inset-x-0 h-40 bg-gradient-to-t from-black/50 to-transparent" />
        </div>
      }
      title="Controlled admin bootstrap"
      description="This one-time setup creates the first authorized SchemeKnit platform administrator. After completion, this page becomes permanently unavailable."
      securityNote="One-time bootstrap — requires PLATFORM_ADMIN_BOOTSTRAP_SECRET from your deployment operator."
      steps={[
        { label: 'Identity', active: true },
        { label: 'Bootstrap secret' },
        { label: 'Password' },
      ]}
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <AuthField id="psetup-name" label="Full name">
          <Input
            id="psetup-name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
            autoComplete="name"
            placeholder="Platform Administrator"
            aria-invalid={error ? true : undefined}
          />
        </AuthField>
        <AuthField id="psetup-email" label="Email">
          <Input
            id="psetup-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            placeholder="admin@bloomcore.com"
            aria-invalid={error ? true : undefined}
          />
        </AuthField>
        <AuthField
          id="psetup-secret"
          label="Bootstrap setup secret"
          hint="The secret comes from secure server configuration (PLATFORM_ADMIN_BOOTSTRAP_SECRET). It is never stored or logged."
        >
          <PasswordInput
            id="psetup-secret"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            required
            autoComplete="off"
            placeholder="Provided by your deployment operator"
            toggleLabel="Show secret"
          />
        </AuthField>
        <AuthField
          id="psetup-password"
          label="Password"
          hint={PASSWORD_POLICY.description}
        >
          <PasswordInput
            id="psetup-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            placeholder="Create a password"
            toggleLabel="Show password"
          />
        </AuthField>
        <AuthField id="psetup-confirm" label="Confirm password">
          <PasswordInput
            id="psetup-confirm"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            placeholder="Confirm your password"
            toggleLabel="Show password"
          />
        </AuthField>
        <PasswordMatchIndicator password={password} confirm={confirmPassword} />
        <AuthError message={error} />

        <Button
          type="submit"
          disabled={loading || (!match.matched && confirmPassword.length > 0)}
          className="h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold shadow-[0_4px_14px_rgba(16,42,67,0.3)] hover:bg-[#0d2740] active:scale-[0.98] transition focus-visible:ring-2 focus-visible:ring-[#04A9CE] focus-visible:ring-offset-2 disabled:opacity-60"
        >
          {loading ? (
            <span className="inline-flex items-center gap-2">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Please wait…
            </span>
          ) : (
            'Create first platform admin'
          )}
        </Button>
      </form>

      <div className="mt-6 rounded-xl border border-border bg-muted p-4 shadow-sm">
        <p className="text-sm text-muted-foreground text-center leading-relaxed">
          The first platform admin uses the same password policy as every
          other account. After setup, you can change your password from
          Settings at any time.
        </p>
      </div>
    </AuthShell>
  )
}
