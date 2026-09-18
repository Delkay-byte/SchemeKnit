import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'License & Subscription Terms',
  description: 'Plans, quotas, and licensing terms for SchemeKnit.',
}

export default function LicenseSubscriptionPage() {
  return (
    <LegalPageLayout
      title="License & Subscription Terms"
      subtitle="Plans, quotas, and licensing terms for SchemeKnit."
      lastUpdated="September 2026"
    >
      <LegalSection title="1. Individual Teacher Plans">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2 pr-4 font-semibold">Plan</th>
              <th className="py-2 pr-4 font-semibold">Generation quota</th>
              <th className="py-2 pr-4 font-semibold">AI</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            <tr>
              <td className="py-2 pr-4">Free Teacher</td>
              <td className="py-2 pr-4">Limited number of generated lesson plans</td>
              <td className="py-2 pr-4">Limited trial credits</td>
            </tr>
            <tr>
              <td className="py-2 pr-4">Teacher Pro</td>
              <td className="py-2 pr-4">Higher / unlimited lesson generation</td>
              <td className="py-2 pr-4">Included with quota</td>
            </tr>
          </tbody>
        </table>
        <p>
          Generation quota counts individual generated lesson plans, not
          schemes. A scheme containing 15 indicators across 5 weeks may
          produce many individual lessons — each counts toward the quota.
        </p>
      </LegalSection>

      <LegalSection title="2. School Licenses">
        <p>
          School licenses are activated per term or per year and cover a
          configured number of teacher seats. A school administrator manages
          teacher accounts within the licensed seat count. Teachers outside
          the seat limit cannot be added until seats are freed or the license
          is upgraded.
        </p>
      </LegalSection>

      <LegalSection title="3. What Each Lesson Includes">
        <p>
          Each generated lesson plan is a single teaching period focused on
          one curriculum indicator. It includes objectives, teaching and
          learner activities, assessment, and homework derived from that
          indicator. Multiple indicators in a scheme week produce multiple
          separate lesson plans.
        </p>
      </LegalSection>

      <LegalSection title="4. Payment Verification">
        <p>
          Payments are verified manually. Subscription or license activation
          occurs only after verification. We do not process card or
          mobile-money transactions automatically and do not store full
          payment credentials.
        </p>
      </LegalSection>

      <LegalSection title="5. AI Usage">
        <p>
          AI enrichment is optional and quota-limited. When enabled, AI
          receives the specific lesson's indicator and context — not the
          entire scheme. AI-generated content is advisory and must be
          reviewed by the teacher before classroom use. AI may be unavailable
          during provider outages; deterministic lesson generation continues
          to work without AI.
        </p>
      </LegalSection>

      <LegalSection title="6. Storage and Exports">
        <p>
          Uploaded schemes and generated lessons are stored in access-controlled
          storage. Export files (DOCX, PDF, XLSX, ZIP) are temporary and are
          removed after 30 days or on download. Storage limits may apply
          according to your plan.
        </p>
      </LegalSection>

      <LegalSection title="7. License Termination">
        <p>
          We may suspend or terminate access for violations of the Terms of
          Service. Upon termination for cause, no refund is provided. Upon
          termination for any other reason, the remaining paid period is
          refunded proportionally.
        </p>
      </LegalSection>

      <LegalSection title="8. Contact">
        <p>
          For licensing questions, please{' '}
          <a href="/contact" className="text-brand-cyan underline">contact us</a>.
        </p>
      </LegalSection>
    </LegalPageLayout>
  )
}
