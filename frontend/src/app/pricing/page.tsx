'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { PublicPage } from '@/components/public-page'
import { api } from '@/lib/api'
import type { CataloguePlan } from '@/types'
import { authHref, upgradePath } from '@/lib/purchase-return'

const FALLBACK: CataloguePlan[] = [
  {
    slug: 'free', name: 'Free', description: 'Two lesson-plan generations every calendar month.',
    price_pesewas: 0, price_ghs: 0, currency: 'GHS', duration_days: 0, credits: 2,
    credit_validity_days: null, package_kind: 'free', validity_label: '2 per calendar month',
    payment_terms: 'Free. No payment information required.', features: [], active: false, free: true,
  },
  {
    slug: 'flexible-credit-pack', name: 'Flexible Credit Pack',
    description: 'Twenty lesson-plan credits that stay available until used.',
    price_pesewas: 1200, price_ghs: 12, currency: 'GHS', duration_days: 0, credits: 20,
    credit_validity_days: null, package_kind: 'flexible', validity_label: 'Credits do not expire',
    payment_terms: 'One-time prepaid payment. No automatic renewal.',
    features: [], active: true,
  },
  {
    slug: 'teacher-monthly', name: 'Teacher Monthly',
    description: 'Forty lesson-plan credits for thirty days.',
    price_pesewas: 2200, price_ghs: 22, currency: 'GHS', duration_days: 30, credits: 40,
    credit_validity_days: 30, package_kind: 'timed', validity_label: '30 days',
    payment_terms: 'One-time prepaid payment. No automatic renewal.',
    features: [], active: true,
  },
  {
    slug: 'teacher-term-pass', name: 'Teacher Term Pass',
    description: 'One hundred and sixty lesson-plan credits for a school term.',
    price_pesewas: 5000, price_ghs: 50, currency: 'GHS', duration_days: 120, credits: 160,
    credit_validity_days: 120, package_kind: 'timed', validity_label: '120 days',
    payment_terms: 'One-time prepaid payment. No automatic renewal.',
    features: [], active: true,
  },
  {
    slug: 'academic-year-pass', name: 'Academic Year Pass',
    description: 'Four hundred and eighty lesson-plan credits for a full academic year.',
    price_pesewas: 12000, price_ghs: 120, currency: 'GHS', duration_days: 365, credits: 480,
    credit_validity_days: 365, package_kind: 'timed', validity_label: '365 days',
    payment_terms: 'One-time prepaid payment. No automatic renewal.',
    features: [], active: true,
  },
]

function price(plan: CataloguePlan) {
  return plan.price_pesewas === 0 ? 'GH₵0' : `GH₵${(plan.price_pesewas / 100).toFixed(2)}`
}

export default function PricingPage() {
  const [plans, setPlans] = useState<CataloguePlan[]>(FALLBACK)
  const [selectedPlan, setSelectedPlan] = useState<CataloguePlan | null>(null)
  const selectedNext = selectedPlan ? upgradePath(selectedPlan.slug) : null

  useEffect(() => {
    api.getCatalogue()
      .then((data) => {
        if (Array.isArray(data?.plans) && data.plans.length) setPlans(data.plans)
      })
      .catch(() => { /* fallback keeps the approved values visible */ })
  }, [])

  return (
    <PublicPage
      eyebrow="Pricing"
      title="Simple packages, measured in lesson plans"
      description="Every credit generates one independently teachable, indicator-level lesson plan. One indicator produces one plan; three indicators in a week can produce three separate plans."
    >
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        {plans.map((plan) => (
          <article
            key={plan.slug}
            className={`flex flex-col rounded-2xl border bg-white p-6 shadow-sm ${
              plan.slug === 'teacher-term-pass'
                ? 'border-[#04A9CE] ring-2 ring-[#04A9CE]/20'
                : 'border-slate-200'
            }`}
            data-package={plan.slug}
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-lg font-semibold text-[#102A43]">{plan.name}</h2>
              {plan.slug === 'teacher-term-pass' && (
                <span className="rounded-full bg-[#04A9CE]/10 px-2.5 py-1 text-xs font-semibold text-[#04769B]">
                  Popular
                </span>
              )}
            </div>
            <p className="mt-2 text-3xl font-bold text-[#102A43]">{price(plan)}</p>
            <p className="mt-1 text-sm text-slate-600">
              {plan.credits} lesson-plan credit{plan.credits === 1 ? '' : 's'}
            </p>
            <p className="text-sm text-slate-600">{plan.validity_label}</p>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">{plan.description}</p>
            <ul className="mt-4 flex-1 space-y-2 text-sm text-slate-600">
              {(plan.features || []).map((f) => (
                <li key={f} className="flex gap-2">
                  <span aria-hidden="true" className="text-[#04A9CE]">✓</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-xs text-slate-500">{plan.payment_terms}</p>
            {plan.free ? (
              <Button asChild className="mt-4 w-full">
                <Link href="/signup">Start Free</Link>
              </Button>
            ) : (
              <Button
                type="button"
                className="mt-4 w-full"
                onClick={() => setSelectedPlan(plan)}
                data-choose-package={plan.slug}
              >
                Choose this package
              </Button>
            )}
          </article>
        ))}
      </div>

      <section className="mt-12 grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="font-semibold text-[#102A43]">Monthly free credits</h3>
          <p className="mt-2 text-sm text-slate-600">
            Two credits every calendar month (Africa/Accra). Unused free credits
            do not roll over.
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="font-semibold text-[#102A43]">Flexible purchased credits</h3>
          <p className="mt-2 text-sm text-slate-600">
            The Flexible Credit Pack never expires. Those credits stay available
            even after a monthly, term or academic-year package ends.
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="font-semibold text-[#102A43]">Time-limited package credits</h3>
          <p className="mt-2 text-sm text-slate-600">
            Monthly, Term and Academic Year credits run from the confirmed
            activation time for 30, 120 or 365 days.
          </p>
        </div>
      </section>

      <p className="mt-8 rounded-xl bg-white p-5 text-sm text-slate-600 shadow-sm">
        Pay by <strong>Bank Transfer</strong> or <strong>Mobile Money</strong> (MTN,
        Telecel, AirtelTigo). Both are one-time prepaid payments: there is no
        automatic renewal. A package is activated only after SchemeKnit verifies
        the payment with Paystack.
      </p>

      <Dialog
        open={selectedPlan !== null}
        onOpenChange={(open) => { if (!open) setSelectedPlan(null) }}
      >
        <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto p-5 sm:p-6">
          <DialogHeader className="pr-8">
            <DialogTitle className="text-xl leading-snug sm:text-2xl">
              Almost there! Your package is waiting.
            </DialogTitle>
            <DialogDescription className="text-sm leading-relaxed">
              To purchase this package, you need a SchemeKnit teacher account.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 text-sm leading-relaxed text-slate-600">
            <p>
              Already have an account? Sign in to continue.
            </p>
            <p>
              New to SchemeKnit? Create your free teacher account first. Once
              you have signed in or completed registration, we will take you
              directly to checkout for the package you selected.
            </p>
            <p className="font-medium text-[#102A43]">
              Creating an account is free and does not charge you.
            </p>
          </div>

          {selectedPlan && (
            <div
              className="rounded-xl border border-[#04A9CE]/30 bg-[#04A9CE]/5 p-4"
              data-selected-package={selectedPlan.slug}
            >
              <p className="text-xs font-semibold uppercase tracking-wide text-[#04769B]">
                Selected package
              </p>
              <p className="mt-1 text-lg font-bold text-[#102A43]">
                {selectedPlan.name}
              </p>
              <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
                <div>
                  <dt className="text-xs uppercase text-slate-500">Price</dt>
                  <dd className="font-semibold text-[#102A43]">
                    {price(selectedPlan)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-slate-500">Credits</dt>
                  <dd className="font-semibold text-[#102A43]">
                    {selectedPlan.credits} lesson-plan credit
                    {selectedPlan.credits === 1 ? '' : 's'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-slate-500">Validity</dt>
                  <dd className="font-semibold text-[#102A43]">
                    {selectedPlan.validity_label}
                  </dd>
                </div>
              </dl>
            </div>
          )}

          <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900">
            New teacher registrations currently require a valid SchemeKnit
            pilot invitation code. Please use the code supplied with your
            invitation when creating your account.
          </p>

          <DialogFooter className="flex-col gap-2 sm:flex-row-reverse">
            {selectedNext && (
              <>
                <Button asChild className="w-full">
                  <Link href={authHref('/signup', selectedNext)}>
                    Create a free teacher account
                  </Link>
                </Button>
                <Button asChild variant="outline" className="w-full">
                  <Link href={authHref('/login', selectedNext)}>
                    I already have an account — Sign in
                  </Link>
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PublicPage>
  )
}
