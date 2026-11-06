'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { PageHeader } from '@/components/ui/page-header'
import { api } from '@/lib/api'
import { normalizeError } from '@/lib/error-normalizer'
import {
  amountLabel,
  balanceLabel,
  purchaseHeadline,
  purchasePhase,
  purchaseTone,
  type PurchaseView,
} from '@/lib/purchase-state'

const TONE_CLASS: Record<string, string> = {
  success: 'border-green-200 bg-green-50 text-green-900',
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
  danger: 'border-red-200 bg-red-50 text-red-900',
  info: 'border-sky-200 bg-sky-50 text-sky-900',
}

export default function PaymentCallbackPage() {
  const [reference, setReference] = useState('')
  const [purchase, setPurchase] = useState<PurchaseView | null>(null)
  const [message, setMessage] = useState('Verifying your payment with Paystack…')
  const [busy, setBusy] = useState(true)

  const load = useCallback(async (ref: string) => {
    setBusy(true)
    setMessage('Verifying your payment with Paystack…')
    try {
      const data = await api.verifyPaystack(ref)
      setPurchase(data?.purchase || null)
      setMessage('')
    } catch (err) {
      const text = normalizeError(err).message
      try {
        const status = await api.chargeStatus(ref)
        if (status?.purchase) {
          setPurchase(status.purchase)
          setMessage('')
        } else {
          setMessage(text)
        }
      } catch {
        setMessage(text)
      }
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    const ref = new URLSearchParams(window.location.search).get('reference') ||
      new URLSearchParams(window.location.search).get('trxref') || ''
    setReference(ref)
    if (!ref) {
      setMessage('No payment reference was provided.')
      setBusy(false)
      return
    }
    void load(ref)
  }, [load])

  const phase = purchasePhase(purchase)
  const tone = purchaseTone(phase)
  const licence = purchase?.licence || null

  return (
    <div className="min-h-screen">
      <main className="container mx-auto max-w-2xl px-4 py-8">
        <PageHeader
          eyebrow="Billing"
          title="Purchase confirmation"
          description="Payment and activation are separate. This page reports both."
        />
        <SurfaceCard className="mt-6 px-6 py-6" data-payment-result={phase}>
          <div className={`rounded-lg border px-4 py-3 ${TONE_CLASS[tone]}`} role="status">
            <p className="font-semibold">{purchaseHeadline(phase)}</p>
            {busy && <p className="mt-1 text-sm">Checking with Paystack…</p>}
            {!busy && message && <p className="mt-1 text-sm">{message}</p>}
          </div>

          {purchase && (
            <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2" data-purchase-summary>
              <div>
                <dt className="text-xs uppercase text-slate-500">Package</dt>
                <dd className="font-medium">{purchase.package?.name || '—'}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Amount paid</dt>
                <dd className="font-medium">{amountLabel(purchase)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Payment status</dt>
                <dd className="font-medium">
                  {phase === 'activated' || phase === 'needs_attention'
                    ? 'Successful'
                    : purchase.payment_status || '—'}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Fulfilment</dt>
                <dd className="font-medium">{purchase.fulfilment_status || '—'}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Transaction reference</dt>
                <dd className="break-all font-mono text-xs">{purchase.reference || reference}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Purchase date</dt>
                <dd className="font-medium">
                  {purchase.paid_at ? new Date(purchase.paid_at).toLocaleString() : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Credits activated</dt>
                <dd className="font-medium">
                  {phase === 'activated'
                    ? (purchase.credits_granted ?? purchase.package?.credits ?? 0)
                    : 'Not activated yet'}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Current credit balance</dt>
                <dd className="font-medium">{balanceLabel(purchase)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Licence status</dt>
                <dd className="font-medium">{licence?.status || 'Not issued yet'}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Payment channel</dt>
                <dd className="font-medium">{purchase.channel || '—'}</dd>
              </div>
            </dl>
          )}

          {purchase && phase === 'activated' && (
            <p className="mt-4 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
              Licence and package benefits are activated automatically on this
              account. You do not need to copy or enter a licence key.
            </p>
          )}

          {phase === 'needs_attention' && (
            <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              Your payment was received. SchemeKnit is completing the licence/credit
              activation. Do not pay again — refresh this page or contact support with
              the reference above.
            </p>
          )}
          {phase === 'payment_pending' && (
            <p className="mt-3 text-sm text-muted-foreground">
              If you have not approved the prompt on your phone, do that now. Entering
              an OTP alone does not complete the purchase.
            </p>
          )}
          {phase === 'payment_failed' && (
            <p className="mt-3 text-sm text-muted-foreground">
              This payment did not complete. No credits were issued. You can start
              a new purchase from the package page.
            </p>
          )}

          <div className="mt-6 flex flex-wrap gap-3">
            {(phase === 'payment_pending' || phase === 'processing' ||
              phase === 'needs_attention') && (
              <Button onClick={() => reference && void load(reference)} disabled={busy}>
                {busy ? 'Checking…' : 'Refresh status'}
              </Button>
            )}
            {phase === 'activated' && (
              <Button asChild><Link href="/subscription">View credits and licence</Link></Button>
            )}
            {phase !== 'activated' && (
              <Button asChild variant="outline"><Link href="/upgrade">Back to plans</Link></Button>
            )}
            <Button asChild variant="outline"><Link href="/dashboard">Dashboard</Link></Button>
          </div>
        </SurfaceCard>
      </main>
    </div>
  )
}
