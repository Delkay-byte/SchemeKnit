'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Field, TextArea } from '@/components/ui/field'
import { Banner } from '@/components/ui/banner'
import { StatusPill } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Phone, Building, CheckCircle, Clock, XCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { PageHeader } from '@/components/ui/page-header'
import { formatCurrency } from '@/lib/utils-display'

interface PaymentConfig {
  mtn_momo: { phone: string; account_name: string; enabled: boolean }
  bank_transfer: { bank: string; account_number: string; branch: string; account_name: string; enabled: boolean }
  currency: string
}

interface ProductPlan {
  id: string
  name: string
  description: string
  product_type: string
  price: number
  currency: string
  duration_days: number | null
  features: string[]
}

interface PaymentHistory {
  id: string
  payment_method: string
  amount: number
  currency: string
  product_type: string
  product_name: string
  reference: string
  payer_name: string
  status: string
  submitted_at: string
  reviewed_at: string | null
  rejection_reason: string
}

export default function PaymentsPage() {
  const [config, setConfig] = useState<PaymentConfig | null>(null)
  const [plans, setPlans] = useState<ProductPlan[]>([])
  const [history, setHistory] = useState<PaymentHistory[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [selectedPlan, setSelectedPlan] = useState<ProductPlan | null>(null)
  const [showSubmitForm, setShowSubmitForm] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [form, setForm] = useState({
    payment_method: 'mtn_momo',
    payer_name: '',
    payer_phone: '',
    reference: '',
    notes: '',
  })

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      setLoadError(null)
      const [configData, plansData, historyData] = await Promise.all([
        api.getPaymentConfig(),
        api.listProductPlans(),
        api.getPaymentHistory(),
      ])
      setConfig(configData)
      setPlans(plansData.plans || [])
      setHistory(historyData.payments || [])
    } catch (err) {
      console.error('Failed to load payment data:', err)
      setLoadError(
        err instanceof Error && err.message
          ? err.message
          : 'Could not load payment information. Check your connection and try again.',
      )
    } finally {
      setLoading(false)
    }
  }

  const handleSelectPlan = (plan: ProductPlan) => {
    setSelectedPlan(plan)
    setShowSubmitForm(true)
    setMessage(null)
  }

  const handleSubmitPayment = async () => {
    if (!selectedPlan) return
    if (!form.payer_name.trim()) {
      setMessage({ type: 'error', text: 'Please enter your name' })
      return
    }
    try {
      setSubmitting(true)
      await api.submitPayment({
        payment_method: form.payment_method,
        amount: selectedPlan.price,
        product_type: selectedPlan.product_type,
        product_id: selectedPlan.id,
        product_name: selectedPlan.name,
        reference: form.reference,
        payer_name: form.payer_name,
        payer_phone: form.payer_phone,
        notes: form.notes,
      })
      setMessage({ type: 'success', text: 'Payment submitted successfully. Your access will be activated after verification.' })
      setShowSubmitForm(false)
      setSelectedPlan(null)
      setForm({ payment_method: 'mtn_momo', payer_name: '', payer_phone: '', reference: '', notes: '' })
      loadData()
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Submission failed' })
    } finally {
      setSubmitting(false)
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'verified': return <CheckCircle className="h-4 w-4 text-green-600" aria-hidden="true" />
      case 'rejected': return <XCircle className="h-4 w-4 text-red-600" aria-hidden="true" />
      case 'pending': return <Clock className="h-4 w-4 text-yellow-600" aria-hidden="true" />
      default: return null
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="min-h-screen">
        <main className="container mx-auto px-4 py-8 max-w-4xl">
          <div className="mb-6">
            <PageHeader
              eyebrow="Billing"
              title="Payments & Subscriptions"
              description="Manage your SchemeKnit subscription"
            />
          </div>
          <Banner tone="danger" data-payments-error>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span>{loadError}</span>
              <Button variant="outline" size="sm" onClick={() => loadData()}>
                Try Again
              </Button>
            </div>
          </Banner>
        </main>
      </div>
    )
  }

  const sectionHeading = 'text-xl font-semibold text-[#102A43]'

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8 max-w-4xl">
        <div className="mb-6">
          <PageHeader
            eyebrow="Billing"
            title="Payments & Subscriptions"
            description="Manage your SchemeKnit subscription"
          />
        </div>

        {message && (
          <Banner tone={message.type === 'success' ? 'success' : 'danger'} className="mb-6">
            {message.text}
          </Banner>
        )}

        {/* Plans */}
        <section className="mb-8">
          <h3 className={`${sectionHeading} mb-1`}>Available Plans</h3>
          <p className="mb-4 text-sm text-muted-foreground">Choose a plan, submit payment, and get verified.</p>
          <div className="grid gap-4 md:grid-cols-3">
            {plans.map((plan) => (
              <SurfaceCard
                key={plan.id}
                data-plan-card
                accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
                className="flex flex-col px-5 py-5"
              >
                <h4 className="text-lg font-semibold text-[#102A43]">{plan.name}</h4>
                <p className="mt-1 text-sm text-muted-foreground">{plan.description}</p>
                <div className="mt-3 text-3xl font-bold text-[#04769B]">
                  {formatCurrency(plan.price)}
                </div>
                {plan.duration_days && (
                  <p className="mt-1 text-sm text-muted-foreground">
                    {plan.duration_days} days access
                  </p>
                )}
                <ul className="mt-3 mb-4 space-y-1 text-xs text-muted-foreground">
                  {plan.features.map((f, i) => (
                    <li key={i}>&#10003; {f.replace(/_/g, ' ')}</li>
                  ))}
                </ul>
                <Button onClick={() => handleSelectPlan(plan)} className="mt-auto w-full">
                  Purchase
                </Button>
              </SurfaceCard>
            ))}
          </div>
        </section>

        {/* Payment Methods */}
        {config && (
          <section className="mb-8">
            <h3 className={`${sectionHeading} mb-4`}>Payment Methods</h3>
            <div className="grid gap-4 md:grid-cols-2">
              {config.mtn_momo.enabled && (
                <SurfaceCard data-mtn-method className="px-5 py-5">
                  <h4 className="flex items-center text-lg font-semibold text-[#102A43]">
                    <Phone className="mr-2 h-5 w-5 text-[#04A9CE]" aria-hidden="true" />
                    MTN Mobile Money
                  </h4>
                  <div className="mt-3 space-y-2">
                    <p className="text-2xl font-bold text-[#102A43]">{config.mtn_momo.phone}</p>
                    <p className="text-muted-foreground">{config.mtn_momo.account_name}</p>
                    <p className="text-xs text-muted-foreground">
                      Send money to this number. Use your name as reference.
                    </p>
                  </div>
                </SurfaceCard>
              )}
              {config.bank_transfer.enabled && (
                <SurfaceCard data-bank-method className="px-5 py-5">
                  <h4 className="flex items-center text-lg font-semibold text-[#102A43]">
                    <Building className="mr-2 h-5 w-5 text-[#04A9CE]" aria-hidden="true" />
                    Bank Transfer
                  </h4>
                  <div className="mt-3 space-y-2">
                    <p className="font-semibold text-[#102A43]">{config.bank_transfer.bank}</p>
                    <p className="text-2xl font-bold text-[#102A43]">{config.bank_transfer.account_number}</p>
                    <p className="text-muted-foreground">Branch: {config.bank_transfer.branch}</p>
                    <p className="text-muted-foreground">Account Name: {config.bank_transfer.account_name}</p>
                    <p className="text-xs text-muted-foreground">
                      Use your name as payment reference.
                    </p>
                  </div>
                </SurfaceCard>
              )}
            </div>
          </section>
        )}

        {/* Submit Payment Form */}
        {showSubmitForm && selectedPlan && (
          <section className="mb-8">
            <SurfaceCard data-submit-payment accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]" className="px-5 py-5 sm:px-6">
              <h4 className="text-lg font-semibold text-[#102A43]">Submit Payment</h4>
              <p className="text-sm text-muted-foreground">
                You are paying {formatCurrency(selectedPlan.price)} for {selectedPlan.name}
              </p>
              <div className="mt-4 space-y-4">
                <Field label="Payment Method" htmlFor="payment-method">
                  <Select
                    id="payment-method"
                    value={form.payment_method}
                    onChange={(e) => setForm({ ...form, payment_method: e.target.value })}
                  >
                    <option value="mtn_momo">MTN Mobile Money</option>
                    <option value="bank_transfer">Bank Transfer</option>
                  </Select>
                </Field>
                <Field label="Your Name" htmlFor="payer-name" required>
                  <Input
                    id="payer-name"
                    type="text"
                    value={form.payer_name}
                    onChange={(e) => setForm({ ...form, payer_name: e.target.value })}
                    placeholder="Name as it appears on payment"
                    required
                  />
                </Field>
                <Field label="Phone Number" htmlFor="payer-phone">
                  <Input
                    id="payer-phone"
                    type="tel"
                    value={form.payer_phone}
                    onChange={(e) => setForm({ ...form, payer_phone: e.target.value })}
                    placeholder="Your phone number"
                  />
                </Field>
                <Field label="Transaction Reference" htmlFor="payment-reference">
                  <Input
                    id="payment-reference"
                    type="text"
                    value={form.reference}
                    onChange={(e) => setForm({ ...form, reference: e.target.value })}
                    placeholder="MoMo transaction ID or bank reference"
                  />
                </Field>
                <Field label="Notes" htmlFor="payment-notes">
                  <TextArea
                    id="payment-notes"
                    value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                    placeholder="Optional notes"
                    rows={2}
                  />
                </Field>
                <div className="flex gap-2">
                  <Button onClick={handleSubmitPayment} disabled={submitting}>
                    {submitting ? 'Submitting...' : 'Submit Payment'}
                  </Button>
                  <Button variant="outline" onClick={() => setShowSubmitForm(false)}>Cancel</Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Access will be activated only after admin verification. This may take up to 24 hours.
                </p>
              </div>
            </SurfaceCard>
          </section>
        )}

        {/* Payment History */}
        <section>
          <h3 className={`${sectionHeading} mb-4`}>Payment History</h3>
          {history.length === 0 ? (
            <SurfaceCard className="px-6 py-8 text-center text-muted-foreground">
              No payment history yet.
            </SurfaceCard>
          ) : (
            <SurfaceCard className="overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50 hover:bg-muted/50">
                    <TableHead>Payment</TableHead>
                    <TableHead>Submitted</TableHead>
                    <TableHead className="text-right">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {history.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell>
                        <p className="font-medium text-[#102A43]">{p.product_name || p.product_type}</p>
                        <p className="text-sm text-muted-foreground">
                          {p.payment_method === 'mtn_momo' ? 'MTN MoMo' : 'Bank Transfer'} &bull;
                          {' '}{formatCurrency(p.amount)}
                        </p>
                        {p.rejection_reason && (
                          <p className="mt-1 text-xs text-red-600">Reason: {p.rejection_reason}</p>
                        )}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {new Date(p.submitted_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell className="text-right">
                        <span className="inline-flex items-center gap-2">
                          {getStatusIcon(p.status)}
                          <StatusPill
                            tone={p.status === 'verified' ? 'success' : p.status === 'rejected' ? 'danger' : 'warning'}
                          >
                            {p.status.charAt(0).toUpperCase() + p.status.slice(1)}
                          </StatusPill>
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </SurfaceCard>
          )}
        </section>
      </main>
    </div>
  )
}
