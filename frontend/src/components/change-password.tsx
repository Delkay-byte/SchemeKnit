'use client'

import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { PasswordInput, PasswordMatchIndicator, passwordMatchStatus } from '@/components/password-input'
import { validatePassword, PASSWORD_POLICY } from '@/lib/password-policy'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { KeyRound } from 'lucide-react'

/**
 * Self-service password change for any authenticated role.
 *
 * Requires the CURRENT password (verified server-side). The new password must
 * satisfy the production policy. On success the backend issues a fresh token
 * (stamped with the new password version) which replaces the stored one so the
 * current session stays valid while every OTHER session is invalidated.
 */
export function ChangePasswordCard() {
  const { token, login } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  const match = passwordMatchStatus(newPassword, confirmPassword)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')

    const pwCheck = validatePassword(newPassword)
    if (!pwCheck.ok) {
      setError(pwCheck.message)
      return
    }
    if (currentPassword === newPassword) {
      setError('New password must be different from your current password.')
      return
    }
    if (!match.matched) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      const res = await api.changePassword(currentPassword, newPassword)
      // Replace the stored token with the fresh one so THIS tab's session
      // remains valid; all other sessions are invalidated by the pwv bump.
      if (res.access_token && token) {
        const savedUser = sessionStorage.getItem('teachflow_user')
        if (savedUser) {
          const userObj = JSON.parse(savedUser)
          sessionStorage.setItem('teachflow_token', res.access_token)
          sessionStorage.setItem('teachflow_user', JSON.stringify(userObj))
          api.setToken(res.access_token)
        }
      }
      setSuccess('Password changed successfully. Your other devices will need to sign in again.')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Password change failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-muted-foreground" />
          <div>
            <CardTitle className="text-lg">Change Password</CardTitle>
            <CardDescription>
              Enter your current password, then choose a new one.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4 max-w-md">
          <div>
            <label htmlFor="current-password" className="block text-sm font-medium mb-1">
              Current Password
            </label>
            <PasswordInput
              id="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              minLength={8}
              autoComplete="current-password"
              placeholder="Your current password"
              toggleLabel="Show password"
            />
          </div>
          <div>
            <label htmlFor="new-password" className="block text-sm font-medium mb-1">
              New Password
            </label>
            <PasswordInput
              id="new-password"
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
            <label htmlFor="confirm-new-password" className="block text-sm font-medium mb-1">
              Confirm New Password
            </label>
            <PasswordInput
              id="confirm-new-password"
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
          {success && (
            <p className="text-sm text-emerald-700 bg-emerald-50 p-2 rounded border border-emerald-200">
              {success}
            </p>
          )}

          <Button
            type="submit"
            disabled={loading || (!match.matched && confirmPassword.length > 0)}
          >
            {loading ? 'Please wait...' : 'Change Password'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
