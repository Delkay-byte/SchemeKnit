import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import { pageMetadata } from '@/lib/site-url'
import { BUSINESS_NAME, CONTACT_EMAIL, contactMailtoUrl } from '@/lib/contact'

export const metadata = pageMetadata({
  title: 'Refund & Cancellation Policy',
  description: 'Refund and cancellation terms for SchemeKnit prepaid packages.',
  path: '/refunds-cancellation',
})

export default function RefundsCancellationPage() {
  return (
    <LegalPageLayout
      title="Refund & Cancellation Policy"
      subtitle="Refund and cancellation terms for SchemeKnit prepaid packages."
      lastUpdated="October 2026"
    >
      <LegalSection title="1. Prepaid packages and no automatic renewal">
        <p>
          All individual teacher packages are one-time prepaid purchases.
          Nothing renews automatically and there is no recurring card charge.
          A Monthly, Term or Academic Year package ends at its validity date;
          continuing requires a fresh purchase. Flexible Credit Pack credits
          do not expire.
        </p>
      </LegalSection>

      <LegalSection title="2. Payments that do not activate a package">
        <ul className="list-disc space-y-1 pl-6">
          <li>Failed payments do not activate a package or credits.</li>
          <li>Expired payments do not activate a package or credits.</li>
          <li>Pending payments do not activate a package until verified.</li>
          <li>
            If a payment is verified in error, or the same payment is verified
            twice, we will investigate and correct the entitlement.
          </li>
        </ul>
        <p>
          If money left your account but no package activated, contact us with
          the payment reference and account email so we can reconcile it.
        </p>
      </LegalSection>

      <LegalSection title="3. Refund requests">
        <p>
          You may request a refund by emailing{' '}
          <a href={contactMailtoUrl('SchemeKnit — Refund Request')} className="text-brand-cyan underline break-all">
            {CONTACT_EMAIL}
          </a>{' '}
          with your account email, payment reference, amount and the reason
          for the request.
        </p>
        <p>
          We review each request individually. Relevant factors include whether
          the package was activated, whether credits were used, whether a
          technical fault prevented use, and any statutory rights that apply.
          We may ask for information needed to verify the payment and the
          account.
        </p>
      </LegalSection>

      <LegalSection title="4. Unused, used and expired credits">
        <ul className="list-disc space-y-1 pl-6">
          <li>
            <strong>Unused credits:</strong> may be considered for a refund
            where the package was recently purchased and no technical or
            statutory bar applies.
          </li>
          <li>
            <strong>Credits already consumed:</strong> lesson plans already
            generated are delivered digital content. Amounts attributable to
            consumed credits are not normally refunded.
          </li>
          <li>
            <strong>Expired package credits:</strong> time-limited credits that
            expired unused are not automatically refunded merely because the
            validity period ended.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="5. Technical faults">
        <p>
          If a technical fault in SchemeKnit prevents you from using a
          purchased package, contact us with what happened and when. Where we
          confirm a platform fault, we may restore credits, extend validity,
          correct the entitlement or refund the affected amount. This does not
          limit any statutory right you may have.
        </p>
      </LegalSection>

      <LegalSection title="6. School licences">
        <p>
          School licence refunds and cancellations are reviewed under the
          applicable licence terms and the school agreement. If a school
          cancels mid-term, generation access normally ends at the end of the
          paid period and generated lesson plans remain available for export
          according to the retention policy. Any refund is assessed
          individually and is subject to the same statutory framework.
        </p>
      </LegalSection>

      <LegalSection title="7. Ghana's Electronic Transactions Act, 2008 (Act 772)">
        <p>
          Section 49 of the Electronic Transactions Act, 2008 (Act 772)
          provides a seven-day grace period for certain service transactions,
          subject to statutory exceptions. The Act also contains exceptions
          relevant to services that begin with the consumer&apos;s consent
          before the grace period expires.
        </p>
        <p>
          We do not treat every SchemeKnit digital purchase as automatically
          within an exception, and we do not treat every purchase as
          automatically refundable regardless of the law. How the Act applies
          to prepaid lesson-plan generation, immediate digital access and
          credits already used requires a case-specific assessment.
        </p>
        <p>
          Nothing in this policy excludes or limits a statutory right that
          cannot lawfully be excluded. If you believe a statutory right applies,
          tell us in your request so it can be considered.
        </p>
      </LegalSection>

      <LegalSection title="8. Checkout consent — legal review outstanding">
        <p>
          SchemeKnit does not currently present a separate immediate-start
          consent or waiver at checkout. Whether one is legally required for
          this service, what wording it should use, and what record should be
          kept are flagged for review by a Ghanaian legal practitioner before
          any such mechanism is introduced. General acceptance of the Terms of
          Service is not treated here as a waiver of a statutory cancellation
          right.
        </p>
      </LegalSection>

      <LegalSection title="9. Statutory rights and contact">
        <p>
          This policy is subject to mandatory applicable law, including
          consumer protections under Ghanaian law. Questions or requests:
          {' '}{BUSINESS_NAME},{' '}
          <a href={contactMailtoUrl('SchemeKnit — Refund Request')} className="text-brand-cyan underline break-all">
            {CONTACT_EMAIL}
          </a>
          , or use our{' '}
          <a href="/contact" className="text-brand-cyan underline">Contact page</a>.
        </p>
        <p className="text-sm text-muted-foreground">
          This policy describes the current commercial approach. It is not a
          substitute for advice from a Ghanaian legal practitioner.
        </p>
      </LegalSection>
    </LegalPageLayout>
  )
}
