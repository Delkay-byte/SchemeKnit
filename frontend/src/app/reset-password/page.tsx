'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PasswordInput, PasswordMatchIndicator, passwordMatchStatus } from '@/components/password-input'
import { AuthShell } from '@/components/auth/auth-shell'
import { AuthField, AuthError } from '@/components/auth/auth-field'
import { validatePassword, PASSWORD_POLICY } from '@/lib/password-policy'
import { api } from '@/lib/api'
import { useSearchParams } from 'next/navigation'
import { ArrowRight, ShieldCheck, CheckCircle2 } from 'lucide-react'

/**
 * Public password-reset completion page.
 * Token arrives out-of-band (admin / CLI break-glass). Flow unchanged.
 */
export default function ResetPasswordPage() {
  const searchParams = useSearchParams()
  const [token, setToken] = useState('')
  const [targetEmail, setTargetEmail] = useState('')
  const [targetName, setTargetName] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [validating, setValidating] = useState(false)
  const [success, setSuccess] = useState(false)

  const match = passwordMatchStatus(newPassword, confirmPassword)

  useEffect(() => {
    const t = searchParams.get('token')
    if (t) {
      setToken(t)
    }
  }, [searchParams])

  const handleValidate = async () => {
    if (!token.trim()) {
      setError('Please enter your reset token.')
      return
    }
    setError('')
    setValidating(true)
    try {
      const res = await api.validateResetToken(token.trim())
      setTargetEmail(res.email)
      setTargetName(res.full_name)
    } catch (err) {
      setTargetEmail('')
      setTargetName('')
      setError(err instanceof Error ? err.message : 'Invalid reset token')
    } finally {
      setValidating(false)
    }
  }

  useEffect(() => {
    if (token && !targetEmail && !validating && !success) {
      handleValidate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!token.trim()) {
      setError('Reset token is required.')
      return
    }
    if (!targetEmail) {
      setError('Please validate your reset token first.')
      return
    }
    const pwCheck = validatePassword(newPassword)
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
      await api.confirmPasswordReset(token.trim(), newPassword)
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Password reset failed')
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <AuthShell
        role="password_reset"
        title="Password reset complete"
        description="Your password has been reset successfully. Sign in with your new password."
      >
        <div className="space-y-4 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-100 shadow-inner">
            <CheckCircle2 className="h-8 w-8 text-emerald-600" aria-hidden="true" />
          </div>
          <Link href="/login">
            <Button className="h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold shadow-[0_4px_14px_rgba(16,42,67,0.25)] hover:bg-[#0d2740] active:scale-[0.98] transition">
              <span className="inline-flex items-center gap-2">
                Sign in
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </span>
            </Button>
          </Link>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      role="password_reset"
      title="Reset your password"
      description="Let's get you back into your SchemeKnit workspace. Enter the one-time token, then choose a new password."
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <AuthField id="reset-token" label="Reset token">
          <div className="flex gap-2">
            <Input
              id="reset-token"
              type="text"
              value={token}
              onChange={(e) => {
                setToken(e.target.value)
                setTargetEmail('')
              }}
              required
              autoComplete="off"
              placeholder="Paste your reset token"
              className="font-mono text-sm"
              aria-invalid={error ? true : undefined}
            />
            <Button
              type="button"
              variant="outline"
              onClick={handleValidate}
              disabled={validating || !token.trim()}
              className="shrink-0 rounded-lg border-[#102A43]/20 bg-white px-4 font-semibold hover:border-[#04A9CE]/50 hover:text-[#0389a8]"
            >
              {validating ? (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#102A43]/20 border-t-[#102A43]" />
                  Checking…
                </span>
              ) : (
                'Verify'
              )}
            </Button>
          </div>
        </AuthField>
        <p className="text-xs text-muted-foreground -mt-2">
          The token is single-use and expires 30 minutes after it was issued.
        </p>

        {targetEmail && (
          <div
            className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-2.5 text-xs shadow-sm"
            role="status"
          >
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden="true" />
            <p className="leading-relaxed text-emerald-800">
              Token verified for <strong>{targetName}</strong> ({targetEmail}).
            </p>
          </div>
        )}

        <AuthField
          id="reset-new-password"
          label="New password"
          hint={PASSWORD_POLICY.description}
        >
          <PasswordInput
            id="reset-new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            placeholder="Create a new password"
            toggleLabel="Show password"
          />
        </AuthField>

        <AuthField id="reset-confirm-password" label="Confirm new password">
          <PasswordInput
            id="reset-confirm-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            placeholder="Confirm your new password"
            toggleLabel="Show password"
          />
        </AuthField>
        <PasswordMatchIndicator password={newPassword} confirm={confirmPassword} />

        <AuthError message={error} />

        <Button
          type="submit"
          disabled={loading || (!match.matched && confirmPassword.length > 0)}
          className="h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold shadow-[0_4px_14px_rgba(16,42,67,0.25)] hover:bg-[#0d2740] active:scale-[0.98] transition focus-visible:ring-2 focus-visible:ring-[#04A9CE] focus-visible:ring-offset-2 disabled:opacity-60"
        >
          {loading ? (
            <span className="inline-flex items-center gap-2">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Please wait…
            </span>
          ) : (
            'Reset password'
          )}
        </Button>
      </form>

      <div className="mt-4 text-center">
        <Link
          href="/login"
          className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
        >
          Back to sign in
        </Link>
      </div>
    </AuthShell>
  )
}
