'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/password-input'
import { api } from '@/lib/api'
import { MfaEnrollPanel } from '@/components/mfa-enroll-panel'
import { Shield, Copy } from 'lucide-react'

export function MfaSettingsCard() {
  const [status, setStatus] = useState<{ enabled: boolean; recovery_codes_remaining: number } | null>(null)
  const [enrolling, setEnrolling] = useState(false)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [acknowledged, setAcknowledged] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api.getMfaStatus().then(setStatus).catch(() => setStatus(null))
  useEffect(() => { load() }, [])

  const begin = async () => {
    setError(''); setSuccess(''); setRecoveryCodes(null)
    setEnrolling(true)
  }

  const disable = async () => {
    setError(''); setSuccess(''); setBusy(true)
    try {
      await api.disableMfa(password, code)
      setPassword(''); setCode('')
      setSuccess('MFA disabled.')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not disable MFA')
    } finally { setBusy(false) }
  }

  const regenerate = async () => {
    setError(''); setSuccess(''); setBusy(true)
    try {
      const res = await api.regenerateMfaRecovery(password, code)
      setRecoveryCodes(res.recovery_codes)
      setAcknowledged(false)
      setSuccess('New recovery codes generated. Previous codes are invalid.')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not regenerate recovery codes')
    } finally { setBusy(false) }
  }

  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text) } catch { /* manual copy */ }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-muted-foreground" />
          <div>
            <CardTitle className="text-lg">Two-Factor Authentication</CardTitle>
            <CardDescription>
              Protect platform administration with an authenticator app.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        {success && <p role="status" className="text-sm text-emerald-700">{success}</p>}

        {status && (
          <p className="text-sm text-muted-foreground">
            Status: <strong>{status.enabled ? 'Enabled' : 'Not enabled'}</strong>
            {status.enabled && ` · Recovery codes remaining: ${status.recovery_codes_remaining}`}
          </p>
        )}

        {recoveryCodes && (
          <div className="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-4">
            <p className="text-sm font-semibold text-amber-900">
              Recovery codes — shown once. Store them offline.
            </p>
            <div className="grid grid-cols-2 gap-2 font-mono text-sm">
              {recoveryCodes.map((c) => (
                <span key={c} className="rounded bg-white px-2 py-1">{c}</span>
              ))}
            </div>
            <Button type="button" variant="outline" onClick={() => copy(recoveryCodes.join('\n'))}>
              <Copy className="h-4 w-4" /> Copy codes
            </Button>
            <label className="flex items-start gap-2 text-sm text-amber-900">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
                className="mt-1"
              />
              I have stored these recovery codes securely. They cannot be shown again.
            </label>
            {!acknowledged && (
              <p className="text-xs text-amber-800">Acknowledge before leaving this page.</p>
            )}
          </div>
        )}

        {!status?.enabled && !enrolling && (
          <Button onClick={begin} disabled={busy}>Enable MFA</Button>
        )}

        {!status?.enabled && enrolling && (
          <MfaEnrollPanel
            onComplete={async () => {
              setEnrolling(false)
              setSuccess('MFA enabled. Store the recovery codes securely.')
              await load()
            }}
          />
        )}

        {status?.enabled && (
          <div className="space-y-3 rounded-lg border p-4">
            <p className="text-sm font-medium">Manage MFA</p>
            <p className="text-xs text-muted-foreground">
              To change authenticator, turn MFA off first with your password and
              a current code, then enroll the new device. The current secret is
              never shown again.
            </p>
            <PasswordInput
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Current password"
              autoComplete="current-password"
              toggleLabel="Show password"
            />
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Authenticator or recovery code"
              autoComplete="one-time-code"
            />
            <div className="flex flex-wrap gap-2">
              <Button onClick={regenerate} disabled={busy} variant="outline">Regenerate recovery codes</Button>
              <Button onClick={disable} disabled={busy} variant="destructive">Disable MFA</Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
