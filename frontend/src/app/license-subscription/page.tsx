import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import { pageMetadata } from '@/lib/site-url'
import { BUSINESS_NAME, CONTACT_EMAIL, contactMailtoUrl } from '@/lib/contact'

export const metadata = pageMetadata({
  title: 'License & Subscription Terms',
  description: 'Individual teacher packages, credits and school licensing for SchemeKnit.',
  path: '/license-subscription',
})

export default function LicenseSubscriptionPage() {
  return (
    <LegalPageLayout
      title="License & Subscription Terms"
      subtitle="Individual teacher packages, credits and school licensing for SchemeKnit."
      lastUpdated="October 2026"
    >
      <LegalSection title="1. Individual teacher packages">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[38rem] border-collapse text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-2 pr-4 font-semibold">Package</th>
                <th className="py-2 pr-4 font-semibold">Price</th>
                <th className="py-2 pr-4 font-semibold">Lesson-plan credits</th>
                <th className="py-2 pr-4 font-semibold">Validity</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              <tr><td className="py-2 pr-4">Free</td><td className="py-2 pr-4">GH₵0</td><td className="py-2 pr-4">2 per calendar month</td><td className="py-2 pr-4">Monthly reset</td></tr>
              <tr><td className="py-2 pr-4">Flexible Credit Pack</td><td className="py-2 pr-4">GH₵12</td><td className="py-2 pr-4">20</td><td className="py-2 pr-4">Credits never expire</td></tr>
              <tr><td className="py-2 pr-4">Teacher Monthly</td><td className="py-2 pr-4">GH₵22</td><td className="py-2 pr-4">40</td><td className="py-2 pr-4">30 days</td></tr>
              <tr><td className="py-2 pr-4">Teacher Term Pass</td><td className="py-2 pr-4">GH₵50</td><td className="py-2 pr-4">160</td><td className="py-2 pr-4">120 days</td></tr>
              <tr><td className="py-2 pr-4">Academic Year Pass</td><td className="py-2 pr-4">GH₵120</td><td className="py-2 pr-4">480</td><td className="py-2 pr-4">365 days</td></tr>
            </tbody>
          </table>
        </div>
        <p>
          These are the approved individual teacher packages and prices. The
          server-side catalogue remains the source of truth; a package is never
          activated from a client-supplied price or credit amount.
        </p>
      </LegalSection>

      <LegalSection title="2. How credits work">
        <ul className="list-disc space-y-1 pl-6">
          <li>
            One credit produces one independently teachable indicator-level
            lesson plan.
          </li>
          <li>
            Multiple indicators in a scheme week can produce separate lesson
            plans, each using the relevant credit according to the actual
            credit implementation.
          </li>
          <li>
            A cached result, a failed provider call or a deterministic fallback
            does not consume a credit.
          </li>
          <li>
            Free credits reset according to the calendar-month policy. Unused
            free credits do not roll over.
          </li>
          <li>
            Flexible Credit Pack credits do not expire. Time-limited packages
            expire at the end of their stated validity from the confirmed
            activation time.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="3. Activation and payment">
        <p>
          All individual paid packages are one-time purchases. There is no
          automatic renewal and no recurring card charge. Payment is by Bank
          Transfer or Mobile Money through Paystack. A package activates only
          after Paystack confirms the payment and SchemeKnit verifies the
          reference, amount, currency and account. Failed, pending or expired
          payments do not activate credits.
        </p>
      </LegalSection>

      <LegalSection title="4. Balance and payment history">
        <p>
          A signed-in teacher can view their available credit balance and
          package state in the workspace, and can see payment history where
          the payment features are available. Saved generated lesson plans
          remain accessible according to the account status and our{' '}
          <a href="/data-retention" className="text-brand-cyan underline">
            Data Retention Policy
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection title="5. School licences">
        <p>
          School licences are separate from individual teacher prepaid
          packages. A school licence covers a configured number of teacher
          seats for its stated term or year. A school administrator manages
          teacher accounts within the licensed seat count. School licensing,
          activation, renewal and cancellation are governed by the applicable
          school licence terms and do not create an individual teacher credit
          balance.
        </p>
      </LegalSection>

      <LegalSection title="6. AI usage">
        <p>
          AI enrichment is optional and quota-limited. When enabled, the
          selected AI provider receives the specific lesson&apos;s indicator and
          context needed for that enrichment, not the entire scheme of work.
          AI content is advisory and must be reviewed by the teacher.
          Deterministic generation continues when AI is unavailable.
        </p>
      </LegalSection>

      <LegalSection title="7. Storage and exports">
        <p>
          Uploaded schemes and generated lessons are stored in access-controlled
          storage. Exports may be generated on demand in DOCX, PDF, XLSX or ZIP
          where supported. Download links are short-lived and single-use.
          Retention of stored files is described in the{' '}
          <a href="/data-retention" className="text-brand-cyan underline">
            Data Retention Policy
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection title="8. Suspension and termination">
        <p>
          We may suspend or terminate access for serious or repeated violations
          of the Terms of Service, fraud or security risk. Termination for cause
          does not automatically create a refund, but it does not remove
          statutory rights that cannot be excluded. Any other termination is
          handled under the applicable terms and refund policy.
        </p>
      </LegalSection>

      <LegalSection title="9. Related policies and contact">
        <p>
          Read the <a href="/terms" className="text-brand-cyan underline">Terms of Service</a>,{' '}
          <a href="/privacy-policy" className="text-brand-cyan underline">Privacy Policy</a>,{' '}
          <a href="/refunds-cancellation" className="text-brand-cyan underline">Refund &amp; Cancellation Policy</a>{' '}
          and <a href="/cookie-policy" className="text-brand-cyan underline">Cookie Policy</a>.
          Questions: {BUSINESS_NAME},{' '}
          <a href={contactMailtoUrl('SchemeKnit — Licensing Enquiry')} className="text-brand-cyan underline break-all">
            {CONTACT_EMAIL}
          </a>
          , or the <a href="/contact" className="text-brand-cyan underline">Contact page</a>.
        </p>
      </LegalSection>
    </LegalPageLayout>
  )
}
