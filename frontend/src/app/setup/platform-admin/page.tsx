'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { PasswordInput, PasswordMatchIndicator, passwordMatchStatus } from '@/components/password-input'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { validateEmail, validatePassword, PASSWORD_POLICY } from '@/lib/password-policy'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { Shield, ArrowRight, CheckCircle2 } from 'lucide-react'

/**
 * One-time Platform Admin bootstrap page.
 *
 * Available ONLY while zero platform admins exist. The backend enforces this
 * (returns 410 after the first admin is created) — this page is just the UX.
 * Requires a bootstrap secret from server configuration.
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
        // Backend unavailable → treat as not required (fail closed).
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
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  // Backend says setup is done (or is unreachable — fail closed).
  if (!bootstrapRequired) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <div className="flex justify-center mb-2">
              <SchemeKnitMark size={28} />
            </div>
            <CardTitle className="text-2xl">Setup Already Complete</CardTitle>
            <CardDescription>
              Platform administrator setup has already been completed. This
              page is no longer available.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <Link href="/login/platform-admin">
              <Button className="w-full">
                Go to Platform Admin Login <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (success) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <div className="flex justify-center mb-3">
              <CheckCircle2 className="h-14 w-14 text-emerald-600" />
            </div>
            <CardTitle className="text-2xl">Setup Complete</CardTitle>
            <CardDescription>
              Platform administration setup has been completed successfully.
              Redirecting to the platform admin console…
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/30 flex items-center justify-center p-4">
      <Card className="w-full max-w-lg">
        <div className="h-2 bg-gradient-to-r from-slate-800 to-slate-700" />
        <CardHeader className="text-center">
          <div className="flex justify-center mb-2">
            <SchemeKnitMark size={32} />
          </div>
          <div className="flex items-center justify-center gap-2 mb-1">
            <Shield className="h-5 w-5 text-slate-600" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              One-Time Setup
            </span>
          </div>
          <CardTitle className="text-2xl">
            Set Up SchemeKnit Platform Administration
          </CardTitle>
          <CardDescription>
            This one-time setup creates the first authorized SchemeKnit platform
            administrator. After completion, this page becomes permanently
            unavailable.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Full Name</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                autoComplete="name"
                placeholder="Platform Administrator"
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="admin@bloomcore.com"
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Bootstrap Setup Secret
              </label>
              <PasswordInput
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                required
                autoComplete="off"
                placeholder="Provided by your deployment operator"
                toggleLabel="Show secret"
              />
              <p className="text-xs text-muted-foreground mt-1">
                The secret comes from secure server configuration
                (PLATFORM_ADMIN_BOOTSTRAP_SECRET). It is never stored or logged.
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Password</label>
              <PasswordInput
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
                placeholder="Create a password"
                toggleLabel="Show password"
              />
              <p className="text-xs text-muted-foreground mt-1">
                {PASSWORD_POLICY.description}
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Confirm Password
              </label>
              <PasswordInput
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
                placeholder="Confirm your password"
                toggleLabel="Show password"
              />
              <PasswordMatchIndicator
                password={password}
                confirm={confirmPassword}
              />
            </div>

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 p-2 rounded">
                {error}
              </p>
            )}

            <Button
              type="submit"
              disabled={loading || (!match.matched && confirmPassword.length > 0)}
              className="w-full"
            >
              {loading ? 'Please wait...' : 'Create First Platform Admin'}
            </Button>
          </form>

          <div className="mt-6 p-4 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground text-center">
              The first platform admin uses the same password policy as every
              other account. After setup, you can change your password from
              Settings at any time.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
