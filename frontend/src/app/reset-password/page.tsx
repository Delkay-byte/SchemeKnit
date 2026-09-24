'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { PasswordInput, PasswordMatchIndicator, passwordMatchStatus } from '@/components/password-input'
import { AuthShell } from '@/components/auth/auth-shell'
import { validatePassword, PASSWORD_POLICY } from '@/lib/password-policy'
import { api } from '@/lib/api'
import { useSearchParams } from 'next/navigation'
import { ArrowRight } from 'lucide-react'

/**
 * Public password-reset completion page.
 *
 * The user arrives here with a one-time reset token (delivered out-of-band by
 * an admin or the CLI break-glass tool). This page validates the token against
 * the target account, then lets the user set a new password.
 */
export default function ResetPasswordPage() {
  const router = useRouter()
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

  // Auto-fill token from ?token= query param (convenience link).
  useEffect(() => {
    const t = searchParams.get('token')
    if (t) {
      setToken(t)
    }
  }, [searchParams])

  // Validate the token whenever it changes (shows the target account).
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

  // Auto-validate when a token is present from the URL.
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
        title="Password Reset"
        description="Your password has been reset successfully. Sign in with your new password."
      >
        <Link href="/login">
          <Button className="w-full">
            Sign In <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </Link>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      role="password_reset"
      title="Reset Your Password"
      description="Enter the one-time reset token you received, then choose a new password."
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">
            Reset Token
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={token}
              onChange={(e) => {
                setToken(e.target.value)
                setTargetEmail('')
              }}
              required
              autoComplete="off"
              placeholder="Paste your reset token here"
              className="w-full px-3 py-2 border rounded-md font-mono text-sm"
            />
            <Button
              type="button"
              variant="outline"
              onClick={handleValidate}
              disabled={validating || !token.trim()}
            >
              {validating ? 'Checking...' : 'Verify'}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            The token is single-use and expires 30 minutes after it was
            issued.
          </p>
        </div>

        {targetEmail && (
          <div className="p-3 rounded-lg border border-blue-200 bg-blue-50">
            <p className="text-sm text-blue-700">
              Token verified for{' '}
              <strong>{targetName}</strong> ({targetEmail}).
            </p>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium mb-1">
            New Password
          </label>
          <PasswordInput
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            placeholder="Create a new password"
            toggleLabel="Show password"
          />
          <p className="text-xs text-muted-foreground mt-1">
            {PASSWORD_POLICY.description}
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">
            Confirm New Password
          </label>
          <PasswordInput
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            placeholder="Confirm your new password"
            toggleLabel="Show password"
          />
          <PasswordMatchIndicator
            password={newPassword}
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
          {loading ? 'Please wait...' : 'Reset Password'}
        </Button>
      </form>

      <div className="mt-4 text-center">
        <Link
          href="/login"
          className="text-xs text-muted-foreground hover:text-foreground underline"
        >
          Back to sign in
        </Link>
      </div>
    </AuthShell>
  )
}
