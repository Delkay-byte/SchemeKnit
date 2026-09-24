'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { PasswordInput, PasswordMatchIndicator } from '@/components/password-input'
import { AuthShell } from '@/components/auth/auth-shell'
import { AuthField, AuthError } from '@/components/auth/auth-field'
import {
  validatePassword, validateEmail, PASSWORD_POLICY,
} from '@/lib/password-policy'

export default function SetupPage() {
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [schoolName, setSchoolName] = useState('')
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!authLoading && user) {
      router.push('/dashboard')
      return
    }
    api.getSetupStatus().then((res) => {
      if (!res.needs_setup) {
        router.push('/login')
      } else {
        setChecking(false)
      }
    }).catch(() => {
      setChecking(false)
    })
  }, [user, authLoading, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    const emailCheck = validateEmail(email)
    if (!emailCheck.ok) {
      setError(emailCheck.message)
      return
    }
    const pwCheck = validatePassword(password)
    if (!pwCheck.ok) {
      setError(pwCheck.message)
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setLoading(true)
    try {
      await api.firstRunSetup({ name, email, password, school_name: schoolName })
      window.location.href = '/dashboard'
    } catch (err: any) {
      setError(err.message || 'Setup failed')
    } finally {
      setLoading(false)
    }
  }

  if (authLoading || checking) {
    return (
      <div className="min-h-screen bg-[#F8F7FC] flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600" role="status" aria-label="Loading" />
      </div>
    )
  }

  return (
    <AuthShell
      role="first_run"
      title="Initialize SchemeKnit"
      description="System initialization — create your administrator account to bring this environment online."
      steps={[
        { label: 'Admin details', active: true },
        { label: 'School (optional)' },
        { label: 'Ready' },
      ]}
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <AuthField id="setup-name" label="Your name">
          <Input
            id="setup-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Kwame Asante"
            required
            autoComplete="name"
            aria-invalid={error ? true : undefined}
          />
        </AuthField>
        <AuthField id="setup-email" label="Email / username">
          <Input
            id="setup-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="admin@school.edu.gh"
            required
            autoComplete="email"
            aria-invalid={error ? true : undefined}
          />
        </AuthField>
        <AuthField id="setup-school" label="School name (optional)">
          <Input
            id="setup-school"
            type="text"
            value={schoolName}
            onChange={(e) => setSchoolName(e.target.value)}
            placeholder="Accra Academy"
            autoComplete="organization"
          />
        </AuthField>
        <AuthField
          id="setup-password"
          label="Password"
          hint={PASSWORD_POLICY.description}
        >
          <PasswordInput
            id="setup-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            required
            toggleLabel="Show password"
            autoComplete="new-password"
          />
        </AuthField>
        <AuthField id="setup-confirm" label="Confirm password">
          <PasswordInput
            id="setup-confirm"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Confirm password"
            required
            toggleLabel="Show password"
            autoComplete="new-password"
          />
        </AuthField>
        <PasswordMatchIndicator password={password} confirm={confirmPassword} />
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
            'Create admin account'
          )}
        </Button>
      </form>

      <div className="mt-5 rounded-xl border border-violet-200/70 bg-violet-50/60 p-4 shadow-sm">
        <p className="text-xs leading-relaxed text-muted-foreground text-center">
          This is a one-time first-run setup. After the administrator account is
          created, this page redirects to sign-in.
        </p>
      </div>
    </AuthShell>
  )
}
