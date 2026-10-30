'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { PageHeader } from '@/components/ui/page-header'
import { api } from '@/lib/api'
import type { CreditStatus } from '@/types'

function fmtDate(v?: string | null) {
  return v ? new Date(v).toLocaleDateString() : '—'
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: 'Pending', success: 'Paid', failed: 'Failed',
    expired: 'Expired', reversed: 'Reversed', abandoned: 'Abandoned',
  }
  return labels[status] || status
}

export default function SubscriptionPage() {
  const [data, setData] = useState<any>(null)
  const [refData, setRefData] = useState<any>(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')

  const load = () => {
    api.getMySubscription()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load subscription.'))
    api.getMyReferrals().then(setRefData).catch(() => {})
  }
  useEffect(() => { load() }, [])

  const copy = async (text: string, key: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(key)
      setTimeout(() => setCopied(''), 1500)
    } catch { /* clipboard unavailable */ }
  }

  const referralLink = refData && typeof window !== 'undefined'
    ? `${window.location.origin}${refData.link_path}`
    : refData?.link_path || ''
  const whatsapp = referralLink
    ? `https://wa.me/?text=${encodeURIComponent(`Join me on SchemeKnit for lesson planning. You get 3 bonus credits after your first successful purchase: ${referralLink}`)}`
    : '#'

  const credits: CreditStatus | null = data?.credits || null

  return (
    <div className="min-h-screen">
      <main className="container mx-auto max-w-3xl px-4 py-8">
        <PageHeader
          eyebrow="Billing"
          title="Your credits and packages"
          description="Free monthly credits, package credits, flexible purchases and referral bonuses are kept separate."
        />
        {error && <div className="mt-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm" role="alert">{error}</div>}

        {!data ? (
          <p className="mt-6 text-sm text-muted-foreground">Loading…</p>
        ) : (
          <div className="mt-6 space-y-6">
            {credits && (
              <SurfaceCard className="px-6 py-6" data-credit-balances>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <div>
                    <p className="text-xs uppercase text-slate-500">Free monthly</p>
                    <p className="text-2xl font-bold text-[#102A43]">{credits.free.remaining}</p>
                    <p className="text-xs text-slate-500">of {credits.free.limit} · resets {credits.free.resets}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase text-slate-500">Package credits</p>
                    <p className="text-2xl font-bold text-[#102A43]">{credits.package}</p>
                    <p className="text-xs text-slate-500">time-limited</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase text-slate-500">Flexible purchased</p>
                    <p className="text-2xl font-bold text-[#102A43]">{credits.purchased}</p>
                    <p className="text-xs text-slate-500">never expire</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase text-slate-500">Referral bonus</p>
                    <p className="text-2xl font-bold text-[#102A43]">{credits.referral}</p>
                    <p className="text-xs text-slate-500">separate from purchased</p>
                  </div>
                </div>
                {credits.packages.length > 0 && (
                  <ul className="mt-4 divide-y divide-slate-100 text-sm">
                    {credits.packages.map((p) => (
                      <li key={`${p.slug}-${p.expires_at}`} className="flex justify-between gap-3 py-2">
                        <span>{p.label}</span>
                        <span className="text-muted-foreground">{p.remaining} credits · expires {fmtDate(p.expires_at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <Button asChild className="mt-4" size="sm">
                  <Link href="/upgrade">Buy more credits</Link>
                </Button>
              </SurfaceCard>
            )}

            <SurfaceCard className="px-6 py-6" data-subscription-status={data.subscription?.status || 'none'}>
              <h2 className="text-lg font-semibold text-[#102A43]">Current package</h2>
              {data.subscription ? (
                <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                  <div><dt className="text-xs uppercase text-slate-500">Package</dt><dd>{data.plan?.name || 'Package'}</dd></div>
                  <div><dt className="text-xs uppercase text-slate-500">Status</dt><dd>{data.subscription.status}</dd></div>
                  <div><dt className="text-xs uppercase text-slate-500">Activated</dt><dd>{fmtDate(data.subscription.current_period_start)}</dd></div>
                  <div><dt className="text-xs uppercase text-slate-500">Paid through</dt><dd>{fmtDate(data.subscription.paid_through)}</dd></div>
                  <div><dt className="text-xs uppercase text-slate-500">Payment</dt><dd>{data.subscription.payment_method === 'mobile_money' ? 'Mobile Money' : 'Bank Transfer'}</dd></div>
                  <div><dt className="text-xs uppercase text-slate-500">Renewal</dt><dd>Prepaid — no automatic renewal</dd></div>
                </dl>
              ) : (
                <div className="mt-2">
                  <p className="text-sm text-muted-foreground">No paid package yet. The free monthly allowance still applies.</p>
                  <Button asChild className="mt-3" size="sm"><Link href="/upgrade">View packages</Link></Button>
                </div>
              )}
              <p className="mt-3 text-xs text-muted-foreground">
                Saved lesson plans stay available after a package ends. Expiry only stops new generation from that package balance.
              </p>
            </SurfaceCard>

            {refData && (
              <SurfaceCard className="px-6 py-6" data-referral-section>
                <h2 className="text-lg font-semibold text-[#102A43]">Invite a teacher</h2>
                <p className="mt-1 text-sm text-slate-600">{refData.language}</p>
                <p className="mt-2 text-xs text-slate-500">
                  Referral bonuses are separate from purchased credits. Registration alone earns nothing;
                  the reward follows the first successful paid purchase.
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <code className="max-w-full break-all rounded bg-slate-100 px-2 py-1 text-xs">{referralLink}</code>
                  <Button size="sm" variant="outline" onClick={() => copy(referralLink, 'link')}>
                    {copied === 'link' ? 'Copied' : 'Copy link'}
                  </Button>
                  <a
                    href={whatsapp}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center rounded-md bg-[#25D366] px-3 py-1.5 text-sm font-semibold text-white hover:bg-[#1ebe5b]"
                  >
                    Share on WhatsApp
                  </a>
                </div>
                <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                  <div><dt className="text-xs uppercase text-slate-500">Invited</dt><dd className="font-semibold">{refData.invited}</dd></div>
                  <div><dt className="text-xs uppercase text-slate-500">Registered</dt><dd className="font-semibold">{refData.registered}</dd></div>
                  <div><dt className="text-xs uppercase text-slate-500">First purchases</dt><dd className="font-semibold">{refData.qualifying}</dd></div>
                  <div><dt className="text-xs uppercase text-slate-500">Credits earned</dt><dd className="font-semibold">{refData.credits_earned}</dd></div>
                </dl>
                <p className="mt-2 text-xs text-slate-500">
                  {refData.term_rewarded} of {refData.term_limit} rewarded referrals used this academic term.
                </p>
                {refData.history?.length > 0 && (
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="text-slate-500">
                        <tr><th className="py-1 pr-3">Teacher</th><th className="py-1 pr-3">Status</th><th className="py-1 pr-3">Credits</th><th className="py-1">Rewarded</th></tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {refData.history.map((h: any) => (
                          <tr key={h.id}>
                            <td className="py-1.5 pr-3">{h.referred}</td>
                            <td className="py-1.5 pr-3">{h.status}</td>
                            <td className="py-1.5 pr-3">{h.credits}</td>
                            <td className="py-1.5">{fmtDate(h.rewarded_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </SurfaceCard>
            )}

            <SurfaceCard className="px-6 py-6">
              <h2 className="text-lg font-semibold text-[#102A43]">Purchase history</h2>
              <ul className="mt-3 divide-y divide-slate-100 text-sm">
                {(data.payments || []).map((p: any) => (
                  <li key={p.reference} className="flex flex-wrap justify-between gap-2 py-2">
                    <span className="font-mono text-xs">{p.reference}</span>
                    <span>{statusLabel(p.status)} · GH₵{(p.amount_pesewas / 100).toFixed(2)}</span>
                    <span className="text-muted-foreground">{p.payment_method === 'mobile_money' ? 'Mobile Money' : p.payment_method === 'bank_transfer' ? 'Bank Transfer' : 'Card (historical)'}</span>
                    <span className="text-muted-foreground">{fmtDate(p.created_at)}</span>
                  </li>
                ))}
                {(data.payments || []).length === 0 && (
                  <li className="py-2 text-muted-foreground">No payments yet.</li>
                )}
              </ul>
            </SurfaceCard>

            {data.licence && (
              <SurfaceCard className="px-6 py-6" data-licence-status={data.licence.status}>
                <h2 className="text-lg font-semibold text-[#102A43]">Licence</h2>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <code className="rounded bg-slate-100 px-2 py-1 font-mono text-sm" data-my-licence-key>{data.licence.key}</code>
                  <Button size="sm" variant="outline" onClick={() => copy(data.licence.key, 'licence')}>
                    {copied === 'licence' ? 'Copied' : 'Copy'}
                  </Button>
                </div>
                <p className="mt-3 text-sm">
                  Status: {data.licence.status} · Valid until {fmtDate(data.licence.expires_at)}
                </p>
              </SurfaceCard>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
