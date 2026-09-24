'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Field, TextArea } from '@/components/ui/field'
import { Banner } from '@/components/ui/banner'
import { StatusPill } from '@/components/ui/badge'
import { CreditCard, Phone, Building, CheckCircle, Clock, XCircle } from 'lucide-react'
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
      case 'verified': return <CheckCircle className="h-4 w-4 text-green-600" />
      case 'rejected': return <XCircle className="h-4 w-4 text-red-600" />
      case 'pending': return <Clock className="h-4 w-4 text-yellow-600" />
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

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8 max-w-4xl">
        <div className="mb-6">
          <PageHeader
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
          <h3 className="text-xl font-semibold mb-4">Available Plans</h3>
          <div className="grid md:grid-cols-3 gap-4">
            {plans.map((plan) => (
              <Card key={plan.id} className="hover:shadow-lg transition-shadow">
                <CardHeader>
                  <CardTitle className="text-lg">{plan.name}</CardTitle>
                  <CardDescription>{plan.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold text-primary mb-2">
                    {formatCurrency(plan.price)}
                  </div>
                  {plan.duration_days && (
                    <p className="text-sm text-muted-foreground mb-4">
                      {plan.duration_days} days access
                    </p>
                  )}
                  <ul className="text-xs text-muted-foreground space-y-1 mb-4">
                    {plan.features.map((f, i) => (
                      <li key={i}>&#10003; {f.replace(/_/g, ' ')}</li>
                    ))}
                  </ul>
                  <Button onClick={() => handleSelectPlan(plan)} className="w-full">
                    Purchase
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* Payment Methods */}
        {config && (
          <section className="mb-8">
            <h3 className="text-xl font-semibold mb-4">Payment Methods</h3>
            <div className="grid md:grid-cols-2 gap-4">
              {config.mtn_momo.enabled && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center text-lg">
                      <Phone className="h-5 w-5 mr-2" />
                      MTN Mobile Money
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <p className="text-2xl font-bold">{config.mtn_momo.phone}</p>
                    <p className="text-muted-foreground">{config.mtn_momo.account_name}</p>
                    <p className="text-xs text-muted-foreground">
                      Send money to this number. Use your name as reference.
                    </p>
                  </CardContent>
                </Card>
              )}
              {config.bank_transfer.enabled && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center text-lg">
                      <Building className="h-5 w-5 mr-2" />
                      Bank Transfer
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <p className="font-semibold">{config.bank_transfer.bank}</p>
                    <p className="text-2xl font-bold">{config.bank_transfer.account_number}</p>
                    <p className="text-muted-foreground">Branch: {config.bank_transfer.branch}</p>
                    <p className="text-muted-foreground">Account Name: {config.bank_transfer.account_name}</p>
                    <p className="text-xs text-muted-foreground">
                      Use your name as payment reference.
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>
          </section>
        )}

        {/* Submit Payment Form */}
        {showSubmitForm && selectedPlan && (
          <section className="mb-8">
            <Card>
              <CardHeader>
                <CardTitle>Submit Payment</CardTitle>
                <CardDescription>
                  You are paying {formatCurrency(selectedPlan.price)} for {selectedPlan.name}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
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
                <Field label={<>Your Name *</>} htmlFor="payer-name">
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
              </CardContent>
            </Card>
          </section>
        )}

        {/* Payment History */}
        <section>
          <h3 className="text-xl font-semibold mb-4">Payment History</h3>
          {history.length === 0 ? (
            <Card>
              <CardContent className="p-8 text-center text-muted-foreground">
                No payment history yet.
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {history.map((p) => (
                <Card key={p.id}>
                  <CardContent className="p-4 flex items-center justify-between">
                    <div>
                      <p className="font-medium">{p.product_name || p.product_type}</p>
                      <p className="text-sm text-muted-foreground">
                        {p.payment_method === 'mtn_momo' ? 'MTN MoMo' : 'Bank Transfer'} &bull;
                        {formatCurrency(p.amount)} &bull;
                        {new Date(p.submitted_at).toLocaleDateString()}
                      </p>
                      {p.rejection_reason && (
                        <p className="text-xs text-red-600 mt-1">Reason: {p.rejection_reason}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {getStatusIcon(p.status)}
                      <StatusPill
                        tone={p.status === 'verified' ? 'success' : p.status === 'rejected' ? 'danger' : 'warning'}
                      >
                        {p.status.charAt(0).toUpperCase() + p.status.slice(1)}
                      </StatusPill>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
