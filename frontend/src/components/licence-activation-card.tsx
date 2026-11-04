'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { normalizeError } from '@/lib/error-normalizer'

export interface LicenceActivationCardProps {
  accountEmail?: string
  prefilledKey?: string
  alreadyActive?: boolean
  onActivated?: () => void
}

/** Same-page licence key display, copy and activation. */
export function LicenceActivationCard({
  accountEmail,
  prefilledKey = '',
  alreadyActive = false,
  onActivated,
}: LicenceActivationCardProps) {
  const [key, setKey] = useState(prefilledKey)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const copy = async () => {
    if (!prefilledKey) return
    try {
      await navigator.clipboard.writeText(prefilledKey)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setError('Copy failed. Select the key and copy it manually.')
    }
  }

  const activate = async () => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await api.redeemLicenceKey(key.trim())
      setMessage(result?.message || 'Licence activated.')
      onActivated?.()
    } catch (err) {
      setError(normalizeError(err).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4" data-licence-card>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Your licence key
      </p>
      {prefilledKey ? (
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <code className="break-all font-mono text-sm" data-licence-key>{prefilledKey}</code>
          <Button type="button" size="sm" variant="outline" onClick={copy}>
            {copied ? 'Copied' : 'Copy'}
          </Button>
        </div>
      ) : (
        <p className="mt-1 text-sm text-muted-foreground">No key has been issued yet.</p>
      )}

      {alreadyActive && (
        <p className="mt-2 text-sm text-green-700" role="status">
          This licence is already active on {accountEmail || 'this account'}. You do
          not need to re-enter it.
        </p>
      )}

      <div className="mt-3">
        <label htmlFor="licence-redeem-key" className="mb-1 block text-xs font-medium text-muted-foreground">
          Enter licence key
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            id="licence-redeem-key"
            value={key}
            onChange={(event) => setKey(event.target.value.toUpperCase())}
            placeholder="TF-XXXX-XXXX-XXXX-XXXX"
            autoComplete="off"
            spellCheck={false}
          />
          <Button
            type="button"
            onClick={activate}
            disabled={busy || !key.trim()}
            data-activate-licence
          >
            {busy ? 'Activating…' : 'Activate licence'}
          </Button>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Activates for {accountEmail || 'the signed-in teacher account'} only. A key
          issued to another account cannot be transferred.
        </p>
      </div>

      {message && <p className="mt-2 text-sm text-green-700" role="status">{message}</p>}
      {error && <p className="mt-2 text-sm text-red-700" role="alert">{error}</p>}
    </section>
  )
}
