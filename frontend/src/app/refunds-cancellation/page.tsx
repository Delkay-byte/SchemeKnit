import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Refund & Cancellation Policy',
  description: 'Refund and cancellation terms for SchemeKnit subscriptions.',
}

export default function RefundsCancellationPage() {
  return (
    <LegalPageLayout
      title="Refund & Cancellation Policy"
      subtitle="Refund and cancellation terms for SchemeKnit subscriptions."
      lastUpdated="September 2026"
    >
      <LegalSection title="1. No Automatic Renewal">
        <p>
          All TeachFlow packages are prepaid. Nothing renews automatically and
          there is no recurring card charge. A Monthly, Term or Academic Year
          package simply ends at its validity date; to continue generating you
          make a fresh purchase. Flexible Credit Pack credits do not expire.
        </p>
      </LegalSection>

      <LegalSection title="2. Refund Eligibility">
        <p>
          Because packages activate only after Paystack verification, the
          following refund rules apply:
        </p>
        <ul className="list-disc space-y-1 pl-6">
          <li>
            If a package was activated but the service was never usable due to
            a platform fault, you may request a full refund within 14 days of
            activation.
          </li>
          <li>
            If a payment was verified in error (duplicate verification, wrong
            package), the excess amount will be refunded or credited.
          </li>
          <li>
            A package that has ended is not refunded, but saved lesson plans
            remain accessible and exportable.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="3. How to Request a Refund">
        <p>
          To request a refund, please contact us through our{' '}
          <a href="/contact" className="text-brand-cyan underline">Contact page</a>{' '}
          with your account email and payment details. Refund requests are
          reviewed individually, and approved refunds are processed within
          14 business days.
        </p>
      </LegalSection>

      <LegalSection title="4. School Licenses">
        <p>
          School license cancellations follow the same rules. If a school
          deactivates SchemeKnit mid-term, teachers lose generation access
          at the end of the paid period. Generated lesson plans remain
          accessible for export.
        </p>
      </LegalSection>

      <LegalSection title="5. No Refund Circumstances">
        <ul className="list-disc space-y-1 pl-6">
          <li>
            Refunds are not issued for credits already consumed by successfully
            generated lesson plans.
          </li>
          <li>
            Refunds are not issued for content generated and exported before
            cancellation.
          </li>
          <li>
            Refunds are not issued for violations of the Terms of Service
            resulting in account suspension.
          </li>
        </ul>
      </LegalSection>
    </LegalPageLayout>
  )
}
