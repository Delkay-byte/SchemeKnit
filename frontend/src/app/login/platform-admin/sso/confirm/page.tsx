'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AuthShell } from '@/components/auth/auth-shell'
import { AuthField, AuthError } from '@/components/auth/auth-field'
import { PasswordInput } from '@/components/password-input'
import { Button } from '@/components/ui/button'
import { getApiBaseUrl } from '@/lib/api'
import { normalizeError } from '@/lib/error-normalizer'
import { ShieldCheck, Loader2 } from 'lucide-react'

/**
 * Link-confirmation step for platform-admin SSO (BloomCore Identity).
 *
 * Reached via a 303 redirect from `GET /api/auth/oidc/callback` when the
 * Control Center reports the central identity as `pending`. The one-time
 * `attempt` token comes from the redirect query; the pairing confirm cookie
 * lives on the backend origin and is sent automatically by the browser.
 *
 * The user proves the EXISTING local SchemeKnit platform-admin password. On
 * success the backend creates the identity link, sends the signed proof to
 * the Control Center, mints a native session and returns the standard login
 * response, which is stored exactly like a password login.
 */
export default function PlatformAdminSsoConfirmPage() {
  const router = useRouter()
  const [attempt, setAttempt] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const token = params.get('attempt') || ''
    setAttempt(token)
    setReady(true)
    if (!token) {
      setError(
        'This confirmation link is incomplete. Please start again from the sign-in page.'
      )
    }
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!attempt || loading) return
    setError('')
    setLoading(true)
    try {
      // credentials: 'include' carries the backend-origin confirm cookie that
      // binds this POST to the single-use OIDC flow (CORS allows credentials).
      const res = await fetch(`${getApiBaseUrl()}/api/auth/oidc/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ attempt, password }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(
          body?.detail ||
            'Confirmation failed. Check your password and try again.'
        )
        return
      }
      // Standard login response shape — store exactly like a password login.
      sessionStorage.setItem('teachflow_token', body.access_token)
      sessionStorage.setItem('teachflow_user', JSON.stringify(body.user))
      router.replace('/platform-admin')
    } catch (err) {
      setError(normalizeError(err).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      role="platform_admin"
      title="Confirm your SchemeKnit identity"
      description="Your BloomCore Identity account is linked to an existing SchemeKnit platform administrator. Confirm the link with your existing SchemeKnit password."
      securityNote="SECURE ADMIN ACCESS — Authorized SchemeKnit platform staff only."
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <AuthError message={error} />
        <AuthField
          id="sso-confirm-password"
          label="Existing SchemeKnit password"
          hint="One-time confirmation to bind your BloomCore Identity to this administrator account."
        >
          <PasswordInput
            id="sso-confirm-password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={!attempt || loading}
            required
          />
        </AuthField>
        <Button
          type="submit"
          className="w-full"
          disabled={!attempt || loading || password.length === 0}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          )}
          {loading ? 'Confirming…' : 'Confirm and sign in'}
        </Button>
        {!ready ? null : (
          <p className="text-center text-xs text-muted-foreground">
            Trouble confirming?{' '}
            <a href="/login/platform-admin" className="underline">
              Use password sign-in instead
            </a>
          </p>
        )}
      </form>
    </AuthShell>
  )
}
