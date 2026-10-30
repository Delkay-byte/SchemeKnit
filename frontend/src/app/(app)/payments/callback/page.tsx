'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { PageHeader } from '@/components/ui/page-header'
import { api } from '@/lib/api'

export default function PaymentCallbackPage() {
  const [state, setState] = useState<'checking' | 'success' | 'pending' | 'failed'>('checking')
  const [message, setMessage] = useState('Verifying your payment with Paystack…')
  const [licence, setLicence] = useState<any>(null)
  const [reference, setReference] = useState('')

  useEffect(() => {
    const ref = new URLSearchParams(window.location.search).get('reference') ||
      new URLSearchParams(window.location.search).get('trxref') || ''
    setReference(ref)
    if (!ref) {
      setState('failed')
      setMessage('No payment reference was provided.')
      return
    }
    api.verifyPaystack(ref)
      .then((data) => {
        setState('success')
        setLicence(data.licence)
        setMessage('Payment verified. Your subscription is active.')
      })
      .catch((err) => {
        const text = err instanceof Error ? err.message : 'Payment could not be verified.'
        setState(/not been confirmed|pending/i.test(text) ? 'pending' : 'failed')
        setMessage(text)
      })
  }, [])

  return (
    <div className="min-h-screen">
      <main className="container mx-auto max-w-2xl px-4 py-8">
        <PageHeader eyebrow="Billing" title="Payment result" description="TeachFlow verifies every payment on the server before issuing a licence." />
        <SurfaceCard className="mt-6 px-6 py-6" data-payment-result={state}>
          <p className="text-sm" role="status">{message}</p>
          {state === 'success' && licence && (
            <div className="mt-4 rounded-lg bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Your licence key</p>
              <p className="mt-1 font-mono text-lg" data-licence-key>{licence.key}</p>
              <p className="mt-2 text-xs text-muted-foreground">
                Valid until {licence.expires_at ? new Date(licence.expires_at).toLocaleDateString() : '—'}.
              </p>
            </div>
          )}
          {state === 'pending' && (
            <p className="mt-3 text-sm text-muted-foreground">
              Paystack has not confirmed this payment yet. No licence has been issued.
              Refresh this page shortly{reference ? ` (reference ${reference})` : ''}.
            </p>
          )}
          <div className="mt-6 flex flex-wrap gap-3">
            {state === 'success' && (
              <Button asChild><Link href="/subscription">View subscription</Link></Button>
            )}
            <Button asChild variant="outline"><Link href="/upgrade">Back to plans</Link></Button>
          </div>
        </SurfaceCard>
      </main>
    </div>
  )
}
