'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'
import { PasswordInput, PasswordMatchIndicator } from '@/components/password-input'
import { AuthShell } from '@/components/auth/auth-shell'
import { AuthField, AuthError } from '@/components/auth/auth-field'
import { TurnstileWidget, TURNSTILE_SITE_KEY } from '@/components/turnstile-widget'
import { validateEmail, validatePassword, PASSWORD_POLICY } from '@/lib/password-policy'
import { authHref, currentNextPath } from '@/lib/purchase-return'

export default function IndividualSignupPage() {
  const router = useRouter()
  const { login } = useAuth()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [referralCode, setReferralCode] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [turnstileToken, setTurnstileToken] = useState('')
  const [turnstileReset, setTurnstileReset] = useState(0)
  const [nextPath, setNextPath] = useState<string | null>(null)
  // The backend is authoritative. The env flag is only the initial value used
  // before the policy call resolves (and while the API is unreachable).
  const [policy, setPolicy] = useState<{
    registration_mode: string
    self_registration: boolean
    invite_code_required: boolean
  } | null>(null)
  const [policyError, setPolicyError] = useState(false)
  const [inviteRequired, setInviteRequired] = useState(
    process.env.NEXT_PUBLIC_PILOT_INVITE_REQUIRED === 'true',
  )

  const loadPolicy = useCallback(async () => {
    setPolicyError(false)
    try {
      const res = await api.getRegistrationPolicy()
      setPolicy(res)
      setInviteRequired(res.invite_code_required)
    } catch {
      // Never assume registration is open: block submit until the backend
      // policy is known.
      setPolicy(null)
      setPolicyError(true)
    }
  }, [])

  useEffect(() => {
    void loadPolicy()
  }, [loadPolicy])

  // Referral attribution: capture the code from the link and keep it for a
  // later registration in this browser. It is submitted once, at signup.
  useEffect(() => {
    setNextPath(currentNextPath())
    const fromUrl = new URLSearchParams(window.location.search).get('ref') || ''
    const stored = (() => {
      try { return localStorage.getItem('teachflow_referral') || '' } catch { return '' }
    })()
    const code = (fromUrl || stored).trim().toUpperCase()
    if (code) {
      setReferralCode(code)
      try { localStorage.setItem('teachflow_referral', code) } catch { /* storage unavailable */ }
      if (fromUrl) api.trackReferral(code).catch(() => {})
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!policy) {
      setError('Registration availability could not be confirmed. Please retry.')
      return
    }
    if (!policy.self_registration) {
      setError('Self-registration is currently closed.')
      return
    }
    const emailCheck = validateEmail(email)
    if (!emailCheck.ok) {
      setError(emailCheck.message)
      return
    }
    if (!fullName.trim()) {
      setError('Please enter your full name.')
      return
    }
    const pwCheck = validatePassword(password)
    if (!pwCheck.ok) {
      setError(pwCheck.message)
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    if (inviteRequired && !inviteCode.trim()) {
      setError('Enter the pilot invite code from your invitation.')
      return
    }
    if (TURNSTILE_SITE_KEY && !turnstileToken) {
      setError('Please complete the bot-verification challenge first.')
      return
    }

    setError('')
    setLoading(true)

    try {
      const res = await api.registerIndividual(
        email,
        password,
        fullName.trim(),
        referralCode,
        inviteRequired ? inviteCode.trim() : '',
        turnstileToken,
      )
      if (res.access_token) {
        await login(email, password, 'teacher')
      }
      router.push(currentNextPath() || '/dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
      // A token is single-use: a failed attempt must request a fresh one.
      setTurnstileToken('')
      setTurnstileReset((value) => value + 1)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      role="register"
      title="Create your SchemeKnit account"
      description="Start your professional lesson-planning workspace — no school or payment required. The Free plan includes 2 lesson-plan generations per month."
      steps={[
        { label: 'Your details', active: true },
        { label: 'Secure password' },
        { label: 'Ready' },
      ]}
      footer={
        <p className="text-center text-sm text-muted-foreground">
          Already have an account?{' '}
          <Link
            href={authHref('/login', nextPath)}
            className="font-semibold text-[#04A9CE] underline underline-offset-2"
          >
            Sign in
          </Link>
        </p>
      }
    >
      {policy && !policy.self_registration ? (
        <div role="status" className="space-y-3 rounded-xl border border-border bg-[#F4F7FA] p-4 text-sm text-muted-foreground">
          <p>
            New teacher self-registration is currently closed. Contact your
            school administrator or SchemeKnit support for access.
          </p>
          <Link href="/login" className="font-semibold text-[#04A9CE] underline underline-offset-2">
            Return to sign in
          </Link>
        </div>
      ) : (
      <>
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <AuthField id="signup-name" label="Full name">
          <Input
            id="signup-name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
            placeholder="Ama Mensah"
            autoComplete="name"
            autoFocus
            aria-invalid={error ? true : undefined}
          />
        </AuthField>

        <AuthField id="signup-email" label="Email">
          <Input
            id="signup-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder="name@gmail.com"
            autoComplete="email"
            aria-invalid={error ? true : undefined}
          />
        </AuthField>

        <AuthField
          id="signup-password"
          label="Password"
          hint={PASSWORD_POLICY.description}
        >
          <PasswordInput
            id="signup-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            placeholder="Create a password"
            autoComplete="new-password"
            toggleLabel="Show password"
            className="h-11 rounded-lg border-input bg-white px-3.5 text-sm text-[#102A43] shadow-[0_1px_2px_rgba(16,42,67,0.04)] transition-all hover:border-[#04A9CE]/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45"
          />
        </AuthField>

        <AuthField id="signup-confirm" label="Confirm password">
          <PasswordInput
            id="signup-confirm"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={8}
            placeholder="Re-enter your password"
            autoComplete="new-password"
            toggleLabel="Show password"
            className="h-11 rounded-lg border-input bg-white px-3.5 text-sm text-[#102A43] shadow-[0_1px_2px_rgba(16,42,67,0.04)] transition-all hover:border-[#04A9CE]/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45"
          />
        </AuthField>

        <PasswordMatchIndicator password={password} confirm={confirm} />

        {inviteRequired && (
          <AuthField id="signup-invite" label="Pilot invite code">
            <Input
              id="signup-invite"
              type="text"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              required
              placeholder="From your invitation"
              autoComplete="off"
            />
          </AuthField>
        )}

        <AuthField id="signup-referral" label="Referral code (optional)">
          <Input
            id="signup-referral"
            type="text"
            value={referralCode}
            onChange={(e) => setReferralCode(e.target.value.toUpperCase())}
            placeholder="From your invite link"
            autoComplete="off"
          />
        </AuthField>

        <TurnstileWidget
          siteKey={TURNSTILE_SITE_KEY}
          action="register"
          onToken={setTurnstileToken}
          resetKey={turnstileReset}
        />

        {policyError && (
          <div
            role="alert"
            className="flex flex-col gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 text-xs text-amber-900"
          >
            <span>
              We could not confirm registration availability. Self-registration
              is not enabled until the server policy is confirmed.
            </span>
            <Button
              type="button"
              variant="outline"
              onClick={() => void loadPolicy()}
              className="self-start"
            >
              Retry
            </Button>
          </div>
        )}

        <AuthError message={error} />

        <Button
          type="submit"
          disabled={
            loading
            || !policy
            || !policy.self_registration
            || Boolean(TURNSTILE_SITE_KEY && !turnstileToken)
          }
          className="h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold shadow-[0_4px_14px_rgba(16,42,67,0.25)] hover:bg-[#0d2740] active:scale-[0.98] transition focus-visible:ring-2 focus-visible:ring-[#04A9CE] focus-visible:ring-offset-2 disabled:opacity-60"
        >
          {loading ? (
            <span className="inline-flex items-center gap-2">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Creating account…
            </span>
          ) : (
            'Create account'
          )}
        </Button>
      </form>

      <div className="mt-5 rounded-xl border border-border bg-[#F4F7FA] p-4 shadow-sm">
        <p className="text-xs leading-relaxed text-muted-foreground text-center">
          Free plan: 2 indicator-level lesson plans per calendar month, individual DOCX and
          PDF export, and no payment information required. Paid packages are prepaid by
          Bank Transfer or Mobile Money.
        </p>
      </div>
      </>
      )}
    </AuthShell>
  )
}
