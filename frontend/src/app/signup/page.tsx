'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'
import { PasswordInput, PasswordMatchIndicator } from '@/components/password-input'
import { AuthShell } from '@/components/auth/auth-shell'
import { AuthField, AuthError } from '@/components/auth/auth-field'
import { validateEmail, validatePassword, PASSWORD_POLICY } from '@/lib/password-policy'

export default function IndividualSignupPage() {
  const router = useRouter()
  const { login } = useAuth()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

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

    setError('')
    setLoading(true)

    try {
      const res = await api.registerIndividual(email, password, fullName.trim())
      if (res.access_token) {
        await login(email, password)
      }
      router.push('/dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      role="register"
      title="Create your SchemeKnit account"
      description="Start your professional lesson-planning workspace — no school required. Free Tier includes 5 lesson plans per month."
      steps={[
        { label: 'Your details', active: true },
        { label: 'Secure password' },
        { label: 'Ready' },
      ]}
      footer={
        <p className="text-center text-sm text-muted-foreground">
          Already have an account?{' '}
          <Link
            href="/login"
            className="font-semibold text-[#04A9CE] underline underline-offset-2"
          >
            Sign in
          </Link>
        </p>
      }
    >
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

        <AuthError message={error} />

        <Button
          type="submit"
          disabled={loading}
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
          Free Tier includes 5 lesson plans per calendar month, individual DOCX and
          PDF export, 1 custom template and 5 lifetime AI credits.
        </p>
      </div>
    </AuthShell>
  )
}
