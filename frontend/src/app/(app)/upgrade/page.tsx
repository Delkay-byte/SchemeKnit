'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Banner } from '@/components/ui/banner'
import { ArrowLeft, Building, Smartphone, Clock } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { PageHeader } from '@/components/ui/page-header'
import { api } from '@/lib/api'
import { upgradePath } from '@/lib/purchase-return'
import type { CataloguePlan, CreditStatus } from '@/types'
import { normalizeError } from '@/lib/error-normalizer'
import {
  PENDING_CHECK_DELAY_MS, PENDING_POLL_INTERVAL_MS, canSubmitOtp,
  chargeStage, chargeStageMessage, isAwaitingMomoAuthorisation,
  isBankTransferPrompt, isExpired, isFinalFailure, isOtpRequired,
  isPayOffline, isSuccess, shouldPollCharge,
} from '@/lib/payment-flow'

type Charge = {
  reference: string
  status: string
  charge_status?: string
  display_text?: string
  payment_details?: {
    account_name?: string
    account_number?: string
    bank_name?: string
    account_expires_at?: string
    transaction_reference?: string
  }
}

function money(pesewas: number) {
  return `GH₵${(pesewas / 100).toFixed(2)}`
}

export default function UpgradePage() {
  const router = useRouter()
  const params = useSearchParams()
  const { user, loading: authLoading } = useAuth()
  const [plans, setPlans] = useState<CataloguePlan[]>([])
  const [credits, setCredits] = useState<CreditStatus | null>(null)
  const [selected, setSelected] = useState('')
  const [method, setMethod] = useState<'bank_transfer' | 'mobile_money'>('bank_transfer')
  const [phone, setPhone] = useState('')
  const [provider, setProvider] = useState('mtn')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [charge, setCharge] = useState<Charge | null>(null)
  const [otp, setOtp] = useState('')
  const [otpError, setOtpError] = useState('')
  const [submittingOtp, setSubmittingOtp] = useState(false)
  const [canCheck, setCanCheck] = useState(false)
  const [checking, setChecking] = useState(false)
  const [statusError, setStatusError] = useState('')
  // Monotonic token: a slow, stale status response must never overwrite a
  // newer state (or a successful OTP submission).
  const checkSeq = useRef(0)

  useEffect(() => {
    if (!authLoading && !user) {
      const wanted = params.get('package')
      const target = wanted ? upgradePath(wanted) : null
      router.push(
        target ? `/login?next=${encodeURIComponent(target)}` : '/login',
      )
      return
    }
    if (!user) return
    if (user.role === 'school_admin') {
      router.push('/school-admin')
      return
    }
    if (user.role === 'platform_admin') {
      router.push('/platform-admin')
      return
    }
    if (user.role !== 'teacher') {
      router.push('/dashboard')
      return
    }
    api.getCatalogue()
      .then((d) => {
        const purchasable = (d.plans || []).filter((p: CataloguePlan) => p.active)
        setPlans(purchasable)
        const wanted = params.get('package')
        if (wanted) {
          const valid = purchasable.some((p: CataloguePlan) => p.slug === wanted)
          setSelected(valid ? String(wanted) : '')
          if (!valid) {
            setError(
              'The selected package is no longer available. Choose a current '
              + 'package below; no payment has been started.',
            )
          }
        } else {
          setSelected(purchasable[0]?.slug || '')
        }
      })
      .catch(() => setError('Packages could not be loaded. No payment can be started.'))
    api.getCredits().then(setCredits).catch(() => {})
    // Restore a still-pending prepaid charge after a refresh/return so the
    // customer does not lose the account details or create a second purchase.
    api.getMySubscription()
      .then((d) => {
        if (d?.pending_payment?.reference) setCharge(d.pending_payment)
      })
      .catch(() => {})
  }, [user, authLoading, params, router])

  // Poll a prepaid charge until Paystack confirms it, fails it, or it expires.
  // Paystack asks merchants to wait at least 10 seconds before checking a
  // pending charge, and OTP entry must be completed first.
  useEffect(() => {
    if (!charge || !shouldPollCharge(charge)) return
    const reference = charge.reference
    const id = window.setInterval(async () => {
      const seq = ++checkSeq.current
      try {
        const next = await api.chargeStatus(reference)
        if (seq !== checkSeq.current) return
        setCharge(next)
        setStatusError('')
        if (isSuccess(next)) {
          window.clearInterval(id)
          router.push('/subscription?activated=1')
        } else if (isFinalFailure(next)) {
          window.clearInterval(id)
          setBusy(false)
        }
      } catch {
        // A network hiccup is not proof the payment failed — keep polling and
        // show an honest "temporarily unavailable" note.
        if (seq === checkSeq.current) {
          setStatusError('Payment status is temporarily unavailable. Your payment is still being checked.')
        }
      }
    }, PENDING_POLL_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [charge?.reference, charge?.status, charge?.charge_status, router])

  useEffect(() => {
    if (!charge || charge.status !== 'pending') {
      setCanCheck(false)
      return
    }
    setCanCheck(false)
    const timer = window.setTimeout(() => setCanCheck(true), PENDING_CHECK_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [charge?.reference, charge?.status, charge?.charge_status])

  const start = async () => {
    if (!selected) return
    setError('')
    setBusy(true)
    setCharge(null)
    setOtp('')
    setOtpError('')
    setStatusError('')
    setCanCheck(false)
    checkSeq.current += 1
    try {
      const data = method === 'bank_transfer'
        ? await api.bankTransferCharge(selected)
        : await api.momoCharge(selected, phone, provider)
      setCharge(data)
      // The charge itself now drives the UI (OTP form / pending / success),
      // so the start button must not stay stuck in "sending" state.
      setBusy(false)
      if (data.status === 'success') {
        router.push('/subscription?activated=1')
      } else if (data.status === 'failed') {
        setBusy(false)
      }
    } catch (err) {
      setError(normalizeError(err).message)
      setBusy(false)
    }
  }

  if (authLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-primary" />
      </div>
    )
  }

  const plan = plans.find((p) => p.slug === selected)

  return (
    <div className="min-h-screen">
      <main className="container mx-auto max-w-4xl px-4 py-8">
        <Link href="/dashboard" className="mb-6 inline-flex items-center text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="mr-1 h-4 w-4" /> Back to Dashboard
        </Link>

        <PageHeader
          eyebrow="Upgrade"
          title="Buy lesson-plan credits"
          description="Prepaid packages. Bank Transfer or Mobile Money only — no card and no automatic renewal."
        />

        {credits && (
          <SurfaceCard className="mt-6 px-5 py-4" data-credit-balance>
            <div className="grid gap-3 text-sm sm:grid-cols-4">
              <div><p className="text-xs uppercase text-slate-500">Free monthly</p><p className="text-xl font-bold text-[#102A43]">{credits.free.remaining}</p></div>
              <div><p className="text-xs uppercase text-slate-500">Package</p><p className="text-xl font-bold text-[#102A43]">{credits.package}</p></div>
              <div><p className="text-xs uppercase text-slate-500">Flexible</p><p className="text-xl font-bold text-[#102A43]">{credits.purchased}</p></div>
              <div><p className="text-xs uppercase text-slate-500">Referral</p><p className="text-xl font-bold text-[#102A43]">{credits.referral}</p></div>
            </div>
          </SurfaceCard>
        )}

        {error && <Banner tone="danger" className="mt-4">{error}</Banner>}

        <section className="mt-6">
          <h2 className="text-lg font-semibold text-[#102A43]">Choose a package</h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            {plans.map((p) => (
              <button
                key={p.slug}
                type="button"
                onClick={() => setSelected(p.slug)}
                className={`rounded-xl border p-4 text-left transition ${
                  selected === p.slug
                    ? 'border-[#04A9CE] ring-2 ring-[#04A9CE]/20'
                    : 'border-slate-200 hover:border-[#04A9CE]/50'
                }`}
                data-package={p.slug}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <h3 className="font-semibold text-[#102A43]">{p.name}</h3>
                  <span className="font-semibold text-[#035f7c]">{money(p.price_pesewas)}</span>
                </div>
                <p className="mt-1 text-sm text-slate-600">
                  {p.credits} indicator-level lesson plans · {p.validity_label}
                </p>
                <p className="mt-2 text-xs text-slate-500">{p.description}</p>
              </button>
            ))}
            {plans.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Packages are unavailable right now. No payment can be started.
              </p>
            )}
          </div>
        </section>

        {plan && (
          <SurfaceCard className="mt-6 px-5 py-5" data-checkout>
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="text-lg font-semibold text-[#102A43]">Pay for {plan.name}</h2>
              <span className="text-lg font-bold text-[#035f7c]">{money(plan.price_pesewas)}</span>
            </div>
            <p className="mt-1 text-sm text-slate-600">
              {plan.credits} credits · {plan.validity_label}. {plan.payment_terms}
            </p>

            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setMethod('bank_transfer')}
                className={`flex items-center gap-2 rounded-lg border px-4 py-3 text-sm font-semibold ${
                  method === 'bank_transfer' ? 'border-[#04A9CE] bg-[#04A9CE]/5' : 'border-slate-200'
                }`}
                data-method="bank_transfer"
              >
                <Building className="h-4 w-4" /> Bank Transfer
              </button>
              <button
                type="button"
                onClick={() => setMethod('mobile_money')}
                className={`flex items-center gap-2 rounded-lg border px-4 py-3 text-sm font-semibold ${
                  method === 'mobile_money' ? 'border-[#04A9CE] bg-[#04A9CE]/5' : 'border-slate-200'
                }`}
                data-method="mobile_money"
              >
                <Smartphone className="h-4 w-4" /> Mobile Money
              </button>
            </div>

            {method === 'mobile_money' && (
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="text-sm">
                  <span className="mb-1 block text-xs font-semibold uppercase text-slate-500">Network</span>
                  <select
                    className="w-full rounded-lg border border-slate-300 px-3 py-2"
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                    data-momo-provider
                  >
                    <option value="mtn">MTN Mobile Money</option>
                    <option value="telecel">Telecel Cash</option>
                    <option value="airteltigo">AirtelTigo Money</option>
                  </select>
                </label>
                <label className="text-sm">
                  <span className="mb-1 block text-xs font-semibold uppercase text-slate-500">Mobile number</span>
                  <input
                    className="w-full rounded-lg border border-slate-300 px-3 py-2"
                    placeholder="0241234567"
                    inputMode="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    data-momo-phone
                  />
                </label>
              </div>
            )}

            <Button
              className="mt-4"
              onClick={start}
              disabled={busy || charge?.status === 'pending' || (method === 'mobile_money' && phone.trim().length < 10)}
              data-start-payment
            >
              {busy ? 'Waiting for confirmation…' : method === 'bank_transfer' ? 'Get bank transfer details' : 'Send Mobile Money request'}
            </Button>
            {charge?.status === 'pending' && (
              <Button
                variant="outline"
                size="sm"
                className="ml-2 mt-4"
                onClick={() => setCharge(null)}
              >
                Start a different payment
              </Button>
            )}

            {charge && (() => {
              const stage = chargeStage(charge)
              const display = (charge.display_text || '').trim()
              return (
                <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4"
                  role="status" data-charge-status={charge.status} data-payment-stage={stage}>
                  {stage === 'otp' ? (
                    <div data-momo-otp>
                      <p className="font-semibold text-[#102A43]">Enter your one-time password</p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Paystack asked for the SMS one-time password for this payment.
                        Enter it here to continue. This is not your Mobile Money PIN.
                      </p>
                      {display && <p className="mt-2 text-sm text-[#102A43]">{display}</p>}
                      <div className="mt-3 max-w-xs">
                        <label htmlFor="momo-otp" className="text-xs font-medium">One-time password</label>
                        <input
                          id="momo-otp"
                          inputMode="numeric"
                          autoComplete="one-time-code"
                          aria-describedby="momo-otp-help"
                          value={otp}
                          onChange={(e) => { setOtp(e.target.value.replace(/\D/g, '').slice(0, 8)); setOtpError('') }}
                          className="mt-1 w-full rounded-md border border-input bg-white px-3 py-2 text-sm tracking-widest"
                          placeholder="e.g. 123456"
                        />
                        <p id="momo-otp-help" className="mt-1 text-xs text-slate-500">
                          Synthetic test codes only in development. Never share this code.
                        </p>
                      </div>
                      {otpError && <p className="mt-2 text-xs text-destructive" role="alert">{otpError}</p>}
                      <p className="mt-2 text-xs text-slate-500">
                        Payment reference {charge.reference}. Quote it to support if the code does not arrive.
                      </p>
                      <Button
                        className="mt-3"
                        disabled={submittingOtp || !canSubmitOtp(charge, otp)}
                        onClick={async () => {
                          if (submittingOtp) return
                          setSubmittingOtp(true)
                          setOtpError('')
                          try {
                            const next = await api.submitMomoOtp(charge.reference, otp)
                            checkSeq.current += 1
                            setCharge(next)
                            setOtp('')
                            if (isSuccess(next)) {
                              router.push('/subscription?activated=1')
                            } else if (isFinalFailure(next)) {
                              setBusy(false)
                            } else if (isOtpRequired(next)) {
                              setOtpError('That code was not accepted. Check the SMS and try again.')
                            }
                          } catch (err) {
                            setOtpError(normalizeError(err).message)
                          } finally {
                            setSubmittingOtp(false)
                          }
                        }}
                      >
                        {submittingOtp ? 'Submitting…' : 'Submit OTP'}
                      </Button>
                    </div>
                  ) : isBankTransferPrompt(charge) ? (
                    <>
                      <p className="flex items-center gap-2 font-semibold text-[#102A43]">
                        <Clock className="h-4 w-4" /> Waiting for your transfer
                      </p>
                      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                        <div><dt className="text-xs uppercase text-slate-500">Bank</dt><dd>{charge.payment_details.bank_name}</dd></div>
                        <div><dt className="text-xs uppercase text-slate-500">Account number</dt><dd className="font-mono text-base">{charge.payment_details.account_number}</dd></div>
                        <div><dt className="text-xs uppercase text-slate-500">Account name</dt><dd>{charge.payment_details.account_name}</dd></div>
                        <div><dt className="text-xs uppercase text-slate-500">Amount due</dt><dd className="font-semibold">{plan ? money(plan.price_pesewas) : '—'}</dd></div>
                        <div><dt className="text-xs uppercase text-slate-500">Transfer reference</dt><dd className="font-mono break-all">{charge.payment_details.transaction_reference || charge.reference}</dd></div>
                        <div><dt className="text-xs uppercase text-slate-500">Expires</dt><dd>{charge.payment_details.account_expires_at ? new Date(charge.payment_details.account_expires_at).toLocaleString() : '—'}</dd></div>
                      </dl>
                      <p className="mt-3 text-xs text-slate-500">
                        Nothing is activated until Paystack confirms the transfer. This page checks automatically.
                      </p>
                    </>
                  ) : stage === 'success' ? (
                    <div data-payment-success>
                      <p className="font-semibold text-green-800">Payment successful</p>
                      <p className="mt-1 text-sm text-[#102A43]">
                        Your package is now active. Your credits are available on your dashboard.
                      </p>
                    </div>
                  ) : stage === 'failed' || stage === 'expired' ? (
                    <div data-payment-failed>
                      <p className="font-semibold text-[#102A43]">
                        {stage === 'expired' ? 'Payment session expired' : 'Payment was not completed'}
                      </p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {chargeStageMessage(stage)} No credits were issued.
                      </p>
                    </div>
                  ) : (
                    <div data-payment-waiting>
                      <p className="font-semibold text-[#102A43]">
                        {stage === 'pay_offline' || stage === 'awaiting_momo_authorisation'
                          ? 'Check your phone'
                          : 'Waiting for confirmation'}
                      </p>
                      <p className="mt-1 text-sm text-[#102A43]">
                        {display || chargeStageMessage(stage)}
                      </p>
                      {isPayOffline(charge) && (
                        <div className="mt-3 rounded-md border border-slate-200 bg-white p-3 text-sm text-[#102A43]">
                          <p className="font-medium">Mobile Money authorisation</p>
                          <p className="mt-1">
                            Follow the prompt on your phone. If your provider asks for the
                            SMS code, enter it in the Mobile Money prompt — not on SchemeKnit.
                          </p>
                          <p className="mt-1">
                            Enter your Mobile Money PIN only in your provider&apos;s own interface.
                            SchemeKnit will never ask for it.
                          </p>
                          <p className="mt-2 text-xs text-muted-foreground">
                            No prompt on your phone? Confirm the number is registered for
                            Mobile Money, keep the phone connected, then start a new request.
                            Nothing is charged until Paystack confirms the payment.
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {charge.status === 'pending' && !isOtpRequired(charge) && (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!canCheck || checking}
                        onClick={async () => {
                          if (checking) return
                          const seq = ++checkSeq.current
                          setChecking(true)
                          setStatusError('')
                          try {
                            const next = await api.chargeStatus(charge.reference)
                            if (seq !== checkSeq.current) return
                            setCharge(next)
                            if (isSuccess(next)) {
                              router.push('/subscription?activated=1')
                            } else if (isFinalFailure(next)) {
                              setBusy(false)
                            }
                          } catch {
                            if (seq === checkSeq.current) {
                              setStatusError('Payment status is temporarily unavailable. Your payment is still being checked; try again in a moment.')
                            }
                          } finally {
                            if (seq === checkSeq.current) setChecking(false)
                          }
                        }}
                      >
                        {checking ? 'Checking…' : canCheck ? 'Check status now' : 'Checking becomes available in 10s…'}
                      </Button>
                      <span className="text-xs text-slate-500">Reference {charge.reference}</span>
                    </div>
                  )}

                  {(stage === 'failed' || stage === 'expired') && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-3"
                      onClick={() => {
                        checkSeq.current += 1
                        setCharge(null)
                        setStatusError('')
                        setOtp('')
                        setOtpError('')
                      }}
                    >
                      Start a new payment
                    </Button>
                  )}

                  {statusError && (
                    <p className="mt-2 text-xs text-amber-800" role="status">{statusError}</p>
                  )}
                </div>
              )
            })()}
          </SurfaceCard>
        )}

        <p className="mt-6 text-xs text-muted-foreground">
          Already have a package? <Link href="/subscription" className="underline">View your credits and payment history</Link>.
        </p>
      </main>
    </div>
  )
}
